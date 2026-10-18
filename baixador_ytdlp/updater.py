"""Verificação e instalação segura de atualizações do aplicativo.

A consulta é feita apenas no GitHub Releases público. O instalador só é
baixado após ação explícita do usuário e é validado contra o SHA-256 publicado
na mesma release antes de ser executado.

No Windows o instalador Inno Setup faz a troca. No macOS o pacote é o ``.zip``
com o ``.app``: ele é extraído, conferido com ``codesign`` e um script curto
troca o ``.app`` em uso depois que o aplicativo fecha, e o reabre.
"""
from __future__ import annotations

import hashlib
import http.client
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from typing import Any

from .config import APP_ID, APP_VERSION, IS_WINDOWS, UPDATE_DIR
from .plataforma import execucao_empacotada, is_macos
from .tools import CREATE_NO_WINDOW, _verified_ssl_context, require_https

IS_MACOS = is_macos()

RELEASE_API = "https://api.github.com/repos/NoThinkpls/baixador-ytdlp/releases/latest"
USER_AGENT = f"{APP_ID}/{APP_VERSION} update-check"
_VERSION_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:[-+].*)?$")
_SHA256_RE = re.compile(r"^([A-Fa-f0-9]{64})\s+\*?(.+?)\s*$")

# Chaves públicas Ed25519 (base64, 32 bytes) aceitas para o SHA256SUMS.txt.
# Gere o par com ``python scripts/release_signing.py generate``: a privada vai
# para o segredo RELEASE_SIGNING_KEY do GitHub (ambiente protegido), a pública
# entra aqui. Mais de uma chave permite rotação sem quebrar atualizações.
#
# Enquanto a tupla estiver vazia, a assinatura é conferida quando existir, mas
# não é exigida — para que as versões atuais continuem atualizando até a
# primeira release assinada. Com uma chave aqui, release sem .sig é RECUSADA.
RELEASE_PUBLIC_KEYS: tuple[str, ...] = ()
SIGNATURE_ASSET = "SHA256SUMS.txt.sig"
# Releases até a 1.13.7 só tinham os hashes do Mac neste arquivo, sem assinatura.
MACOS_CHECKSUM_ASSET = "SHA256SUMS-macos.txt"
MACOS_STAGING = "macos-nova-versao"

# Roda depois que o app fecha: um .app aberto não deve ser trocado por baixo do
# processo. Se a troca falhar, a versão anterior volta para o lugar. Os caminhos
# chegam como argumentos ($1…$4), nunca interpolados no texto do script.
_MAC_SWAP_SCRIPT = r"""
pid="$1"; alvo="$2"; novo="$3"; log="$4"
exec >>"$log" 2>&1
echo "$(date '+%F %T') aguardando o processo $pid fechar"
tentativas=0
while kill -0 "$pid" 2>/dev/null; do
  tentativas=$((tentativas + 1))
  if [ "$tentativas" -gt 600 ]; then
    echo "o aplicativo não fechou em 2 minutos; atualização abortada"
    exit 1
  fi
  sleep 0.2
done
reserva="${alvo%.app}.anterior-$$.app"
if ! mv "$alvo" "$reserva"; then
  echo "não foi possível mover a versão atual; nada foi alterado"
  open "$alvo"
  exit 1
fi
if mv "$novo" "$alvo"; then
  rm -rf "$reserva"
  echo "$(date '+%F %T') atualizado: $alvo"
else
  echo "a troca falhou; restaurando a versão anterior"
  rm -rf "$alvo"
  mv "$reserva" "$alvo"
fi
open "$alvo"
"""


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
    size: int = 0          # bytes do instalador, informado pelo GitHub
    notes: str = ""        # corpo da release (Markdown)


def _as_size(value) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def version_key(value: str) -> tuple[int, int, int] | None:
    """Converte a parte estável de uma tag SemVer em tupla comparável."""
    match = _VERSION_RE.match((value or "").strip())
    if not match:
        return None
    major, minor, patch = (int(part) for part in match.groups())
    return major, minor, patch


