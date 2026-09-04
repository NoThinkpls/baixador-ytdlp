"""Verificação e instalação segura de atualizações do aplicativo.

A consulta é feita apenas no GitHub Releases público. O instalador só é
baixado após ação explícita do usuário e é validado contra o SHA-256 publicado
na mesma release antes de ser executado.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .config import APP_ID, APP_VERSION, IS_WINDOWS, UPDATE_DIR

RELEASE_API = "https://api.github.com/repos/NoThinkpls/baixador-ytdlp/releases/latest"
USER_AGENT = f"{APP_ID}/{APP_VERSION} update-check"
_VERSION_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:[-+].*)?$")
_SHA256_RE = re.compile(r"^([A-Fa-f0-9]{64})\s+\*?(.+?)\s*$")


class UpdateError(RuntimeError):
    """Erro seguro para apresentar na interface sem expor detalhes de rede."""


@dataclass(frozen=True)
class ReleaseInfo:
    """Release compatível com o instalador do sistema atual."""

    version: str
    tag: str
    page_url: str
    installer_name: str
    installer_url: str
    sha256: str


def version_key(value: str) -> tuple[int, int, int] | None:
    """Converte a parte estável de uma tag SemVer em tupla comparável."""
    match = _VERSION_RE.match((value or "").strip())
    if not match:
        return None
    return tuple(int(part) for part in match.groups())


class AppUpdater:
    """Consulta releases e baixa instaladores sem depender da thread da interface."""

    def find_update(self, current_version: str = APP_VERSION) -> ReleaseInfo | None:
        """Devolve uma release mais nova para esta plataforma, se existir."""
        # A atualização in-place é implementada para o instalador Inno Setup.
        # No macOS a build será distribuída como .app assinada/notarizada, com
        # mecanismo próprio de substituição no pacote.
        if not IS_WINDOWS:
            return None

        current = version_key(current_version)
        if current is None:
            raise UpdateError("A versão instalada não pode ser comparada com segurança.")

        payload = self._request_json(RELEASE_API)
        if payload.get("draft") or payload.get("prerelease"):
            return None

        tag = str(payload.get("tag_name") or "")
        released = version_key(tag)
        if released is None:
            raise UpdateError("A release publicada possui uma versão inválida.")
        if released <= current:
            return None

        assets = payload.get("assets")
        if not isinstance(assets, list):
            raise UpdateError("A release publicada não possui arquivos para atualização.")

        release_version = tag.lstrip("v")
        expected_name = f"BaixadorYtdlp-{release_version}-setup.exe"
        installer = next(
            (asset for asset in assets if asset.get("name") == expected_name),
            None,
        )
        checksums = next(
            (asset for asset in assets if asset.get("name") == "SHA256SUMS.txt"),
            None,
        )
        if not installer or not checksums:
            raise UpdateError(
                "A release não contém o instalador versionado e o arquivo SHA256SUMS.txt."
            )

        installer_url = str(installer.get("browser_download_url") or "")
        checksum_url = str(checksums.get("browser_download_url") or "")
        page_url = str(payload.get("html_url") or "")
        if not installer_url or not checksum_url or not page_url:
            raise UpdateError("A release não possui links de download válidos.")

        sha256 = self._checksum_for(expected_name, self._request_text(checksum_url))
        if sha256 is None:
            raise UpdateError("O hash do instalador não foi publicado na release.")

        return ReleaseInfo(
            version=release_version,
            tag=tag,
            page_url=page_url,
            installer_name=expected_name,
            installer_url=installer_url,
            sha256=sha256.lower(),
        )

    def download(
        self,
        release: ReleaseInfo,
        progress: Callable[[int, int], None] | None = None,
    ) -> Path:
        """Baixa a atualização e confere o hash antes de devolver o instalador."""
        if not IS_WINDOWS:
            raise UpdateError("A instalação automática ainda não está disponível nesta plataforma.")

        UPDATE_DIR.mkdir(parents=True, exist_ok=True)
        target = UPDATE_DIR / release.installer_name
        partial = UPDATE_DIR / f".{release.installer_name}.part"

        try:
            request = Request(release.installer_url, headers={"User-Agent": USER_AGENT})
            with urlopen(request, timeout=45) as response, partial.open("wb") as output:
                header = response.headers.get("Content-Length", "0")
                total = int(header) if header.isdigit() else 0
                received = 0
                while True:
                    block = response.read(1024 * 512)
                    if not block:
                        break
                    output.write(block)
                    received += len(block)
                    if progress:
                        progress(received, total)
        except (HTTPError, URLError, OSError, TimeoutError) as exc:
            partial.unlink(missing_ok=True)
            raise UpdateError("Não foi possível baixar a atualização. Tente novamente.") from exc

        actual = self._file_sha256(partial)
        if actual.lower() != release.sha256.lower():
            partial.unlink(missing_ok=True)
            raise UpdateError(
                "A verificação de segurança falhou: o arquivo baixado não corresponde "
                "ao SHA-256 publicado."
            )

        os.replace(partial, target)
        if progress:
            progress(1, 1)
        return target

    @staticmethod
    def launch_installer(installer: Path) -> None:
        """Abre o instalador validado sem shell e deixa a atualização visível ao usuário."""
        if not IS_WINDOWS:
            raise UpdateError("A instalação automática ainda não está disponível nesta plataforma.")
        if not installer.is_file():
            raise UpdateError("O instalador validado não foi encontrado.")

        kwargs: dict[str, object] = {}
        if sys.platform.startswith("win"):
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            # Não usa /SILENT: a pessoa vê e controla a atualização do próprio app.
            subprocess.Popen([str(installer), "/CLOSEAPPLICATIONS"], **kwargs)
        except OSError as exc:
            raise UpdateError("Não foi possível abrir o instalador da atualização.") from exc

    @staticmethod
    def _file_sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    @staticmethod
    def _checksum_for(filename: str, content: str) -> str | None:
        for line in content.splitlines():
            match = _SHA256_RE.match(line)
            if match and match.group(2).strip() == filename:
                return match.group(1)
        return None

    @staticmethod
    def _request_json(url: str) -> dict:
        try:
            content = AppUpdater._request_text(url)
            payload = json.loads(content)
        except json.JSONDecodeError as exc:
            raise UpdateError("A resposta da atualização não é válida.") from exc
        if not isinstance(payload, dict):
            raise UpdateError("A resposta da atualização não é válida.")
        return payload

    @staticmethod
    def _request_text(url: str) -> str:
        try:
            request = Request(url, headers={"User-Agent": USER_AGENT})
            with urlopen(request, timeout=20) as response:
                return response.read().decode("utf-8")
        except (HTTPError, URLError, UnicodeDecodeError, TimeoutError) as exc:
            raise UpdateError("Não foi possível consultar novas versões agora.") from exc
