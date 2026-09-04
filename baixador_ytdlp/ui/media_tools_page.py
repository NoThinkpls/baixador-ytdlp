"""Página de ferramentas locais: recorte, áudio, remux, compressão e legendas."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog, QGridLayout, QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (BodyLabel, CaptionLabel, CardWidget, ComboBox,
                            FluentIcon as FIF, InfoBar, InfoBarPosition, LineEdit,
                            PrimaryPushButton, ProgressBar, PushButton, SubtitleLabel,
                            TitleLabel)

from ..media_tools import MediaToolOptions, default_destination
from ..workers import MediaToolWorker

OPERATIONS = [
    ("Recortar trecho sem recompressão", "trim"),
    ("Extrair áudio MP3", "audio"),
    ("Remuxar para MKV sem recompressão", "remux"),
    ("Comprimir para MP4 H.264", "compress"),
    ("Criar versão vertical para Shorts (9:16)", "shorts"),
    ("Queimar legendas no vídeo", "burn"),
]
SUBTITLE_FILTER = "Legendas (*.srt *.vtt *.ass);;Todos os arquivos (*.*)"
MEDIA_FILTER = "Mídia (*.mp4 *.mkv *.webm *.mov *.avi *.m4v *.mp3 *.m4a *.wav *.flac);;Todos os arquivos (*.*)"


class MediaToolsPage(QWidget):
    """Executa uma única tarefa de edição local por vez, sempre fora da UI."""

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self.setObjectName("mediaToolsPage")
        self.cfg = cfg
        self.toolchain = None
        self.worker: MediaToolWorker | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 16, 28, 20)
        root.setSpacing(14)
        root.addWidget(TitleLabel("Ferramentas de mídia", self))
        intro = CaptionLabel(
            "As operações usam o FFmpeg instalado pelo aplicativo e sempre gravam em outro arquivo.",
            self,
        )
        intro.setWordWrap(True)
        root.addWidget(intro)

        source_card = CardWidget(self)
        source_layout = QHBoxLayout(source_card)
        source_layout.setContentsMargins(16, 12, 16, 12)
        self.source_edit = LineEdit(source_card)
        self.source_edit.setPlaceholderText("Arquivo de vídeo ou áudio de origem")
        source_button = PushButton(FIF.FOLDER, "Procurar", source_card)
        source_button.clicked.connect(self._choose_source)
        source_layout.addWidget(self.source_edit, 1)
        source_layout.addWidget(source_button)
        root.addWidget(source_card)

        options = CardWidget(self)
        grid = QGridLayout(options)
        grid.setContentsMargins(16, 14, 16, 14)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)

        grid.addWidget(BodyLabel("Operação", options), 0, 0)
        self.operation_combo = ComboBox(options)
        for label, value in OPERATIONS:
            self.operation_combo.addItem(label, userData=value)
        self.operation_combo.currentIndexChanged.connect(self._operation_changed)
        grid.addWidget(self.operation_combo, 0, 1, 1, 3)

        self.trim_label = BodyLabel("Trecho", options)
        grid.addWidget(self.trim_label, 1, 0)
        self.start_edit = LineEdit(options)
        self.start_edit.setPlaceholderText("início 00:01:30")
        self.end_edit = LineEdit(options)
        self.end_edit.setPlaceholderText("fim 00:04:00")
        grid.addWidget(self.start_edit, 1, 1)
        grid.addWidget(self.end_edit, 1, 2)

        self.subtitle_label = BodyLabel("Legenda", options)
        grid.addWidget(self.subtitle_label, 2, 0)
        self.subtitle_edit = LineEdit(options)
        self.subtitle_edit.setPlaceholderText("Arquivo .srt, .vtt ou .ass")
        self.subtitle_button = PushButton(FIF.FOLDER, "Escolher", options)
        self.subtitle_button.clicked.connect(self._choose_subtitles)
        grid.addWidget(self.subtitle_edit, 2, 1, 1, 2)
        grid.addWidget(self.subtitle_button, 2, 3)

        grid.addWidget(BodyLabel("Salvar como", options), 3, 0)
        self.destination_edit = LineEdit(options)
        self.destination_edit.setPlaceholderText("A saída será sugerida ao escolher o arquivo")
        destination_button = PushButton(FIF.SAVE, "Salvar em", options)
        destination_button.clicked.connect(self._choose_destination)
        grid.addWidget(self.destination_edit, 3, 1, 1, 2)
        grid.addWidget(destination_button, 3, 3)
        root.addWidget(options)

        self.progress = ProgressBar(self)
        self.progress.setRange(0, 0)
        self.progress.hide()
        root.addWidget(self.progress)

        bottom = QHBoxLayout()
        self.status = CaptionLabel("Escolha uma operação para começar.", self)
        self.status.setWordWrap(True)
        bottom.addWidget(self.status, 1)
        self.cancel_button = PushButton(FIF.CLOSE, "Cancelar", self)
        self.cancel_button.clicked.connect(self._cancel)
        self.cancel_button.hide()
        self.run_button = PrimaryPushButton(FIF.SYNC, "Processar", self)
        self.run_button.clicked.connect(self._run)
        bottom.addWidget(self.cancel_button)
        bottom.addWidget(self.run_button)
        root.addLayout(bottom)
        root.addStretch(1)
        self._operation_changed(0)

    def set_toolchain(self, toolchain) -> None:
        self.toolchain = toolchain

    def set_media(self, path: str) -> None:
        self.source_edit.setText(path)
        self._suggest_destination()

    def _operation(self) -> str:
        return str(self.operation_combo.currentData())

    def _operation_changed(self, _index: int) -> None:
        trim = self._operation() == "trim"
        burn = self._operation() == "burn"
        for widget in (self.trim_label, self.start_edit, self.end_edit):
            widget.setVisible(trim)
        for widget in (self.subtitle_label, self.subtitle_edit, self.subtitle_button):
            widget.setVisible(burn)
        self._suggest_destination()

    def _choose_source(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Selecionar mídia", "", MEDIA_FILTER)
        if path:
            self.source_edit.setText(path)
            self._suggest_destination()

    def _choose_subtitles(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Selecionar legenda", "", SUBTITLE_FILTER)
        if path:
            self.subtitle_edit.setText(path)

    def _suggest_destination(self) -> None:
        source = Path(self.source_edit.text().strip())
        if source.is_file():
            self.destination_edit.setText(str(default_destination(source, self._operation())))

    def _choose_destination(self) -> None:
        suggested = self.destination_edit.text().strip()
        path, _ = QFileDialog.getSaveFileName(
            self, "Salvar resultado", suggested,
            "Arquivo MP4 (*.mp4);;Arquivo MKV (*.mkv);;Arquivo MP3 (*.mp3);;Todos os arquivos (*.*)",
        )
        if path:
            self.destination_edit.setText(path)

    def _run(self) -> None:
        if self.worker and self.worker.isRunning():
            return
        if not self.toolchain:
            self._show_error("As dependências ainda não estão prontas.")
            return
        source = Path(self.source_edit.text().strip())
        destination_text = self.destination_edit.text().strip()
        if not destination_text:
            self._show_error("Escolha onde salvar o resultado.")
            return
        destination = Path(destination_text)
        options = MediaToolOptions(
            source=source,
            destination=destination,
            operation=self._operation(),
            start=self.start_edit.text().strip(),
            end=self.end_edit.text().strip(),
            subtitles=Path(self.subtitle_edit.text().strip()) if self.subtitle_edit.text().strip() else None,
        )
        worker = MediaToolWorker(options, self.toolchain, self)
        self.worker = worker
        worker.progress.connect(self.status.setText)
        worker.finished_ok.connect(self._done)
        worker.failed.connect(self._failed)
        worker.finished.connect(worker.deleteLater)
        worker.finished.connect(lambda w=worker: self._clear_worker(w))
        worker.start()
        self.progress.show()
        self.run_button.setEnabled(False)
        self.cancel_button.show()
        self.status.setText("Preparando a operação…")


    def _clear_worker(self, worker: MediaToolWorker) -> None:
        if self.worker is worker:
            self.worker = None

    def _cancel(self) -> None:
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.status.setText("Cancelando…")

    def _done(self, output: str) -> None:
        self.progress.hide()
        self.run_button.setEnabled(True)
        self.cancel_button.hide()
        self.status.setText(f"Concluído: {Path(output).name}")
        InfoBar.success(
            "Processamento concluído",
            f"Arquivo salvo em {output}",
            duration=7000,
            position=InfoBarPosition.TOP_RIGHT,
            parent=self.window(),
        )

    def _failed(self, message: str) -> None:
        self.progress.hide()
        self.run_button.setEnabled(True)
        self.cancel_button.hide()
        self.status.setText(message)
        self._show_error(message)

    def _show_error(self, message: str) -> None:
        InfoBar.error(
            "Não foi possível processar a mídia",
            message,
            duration=8000,
            position=InfoBarPosition.TOP_RIGHT,
            parent=self.window(),
        )

    def shutdown(self) -> None:
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.worker.wait(3000)
