"""Modo de linha de comando (``baixador-ytdlp cli …``) usado por scripts e pelo Claude Code."""
from __future__ import annotations

import contextlib
import io
import json
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PySide6.QtCore import QThread, Signal

from baixador_ytdlp import cli
from baixador_ytdlp.clips import ClipRange


class _FakeWorker(QThread):
    progress = Signal(str)
    progress_value = Signal(int)
    finished_ok = Signal(str)
    failed = Signal(str)

    def __init__(self, *args, **kwargs):
        super().__init__()
        self.args = args
        self.cancelled = threading.Event()

    def cancel(self) -> None:
        self.cancelled.set()

    def run(self) -> None:
        self.progress.emit("Processando na CPU… 50%")
        self.progress_value.emit(50)
        self.finished_ok.emit(str(self.args[0].destination))


def _run(argv: list[str]) -> tuple[int, dict, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), \
            patch.object(cli, "_prepare_stdio"), patch("baixador_ytdlp.diagnostics.install_diagnostics"):
        code = cli.run_cli(argv)
    text = out.getvalue()
    return code, (json.loads(text) if text.strip() else {}), err.getvalue()


class CliParsingTests(unittest.TestCase):
    def test_json_path_is_accepted_anywhere(self) -> None:
        rest, path = cli._split_json_path(["baixar", "https://x.y/v", "--json-saida", "r.json",
                                           "--audio"])
        self.assertEqual(rest, ["baixar", "https://x.y/v", "--audio"])
        self.assertEqual(path, "r.json")
        rest, path = cli._split_json_path(["--json-saida=a.json", "status"])
        self.assertEqual((rest, path), (["status"], "a.json"))

    def test_clip_spec_with_and_without_title(self) -> None:
        self.assertEqual(cli._parse_clip("1:20-2:05=Gancho forte"), ClipRange(80, 125, "Gancho forte"))
        self.assertEqual(cli._parse_clip("00:01:00-00:01:30"), ClipRange(60, 90, ""))
        with self.assertRaises(cli.CliError):
            cli._parse_clip("1:20")
        with self.assertRaises(cli.CliError):
            cli._parse_clip("2:00-1:00")

    def test_quality_selector_caps_height_and_keeps_fallback(self) -> None:
        self.assertEqual(cli._quality_selector("melhor"), "bv*+ba/b")
        self.assertEqual(cli._quality_selector("1080p"),
                         "bv*[height<=1080]+ba/b[height<=1080]/bv*+ba/b")
        with self.assertRaises(cli.CliError):
            cli._quality_selector("altíssima")

    def test_playlist_detection_matches_download_page(self) -> None:
        self.assertTrue(cli._is_playlist_url("https://www.youtube.com/playlist?list=PL1"))
        self.assertTrue(cli._is_playlist_url("https://www.youtube.com/@canal"))
        self.assertFalse(cli._is_playlist_url("https://www.youtube.com/watch?v=a&list=PL1"))

    def test_reporter_collapses_percent_suffix(self) -> None:
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            reporter = cli._Reporter()
            for value in range(0, 30):
                reporter.status(f"Processando na CPU… {value}%")
                reporter.percent(value, "trim")
        lines = err.getvalue().splitlines()
        self.assertEqual(lines.count("… Processando na CPU"), 1)
        self.assertEqual(len([line for line in lines if line.startswith("[")]), 6)


class CliRunTests(unittest.TestCase):
    def test_usage_error_returns_json_and_code_2(self) -> None:
        code, result, _ = _run(["baixar"])
        self.assertEqual(code, cli.EXIT_USAGE)
        self.assertFalse(result["ok"])

    def test_missing_file_is_a_failure_with_message(self) -> None:
        code, result, _ = _run(["legendar", "/nao/existe.mp4"])
        self.assertEqual(code, cli.EXIT_FAILED)
        self.assertIn("não encontrado", result["erro"])

    def test_signals_from_worker_thread_reach_the_cli(self) -> None:
        """Sem conexão direta o Qt enfileirava os sinais e o resultado nunca chegava."""
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "video.mp4"
            source.write_bytes(b"x")
            report = Path(temporary) / "resultado.json"
            toolchain = SimpleNamespace()
            with patch.object(cli, "_toolchain", return_value=(None, toolchain)), \
                    patch("baixador_ytdlp.workers.MediaToolWorker", _FakeWorker):
                code, result, err = _run(["ferramenta", "audio", str(source), "--json-saida",
                                          str(report)])
            self.assertEqual(code, cli.EXIT_OK, result)
            self.assertEqual(result["arquivo"], str(Path(temporary) / "video_audio.mp3"))
            self.assertEqual(json.loads(report.read_text(encoding="utf-8")), result)
            self.assertIn("… Processando na CPU", err)
            self.assertIn("[ 50%] audio", err)

    def test_status_reads_settings_without_saving(self) -> None:
        from baixador_ytdlp.config import Settings

        with patch.object(Settings, "save") as save:
            code, result, _ = _run(["status"])
        self.assertEqual(code, cli.EXIT_OK)
        self.assertIn("pasta_downloads", result)
        save.assert_not_called()

    def test_main_dispatches_cli_before_qt(self) -> None:
        source = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")
        tail = source[source.index('if __name__ == "__main__":'):]
        self.assertLess(tail.index("freeze_support()"), tail.index('["cli"]'))
        self.assertLess(tail.index('["cli"]'), tail.index("main()"))


if __name__ == "__main__":
    unittest.main()
