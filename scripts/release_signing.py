"""Gera o par de chaves e assina o SHA256SUMS.txt das releases (Ed25519).

    python scripts/release_signing.py generate
        Imprime a chave PRIVADA (guarde no segredo RELEASE_SIGNING_KEY de um
        environment protegido do GitHub, com aprovação manual) e a PÚBLICA (cole
        em RELEASE_PUBLIC_KEYS, em baixador_ytdlp/updater.py).

    RELEASE_SIGNING_KEY=... python scripts/release_signing.py sign SHA256SUMS.txt
        Grava SHA256SUMS.txt.sig (assinatura em base64) ao lado do arquivo.

    python scripts/release_signing.py verify SHA256SUMS.txt
        Confere o .sig com as chaves embutidas no aplicativo.
"""
from __future__ import annotations

import base64
import os
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from baixador_ytdlp import signing  # noqa: E402
from baixador_ytdlp.updater import RELEASE_PUBLIC_KEYS  # noqa: E402


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    command = argv[0]
    if command == "generate":
        secret = secrets.token_bytes(32)
        print("PRIVADA (segredo RELEASE_SIGNING_KEY):", base64.b64encode(secret).decode())
        print("PÚBLICA (RELEASE_PUBLIC_KEYS):        ",
              base64.b64encode(signing.public_key(secret)).decode())
        return 0
    if len(argv) != 2:
        print(__doc__)
        return 2
    target = Path(argv[1])
    if command == "sign":
        encoded = os.environ.get("RELEASE_SIGNING_KEY", "").strip()
        if not encoded:
            print("RELEASE_SIGNING_KEY não definido.", file=sys.stderr)
            return 1
        secret = base64.b64decode(encoded, validate=True)
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
