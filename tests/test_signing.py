"""Ed25519: vetores da RFC 8032 e validação cruzada com ``cryptography``."""
from __future__ import annotations

import base64
import unittest

from baixador_ytdlp import signing

# RFC 8032, seção 7.1 — TEST 1 (mensagem vazia) e TEST 2 (um byte).
VECTORS = [
    ("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60",
     "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a",
     "",
     "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"),
    ("4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb",
     "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c",
     "72",
     "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00"),
]


class Ed25519Tests(unittest.TestCase):
    def test_rfc8032_vectors(self) -> None:
        for secret, public, message, signature in VECTORS:
            secret_b, message_b = bytes.fromhex(secret), bytes.fromhex(message)
            self.assertEqual(signing.public_key(secret_b).hex(), public)
            self.assertEqual(signing.sign(secret_b, message_b).hex(), signature)
            self.assertTrue(signing.verify(bytes.fromhex(public), message_b,
                                           bytes.fromhex(signature)))

    def test_tampered_message_or_signature_is_rejected(self) -> None:
        secret, public, _message, signature = VECTORS[1]
        public_b, signature_b = bytes.fromhex(public), bytes.fromhex(signature)
        self.assertFalse(signing.verify(public_b, b"\x73", signature_b))
        broken = bytearray(signature_b)
        broken[10] ^= 1
        self.assertFalse(signing.verify(public_b, b"\x72", bytes(broken)))

    def test_detached_accepts_any_published_key(self) -> None:
        secret = bytes.fromhex(VECTORS[0][0])
        message = b"abc  BaixadorYtdlp-1.9.0-setup.exe\n"
        signature = base64.b64encode(signing.sign(secret, message)).decode()
        keys = (base64.b64encode(bytes(32)).decode(),
                base64.b64encode(signing.public_key(secret)).decode())
        self.assertTrue(signing.verify_detached(keys, message, signature))
        self.assertFalse(signing.verify_detached(keys[:1], message, signature))

    def test_matches_cryptography_when_available(self) -> None:
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        except ImportError:
            self.skipTest("cryptography não instalado")
        key = Ed25519PrivateKey.generate()
        secret = key.private_bytes_raw()
        message = b"SHA256SUMS.txt"
        self.assertEqual(signing.sign(secret, message), key.sign(message))


if __name__ == "__main__":
    unittest.main()


class UpdaterSignatureTests(unittest.TestCase):
    def _updater(self, signature_text: str | None):
        from unittest.mock import patch

        from baixador_ytdlp.updater import AppUpdater

        updater = AppUpdater()
        assets = [{"name": "SHA256SUMS.txt"}]
        if signature_text is not None:
            assets.append({"name": "SHA256SUMS.txt.sig",
                           "browser_download_url": "https://example.invalid/sig"})
        return updater, assets, patch.object(AppUpdater, "_request_text",
                                             return_value=signature_text or "")

    def test_signed_checksum_is_accepted(self) -> None:
        secret = bytes.fromhex(VECTORS[0][0])
        text = "abc  BaixadorYtdlp-1.9.0-setup.exe\n"
        keys = (base64.b64encode(signing.public_key(secret)).decode(),)
        signature = base64.b64encode(signing.sign(secret, text.encode())).decode()
        updater, assets, patcher = self._updater(signature)
        with patcher:
            updater._verify_checksum_signature(assets, text, keys)

    def test_missing_or_forged_signature_blocks_update(self) -> None:
        from baixador_ytdlp.updater import UpdateError

        secret = bytes.fromhex(VECTORS[0][0])
        keys = (base64.b64encode(signing.public_key(secret)).decode(),)
        updater, assets, patcher = self._updater(None)
        with patcher, self.assertRaises(UpdateError):
            updater._verify_checksum_signature(assets, "x", keys)
        forged = base64.b64encode(signing.sign(bytes.fromhex(VECTORS[1][0]), b"x")).decode()
        updater, assets, patcher = self._updater(forged)
        with patcher, self.assertRaises(UpdateError):
            updater._verify_checksum_signature(assets, "x", keys)
