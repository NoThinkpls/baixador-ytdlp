"""Página 'Legendar': transcrição local de áudio e vídeo com faster-whisper."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from ..config import Settings
from ..diagnostics import log_event
from ..transcription import FORMATS, TranscriptionOptions
from ..workers import TranscriptionWorker
from .components import (Button, Card, Divider, Headline, InsetGroup, LogView, Muted,
                         PageHeader, PrimaryButton, ProgressBar, ScrollColumn,
                         SectionLabel, Select, SettingRow, Switch, TextField, Toast)

LANGUAGES = [("Português", "pt"), ("Inglês", "en"), ("Espanhol", "es"),
             ("Francês", "fr"), ("Alemão", "de"), ("Italiano", "it"),
             ("Japonês", "ja"), ("Coreano", "ko"), ("Chinês", "zh"),
             ("Detectar automaticamente", "auto")]
MODELS = [("tiny — mais rápido", "tiny"), ("base — rápido", "base"),
          ("small — equilibrado", "small"), ("medium — recomendado", "medium"),
          ("large-v3 — mais preciso", "large-v3")]
MEDIA_FILTER = ("Mídias (*.mp4 *.mkv *.mov *.avi *.webm *.m4v *.flv *.wmv *.mpeg *.mp3 "
                "*.wav *.flac *.aac *.ogg *.m4a *.opus *.m4b);;Todos os arquivos (*.*)")


class TranscriptionPage(QWidget):
    # saída (a legenda) e origem (a mídia) — alimentam o histórico
    transcription_finished = Signal(str, str)

    def __init__(self, cfg: Settings, parent=None):
        super().__init__(parent)
        self.setObjectName("transcriptionPage")
        self.cfg = cfg
        self.toolchain = None
        self.worker: TranscriptionWorker | None = None
        self._paused = False
        self._build_ui()
        self.setAcceptDrops(True)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 20, 28, 0)
        root.setSpacing(16)

        root.addWidget(PageHeader(
            "Legendar",
            "Transcrição local com faster-whisper. Usa CUDA quando dá, e CPU quando não dá.",
            self))

        page = ScrollColumn(self, spacing=14)
        root.addWidget(page, 1)

        page.add(SectionLabel("Arquivos", self))
        page.add(self._files_group())

        page.add(SectionLabel("Modelo", self))
        page.add(self._options_group())

        page.add(SectionLabel("Andamento", self))
        page.add(self._status_card())
        page.add(self._log_view(), 1)

        root.addWidget(self._action_bar())

    def _files_group(self) -> InsetGroup:
        group = InsetGroup(self)

        self.media_edit = TextField("Selecione ou arraste um vídeo ou áudio para cá", group)
        self.media_edit.setClearButtonEnabled(True)
        pick_media = Button("Selecionar", "media", "secondary", group)
        pick_media.clicked.connect(self._pick_media)
        group.add_row(self._path_row(
            group, "Arquivo de mídia",
            "Também aceita arrastar e soltar direto nesta página.",
            self.media_edit, pick_media))

        self.output_edit = TextField("A legenda será criada ao lado da mídia", group)
        self.output_edit.setClearButtonEnabled(True)
        pick_output = Button("Salvar como", "save", "secondary", group)
        pick_output.clicked.connect(self._pick_output)
        group.add_row(self._path_row(
            group, "Arquivo de saída",
            "Deixe em branco para gravar ao lado do arquivo de origem.",
            self.output_edit, pick_output))
        return group

    @staticmethod
    def _path_row(parent, title: str, subtitle: str, field: TextField,
                  button: Button) -> QWidget:
        row = QWidget(parent)
        column = QVBoxLayout(row)
        column.setContentsMargins(16, 12, 16, 14)
        column.setSpacing(8)
        column.addWidget(Headline(title, row))
        column.addWidget(Muted(subtitle, row))
        line = QHBoxLayout()
        line.setSpacing(10)
        line.addWidget(field, 1)
        line.addWidget(button)
        column.addLayout(line)
        return row

    def _options_group(self) -> InsetGroup:
        group = InsetGroup(self)

        self.language = self._combo(LANGUAGES, self.cfg.transcription_language, group)
        self.language.currentIndexChanged.connect(
            lambda: self._save("transcription_language", self.language.currentData()))
        group.add_row(SettingRow("Idioma", "“Detectar automaticamente” custa um pouco mais.",
                                 self.language, group))

        self.model = self._combo(MODELS, self.cfg.transcription_model, group)
        self.model.currentIndexChanged.connect(
            lambda: self._save("transcription_model", self.model.currentData()))
        group.add_row(SettingRow("Modelo Whisper",
                                 "Modelos maiores acertam mais e demoram mais.",
                                 self.model, group))

        format_items = [(label, key) for key, (label, _ext) in FORMATS.items()]
        self.output_format = self._combo(format_items, self.cfg.transcription_format, group)
        self.output_format.currentIndexChanged.connect(self._format_changed)
        group.add_row(SettingRow("Formato da legenda", "", self.output_format, group))

        self.aggressive = Switch(group)
        self.aggressive.setChecked(self.cfg.transcription_aggressive_filter)
        self.aggressive.checkedChanged.connect(
            lambda enabled: self._save("transcription_aggressive_filter", bool(enabled)))
        group.add_row(SettingRow(
            "Filtro anti-alucinação agressivo",
            "Descarta trechos repetidos que o modelo inventa no silêncio.",
            self.aggressive, group))
        return group

    def _status_card(self) -> Card:
        card = Card(self, padding=(16, 14, 16, 16), spacing=10)
        self.hardware = Headline("Hardware será detectado ao iniciar", card, wrap=True)
        card.body.addWidget(self.hardware)

        line = QHBoxLayout()
        line.setSpacing(12)
        self.progress = ProgressBar(card)
        self.progress.setValue(0)
        self.percent_label = Muted("0%", card)
        self.percent_label.setWordWrap(False)
        self.percent_label.setFixedWidth(46)
        self.progress.valueChanged.connect(
            lambda value: self.percent_label.setText(f"{value}%"))
        line.addWidget(self.progress, 1)
        line.addWidget(self.percent_label)
        card.body.addLayout(line)

        self.progress_label = Muted("Pronto para transcrever", card)
        card.body.addWidget(self.progress_label)
        return card

    def _log_view(self) -> LogView:
        self.log = LogView("O andamento da transcrição aparecerá aqui.", self)
        self.log.setMinimumHeight(160)
        return self.log

    def _action_bar(self) -> QWidget:
        bar = QWidget(self)
        column = QVBoxLayout(bar)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        column.addWidget(Divider(bar))

        row = QHBoxLayout()
        row.setContentsMargins(0, 14, 0, 16)
        row.setSpacing(10)

        self.start_btn = PrimaryButton("Iniciar transcrição", "captions", bar)
        self.start_btn.setMinimumHeight(42)
        self.pause_btn = Button("Pausar", "pause", "secondary", bar)
        self.pause_btn.setMinimumHeight(42)
        self.cancel_btn = Button("Cancelar", "stop", "ghost", bar)
        self.cancel_btn.setMinimumHeight(42)
        self.open_btn = Button("Abrir pasta", "folder", "secondary", bar)
        self.open_btn.setMinimumHeight(42)

        self.start_btn.clicked.connect(self.start)
        self.pause_btn.clicked.connect(self.toggle_pause)
        self.cancel_btn.clicked.connect(self.cancel)
        self.open_btn.clicked.connect(self.open_output_folder)
        self.pause_btn.setEnabled(False)
        self.cancel_btn.setEnabled(False)

        row.addWidget(self.start_btn)
        row.addWidget(self.pause_btn)
        row.addWidget(self.cancel_btn)
        row.addStretch(1)
        row.addWidget(self.open_btn)
        column.addLayout(row)
        return bar

    @staticmethod
    def _combo(items, selected: str, parent) -> Select:
        combo = Select(parent)
        for label, value in items:
            combo.addItem(label, userData=value)
        for index in range(combo.count()):
            if combo.itemData(index) == selected:
                combo.setCurrentIndex(index)
                break
        combo.setMinimumWidth(230)
        return combo

    def _save(self, key: str, value) -> None:
        setattr(self.cfg, key, value)
        self.cfg.save()

    def set_toolchain(self, toolchain) -> None:
        self.toolchain = toolchain

    def _pick_media(self) -> None:
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(self, "Selecionar mídia", "", MEDIA_FILTER)
        if path:
            self.set_media(path)

    def set_media(self, path: str) -> None:
        """Ponto de entrada usado pela fila, pelo histórico e pelo arrastar-e-soltar."""
        self.media_edit.setText(path)
        self.output_edit.setText(self._suggested_output(path))

    def _suggested_output(self, media: str = "") -> str:
        """Caminho sugerido da legenda. Nunca chama with_suffix num caminho vazio."""
        extension = FORMATS[self.output_format.currentData()][1]
        source = (media or self.media_edit.text()).strip()
        if not source:
            return ""
        return str(Path(source).with_suffix(extension))

    def _pick_output(self) -> None:
        from PySide6.QtWidgets import QFileDialog
        fmt = self.output_format.currentData()
        label, extension = FORMATS[fmt]
        current = self.output_edit.text().strip() or self._suggested_output()
        path, _ = QFileDialog.getSaveFileName(self, "Salvar legenda", current,
                                              f"{label} (*{extension});;Todos os arquivos (*.*)")
        if path:
            self.output_edit.setText(str(Path(path).with_suffix(extension)))

    def _format_changed(self) -> None:
        fmt = self.output_format.currentData()
        self._save("transcription_format", fmt)
        if self.output_edit.text().strip():
            self.output_edit.setText(str(Path(self.output_edit.text()).with_suffix(FORMATS[fmt][1])))

    # ------------------------------------------------------ arrastar e soltar
    def dragEnterEvent(self, event):  # noqa: N802 - assinatura do Qt
        urls = event.mimeData().urls() if event.mimeData().hasUrls() else []
        if urls and Path(urls[0].toLocalFile()).is_file():
            event.acceptProposedAction()

    def dropEvent(self, event):  # noqa: N802 - assinatura do Qt
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path and Path(path).is_file():
                self.set_media(path)
                event.acceptProposedAction()
                return

    def start(self) -> None:
        if self.worker and self.worker.isRunning():
            return
        if not self.toolchain:
            self._warn("As dependências ainda estão sendo verificadas.")
            return
        media = Path(self.media_edit.text().strip())
        if not media.is_file():
            self._warn("Selecione um arquivo de áudio ou vídeo existente.")
            return
        fmt = self.output_format.currentData()
        output = Path(self.output_edit.text().strip()
                      or str(media.with_suffix(FORMATS[fmt][1]))).with_suffix(FORMATS[fmt][1])
        self.output_edit.setText(str(output))
        opts = TranscriptionOptions(media, output, self.language.currentData(), self.model.currentData(),
                                    fmt, self.aggressive.isChecked())
        self.log.clear()
        self.progress.setValue(0)
        self.progress_label.setText("Iniciando…")
        self.start_btn.setEnabled(False)
        self.pause_btn.setEnabled(True)
        self.cancel_btn.setEnabled(True)
        worker = TranscriptionWorker(opts, self.toolchain, self)
        self.worker = worker
        worker.status.connect(self._status)
        worker.progress.connect(self.progress.setValue)
        worker.finished_ok.connect(self._done)
        worker.cancelled.connect(self._cancelled)
        worker.failed.connect(self._failed)
        worker.finished.connect(self._clear_finished_worker)
        worker.finished.connect(worker.deleteLater)
        log_event("Transcrição solicitada pela interface: %s", media)
        worker.start()

    def _status(self, message: str) -> None:
        self.log.appendPlainText(message)
        self.progress_label.setText(message)
        if message.startswith("Modelo pronto:"):
            self.hardware.setText(message.removeprefix("Modelo pronto: "))

    def toggle_pause(self) -> None:
        if not self.worker:
            return
        self._paused = not self._paused
        self.worker.pause(self._paused)
        self.pause_btn.setText("Continuar" if self._paused else "Pausar")
        self._status("Processamento pausado." if self._paused else "Processamento retomado.")

    def cancel(self) -> None:
        if self.worker:
            self.worker.cancel()
            self.cancel_btn.setEnabled(False)
            self._status("Cancelamento solicitado; parando ao terminar o segmento atual…")

    def _done(self, path: str) -> None:
        self._finish_controls()
        self.transcription_finished.emit(path, self.media_edit.text().strip())
        Toast.success("Transcrição concluída", f"Legenda salva em {Path(path).name}",
                      parent=self.window(), duration=6000)

    def _clear_finished_worker(self) -> None:
        """Não retém uma referência Qt já destruída entre duas execuções."""
        worker = self.sender()
        if worker is self.worker:
            self.worker = None

    def _cancelled(self) -> None:
        self._finish_controls()
        self._status("Transcrição cancelada.")

    def _failed(self, error: str) -> None:
        self._finish_controls()
        self._status(f"Erro: {error}")
        Toast.error("Falha na transcrição", error, parent=self.window(), duration=9000)

    def _finish_controls(self) -> None:
        self.start_btn.setEnabled(True)
        self.pause_btn.setEnabled(False)
        self.pause_btn.setText("Pausar")
        self.cancel_btn.setEnabled(False)
        self._paused = False

    def shutdown(self) -> None:
        """Finaliza o worker antes de o Qt destruir a janela principal."""
        worker = self.worker
        if worker is None or not worker.isRunning():
            return
        self._status("Encerrando transcrição antes de fechar o aplicativo…")
        worker.cancel()
        if not worker.wait(5000):
            worker.force_stop()
            worker.wait(2000)

    def open_output_folder(self) -> None:
        path = Path(self.output_edit.text().strip() or self.media_edit.text().strip())
        folder = path.parent if path else Path.home()
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def _warn(self, message: str) -> None:
        Toast.warning("Atenção", message, parent=self.window(), duration=5000)
