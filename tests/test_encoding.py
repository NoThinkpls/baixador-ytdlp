"""Regressões para saída UTF-8 e páginas de código antigas do Windows."""
from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from baixador_ytdlp.config import Settings
from baixador_ytdlp.downloader import DownloadOptions, build_args
from baixador_ytdlp.probe import _run_json
from baixador_ytdlp.tools import decode_external_output


class _Process:
    returncode = 0

    def __init__(self, stdout: bytes, stderr: bytes = b""):
        self.stdout, self.stderr = stdout, stderr

    def communicate(self, timeout=None):  # noqa: ARG002 - mesma interface do Popen
        return self.stdout, self.stderr


class EncodingTests(unittest.TestCase):
    def test_decodes_legacy_windows_bytes_without_replacement_character(self) -> None:
        # 0xE3/0xE7 são comuns numa página de código pt-BR, mas inválidos em
        # UTF-8 isoladamente. O fallback precisa preservar o texto original.
        with patch("baixador_ytdlp.tools.IS_WINDOWS", True):
            text = decode_external_output("Mendonça — ação".encode("cp1252"))
        self.assertEqual(text, "Mendonça — ação")
        self.assertNotIn("�", text)

    def test_download_forces_utf8_in_ytdlp(self) -> None:
        toolchain = SimpleNamespace(ytdlp=Path("yt-dlp.exe"), bin_dir=Path("bin"))
        args = build_args(
            DownloadOptions("https://example.invalid/video", "downloads"), Settings(), toolchain)
        self.assertIn("--encoding", args)
        self.assertEqual(args[args.index("--encoding") + 1], "utf-8")

    def test_probe_keeps_cp1252_title_when_older_ytdlp_ignores_utf8_flag(self) -> None:
        payload = '{"title":"Mendonça — ação"}'.encode("cp1252")
        process = _Process(payload)
        with patch("baixador_ytdlp.tools.IS_WINDOWS", True), \
                patch("baixador_ytdlp.probe._popen", return_value=process):
            data = _run_json(["yt-dlp"], 10)
        self.assertEqual(data["title"], "Mendonça — ação")


if __name__ == "__main__":
    unittest.main()
