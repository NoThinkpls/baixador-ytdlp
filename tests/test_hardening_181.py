"""Regressões da 1.8.1: consoles no Windows, fila de legendas e janela."""
from __future__ import annotations

import ast
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1] / "baixador_ytdlp"

# Chamadas deliberadamente sem creationflags: GUI do sistema ou só-macOS.
ALLOWED = {
    ("ui/queue_page.py", "subprocess.Popen"),   # explorer/open/xdg-open são gráficos
    ("hardware.py", "subprocess.run"),          # sysctl, somente macOS
    ("processes.py", "subprocess.Popen"),       # o próprio wrapper repassa os flags
}


class ConsoleWindowTests(unittest.TestCase):
    def test_every_subprocess_hides_the_console(self) -> None:
        """Cada chamada nova sem CREATE_NO_WINDOW faz uma janela preta piscar."""
        offenders = []
        for path in ROOT.rglob("*.py"):
            relative = path.relative_to(ROOT).as_posix()
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                name = ast.unparse(node.func)
                if name not in {"subprocess.run", "subprocess.Popen"}:
                    continue
                keywords = {keyword.arg for keyword in node.keywords}
                if "creationflags" in keywords or None in keywords:
                    continue
                if (relative, name) not in ALLOWED:
                    offenders.append(f"{relative}:{node.lineno} {name}")
        self.assertEqual(offenders, [])


@unittest.skipIf(os.environ.get("QT_QPA_PLATFORM") != "offscreen", "requer Qt offscreen")
class TranscriptionQueueTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from PySide6.QtWidgets import QApplication

        cls.app = QApplication.instance() or QApplication([])

    def test_queue_keeps_each_item_options_even_if_form_changes(self) -> None:
        """A 1.8.0 relia o formulário: a legenda podia ir para o vídeo errado."""
        from baixador_ytdlp.config import Settings
        from baixador_ytdlp.ui.transcription_page import TranscriptionPage

        with tempfile.TemporaryDirectory() as temporary:
            first = Path(temporary) / "primeiro.mp4"
            second = Path(temporary) / "segundo.mp4"
            other = Path(temporary) / "arrastado.mp4"
            for path in (first, second, other):
                path.write_bytes(b"x")
            page = TranscriptionPage(Settings())
            page.toolchain = object()
            started = []
            with patch.object(TranscriptionPage, "_run",
                              lambda self, opts, embed: started.append((opts, embed))
                              or setattr(self, "_current_opts", opts)), \
                    patch.object(TranscriptionPage, "_busy", return_value=True):
                page.enqueue_media(str(first), embed=True)
                page.enqueue_media(str(second), embed=True)
            self.assertEqual([opts.media_path for opts, _ in page._pending], [first, second])

            opts, embed = page._pending.popleft()
            page._current_opts, page._current_embed = opts, embed
            page.media_edit.setText(str(other))  # usuário mexe na aba durante a fila
            captured = []
            with patch.object(TranscriptionPage, "_start_soft_subtitle",
                              lambda self, source, subtitle: captured.append(source)), \
                    patch("baixador_ytdlp.ui.transcription_page.Toast"):
                page._done(str(first.with_suffix(".srt")))
            self.assertEqual(captured, [str(first)])


class WindowSettingsTests(unittest.TestCase):
    def test_schema_6_disables_mica_and_legacy_geometry(self) -> None:
        import json

        from baixador_ytdlp import config

        with tempfile.TemporaryDirectory() as temporary:
            settings_path = Path(temporary) / "settings.json"
            settings_path.write_text(json.dumps({
                "settings_schema_version": 4, "mica": True, "window_geometry": "AdnQywAD",
            }), encoding="utf-8")
            with patch.object(config, "SETTINGS_PATH", settings_path):
                loaded = config.Settings.load()
        self.assertFalse(loaded.mica)
        self.assertEqual(loaded.window_geometry, "")
        self.assertEqual(loaded.settings_schema_version, 6)
        self.assertEqual(loaded.ui_language, "pt-BR")

    def test_portable_marker_next_to_macos_bundle(self) -> None:
        from baixador_ytdlp import config

        with tempfile.TemporaryDirectory() as temporary:
            # A implementação resolve o executável; faça o mesmo no teste
            # para que caminhos 8.3 do Windows não gerem uma comparação falsa.
            root = Path(temporary).resolve()
            executable = root / "baixador-ytdlp.app" / "Contents" / "MacOS" / "baixador-ytdlp"
            executable.parent.mkdir(parents=True)
            executable.write_bytes(b"")
            (root / "portable.txt").write_text("x", encoding="utf-8")
            with patch.object(config.sys, "platform", "darwin"), \
                    patch.object(config.sys, "executable", str(executable)), \
                    patch.object(config.sys, "frozen", True, create=True):
                portable = config._portable_root()
        self.assertEqual(portable, root / f"{config.APP_ID}-data")


if __name__ == "__main__":
    unittest.main()

