"""Gera o par de chaves e assina o SHA256SUMS.txt das releases (Ed25519).

    python scripts/release_signing.py generate
        Grava a chave PRIVADA num arquivo fora do repositório (ver key_file();
        faça backup dele) e imprime só a PÚBLICA, para colar em
        RELEASE_PUBLIC_KEYS, em baixador_ytdlp/updater.py.

    python scripts/release_signing.py sign SHA256SUMS.txt
        Grava SHA256SUMS.txt.sig (assinatura em base64) ao lado do arquivo. A
        chave vem de RELEASE_SIGNING_KEY ou do arquivo de key_file().

    python scripts/release_signing.py verify SHA256SUMS.txt
        Confere o .sig com as chaves embutidas no aplicativo.
"""
from __future__ import annotations

import base64
import contextlib
import os
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from baixador_ytdlp import signing  # noqa: E402
from baixador_ytdlp.updater import RELEASE_PUBLIC_KEYS  # noqa: E402


def key_file() -> Path:
    """Fora do repositório e do perfil do app: some com um clone novo, não com o app."""
    override = os.environ.get("RELEASE_SIGNING_KEY_FILE", "").strip()
    if override:
        return Path(override)
    base = os.environ.get("APPDATA") or os.path.join(Path.home(), ".config")
    return Path(base) / "BaixadorYtdlp-release" / "release-signing.key"


def load_private_key() -> bytes | None:
    encoded = os.environ.get("RELEASE_SIGNING_KEY", "").strip()
    path = key_file()
    if not encoded and path.is_file():
        encoded = path.read_text(encoding="ascii").strip()
    if not encoded:
        return None
    secret = base64.b64decode(encoded, validate=True)
    if len(secret) != 32:
        raise SystemExit("Chave privada inválida: esperava 32 bytes em base64.")
    return secret


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    command = argv[0]
    if command == "generate":
        path = key_file()
        if path.exists():
            print(f"Já existe uma chave em {path}. Apague-a de propósito antes de gerar outra: "
                  "trocar a chave impede quem tem a versão antiga de atualizar.", file=sys.stderr)
            return 1
        secret = secrets.token_bytes(32)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(base64.b64encode(secret).decode() + "\n", encoding="ascii")
        with contextlib.suppress(OSError):
            os.chmod(path, 0o600)
        # A privada não é impressa: histórico do terminal e logs não a guardam.
        print("Chave PRIVADA gravada em:", path)
        print("Faça um backup desse arquivo num lugar seguro (sem ele não há como assinar).")
        print("PÚBLICA (cole em RELEASE_PUBLIC_KEYS):",
              base64.b64encode(signing.public_key(secret)).decode())
        return 0
    if len(argv) != 2:
        print(__doc__)
        return 2
    target = Path(argv[1])
    if command == "sign":
        secret = load_private_key()
        if secret is None:
            print(f"Chave privada não encontrada (RELEASE_SIGNING_KEY ou {key_file()}).",
                  file=sys.stderr)
            return 1
        signature = signing.sign(secret, target.read_bytes())
        target.with_name(target.name + ".sig").write_text(
            base64.b64encode(signature).decode() + "\n", encoding="ascii")
        print("Assinatura gravada:", target.name + ".sig")
        return 0
    if command == "verify":
        signature = target.with_name(target.name + ".sig").read_text(encoding="ascii")
        ok = signing.verify_detached(RELEASE_PUBLIC_KEYS, target.read_bytes(), signature)
        print("OK" if ok else "FALHOU")
        return 0 if ok else 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
