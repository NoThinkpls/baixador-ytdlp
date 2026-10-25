"""Cortes verticais (1080x1920) com legenda palavra a palavra e título animado."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl, Qt, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QVBoxLayout, QWidget

from ..clips import ClipError, ClipOptions, is_url, make_range
from ..workers import ClipWorker
from .components import (Button, Divider, Headline, IconButton, InsetGroup, Muted, PageHeader,
                         PrimaryButton, ProgressBar, ScrollColumn, SectionLabel, Select,
                         SettingRow, Switch, TextField, Toast)
from .i18n import tr
from .media_tools_page import MEDIA_FILTER
from .transcription_page import LANGUAGES, MODELS

MAX_CLIPS = 20
PAUSES = [("0,4 s — ritmo acelerado", 0.4), ("0,6 s — recomendado", 0.6),
          ("0,8 s — mais natural", 0.8), ("1,2 s — só pausas longas", 1.2)]


class ClipRow(QWidget):
    """Uma linha da lista de cortes: início, fim, título e remover."""

    removed = Signal(object)
    changed = Signal()

    def __init__(self, number: int, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.number = Muted("", self)
        self.number.setFixedWidth(22)
        self.start = TextField("início 01:30", self)
        self.start.setFixedWidth(118)
        self.end = TextField("fim 02:15", self)
        self.end.setFixedWidth(118)
        self.title = TextField("Título animado (opcional)", self)
        self.remove = IconButton("trash", "Remover corte", self)
        self.remove.clicked.connect(lambda: self.removed.emit(self))
        for field in (self.start, self.end):
            field.textChanged.connect(self.changed)
        layout.addWidget(self.number)
        layout.addWidget(self.start)
        layout.addWidget(self.end)
        layout.addWidget(self.title, 1)
        layout.addWidget(self.remove)
        self.set_number(number)

    def set_number(self, number: int) -> None:
        self.number.setText(f"{number}.")

    def is_filled(self) -> bool:
        return bool(self.start.text().strip() and self.end.text().strip())


class ClipsPage(QWidget):
    """Gera um ou vários cortes por vez, sempre fora da thread da UI."""

    taskbar_progress = Signal(float)
    operation_finished = Signal(str)

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self.setObjectName("clipsPage")
        self.cfg = cfg
        self.toolchain = None
        self.worker: ClipWorker | None = None
        self.rows: list[ClipRow] = []
        self._outputs: list[str] = []
        self._build_ui()

    # ------------------------------------------------------------------ interface
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 20, 28, 0)
        root.setSpacing(0)
        page = ScrollColumn(self, spacing=14)
        root.addWidget(page, 1)
        page.add(PageHeader(
            "Cortes",
            "Gere vídeos verticais com legenda palavra a palavra, sem as pausas.",
            self))
        page.add(self._source_group())
        page.add(SectionLabel("Cortes", self))
        page.add(self._ranges_group())
        page.add(SectionLabel("Estilo", self))
        page.add(self._style_group())
        page.add(SectionLabel("Transcrição", self))
        page.add(self._transcription_group())
        page.add(self._destination_group())
        page.add_stretch()
        root.addWidget(self._action_bar())
        self._add_row()

    def _source_group(self) -> InsetGroup:
        group = InsetGroup(self)
        self.source_edit = TextField("Arquivo de vídeo ou link do YouTube", group)
        self.source_edit.textChanged.connect(self._source_changed)
        button = Button("Escolher arquivo", "folder", "secondary", group)
        button.clicked.connect(self._choose_source)
        group.add_row(self._path_row(
            group, "Vídeo de origem",
            "Use um arquivo do computador ou cole um link: só os trechos escolhidos são "
            "baixados.", self.source_edit, button))
        return group

    def _ranges_group(self) -> InsetGroup:
        group = InsetGroup(self)
        host = QWidget(group)
        column = QVBoxLayout(host)
        column.setContentsMargins(16, 12, 16, 14)
        column.setSpacing(8)
        column.addWidget(Muted(
            "Informe início e fim de cada corte em mm:ss ou hh:mm:ss. O título aparece "
            "animado nos primeiros segundos.", host))
        self.rows_layout = QVBoxLayout()
        self.rows_layout.setSpacing(8)
        column.addLayout(self.rows_layout)
        add_line = QHBoxLayout()
        self.add_button = Button("Adicionar corte", "plus", "secondary", host)
        self.add_button.clicked.connect(lambda: self._add_row(focus=True))
        add_line.addWidget(self.add_button)
        add_line.addStretch(1)
        column.addLayout(add_line)
        group.add_row(host)
        return group

    def _style_group(self) -> InsetGroup:
        group = InsetGroup(self)
        self.framing_combo = Select(group)
        self.framing_combo.addItem("Fundo desfocado — vídeo inteiro", userData="blur")
        self.framing_combo.addItem("Cortar no centro — tela cheia", userData="crop")
        group.add_row(SettingRow(
            "Enquadramento 9:16",
            "O desfoque mostra o quadro todo; o corte no centro preenche a tela, mas perde as "
            "laterais.", self.framing_combo, group))

        self.pauses_switch = Switch(group)
        self.pauses_switch.setChecked(True)
        self.pauses_switch.toggled.connect(self._pauses_toggled)
        group.add_row(SettingRow(
            "Remover pausas",
            "Corta os silêncios entre as falas usando o tempo de cada palavra.",
            self.pauses_switch, group))
        self.pause_combo = Select(group)
        for label, value in PAUSES:
            self.pause_combo.addItem(label, userData=value)
        self.pause_combo.setCurrentIndex(1)
        self.pause_row = group.add_row(SettingRow(
            "Pausa mínima", "Silêncios menores que isso ficam no vídeo.", self.pause_combo, group))

        self.words_combo = Select(group)
        self.words_combo.addItem("2 palavras", userData=2)
        self.words_combo.addItem("3 palavras", userData=3)
        self.words_combo.setCurrentIndex(1)
        group.add_row(SettingRow(
            "Palavras por legenda",
            "A palavra falada aparece em amarelo e um pouco maior.", self.words_combo, group))

        self.upper_switch = Switch(group)
        self.upper_switch.setChecked(True)
        group.add_row(SettingRow(
            "Legenda em maiúsculas", "Mais fácil de ler na tela do celular.",
            self.upper_switch, group))
        return group

    def _transcription_group(self) -> InsetGroup:
        group = InsetGroup(self)
        self.language_combo = Select(group)
        for label, value in LANGUAGES:
            self.language_combo.addItem(label, userData=value)
        self.language_combo.setCurrentIndex(max(0, self.language_combo.findData(
            getattr(self.cfg, "transcription_language", "pt"))))
        group.add_row(SettingRow("Idioma da fala", "", self.language_combo, group))
        self.model_combo = Select(group)
        for label, value in MODELS:
            self.model_combo.addItem(label, userData=value)
        self.model_combo.setCurrentIndex(max(0, self.model_combo.findData(
            getattr(self.cfg, "transcription_model", "medium"))))
        group.add_row(SettingRow(
            "Modelo Whisper",
            "O mesmo da aba Legendar. Usa a GPU NVIDIA quando disponível e a CPU nos demais "
            "casos.", self.model_combo, group))
        return group

    def _destination_group(self) -> InsetGroup:
        group = InsetGroup(self)
        self.output_edit = TextField("Pasta onde os cortes serão salvos", group)
        self.output_edit.textChanged.connect(self._update_run_enabled)
        button = Button("Escolher pasta", "folder", "secondary", group)
        button.clicked.connect(self._choose_output)
        group.add_row(self._path_row(
            group, "Salvar cortes em",
            "Cada corte vira um MP4 1080x1920 separado. O original nunca é alterado.",
            self.output_edit, button))
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

        self.progress_host = QWidget(bar)
        progress_row = QHBoxLayout(self.progress_host)
        progress_row.setContentsMargins(0, 0, 0, 0)
        progress_row.setSpacing(10)
        self.progress = ProgressBar(self.progress_host)
        self.progress_percent = Muted("0%", self.progress_host)
        self.progress_percent.setFixedWidth(42)
        self.progress_percent.setWordWrap(False)
        progress_row.addWidget(self.progress, 1)
        progress_row.addWidget(self.progress_percent)
        self.progress_host.hide()
        column.addWidget(self.progress_host)

        row = QHBoxLayout()
        row.setContentsMargins(0, 14, 0, 16)
        row.setSpacing(10)
        self.status = Muted("Escolha um vídeo e informe os cortes para começar.", bar)
        row.addWidget(self.status, 1)
        self.open_button = Button("Abrir pasta", "folder", "ghost", bar)
        self.open_button.setMinimumHeight(42)
        self.open_button.clicked.connect(self._open_output)
        self.open_button.hide()
        self.cancel_button = Button("Cancelar", "close", "ghost", bar)
        self.cancel_button.setMinimumHeight(42)
        self.cancel_button.clicked.connect(self._cancel)
        self.cancel_button.hide()
        self.run_button = PrimaryButton("Criar cortes", "sparkle", bar)
        self.run_button.setMinimumHeight(42)
        self.run_button.setMinimumWidth(172)
        self.run_button.clicked.connect(self._run)
        self.run_button.setEnabled(False)
        row.addWidget(self.open_button)
        row.addWidget(self.cancel_button)
        row.addWidget(self.run_button)
        column.addLayout(row)
        return bar

    # ------------------------------------------------------------------ lista de cortes
    def _add_row(self, focus: bool = False) -> None:
        if len(self.rows) >= MAX_CLIPS:
            Toast.info("Limite de cortes", f"Crie até {MAX_CLIPS} cortes por vez.",
                       parent=self.window())
            return
        row = ClipRow(len(self.rows) + 1, self)
        row.removed.connect(self._remove_row)
        row.changed.connect(self._update_run_enabled)
        self.rows.append(row)
        self.rows_layout.addWidget(row)
        self._refresh_rows()
        if focus:
            row.start.setFocus(Qt.FocusReason.OtherFocusReason)

    def _remove_row(self, row: ClipRow) -> None:
        if len(self.rows) == 1:
            for field in (row.start, row.end, row.title):
                field.clear()
            return
        self.rows.remove(row)
        self.rows_layout.removeWidget(row)
        row.deleteLater()
        self._refresh_rows()

    def _refresh_rows(self) -> None:
        for number, row in enumerate(self.rows, start=1):
            row.set_number(number)
        self.add_button.setEnabled(len(self.rows) < MAX_CLIPS)
        self._update_run_enabled()

    def _pauses_toggled(self, checked: bool) -> None:
        self.pause_combo.setEnabled(checked)

    # ------------------------------------------------------------------ origem e destino
    def set_toolchain(self, toolchain) -> None:
        self.toolchain = toolchain

    def set_media(self, path: str) -> None:
        self.source_edit.setText(path)

    def _source(self) -> str:
        return self.source_edit.text().strip().strip('"')

    def _source_changed(self, *_args) -> None:
        source = self._source()
        if not self.output_edit.text().strip():
            if is_url(source):
                self.output_edit.setText(str(getattr(self.cfg, "download_dir", "") or ""))
            elif source and Path(source).is_file():
                self.output_edit.setText(str(Path(source).parent))
        self._update_run_enabled()

    def _choose_source(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Selecionar vídeo", "", MEDIA_FILTER)
        if path:
            self.output_edit.clear()
            self.source_edit.setText(path)

    def _choose_output(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Salvar cortes em",
                                                self.output_edit.text().strip())
        if path:
            self.output_edit.setText(path)

    def _open_output(self) -> None:
        folder = Path(self._outputs[-1]).parent if self._outputs else Path(
            self.output_edit.text().strip())
        if folder.is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def _update_run_enabled(self, *_args) -> None:
        if not hasattr(self, "run_button"):
            return
        source = self._source()
        valid_source = is_url(source) or (bool(source) and Path(source).is_file())
        self.run_button.setEnabled(
            valid_source and bool(self.output_edit.text().strip())
            and any(row.is_filled() for row in self.rows)
            and not self.has_active_work())

    # ------------------------------------------------------------------ execução
    def _options(self) -> ClipOptions:
        ranges = []
        for number, row in enumerate(self.rows, start=1):
            if not (row.start.text().strip() or row.end.text().strip()):
                continue
            try:
                ranges.append(make_range(row.start.text(), row.end.text(), row.title.text()))
            except ClipError as exc:
                raise ClipError(f"{tr('Corte')} {number}: {tr(str(exc))}") from exc
        if not ranges:
            raise ClipError("Adicione pelo menos um corte com início e fim.")
        return ClipOptions(
            source=self._source(),
            ranges=tuple(ranges),
            output_dir=Path(self.output_edit.text().strip()),
            framing=str(self.framing_combo.currentData() or "blur"),
            remove_pauses=self.pauses_switch.isChecked(),
            min_pause=float(self.pause_combo.currentData() or 0.6),
            words_per_caption=int(self.words_combo.currentData() or 3),
            uppercase=self.upper_switch.isChecked(),
            language=str(self.language_combo.currentData() or "pt"),
            model_size=str(self.model_combo.currentData() or "medium"),
        )

    def _run(self) -> None:
        if self.has_active_work():
            return
        if not self.toolchain:
            self._show_error("As dependências ainda não estão prontas.")
            return
        try:
            options = self._options()
        except ClipError as exc:
            self._show_error(str(exc))
            return
        self._outputs = []
        worker = ClipWorker(options, self.toolchain, self.cfg, self)
        self.worker = worker
        worker.progress.connect(self.status.setText)
        worker.progress_value.connect(self._set_progress)
        worker.clip_done.connect(self._clip_done)
        worker.finished_ok.connect(self._done)
        worker.failed.connect(self._failed)
        worker.finished.connect(worker.deleteLater)
        worker.finished.connect(lambda w=worker: self._clear_worker(w))
        worker.start()
        self._set_progress(0)
        self.progress_host.show()
        self.open_button.hide()
        self.run_button.setEnabled(False)
        self.cancel_button.show()
        count = len(options.ranges)
        self.status.setText(tr("Preparando 1 corte…") if count == 1
                            else f"{tr('Preparando')} {count} {tr('cortes')}…")

    def _clear_worker(self, worker: ClipWorker) -> None:
        if self.worker is worker:
            self.worker = None
            self._update_run_enabled()

    def _cancel(self) -> None:
        if self.has_active_work():
            assert self.worker is not None
            self.worker.cancel()
            self.status.setText(tr("Cancelando…"))

    def has_active_work(self) -> bool:
        return bool(self.worker and self.worker.isRunning())

    def cancel_current(self) -> None:
        self._cancel()

    def _clip_done(self, path: str) -> None:
        self._outputs.append(path)
        self.open_button.show()

    def _finish_ui(self) -> None:
        self.progress_host.hide()
        self.taskbar_progress.emit(-1.0)
        self.cancel_button.hide()
        self.open_button.setVisible(bool(self._outputs))
        self._update_run_enabled()

    def _done(self, outputs: list) -> None:
        self._set_progress(100)
        self._finish_ui()
        count = len(outputs)
        folder = str(Path(outputs[-1]).parent) if outputs else ""
        self.status.setText(f"{tr('Cortes prontos')}: {count} · {folder}")
        if outputs:
            self.operation_finished.emit(outputs[-1])
        Toast.success("Cortes concluídos",
                      f"{count} {tr('corte(s) salvos em')} {folder}",
                      parent=self.window(), duration=7000)

    def _failed(self, message: str) -> None:
        self._finish_ui()
        self.status.setText(message)
        self._show_error(message)

    def _set_progress(self, value: int) -> None:
        percent = max(0, min(100, int(value)))
        self.progress.setValue(percent)
        self.progress_percent.setText(f"{percent}%")
        self.taskbar_progress.emit(float(percent))

    def _show_error(self, message: str) -> None:
        Toast.error("Não foi possível criar os cortes", message,
                    parent=self.window(), duration=8000)

    def shutdown(self) -> None:
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            if not self.worker.wait(5000):
                self.worker.force_stop()
                self.worker.wait(3000)
