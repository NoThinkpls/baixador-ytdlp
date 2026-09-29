"""O arquivo de origem aparece antes das ferramentas e habilita a ação."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from unittest.mock import patch

from baixador_ytdlp.config import Settings
from baixador_ytdlp.media_tools import CHOICES, DEFAULT_CHOICE
from baixador_ytdlp.ui import i18n
from baixador_ytdlp.ui.media_tools_page import GROUPS, OPERATIONS, MediaToolsPage


class MediaToolsLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_source_first_and_action_requires_file(self) -> None:
        page = MediaToolsPage(Settings())
        page.resize(1100, 750)
        page.show()
        self.app.processEvents()
        self.assertFalse(page.run_button.isEnabled())
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "video.mp4"
            source.write_bytes(b"test")
            page.set_media(str(source))
            self.assertTrue(page.run_button.isEnabled())
            page.source_edit.setText("")
            self.assertFalse(page.run_button.isEnabled())
        self.assertLess(page.source_edit.mapTo(page, page.source_edit.rect().topLeft()).y(),
                        page._tool_cards["trim"].mapTo(page, page._tool_cards["trim"].rect().topLeft()).y())
        page.close()
        page.deleteLater()

    def test_catalogo_e_grupos_batem_e_cada_cartao_existe(self) -> None:
        grouped = [operation for _title, operations in GROUPS for operation in operations]
        self.assertEqual(sorted(grouped), sorted(OPERATIONS))           # nenhuma fora, nenhuma repetida
        page = MediaToolsPage(Settings())
        try:
            self.assertEqual(set(page._tool_cards), set(OPERATIONS))
            self.assertEqual(list(page._tool_cards), grouped)             # ordem visual = ordem dos grupos
        finally:
            page.deleteLater()

    def test_escolhas_da_interface_batem_com_as_do_backend(self) -> None:
        for operation, data in OPERATIONS.items():
            choice = data.get("choice")
            self.assertEqual(bool(choice), operation in CHOICES, operation)
            if choice:
                values = tuple(value for _label, value in choice["options"])
                self.assertEqual(values, CHOICES[operation], operation)
                self.assertIn(DEFAULT_CHOICE[operation], values, operation)

    def test_todo_texto_das_ferramentas_tem_traducao_em_ingles(self) -> None:
        texts: set[str] = set()
        for _title, _ops in GROUPS:
            texts.add(_title)
        for data in OPERATIONS.values():
            texts.update((data["title"], data["summary"], data["action"]))
            for block in (data.get("time"), data.get("choice")):
                if block:
                    texts.update((block["title"], block.get("hint", "")))
            texts.update(label for label, _value in data.get("choice", {}).get("options", []))
        missing = sorted(text for text in texts if text and text not in i18n.EN)
        self.assertEqual(missing, [])

    def test_escolha_atualiza_a_extensao_sugerida(self) -> None:
        page = MediaToolsPage(Settings())
        page.show()
        try:
            with tempfile.TemporaryDirectory() as directory:
                source = Path(directory) / "clipe.mp4"
                source.write_bytes(b"x")
                page.set_media(str(source))
                self.assertFalse(page.choice_row.isVisibleTo(page))
                page._tool_cards["audio"].setChecked(True)
                self.assertTrue(page.choice_row.isVisibleTo(page))
                self.assertTrue(page.destination_edit.text().endswith("clipe_audio.mp3"))
                page.choice_combo.setCurrentIndex(page.choice_combo.findData("flac"))
                self.assertTrue(page.destination_edit.text().endswith("clipe_audio.flac"))
                page._tool_cards["frame"].setChecked(True)     # outra ferramenta, outra lista
                self.assertEqual(page.choice_combo.currentData(), "png")
                self.assertTrue(page.destination_edit.text().endswith("clipe_quadro.png"))
                self.assertEqual(page.choice_combo.count(), len(CHOICES["frame"]))
        finally:
            page.close()
            page.deleteLater()

    def test_linha_de_tempo_muda_com_a_ferramenta(self) -> None:
        page = MediaToolsPage(Settings())
        page.show()
        try:
            self.assertTrue(page.time_row.isVisibleTo(page))
            self.assertTrue(page.end_edit.isVisibleTo(page))
            page._tool_cards["frame"].setChecked(True)             # só o momento, sem "fim"
            self.assertTrue(page.time_row.isVisibleTo(page))
            self.assertFalse(page.end_edit.isVisibleTo(page))
            self.assertEqual(page.time_row.title.text(), "Momento do quadro")
            page._tool_cards["gif"].setChecked(True)
            self.assertTrue(page.end_edit.isVisibleTo(page))
            page._tool_cards["mute"].setChecked(True)
            self.assertFalse(page.time_row.isVisibleTo(page))
            self.assertFalse(page.choice_row.isVisibleTo(page))
            self.assertFalse(page.fast_trim_row.isVisibleTo(page))
            page._tool_cards["trim"].setChecked(True)               # volta ao estado inicial
            self.assertTrue(page.end_edit.isVisibleTo(page))
            self.assertTrue(page.fast_trim_row.isVisibleTo(page))
            self.assertEqual(page.time_row.title.text(), "Início e fim")
        finally:
            page.close()
            page.deleteLater()

    def test_executar_repassa_a_escolha_e_ignora_campos_ocultos(self) -> None:
        page = MediaToolsPage(Settings())
        page.show()
        page.toolchain = object()
        captured = {}

        class FakeWorker:
            def __init__(self, options, toolchain, parent=None):
                captured["options"] = options
                from PySide6.QtCore import QObject, Signal

                class Signals(QObject):
                    progress = Signal(str)
                    progress_value = Signal(int)
                    finished_ok = Signal(str)
                    failed = Signal(str)
                    finished = Signal()
                self.signals = Signals()
                self.progress = self.signals.progress
                self.progress_value = self.signals.progress_value
                self.finished_ok = self.signals.finished_ok
                self.failed = self.signals.failed
                self.finished = self.signals.finished

            def start(self) -> None:
                pass

            def isRunning(self) -> bool:      # noqa: N802 - API Qt
                return False

            def deleteLater(self) -> None:    # noqa: N802 - API Qt
                pass

        try:
            with tempfile.TemporaryDirectory() as directory, \
                    patch("baixador_ytdlp.ui.media_tools_page.MediaToolWorker", FakeWorker):
                source = Path(directory) / "clipe.mp4"
                source.write_bytes(b"x")
                page.set_media(str(source))
                page.start_edit.setText("00:00:10")
                page.end_edit.setText("00:00:20")
                page._tool_cards["speed"].setChecked(True)          # sem linha de tempo
                page.choice_combo.setCurrentIndex(page.choice_combo.findData("4"))
                page._run()
                options = captured["options"]
                self.assertEqual((options.operation, options.choice), ("speed", "4"))
                self.assertEqual((options.start, options.end), ("", ""))
                self.assertTrue(str(options.destination).endswith("clipe_velocidade.mp4"))
        finally:
            page.worker = None
            page.close()
            page.deleteLater()

    def test_linha_oculta_leva_o_divisor_junto(self) -> None:
        page = MediaToolsPage(Settings())
        page.show()
        try:
            group = page.options_group
            holder = group._dividers[page.choice_row]
            page._tool_cards["audio"].setChecked(True)
            self.assertTrue(holder.isVisibleTo(page))
            page._tool_cards["mute"].setChecked(True)
            self.assertFalse(page.choice_row.isVisibleTo(page))
            self.assertFalse(holder.isVisibleTo(page))          # sem linha solta no bloco
        finally:
            page.close()
            page.deleteLater()


if __name__ == "__main__":
    unittest.main()
