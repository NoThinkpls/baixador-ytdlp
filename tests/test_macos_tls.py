"""Regressões da cadeia TLS usada pelo aplicativo empacotado no macOS."""
from __future__ import annotations

import ssl
import urllib.error
import unittest
from unittest.mock import Mock, patch

from baixador_ytdlp.tools import ToolManager


class MacOSTLSTests(unittest.TestCase):
    def test_request_uses_verified_context_first(self) -> None:
        response = Mock()
        verified = Mock(spec=ssl.SSLContext)

        with patch("baixador_ytdlp.tools._verified_ssl_context", return_value=verified), \
                patch("baixador_ytdlp.tools.urllib.request.urlopen", return_value=response) as opening:
            result = ToolManager._request("https://api.github.com/repos/yt-dlp/yt-dlp")

        self.assertIs(result, response)
        self.assertIs(opening.call_args.kwargs["context"], verified)

    def test_frozen_macos_never_disables_certificate_verification(self) -> None:
        certificate_error = ssl.SSLCertVerificationError(
            1, "certificate verify failed: unable to get local issuer certificate"
        )

        with patch("baixador_ytdlp.tools.sys.platform", "darwin"), \
                patch("baixador_ytdlp.tools.sys.frozen", True, create=True), \
                patch("baixador_ytdlp.tools.urllib.request.urlopen",
                      side_effect=urllib.error.URLError(certificate_error)) as opening, \
                patch("baixador_ytdlp.tools.ssl._create_unverified_context",
                      side_effect=AssertionError("TLS inseguro")) as insecure:
            with self.assertRaises(urllib.error.URLError):
                ToolManager._request("https://api.github.com/repos/yt-dlp/yt-dlp")

        self.assertEqual(opening.call_count, 1)
        insecure.assert_not_called()

    def test_fallback_is_not_used_for_untrusted_host(self) -> None:
        certificate_error = ssl.SSLCertVerificationError(1, "CERTIFICATE_VERIFY_FAILED")

        with patch("baixador_ytdlp.tools.sys.platform", "darwin"), \
                patch("baixador_ytdlp.tools.sys.frozen", True, create=True), \
                patch("baixador_ytdlp.tools.urllib.request.urlopen",
                      side_effect=urllib.error.URLError(certificate_error)) as opening:
            with self.assertRaises(urllib.error.URLError):
                ToolManager._request("https://example.invalid/tool")

        self.assertEqual(opening.call_count, 1)


if __name__ == "__main__":
    unittest.main()
