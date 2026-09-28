"""Prepara uma release feita na máquina local (o GitHub Actions está desligado).

Uso, depois do build.ps1:

    python scripts/prepare_release.py            # hashes, assinatura e notas
    python scripts/prepare_release.py --publish  # idem e publica com o gh

O que faz, em dist/installer:
1. Gera SHA256SUMS.txt com todos os .exe e .zip.
2. Assina o arquivo (SHA256SUMS.txt.sig) com a chave Ed25519 privada, lida de
   RELEASE_SIGNING_KEY ou do arquivo criado por
   ``python scripts/release_signing.py generate`` (fora do repositório).
3. Confere a assinatura com as chaves embutidas no app (RELEASE_PUBLIC_KEYS).
   Se o app já exige assinatura e não há chave, a release é bloqueada: todos os
   usuários recusariam a atualização.
4. Extrai do CHANGELOG.md as notas desta versão (o app mostra em "Novidades").
"""
from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from baixador_ytdlp import signing  # noqa: E402
from baixador_ytdlp.config import APP_VERSION  # noqa: E402
from baixador_ytdlp.updater import RELEASE_PUBLIC_KEYS, SIGNATURE_ASSET  # noqa: E402
from release_signing import load_private_key  # noqa: E402

SUMS = "SHA256SUMS.txt"


def write_sums(folder: Path) -> Path:
    packages = sorted(p for p in folder.iterdir() if p.is_file() and p.suffix in {".exe", ".zip"})
    if not packages:
        raise SystemExit(f"Nenhum .exe ou .zip em {folder}. Rode o build.ps1 antes.")
    lines = []
    for package in packages:
        digest = hashlib.sha256()
        with package.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        lines.append(f"{digest.hexdigest().upper()}  {package.name}")
    target = folder / SUMS
    target.write_text("\n".join(lines) + "\n", encoding="ascii")
    return target


def sign_sums(sums: Path, public_keys: tuple[str, ...] = RELEASE_PUBLIC_KEYS) -> Path | None:
    secret = load_private_key()
    signature_path = sums.with_name(SIGNATURE_ASSET)
    signature_path.unlink(missing_ok=True)
    if secret is None:
        if public_keys:
            raise SystemExit(
                "Este app exige releases assinadas, mas a chave privada não foi encontrada. "
                "Sem o .sig nenhum usuário conseguiria atualizar.")
        print("Aviso: sem chave privada; a release sai sem assinatura.")
        return None
    signature = signing.sign(secret, sums.read_bytes())
    import base64

    signature_path.write_text(base64.b64encode(signature).decode() + "\n", encoding="ascii")
    if public_keys and not signing.verify_detached(
            public_keys, sums.read_bytes(), signature_path.read_text(encoding="ascii")):
        signature_path.unlink()
        raise SystemExit(
            "A chave privada não corresponde a RELEASE_PUBLIC_KEYS: os usuários recusariam "
            "esta release.")
    return signature_path


def release_notes(version: str, changelog: Path = ROOT / "CHANGELOG.md") -> str:
    text = changelog.read_text(encoding="utf-8").replace("\r\n", "\n")
    marker = f"## [{version}]"
    start = text.find(marker)
    if start < 0:
        raise SystemExit(f"O CHANGELOG.md não tem a seção {marker}.")
    body_start = text.index("\n", start) + 1
    end = text.find("\n## [", body_start)
    return text[body_start:end if end >= 0 else None].strip() + "\n"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--folder", type=Path, default=ROOT / "dist" / "installer")
    parser.add_argument("--publish", action="store_true", help="publica com o gh ao final")
    args = parser.parse_args(argv)

    folder: Path = args.folder
    sums = write_sums(folder)
    signature = sign_sums(sums)
    notes = folder / "RELEASE_NOTES.md"
    notes.write_text(release_notes(APP_VERSION), encoding="utf-8")

    assets = [str(p) for p in sorted(folder.iterdir())
              if p.is_file() and p.suffix in {".exe", ".zip"}]
    assets.append(str(sums))
    if signature:
        assets.append(str(signature))
    command = ["gh", "release", "create", f"v{APP_VERSION}", "--title", f"v{APP_VERSION}",
               "--notes-file", str(notes), *assets]
    print(f"Pronto para v{APP_VERSION}: {len(assets)} arquivos"
          + (", assinado" if signature else ", SEM assinatura"))
    if not args.publish:
        print("Para publicar:", subprocess.list2cmdline(command))
        return 0
    return subprocess.call(command, cwd=ROOT)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
