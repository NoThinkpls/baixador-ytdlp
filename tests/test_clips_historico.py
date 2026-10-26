"""Página Cortes (estilo salvo, prévia) e histórico de cortes e ferramentas."""
from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from baixador_ytdlp.clips import ClipOptions, ClipRange
from baixador_ytdlp.history import CLIP, TOOL, History, HistoryEntry

HAS_QT = all(importlib.util.find_spec(module) is not None
             for module in ("PySide6", "qframelesswindow"))

if HAS_QT:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from baixador_ytdlp.config import Settings
    from baixador_ytdlp.ui.clips_page import ClipsPage


class HistoricoDadosTests(unittest.TestCase):
    def test_corte_e_ferramenta_sobrevivem_ao_disco(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "history.json"
            history = History(path)
            history.add(HistoryEntry(title="Abertura", path="/v/a_corte01.mp4", kind=CLIP,
                                     source="https://youtu.be/x", operation="01:30–02:15"))
            history.add(HistoryEntry(title="a", path="/v/a.mp3", kind=TOOL,
                                     operation="Extrair áudio"))
            history.flush()
            loaded = History(path).load().entries
        self.assertEqual([entry.kind for entry in loaded], [TOOL, CLIP])
        self.assertTrue(loaded[1].is_clip and loaded[0].is_tool)
        self.assertEqual(loaded[1].operation, "01:30–02:15")
        # Link não é arquivo: não pode virar "mídia de origem existe".
        self.assertIsNone(loaded[1].existing_source())


@unittest.skipUnless(HAS_QT, "Qt ausente")
class PaginaCortesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _page(self, **values) -> tuple[ClipsPage, Settings]:
        cfg = Settings(**values)
        cfg.save = MagicMock()   # nunca grava no perfil de quem roda os testes
        return ClipsPage(cfg), cfg

    def test_estilo_salvo_volta_na_abertura(self) -> None:
        page, _cfg = self._page(clips_font="Arial", clips_font_size=104,
                                clips_text_color="#00FF00", clips_highlight_color="#FF00AA",
                                clips_position=35, clips_words=2, clips_uppercase=False,
                                clips_framing="track")
        style = page.caption_style()
        self.assertEqual((style.size, style.text_color, style.highlight_color),
                         (104, "#00FF00", "#FF00AA"))
        self.assertEqual((style.position, style.words, style.uppercase), (35, 2, False))
        self.assertEqual(page.framing_picker.value(), "track")
        self.assertEqual(page.preview.caption.position, 35)

    def test_mudar_controles_salva_nas_configuracoes(self) -> None:
        page, cfg = self._page()
        page.position_stepper.setValue(40)
        page.highlight_color.set_color("#00e5ff")
        page.framing_picker.set_value("track")
        self.assertEqual((cfg.clips_position, cfg.clips_highlight_color, cfg.clips_framing),
                         (40, "#00E5FF", "track"))
        self.assertTrue(cfg.save.called)
        self.assertEqual(page.preview.caption.highlight_color, "#00E5FF")

    def test_cor_invalida_no_arquivo_nao_quebra(self) -> None:
        page, _cfg = self._page(clips_text_color="vermelho", clips_position=500)
        style = page.caption_style()
        self.assertEqual(style.text_color, "#FFFFFF")
        self.assertEqual(style.position, 92)

    def test_arrastar_na_previa_move_a_legenda(self) -> None:
        page, cfg = self._page()
        page.preview._move_to(page.preview.height() * 0.25)
        self.assertEqual(page.position_stepper.value(), 25)
        self.assertEqual(cfg.clips_position, 25)

    def test_opcoes_levam_o_estilo(self) -> None:
        page, _cfg = self._page(clips_position=30)
        with tempfile.TemporaryDirectory() as tmp:
            page.source_edit.setText("https://www.youtube.com/watch?v=abc")
            page.output_edit.setText(tmp)
            page.rows[0].start.setText("00:10")
            page.rows[0].end.setText("00:40")
            options = page._options()
        self.assertEqual(options.style.position, 30)

    def test_destino_logo_abaixo_da_origem(self) -> None:
        page, _cfg = self._page()
        page.resize(900, 2000)
        page.show()
        QApplication.processEvents()
        source_y = page.source_edit.mapTo(page, page.source_edit.rect().topLeft()).y()
        output_y = page.output_edit.mapTo(page, page.output_edit.rect().topLeft()).y()
        ranges_y = page.rows[0].mapTo(page, page.rows[0].rect().topLeft()).y()
        page.hide()
        self.assertLess(source_y, output_y)
        self.assertLess(output_y, ranges_y)

    def test_duracao_ou_erro_de_cada_corte_enquanto_digita(self) -> None:
        page, _cfg = self._page()
        row = page.rows[0]
        row.start.setText("01:30")
        row.end.setText("02:15")
        self.assertEqual(row.length.text(), "00:45")
        row.end.setText("01:00")
        self.assertEqual(row.length.text(), "inválido")
        self.assertIn("posterior", row.length.toolTip())

    def test_opcoes_de_acabamento_e_animacao_salvas(self) -> None:
        page, cfg = self._page(clips_animation="none", clips_background=True,
                               clips_zoom_cuts=True, clips_title_seconds=0.0)
        self.assertEqual(page.caption_style().animation, "none")
        self.assertTrue(page.caption_style().background)
        self.assertEqual(page.title_combo.currentData(), 0.0)
        page.progress_switch.setChecked(True)
        page.animation_combo.setCurrentIndex(page.animation_combo.findData("karaoke"))
        self.assertTrue(cfg.clips_progress_bar)
        self.assertEqual(cfg.clips_animation, "karaoke")
        with tempfile.TemporaryDirectory() as tmp:
            page.source_edit.setText("https://www.youtube.com/watch?v=abc")
            page.output_edit.setText(tmp)
            page.rows[0].start.setText("00:10")
            page.rows[0].end.setText("00:40")
            options = page._options()
        self.assertTrue(options.zoom_cuts and options.progress_bar)
        self.assertEqual((options.title_seconds, options.style.animation), (0.0, "karaoke"))

    def test_zoom_some_sem_remover_pausas(self) -> None:
        page, _cfg = self._page()
        page.show()
        page.pauses_switch.setChecked(False)
        self.assertFalse(page.zoom_row.isVisible())
        page.pauses_switch.setChecked(True)
        self.assertTrue(page.zoom_row.isVisible())
        page.hide()

    def test_cada_corte_pronto_avisa_o_historico(self) -> None:
        page, _cfg = self._page()
        page._running = ClipOptions(source="/v/aula.mp4", output_dir=Path("/v"),
                                    ranges=(ClipRange(90, 135, "Abertura"), ClipRange(200, 230)))
        page._outputs = []
        received = []
        page.clip_finished.connect(lambda *args: received.append(args))
        page._clip_done("/v/aula_corte01_Abertura.mp4")
        page._clip_done("/v/aula_corte02.mp4")
        self.assertEqual(received, [
            ("/v/aula_corte01_Abertura.mp4", "/v/aula.mp4", "Abertura", "01:30–02:15"),
            ("/v/aula_corte02.mp4", "/v/aula.mp4", "", "03:20–03:50")])


@unittest.skipUnless(HAS_QT, "Qt ausente")
class HistoricoNaJanelaTests(unittest.TestCase):
    """Os ganchos da janela principal, sem montar a janela inteira."""

    def _window(self, enabled: bool = True):
        from baixador_ytdlp.ui.main_window import MainWindow
        fake = SimpleNamespace(cfg=SimpleNamespace(history_enabled=enabled),
                               history=History(Path(tempfile.gettempdir()) / "nunca.json"),
                               history_page=MagicMock())
        return MainWindow, fake

    def test_corte_entra_no_historico(self) -> None:
        window, fake = self._window()
        window._on_clip_finished(fake, "/v/aula_corte01.mp4", "https://youtu.be/x", "",
                                 "01:30–02:15")
        entry = fake.history.entries[0]
        self.assertEqual((entry.kind, entry.title, entry.url), (CLIP, "aula_corte01",
                                                                "https://youtu.be/x"))
        self.assertEqual(entry.folder_path, str(Path("/v")))
        fake.history_page.invalidate.assert_called_once()

    def test_ferramenta_entra_no_historico(self) -> None:
        window, fake = self._window()
        window._on_tool_finished(fake, "/v/aula.mp3", "/v/aula.mp4", "Extrair áudio")
        entry = fake.history.entries[0]
        self.assertEqual((entry.kind, entry.operation, entry.source),
                         (TOOL, "Extrair áudio", "/v/aula.mp4"))

    def test_historico_desligado_nao_guarda(self) -> None:
        window, fake = self._window(enabled=False)
        window._on_tool_finished(fake, "/v/aula.mp3", "/v/aula.mp4", "Extrair áudio")
        window._on_clip_finished(fake, "/v/c.mp4", "/v/aula.mp4", "", "00:01–00:05")
        self.assertEqual(fake.history.entries, [])


@unittest.skipUnless(HAS_QT, "Qt ausente")
class PaginaHistoricoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_resumo_conta_cada_tipo(self) -> None:
        from baixador_ytdlp.ui.history_page import summary_text
        entries = [HistoryEntry(title="a"), HistoryEntry(title="b", kind=CLIP),
                   HistoryEntry(title="c", kind=CLIP), HistoryEntry(title="d", kind=TOOL),
                   HistoryEntry(title="e", kind="transcription")]
        self.assertEqual(summary_text(entries),
                         "1 download · 1 transcrição · 2 cortes · 1 ferramenta")

    def test_cartao_do_corte_tem_suas_acoes(self) -> None:
        from baixador_ytdlp.ui.components import IconButton
        from baixador_ytdlp.ui.history_page import HistoryCard
        with tempfile.TemporaryDirectory() as tmp:
            clip = Path(tmp) / "aula_corte01.mp4"
            clip.write_bytes(b"x")
            entry = HistoryEntry(title="Abertura", path=str(clip), folder_path=tmp, kind=CLIP,
                                 source="https://youtu.be/x", operation="01:30–02:15")
            card = HistoryCard(entry)
            buttons = {button.toolTip(): button for button in card.findChildren(IconButton)}
            self.assertTrue(buttons["Abrir o arquivo"].isEnabled())
            self.assertTrue(buttons["Gerar legenda deste arquivo"].isEnabled())
            received = []
            card.new_clips.connect(received.append)
            buttons["Fazer outros cortes deste vídeo"].click()
            self.assertEqual(received, ["https://youtu.be/x"])
            self.assertIn("corte vertical 01:30–02:15", HistoryCard._meta_text(entry))

    def test_cartao_da_ferramenta(self) -> None:
        from baixador_ytdlp.ui.history_page import HistoryCard
        entry = HistoryEntry(title="aula", path="/nao/existe.mp3", kind=TOOL,
                             operation="Extrair áudio")
        meta = HistoryCard._meta_text(entry)
        self.assertIn("Extrair áudio", meta)
        self.assertIn("arquivo não está mais lá", meta)


@unittest.skipUnless(HAS_QT, "Qt ausente")
class FerramentasAvisamOHistoricoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_ferramenta_concluida_informa_origem_e_nome(self) -> None:
        from unittest.mock import patch

        from baixador_ytdlp.ui.media_tools_page import MediaToolsPage
        cfg = Settings()
        cfg.save = MagicMock()
        page = MediaToolsPage(cfg)
        page._running = ("/v/aula.mp4", "Extrair áudio")
        received = []
        page.tool_finished.connect(lambda *args: received.append(args))
        with patch("baixador_ytdlp.ui.media_tools_page.Toast"):
            page._done("/v/aula.mp3")
        self.assertEqual(received, [("/v/aula.mp3", "/v/aula.mp4", "Extrair áudio")])


if __name__ == "__main__":
    unittest.main()
