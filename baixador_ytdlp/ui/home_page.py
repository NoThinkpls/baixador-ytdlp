"""Página 'Baixar': cola o link, analisa e escolhe qualidade e formato."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QAbstractItemView, QGridLayout, QHBoxLayout, QHeaderView,
                               QTableWidgetItem, QVBoxLayout, QWidget)
from qfluentwidgets import (BodyLabel, CaptionLabel, CardWidget, ComboBox, FluentIcon as FIF,
                            IndeterminateProgressBar, InfoBar, InfoBarPosition, LineEdit,
                            PrimaryPushButton, PushButton, StrongBodyLabel, SubtitleLabel,
                            SwitchButton, TableWidget, TitleLabel, ToolTipFilter)

from ..config import Settings
from ..downloader import DownloadOptions
from ..probe import MediaInfo
from ..workers import ProbeWorker

CONTAINERS = [("MP4 (recomendado)", "mp4"), ("MKV (nunca reconverte)", "mkv"),
              ("WebM", "webm"), ("Manter original", "original")]
AUDIO_FORMATS = [("MP3", "mp3"), ("M4A / AAC", "m4a"), ("Opus", "opus"),
                 ("FLAC (sem perdas)", "flac"), ("WAV", "wav")]


class HomePage(QWidget):
    enqueue = Signal(object)  # DownloadOptions

    def __init__(self, cfg: Settings, parent=None):
        super().__init__(parent)
        self.setObjectName("homePage")
        self.cfg = cfg
        self.toolchain = None
        self.info: MediaInfo | None = None
        self.worker: ProbeWorker | None = None
        self._build_ui()

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 16, 28, 20)
        root.setSpacing(14)

        root.addWidget(TitleLabel("Baixar vídeo", self))

        # --- linha do link
        url_card = CardWidget(self)
        url_row = QHBoxLayout(url_card)
        url_row.setContentsMargins(16, 14, 16, 14)
        url_row.setSpacing(10)

        self.url_edit = LineEdit(url_card)
        self.url_edit.setPlaceholderText("Cole o link do vídeo ou da playlist")
        self.url_edit.setClearButtonEnabled(True)
        self.url_edit.returnPressed.connect(self.analyze)

        self.paste_btn = PushButton(FIF.PASTE, "Colar", url_card)
        self.paste_btn.clicked.connect(self._paste)
        self.analyze_btn = PrimaryPushButton(FIF.SEARCH, "Analisar", url_card)
        self.analyze_btn.clicked.connect(self.analyze)

        url_row.addWidget(self.url_edit, 1)
        url_row.addWidget(self.paste_btn)
        url_row.addWidget(self.analyze_btn)
        root.addWidget(url_card)

        self.busy = IndeterminateProgressBar(self)
        self.busy.hide()
        root.addWidget(self.busy)

        # --- cartão de informações da mídia
        self.info_card = CardWidget(self)
        info_layout = QVBoxLayout(self.info_card)
        info_layout.setContentsMargins(16, 12, 16, 12)
        info_layout.setSpacing(2)
        self.media_title = StrongBodyLabel("—", self.info_card)
        self.media_title.setWordWrap(True)
        self.media_meta = CaptionLabel("", self.info_card)
        info_layout.addWidget(self.media_title)
        info_layout.addWidget(self.media_meta)
        self.info_card.hide()
        root.addWidget(self.info_card)

        # --- tabela de qualidades
        self.quality_label = SubtitleLabel("Qualidade", self)
        self.quality_label.hide()
        root.addWidget(self.quality_label)

        self.table = TableWidget(self)
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(
            ["Qualidade", "FPS", "Vídeo", "Áudio", "Container", "Tamanho", "Observações"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().hide()
        self.table.setBorderVisible(True)
        self.table.setBorderRadius(8)
        self.table.setWordWrap(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        self.table.hide()
        root.addWidget(self.table, 1)

        # --- opções de saída
        self.options_card = CardWidget(self)
        grid = QGridLayout(self.options_card)
        grid.setContentsMargins(16, 14, 16, 14)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(10)

        grid.addWidget(BodyLabel("Formato do arquivo", self.options_card), 0, 0)
        self.container_combo = ComboBox(self.options_card)
        for label, value in CONTAINERS:
            self.container_combo.addItem(label, userData=value)
        self._select_data(self.container_combo, self.cfg.container)
        grid.addWidget(self.container_combo, 0, 1)

        grid.addWidget(BodyLabel("Somente áudio", self.options_card), 0, 2)
        self.audio_switch = SwitchButton(self.options_card)
        self.audio_switch.setOnText("Sim")
        self.audio_switch.setOffText("Não")
        self.audio_switch.checkedChanged.connect(self._toggle_audio)
        grid.addWidget(self.audio_switch, 0, 3)

        grid.addWidget(BodyLabel("Formato do áudio", self.options_card), 0, 4)
        self.audio_combo = ComboBox(self.options_card)
        for label, value in AUDIO_FORMATS:
            self.audio_combo.addItem(label, userData=value)
        self._select_data(self.audio_combo, self.cfg.audio_format)
        self.audio_combo.setEnabled(False)
        grid.addWidget(self.audio_combo, 0, 5)

        self.playlist_hint = CaptionLabel("", self.options_card)
        grid.addWidget(self.playlist_hint, 1, 0, 1, 4)

        self.download_btn = PrimaryPushButton(FIF.DOWNLOAD, "Baixar", self.options_card)
        self.download_btn.clicked.connect(self._emit_job)
        self.download_btn.setEnabled(False)
        self.download_btn.installEventFilter(ToolTipFilter(self.download_btn))
        self.download_btn.setToolTip("Analise um link para liberar o download")
        grid.addWidget(self.download_btn, 1, 5)

        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(5, 1)
        root.addWidget(self.options_card)

    @staticmethod
    def _select_data(combo: ComboBox, value: str) -> None:
        for i in range(combo.count()):
            if combo.itemData(i) == value:
                combo.setCurrentIndex(i)
                return

    # -------------------------------------------------------------- ações
    def set_toolchain(self, toolchain) -> None:
        self.toolchain = toolchain

    def set_url(self, url: str) -> None:
        self.url_edit.setText(url)

    def _paste(self) -> None:
        from PySide6.QtWidgets import QApplication
        text = (QApplication.clipboard().text() or "").strip()
        if text:
            self.url_edit.setText(text)

    def _toggle_audio(self, checked: bool) -> None:
        self.audio_combo.setEnabled(checked)
        self.container_combo.setEnabled(not checked)
        self.table.setEnabled(not checked)

    def analyze(self) -> None:
        url = self.url_edit.text().strip()
        if not url:
            self._warn("Cole um link primeiro.")
            return
        if not self.toolchain:
            self._warn("As dependências ainda não terminaram de carregar.")
            return
        if self.worker and self.worker.isRunning():
            return

        self.busy.show()
        self.analyze_btn.setEnabled(False)
        self.analyze_btn.setText("Analisando…")
        self.worker = ProbeWorker(url, self.toolchain, self.cfg, self)
        self.worker.finished_ok.connect(self._on_info)
        self.worker.failed.connect(self._on_probe_error)
        self.worker.start()

    def _reset_analyze_button(self) -> None:
        self.busy.hide()
        self.analyze_btn.setEnabled(True)
        self.analyze_btn.setText("Analisar")

    def _on_probe_error(self, message: str) -> None:
        self._reset_analyze_button()
        InfoBar.error("Não deu para analisar", message, duration=8000,
                      position=InfoBarPosition.TOP, parent=self.window())

    def _on_info(self, info: MediaInfo) -> None:
        self._reset_analyze_button()
        self.info = info

        self.media_title.setText(info.title)
        meta = [p for p in (info.uploader, f"duração {info.duration}") if p]
        if info.is_playlist:
            meta.append(f"playlist com {info.playlist_count} itens")
        self.media_meta.setText(" · ".join(meta))
        self.info_card.show()

        self.playlist_hint.setText(
            f"Playlist detectada: os {info.playlist_count} itens vão para uma subpasta."
            if info.is_playlist else "")

        self._fill_table(info)
        self.quality_label.show()
        self.table.show()
        self.download_btn.setEnabled(True)
        self.download_btn.setToolTip("")

    def _fill_table(self, info: MediaInfo) -> None:
        rows = info.rows
        self.table.setRowCount(len(rows) + 1)

        auto = [f"Automático — {info.best_label}", "—", "melhor", "melhor", "—", "—",
                "Deixa o yt-dlp escolher a melhor combinação"]
        for col, text in enumerate(auto):
            item = QTableWidgetItem(text)
            self.table.setItem(0, col, item)

        for r, row in enumerate(rows, start=1):
            quality = row.quality + ("  (só áudio)" if row.audio_only else "")
            cells = [quality, row.fps, row.vcodec, row.acodec, row.ext, row.size, row.note]
            for col, text in enumerate(cells):
                self.table.setItem(r, col, QTableWidgetItem(text))

        self.table.selectRow(0)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)

    def _emit_job(self) -> None:
        if not self.info:
            return
        audio_only = self.audio_switch.isChecked()
        selector = "bv*+ba/b"
        row_index = self.table.currentRow()
        if not audio_only and row_index > 0:
            row = self.info.rows[row_index - 1]
            if row.audio_only:
                audio_only = True
            else:
                selector = row.selector

        opts = DownloadOptions(
            url=self.url_edit.text().strip(),
            output_dir=self.cfg.download_dir,
            selector=selector,
            container=self.container_combo.currentData(),
            audio_only=audio_only,
            audio_format=self.audio_combo.currentData(),
            playlist=self.info.is_playlist,
            title=self.info.title,
        )
        self.enqueue.emit(opts)

    def _warn(self, message: str) -> None:
        InfoBar.warning("Atenção", message, duration=4000,
                        position=InfoBarPosition.TOP, parent=self.window())
