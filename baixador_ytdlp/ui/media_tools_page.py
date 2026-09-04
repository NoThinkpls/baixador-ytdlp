"""Página de ferramentas locais: recorte, áudio, remux, compressão e legendas."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QVBoxLayout, QWidget

from ..media_tools import MediaToolOptions, default_destination
from ..workers import MediaToolWorker
from .components import (BusyBar, Button, Divider, Headline, InsetGroup, Muted, PageHeader,
                         PrimaryButton, ScrollColumn, SectionLabel, Select, SettingRow,
                         TextField, Toast)

OPERATIONS = [
    ("Recortar trecho sem recompressão", "trim"),
    ("Extrair áudio MP3", "audio"),
    ("Remuxar para MKV sem recompressão", "remux"),
    ("Comprimir para MP4 H.264", "compress"),
    ("Criar versão vertical para Shorts (9:16)", "shorts"),
    ("Queimar legendas no vídeo", "burn"),
]
SUBTITLE_FILTER = "Legendas (*.srt *.vtt *.ass);;Todos os arquivos (*.*)"
MEDIA_FILTER = ("Mídia (*.mp4 *.mkv *.webm *.mov *.avi *.m4v *.mp3 *.m4a *.wav *.flac);;"
                "Todos os arquivos (*.*)")


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
        root.setContentsMargins(28, 20, 28, 0)
        root.setSpacing(16)

        root.addWidget(PageHeader(
            "Ferramentas",
            "Edições rápidas com o FFmpeg do aplicativo. O original nunca é sobrescrito.",
            self))

        page = ScrollColumn(self, spacing=14)
        root.addWidget(page, 1)

        page.add(SectionLabel("Origem", self))
        page.add(self._source_group())

        page.add(SectionLabel("Operação", self))
        page.add(self._operation_group())

        page.add(SectionLabel("Saída", self))
        page.add(self._destination_group())
        page.add_stretch()

        root.addWidget(self._action_bar())
        self._operation_changed(0)

    def _source_group(self) -> InsetGroup:
        group = InsetGroup(self)
        self.source_edit = TextField("Arquivo de vídeo ou áudio de origem", group)
        source_button = Button("Procurar", "folder", "secondary", group)
        source_button.clicked.connect(self._choose_source)
        group.add_row(self._path_row(
            group, "Arquivo de origem",
            "O resultado é sempre gravado em outro arquivo.",
            self.source_edit, source_button))
        return group

    def _operation_group(self) -> InsetGroup:
        group = InsetGroup(self)

        self.operation_combo = Select(group)
        for label, value in OPERATIONS:
            self.operation_combo.addItem(label, userData=value)
        self.operation_combo.currentIndexChanged.connect(self._operation_changed)
        self.operation_combo.setMinimumWidth(300)
        group.add_row(SettingRow("O que fazer", "", self.operation_combo, group))

        self.start_edit = TextField("início 00:01:30", group)
        self.start_edit.setFixedWidth(150)
        self.end_edit = TextField("fim 00:04:00", group)
        self.end_edit.setFixedWidth(150)
        times = QWidget(group)
        times_row = QHBoxLayout(times)
        times_row.setContentsMargins(0, 0, 0, 0)
        times_row.setSpacing(8)
        times_row.addWidget(self.start_edit)
        times_row.addWidget(self.end_edit)
        self.trim_row = SettingRow("Trecho", "Corte sem recompressão, então o corte cai "
                                             "no quadro-chave mais próximo.", times, group)
        group.add_row(self.trim_row)

        self.subtitle_edit = TextField("Arquivo .srt, .vtt ou .ass", group)
        self.subtitle_button = Button("Escolher", "document", "secondary", group)
        self.subtitle_button.clicked.connect(self._choose_subtitles)
        self.subtitle_row = self._path_row(
            group, "Arquivo de legenda",
            "A legenda é gravada dentro da imagem do vídeo.",
            self.subtitle_edit, self.subtitle_button)
        group.add_row(self.subtitle_row)
        return group

    def _destination_group(self) -> InsetGroup:
        group = InsetGroup(self)
        self.destination_edit = TextField(
            "A saída será sugerida ao escolher o arquivo", group)
        destination_button = Button("Salvar em", "save", "secondary", group)
        destination_button.clicked.connect(self._choose_destination)
        group.add_row(self._path_row(
            group, "Salvar como", "", self.destination_edit, destination_button))
        return group

    @staticmethod
    def _path_row(parent, title: str, subtitle: str, field: TextField,
                  button: Button) -> QWidget:
        row = QWidget(parent)
        column = QVBoxLayout(row)
        column.setContentsMargins(16, 12, 16, 14)
        column.setSpacing(8)
        column.addWidget(Headline(title, row))
        if subtitle:
            column.addWidget(Muted(subtitle, row))
        line = QHBoxLayout()
        line.setSpacing(10)
        line.addWidget(field, 1)
        line.addWidget(button)
        column.addLayout(line)
        return row

    def _action_bar(self) -> QWidget:
        bar = QWidget(self)
        column = QVBoxLayout(bar)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        column.addWidget(Divider(bar))

        self.progress = BusyBar(bar)
        self.progress.hide()
        column.addWidget(self.progress)

        row = QHBoxLayout()
        row.setContentsMargins(0, 14, 0, 16)
        row.setSpacing(10)
        self.status = Muted("Escolha uma operação para começar.", bar)
        row.addWidget(self.status, 1)

        self.cancel_button = Button("Cancelar", "close", "ghost", bar)
        self.cancel_button.setMinimumHeight(42)
        self.cancel_button.clicked.connect(self._cancel)
        self.cancel_button.hide()
        self.run_button = PrimaryButton("Processar", "sparkle", bar)
        self.run_button.setMinimumHeight(42)
        self.run_button.setMinimumWidth(150)
        self.run_button.clicked.connect(self._run)
        row.addWidget(self.cancel_button)
        row.addWidget(self.run_button)
        column.addLayout(row)
        return bar

    def set_toolchain(self, toolchain) -> None:
        self.toolchain = toolchain

    def set_media(self, path: str) -> None:
        self.source_edit.setText(path)
        self._suggest_destination()

    def _operation(self) -> str:
        return str(self.operation_combo.currentData())

    def _operation_changed(self, _index: int) -> None:
        self.trim_row.setVisible(self._operation() == "trim")
        self.subtitle_row.setVisible(self._operation() == "burn")
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
        Toast.success("Processamento concluído", f"Arquivo salvo em {output}",
                      parent=self.window(), duration=7000)

    def _failed(self, message: str) -> None:
        self.progress.hide()
        self.run_button.setEnabled(True)
        self.cancel_button.hide()
        self.status.setText(message)
        self._show_error(message)

    def _show_error(self, message: str) -> None:
        Toast.error("Não foi possível processar a mídia", message,
                    parent=self.window(), duration=8000)

    def shutdown(self) -> None:
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.worker.wait(3000)