class AppUpdater:
    """Consulta releases e baixa instaladores sem depender da thread da interface."""

    def find_update(self, current_version: str = APP_VERSION) -> ReleaseInfo | None:
        """Devolve uma release mais nova para esta plataforma, se existir."""
        # Antes o macOS saía aqui sempre com None, e a interface dizia "já está
        # atualizado" mesmo com versão nova publicada. Linux segue sem
        # atualização pelo app (o .deb fica com o gerenciador de pacotes).
        if not (IS_WINDOWS or IS_MACOS):
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
        # A cópia versionada é a preferida. O alias estável mantém a checagem
        # compatível com releases antigas e com a página de download do README.
        installer_names = self._installer_names(release_version)
        installer = next(
            (asset for name in installer_names
             for asset in assets if str(asset.get("name") or "") == name),
            None,
        )
        checksums = next(
            (asset for asset in assets if asset.get("name") == "SHA256SUMS.txt"),
            None,
        )
        if not assets:
            raise UpdateError(
                f"A versão {tag} foi encontrada, mas os arquivos ainda estão sendo publicados. "
                "Aguarde alguns minutos e tente novamente."
            )
        if not installer or not checksums:
            raise UpdateError(
                "A release ainda não possui o instalador e o SHA256SUMS.txt. "
                "Aguarde a publicação terminar e tente novamente."
            )

        installer_url = str(installer.get("browser_download_url") or "")
        checksum_url = str(checksums.get("browser_download_url") or "")
        page_url = str(payload.get("html_url") or "")
        if not installer_url or not checksum_url or not page_url:
            raise UpdateError("A release não possui links de download válidos.")

        installer_name = str(installer.get("name") or "")
        checksum_text = self._request_text(checksum_url)
        self._verify_checksum_signature(assets, checksum_text)
        sha256 = self._checksum_for(installer_name, checksum_text)
        if sha256 is None and not IS_WINDOWS and not RELEASE_PUBLIC_KEYS:
            # Releases antigas: o hash do Mac só existe no arquivo da plataforma.
            # Com chave publicada, só vale o que está no SHA256SUMS.txt assinado.
            macos_sums = next(
                (asset for asset in assets if asset.get("name") == MACOS_CHECKSUM_ASSET), None)
            macos_url = str((macos_sums or {}).get("browser_download_url") or "")
            if macos_url:
                sha256 = self._checksum_for(installer_name, self._request_text(macos_url))
        if sha256 is None:
            raise UpdateError("O hash do instalador não foi publicado na release.")

        return ReleaseInfo(
            version=release_version,
            tag=tag,
            page_url=page_url,
            installer_name=installer_name,
            installer_url=installer_url,
            sha256=sha256.lower(),
            size=_as_size(installer.get("size")),
            notes=str(payload.get("body") or "").strip()[:20000],
        )

    @staticmethod
    def _installer_names(version: str) -> tuple[str, ...]:
        if IS_WINDOWS:
            return (f"BaixadorYtdlp-{version}-setup.exe", "baixador-ytdlp-setup.exe")
        return (f"BaixadorYtdlp-{version}-macos-arm64.zip", "baixador-ytdlp-macos-arm64.zip")

    def _verify_checksum_signature(self, assets: list, checksum_text: str,
                                   keys: tuple[str, ...] | None = None) -> None:
        """Autenticidade: o SHA256SUMS precisa ter sido assinado pela chave do projeto."""
        from .signing import verify_detached

        keys = RELEASE_PUBLIC_KEYS if keys is None else keys
        signature_asset = next(
            (asset for asset in assets if asset.get("name") == SIGNATURE_ASSET), None)
        if not keys:
            return  # período de transição: ainda não há chave publicada no app
        if not signature_asset:
            raise UpdateError(
                "A release não traz a assinatura do SHA256SUMS.txt. Por segurança, a "
                "atualização automática foi bloqueada; baixe manualmente pela página da release."
            )
        signature_url = str(signature_asset.get("browser_download_url") or "")
        signature = self._request_text(signature_url)
        if not verify_detached(keys, checksum_text.encode("utf-8"), signature):
            raise UpdateError(
                "A assinatura do SHA256SUMS.txt não confere com a chave do projeto. "
                "A atualização foi bloqueada."
            )

    def download(
        self,
        release: ReleaseInfo,
        progress: Callable[[int, int], None] | None = None,
    ) -> Path:
        """Baixa a atualização e confere o hash antes de devolver o instalador."""
        if not (IS_WINDOWS or IS_MACOS):
            raise UpdateError("A instalação automática ainda não está disponível nesta plataforma.")
        if not IS_WINDOWS:
            mac_app_bundle()  # avisa antes de baixar centenas de MB que não poderão ser instalados

        UPDATE_DIR.mkdir(parents=True, exist_ok=True)
        target = UPDATE_DIR / release.installer_name
        partial = UPDATE_DIR / f".{release.installer_name}.part"

        try:
            request = Request(require_https(release.installer_url),
                              headers={"User-Agent": USER_AGENT})
            with urlopen(request, timeout=45, context=_verified_ssl_context()) as response, \
                    partial.open("wb") as output:
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
        except (HTTPError, URLError, OSError, TimeoutError, ValueError,
                http.client.HTTPException) as exc:
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
        if not (IS_WINDOWS or IS_MACOS):
            raise UpdateError("A instalação automática ainda não está disponível nesta plataforma.")
        if not installer.is_file():
            raise UpdateError("O instalador validado não foi encontrado.")
        if not IS_WINDOWS:
            AppUpdater._launch_macos_swap(installer)
            return

        kwargs: dict[str, Any] = {}
        if sys.platform.startswith("win"):
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            # /SILENT pula as páginas do assistente (a pessoa já confirmou no app),
            # mas mantém a janela de progresso visível. Não é /VERYSILENT: a
            # instalação continua à vista e pode mostrar erros. O próprio
            # instalador reabre o app ao terminar (entrada [Run] com WizardSilent).
            subprocess.Popen([str(installer), "/SILENT", "/SP-", "/CLOSEAPPLICATIONS",
                              "/NORESTART"], **kwargs)
        except OSError as exc:
            raise UpdateError("Não foi possível abrir o instalador da atualização.") from exc

    @staticmethod
    def _launch_macos_swap(archive: Path) -> None:
        """Extrai e confere o .app novo e agenda a troca para depois que o app fechar."""
        target = mac_app_bundle()
        staging = UPDATE_DIR / MACOS_STAGING
        shutil.rmtree(staging, ignore_errors=True)
        staging.mkdir(parents=True, exist_ok=True)
        try:
            # ditto preserva a assinatura e os atributos do pacote (unzip não).
            subprocess.run(["/usr/bin/ditto", "-x", "-k", str(archive), str(staging)],
                           check=True, capture_output=True, timeout=600,
                           creationflags=CREATE_NO_WINDOW)
        except (OSError, subprocess.SubprocessError) as exc:
            raise UpdateError("Não foi possível extrair a atualização baixada.") from exc
        bundles = [*staging.glob("*.app"), *staging.glob("*/*.app")]
        if len(bundles) != 1:
            raise UpdateError("O pacote da atualização não contém o aplicativo esperado.")
        new_app = bundles[0]
        check = subprocess.run(
            ["/usr/bin/codesign", "--verify", "--deep", "--strict", str(new_app)],
            capture_output=True, text=True, timeout=300, creationflags=CREATE_NO_WINDOW)
        if check.returncode:
            raise UpdateError("A assinatura do aplicativo baixado não é válida. "
                              "A atualização foi bloqueada.")
        # Baixado pelo próprio app não recebe quarentena, mas uma cópia antiga pode ter.
        subprocess.run(["/usr/bin/xattr", "-dr", "com.apple.quarantine", str(new_app)],
                       capture_output=True, timeout=120, creationflags=CREATE_NO_WINDOW)
        log = UPDATE_DIR / "atualizacao-macos.log"
        try:
            subprocess.Popen(
                ["/bin/sh", "-c", _MAC_SWAP_SCRIPT, "baixador-update",
                 str(os.getpid()), str(target), str(new_app), str(log)],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, start_new_session=True,
                creationflags=CREATE_NO_WINDOW,
            )
        except OSError as exc:
            raise UpdateError("Não foi possível preparar a troca do aplicativo.") from exc

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
            if match:
                candidate = Path(match.group(2).strip()).name
                if candidate.casefold() == filename.casefold():
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
            request = Request(require_https(url), headers={"User-Agent": USER_AGENT})
            with urlopen(request, timeout=20, context=_verified_ssl_context()) as response:
                return response.read().decode("utf-8")
        except (HTTPError, URLError, OSError, UnicodeDecodeError, TimeoutError, ValueError,
                http.client.HTTPException) as exc:
            raise UpdateError("Não foi possível consultar novas versões agora.") from exc


def mac_app_bundle(executable: str | None = None, frozen: bool | None = None) -> Path:
    """O .app em execução, se ele puder ser substituído pela versão nova."""
    frozen = execucao_empacotada() if frozen is None else frozen
    if not frozen:
        # Rodando pelo código-fonte, sys.executable aponta para o Python.app do
        # framework, que jamais deve ser trocado.
        raise UpdateError("Esta cópia roda pelo código-fonte; atualize com git pull.")
    path = Path(executable or sys.executable).resolve()
    bundle = next((parent for parent in path.parents if parent.suffix == ".app"), None)
    if bundle is None:
        raise UpdateError("O aplicativo não está num pacote .app; baixe a nova versão manualmente.")
    if "AppTranslocation" in bundle.parts:
        raise UpdateError(
            "O macOS abriu o app numa cópia temporária somente leitura. Arraste-o para a "
            "pasta Aplicativos, abra de lá e tente atualizar de novo.")
    if not (os.access(bundle.parent, os.W_OK) and os.access(bundle, os.W_OK)):
        raise UpdateError(
            f"Sem permissão para substituir o app em {bundle.parent}. "
            "Baixe a nova versão manualmente.")
    return bundle
