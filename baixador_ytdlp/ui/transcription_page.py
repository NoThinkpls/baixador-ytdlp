"""Aba Fluent para a transcrição local de áudio e vídeo."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QFileDialog, QFormLayout, QGridLayout, QHBoxLayout,
                               QPlainTextEdit, QProgressBar, QVBoxLayout, QWidget)
from qfluentwidgets import (BodyLabel, CaptionLabel, CardWidget, ComboBox,
                            FluentIcon as FIF, InfoBar, InfoBarPosition, LineEdit,
                            PrimaryPushButton, PushButton, StrongBodyLabel, SwitchButton,
                            TitleLabel)

from ..config import Settings
from ..transcription import FORMATS, TranscriptionOptions
from ..workers import TranscriptionWorker

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
        root.setContentsMargins(28, 16, 28, 20)
        root.setSpacing(14)

        root.addWidget(TitleLabel("Legendar e transcrever", self))
        description = CaptionLabel(
            "Transcrição local com faster-whisper. O modelo usa CUDA/float16 quando disponível "
            "e CPU/int8 de forma automática quando a GPU não puder ser usada.", self)
        description.setWordWrap(True)
        root.addWidget(description)

        file_card = CardWidget(self)
        form = QFormLayout(file_card)
        form.setContentsMargins(16, 14, 16, 14)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(12)

        self.media_edit = LineEdit(file_card)
        self.media_edit.setPlaceholderText("Selecione ou arraste um vídeo ou áudio para cá")
        self.media_edit.setClearButtonEnabled(True)
        pick_media = PushButton(FIF.MEDIA, "Selecionar", file_card)
        pick_media.clicked.connect(self._pick_media)
        media_row = QHBoxLayout()
        media_row.addWidget(self.media_edit, 1)
        media_row.addWidget(pick_media)
        form.addRow("Arquivo de mídia", media_row)

        self.output_edit = LineEdit(file_card)
        self.output_edit.setPlaceholderText("A legenda será criada ao lado da mídia")
        self.output_edit.setClearButtonEnabled(True)
        pick_output = PushButton(FIF.SAVE_AS, "Salvar como", file_card)
        pick_output.clicked.connect(self._pick_output)
        output_row = QHBoxLayout()
        output_row.addWidget(self.output_edit, 1)
        output_row.addWidget(pick_output)
        form.addRow("Arquivo de saída", output_row)
        root.addWidget(file_card)

        options = CardWidget(self)
        grid = QGridLayout(options)
        grid.setContentsMargins(16, 14, 16, 14)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(10)

        self.language = self._combo(LANGUAGES, self.cfg.transcription_language, options)
        self.language.currentIndexChanged.connect(
            lambda: self._save("transcription_language", self.language.currentData()))
        self.model = self._combo(MODELS, self.cfg.transcription_model, options)
        self.model.currentIndexChanged.connect(
            lambda: self._save("transcription_model", self.model.currentData()))
        format_items = [(label, key) for key, (label, _ext) in FORMATS.items()]
        self.output_format = self._combo(format_items, self.cfg.transcription_format, options)
        self.output_format.currentIndexChanged.connect(self._format_changed)

        grid.addWidget(BodyLabel("Idioma", options), 0, 0)
        grid.addWidget(self.language, 0, 1)
        grid.addWidget(BodyLabel("Modelo Whisper", options), 0, 2)
        grid.addWidget(self.model, 0, 3)
        grid.addWidget(BodyLabel("Formato", options), 1, 0)
        grid.addWidget(self.output_format, 1, 1)

        self.aggressive = SwitchButton(options)
        self.aggressive.setOnText("Ligado")
        self.aggressive.setOffText("Desligado")
        self.aggressive.setChecked(self.cfg.transcription_aggressive_filter)
        self.aggressive.checkedChanged.connect(
            lambda enabled: self._save("transcription_aggressive_filter", bool(enabled)))
        grid.addWidget(BodyLabel("Filtro anti-alucinação agressivo", options), 1, 2)
        grid.addWidget(self.aggressive, 1, 3)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)
        root.addWidget(options)

        status_card = CardWidget(self)
        status = QVBoxLayout(status_card)
        status.setContentsMargins(16, 12, 16, 12)
        self.hardware = StrongBodyLabel("Hardware será detectado ao iniciar", status_card)
        self.progress = QProgressBar(status_card)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(True)
        self.progress_label = CaptionLabel("Pronto para transcrever", status_card)
        status.addWidget(self.hardware)
        status.addWidget(self.progress)
        status.addWidget(self.progress_label)
        root.addWidget(status_card)

        controls = QHBoxLayout()
        self.start_btn = PrimaryPushButton(FIF.MESSAGE, "Iniciar transcrição", self)
        self.pause_btn = PushButton(FIF.PAUSE, "Pausar", self)
        self.cancel_btn = PushButton(FIF.CANCEL, "Cancelar", self)
        self.open_btn = PushButton(FIF.FOLDER, "Abrir pasta", self)
        self.start_btn.clicked.connect(self.start)
        self.pause_btn.clicked.connect(self.toggle_pause)
        self.cancel_btn.clicked.connect(self.cancel)
        self.open_btn.clicked.connect(self.open_output_folder)
        self.pause_btn.setEnabled(False)
        self.cancel_btn.setEnabled(False)
        controls.addWidget(self.start_btn)
        controls.addWidget(self.pause_btn)
        controls.addWidget(self.cancel_btn)
        controls.addStretch(1)
        controls.addWidget(self.open_btn)
        root.addLayout(controls)

        self.log = QPlainTextEdit(self)
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(500)
        self.log.setPlaceholderText("O andamento da transcrição aparecerá aqui.")
        self.log.setMinimumHeight(150)
        root.addWidget(self.log, 1)

    @staticmethod
    def _combo(items, selected: str, parent) -> ComboBox:
        combo = ComboBox(parent)
        for label, value in items:
            combo.addItem(label, userData=value)
        for index in range(combo.count()):
            if combo.itemData(index) == selected:
                combo.setCurrentIndex(index)
                break
        return combo

    def _save(self, key: str, value) -> None:
        setattr(self.cfg, key, value)
        self.cfg.save()

    def set_toolchain(self, toolchain) -> None:
        self.toolchain = toolchain

    def _pick_media(self) -> None:
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
        self.worker = TranscriptionWorker(opts, self.toolchain, self)
        self.worker.status.connect(self._status)
        self.worker.progress.connect(self.progress.setValue)
        self.worker.finished_ok.connect(self._done)
        self.worker.cancelled.connect(self._cancelled)
        self.worker.failed.connect(self._failed)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker.start()

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
        InfoBar.success("Transcrição concluída", f"Legenda salva em {Path(path).name}", duration=6000,
                        position=InfoBarPosition.TOP_RIGHT, parent=self.window())

    def _cancelled(self) -> None:
        self._finish_controls()
        self._status("Transcrição cancelada.")

    def _failed(self, error: str) -> None:
        self._finish_controls()
        self._status(f"Erro: {error}")
        InfoBar.error("Falha na transcrição", error, duration=9000,
                      position=InfoBarPosition.TOP, parent=self.window())

    def _finish_controls(self) -> None:
        self.start_btn.setEnabled(True)
        self.pause_btn.setEnabled(False)
        self.pause_btn.setText("Pausar")
        self.cancel_btn.setEnabled(False)
        self._paused = False

    def open_output_folder(self) -> None:
        path = Path(self.output_edit.text().strip() or self.media_edit.text().strip())
        folder = path.parent if path else Path.home()
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def _warn(self, message: str) -> None:
        InfoBar.warning("Atenção", message, duration=5000,
                        position=InfoBarPosition.TOP, parent=self.window())
