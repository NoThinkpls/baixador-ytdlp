"""Página 'Baixar': cola o link, analisa e escolhe qualidade, formato e destino."""
from __future__ import annotations

import re
import shutil
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QFileDialog, QHBoxLayout,
                               QHeaderView, QInputDialog, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

from ..config import Settings
from ..downloader import DownloadOptions
from ..probe import MediaInfo, kill_running
from ..workers import ProbeWorker
from . import theme
from .components import (BusyBar, Button, Card, Divider, Headline, InsetGroup, Muted,
                         PageHeader, PrimaryButton, ScrollColumn, SectionLabel, Select,
                         SettingRow, Switch, TextField, Toast)

CONTAINERS = [("MP4 (recomendado)", "mp4"), ("MKV (nunca reconverte)", "mkv"),
              ("WebM", "webm"), ("Manter original", "original")]
AUDIO_FORMATS = [("MP3", "mp3"), ("M4A / AAC", "m4a"), ("Opus", "opus"),
                 ("FLAC (sem perdas)", "flac"), ("WAV", "wav")]
TIME_RE = re.compile(r"^(?:\d{1,2}:)?(?:[0-5]?\d:)?[0-5]?\d(?:\.\d+)?$")
URL_LIST_RE = re.compile(r'https?://[^\s<>"\']+')
MAX_BATCH_URLS = 500


class HomePage(QWidget):
    enqueue = Signal(object)  # DownloadOptions
    enqueue_many = Signal(list)  # list[DownloadOptions]

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
        root.setContentsMargins(28, 20, 28, 0)
        root.setSpacing(16)

        root.addWidget(PageHeader(
            "Baixar",
            "Cole o link de um vídeo ou de uma playlist e escolha como quer o arquivo.",
            self))

        page = ScrollColumn(self, spacing=14)
        root.addWidget(page, 1)

        page.add(self._link_card())

        self.busy = BusyBar(self)
        self.busy.hide()
        page.add(self.busy)

        self.info_card = self._info_card()
        self.info_card.hide()
        page.add(self.info_card)

        self.quality_label = SectionLabel("Qualidade", self)
        self.quality_label.hide()
        page.add(self.quality_label)
        page.add(self._quality_table())

        page.add(SectionLabel("Saída", self))
        page.add(self._output_group())

        page.add(SectionLabel("Destino", self))
        page.add(self._destination_group())

        page.add(SectionLabel("Perfis", self))
        page.add(self._profile_group())
        page.add_stretch()

        root.addWidget(self._action_bar())

    def _link_card(self) -> Card:
        """Bloco de entrada: é o primeiro gesto da tela, então ganha destaque."""
        card = Card(self, padding=(16, 16, 16, 16), spacing=10, horizontal=True)

        self.url_edit = TextField("Cole o link do vídeo ou da playlist", card)
        self.url_edit.setClearButtonEnabled(True)
        self.url_edit.setMinimumHeight(42)
        self.url_edit.setFont(theme.font(14, 400))
        self.url_edit.returnPressed.connect(self.analyze)

        self.paste_btn = Button("Colar", "paste", "secondary", card)
        self.paste_btn.setMinimumHeight(42)
        self.paste_btn.clicked.connect(self._paste)

        self.import_list_btn = Button("Importar lista", "document", "secondary", card)
        self.import_list_btn.setMinimumHeight(42)
        self.import_list_btn.setToolTip("Importar até 500 links de um arquivo de texto")
        self.import_list_btn.clicked.connect(self._import_url_list)

        self.analyze_btn = PrimaryButton("Analisar", "search", card)
        self.analyze_btn.setMinimumHeight(42)
        self.analyze_btn.clicked.connect(self.analyze)

        card.body.addWidget(self.url_edit, 1)
        card.body.addWidget(self.paste_btn)
        card.body.addWidget(self.import_list_btn)
        card.body.addWidget(self.analyze_btn)
        return card

    def _info_card(self) -> Card:
        card = Card(self, padding=(16, 14, 16, 14), spacing=3)
        self.media_title = Headline("—", card, wrap=True)
        self.media_meta = Muted("", card)
        card.body.addWidget(self.media_title)
        card.body.addWidget(self.media_meta)
        return card

    def _quality_table(self) -> QTableWidget:
        self.table = QTableWidget(self)
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(
            ["Qualidade", "FPS", "Vídeo", "Áudio", "Container", "Tamanho", "Observações"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setFrameShape(QTableWidget.Shape.NoFrame)
        self.table.setShowGrid(False)
        self.table.setWordWrap(False)
        self.table.setAlternatingRowColors(True)
        self.table.setFont(theme.body())
        self.table.verticalHeader().hide()
        # Altura de linha fixa: o Qt para de medir cada célula a cada repaint.
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.table.verticalHeader().setDefaultSectionSize(36)
        header = self.table.horizontalHeader()
        header.setFont(theme.font(11, 700, 0.4))
        header.setHighlightSections(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        self.table.setMinimumHeight(200)
        self.table.setMaximumHeight(340)
        self.table.hide()
        return self.table

    def _output_group(self) -> InsetGroup:
        group = InsetGroup(self)

        self.container_combo = Select(group)
        for label, value in CONTAINERS:
            self.container_combo.addItem(label, userData=value)
        self._select_data(self.container_combo, self.cfg.container)
        self.container_combo.setMinimumWidth(200)
        group.add_row(SettingRow(
            "Formato do arquivo",
            "Container do vídeo final. MKV nunca reconverte.",
            self.container_combo, group))

        self.audio_switch = Switch(group)
        self.audio_switch.checkedChanged.connect(self._toggle_audio)
        group.add_row(SettingRow(
            "Somente áudio",
            "Extrai a trilha e descarta o vídeo.",
            self.audio_switch, group))

        self.audio_combo = Select(group)
        for label, value in AUDIO_FORMATS:
            self.audio_combo.addItem(label, userData=value)
        self._select_data(self.audio_combo, self.cfg.audio_format)
        self.audio_combo.setEnabled(False)
        self.audio_combo.setMinimumWidth(200)
        group.add_row(SettingRow(
            "Formato do áudio",
            "Vale quando “Somente áudio” está ligado.",
            self.audio_combo, group))

        self.trim_check = Switch(group)
        self.trim_check.setToolTip(
            "Corta na origem: o yt-dlp baixa apenas o intervalo pedido.")
        self.trim_check.toggled.connect(self._toggle_trim)
        group.add_row(SettingRow(
            "Baixar só um trecho",
            "Corta na origem — o download inteiro nem chega a acontecer.",
            self.trim_check, group))

        self.start_edit = TextField("de 00:01:30", group)
        self.start_edit.setFixedWidth(140)
        self.start_edit.setEnabled(False)
        self.end_edit = TextField("até 00:04:00", group)
        self.end_edit.setFixedWidth(140)
        self.end_edit.setEnabled(False)
        times = QWidget(group)
        times_row = QHBoxLayout(times)
        times_row.setContentsMargins(0, 0, 0, 0)
        times_row.setSpacing(8)
        times_row.addWidget(self.start_edit)
        times_row.addWidget(self.end_edit)
        self.trim_row = SettingRow(
            "Intervalo", "Use mm:ss ou hh:mm:ss. Um dos dois já basta.", times, group)
        self.trim_row.hide()
        group.add_row(self.trim_row)
        return group

    def _destination_group(self) -> InsetGroup:
        group = InsetGroup(self)

        self.folder_check = Switch(group)
        self.folder_check.setChecked(bool(self.cfg.ask_output_dir))
        self.folder_check.toggled.connect(self._toggle_folder)
        group.add_row(SettingRow(
            "Escolher a pasta deste download",
            "Desligado, o arquivo vai direto para a pasta padrão das configurações.",
            self.folder_check, group))

        row = QWidget(group)
        column = QVBoxLayout(row)
        column.setContentsMargins(16, 12, 16, 14)
        column.setSpacing(8)
        column.addWidget(Headline("Pasta de saída", row))

        line = QHBoxLayout()
        line.setSpacing(10)
        self.folder_edit = TextField("Caminho da pasta de destino", row)
        self.folder_edit.setText(self.cfg.last_output_dir or self.cfg.download_dir)
        self.browse_btn = Button("Procurar", "folder", "secondary", row)
        self.browse_btn.clicked.connect(self._browse_folder)
        line.addWidget(self.folder_edit, 1)
        line.addWidget(self.browse_btn)
        column.addLayout(line)

        self.folder_hint = Muted("", row)
        column.addWidget(self.folder_hint)
        group.add_row(row)

        self._toggle_folder(self.folder_check.isChecked())
        return group

    def _profile_group(self) -> InsetGroup:
        group = InsetGroup(self)
        row = QWidget(group)
        column = QVBoxLayout(row)
        column.setContentsMargins(16, 12, 16, 14)
        column.setSpacing(8)
        column.addWidget(Headline("Perfil salvo", row))
        column.addWidget(Muted(
            "Guarda apenas formato e modo de áudio. Caminhos e cookies nunca entram "
            "num perfil.", row))

        line = QHBoxLayout()
        line.setSpacing(10)
        self.profile_combo = Select(row)
        self.profile_combo.currentIndexChanged.connect(self._apply_profile)
        self.save_profile_btn = Button("Salvar perfil", "save", "secondary", row)
        self.save_profile_btn.clicked.connect(self._save_profile)
        self.delete_profile_btn = Button("Excluir", "trash", "ghost", row)
        self.delete_profile_btn.clicked.connect(self._delete_profile)
        line.addWidget(self.profile_combo, 1)
        line.addWidget(self.save_profile_btn)
        line.addWidget(self.delete_profile_btn)
        column.addLayout(line)

        group.add_row(row)
        self._refresh_profiles()
        return group

    def _action_bar(self) -> QWidget:
        """Barra fixa no rodapé: a ação principal nunca sai do alcance da rolagem."""
        bar = QWidget(self)
        column = QVBoxLayout(bar)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        column.addWidget(Divider(bar))

        row = QHBoxLayout()
        row.setContentsMargins(0, 14, 0, 16)
        row.setSpacing(16)
        self.playlist_hint = Muted("", bar)
        row.addWidget(self.playlist_hint, 1)

        self.download_btn = PrimaryButton("Baixar", "download", bar)
        self.download_btn.setMinimumHeight(42)
        self.download_btn.setMinimumWidth(168)
        self.download_btn.clicked.connect(self._emit_job)
        self.download_btn.setEnabled(False)
        self.download_btn.setToolTip("Analise um link para liberar o download")
        row.addWidget(self.download_btn)
        column.addLayout(row)
        return bar

    @staticmethod
    def _select_data(combo: Select, value: str) -> None:
        for i in range(combo.count()):
            if combo.itemData(i) == value:
                combo.setCurrentIndex(i)
                return

    # -------------------------------------------------------------- ações
    def set_toolchain(self, toolchain) -> None:
        self.toolchain = toolchain

    def set_url(self, url: str) -> None:
        self.url_edit.setText(url)

    def refresh_default_folder(self) -> None:
        """Chamado quando a pasta padrão muda em Configurações."""
        if not self.folder_check.isChecked():
            self.folder_hint.setText(f"Usando a pasta padrão: {self.cfg.download_dir}")
            self.folder_edit.setText(self.cfg.last_output_dir or self.cfg.download_dir)

    def _import_url_list(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Importar lista de links",
            "",
            "Listas de links (*.txt *.csv *.url);;Todos os arquivos (*.*)",
        )
        if not path:
            return
        file_path = Path(path)
        try:
            if file_path.stat().st_size > 5 * 1024 * 1024:
                raise ValueError("A lista passa de 5 MB. Divida-a em arquivos menores.")
            text = file_path.read_text(encoding="utf-8", errors="replace")
        except (OSError, ValueError) as exc:
            self._warn(f"Não foi possível importar a lista: {exc}")
            return

        seen: set[str] = set()
        urls: list[str] = []
        for match in URL_LIST_RE.findall(text):
            url = match.rstrip(".,;:)]}>")
            if url not in seen:
                seen.add(url)
                urls.append(url)
            if len(urls) >= MAX_BATCH_URLS:
                break
        if not urls:
            self._warn("Nenhum link HTTP(S) foi encontrado no arquivo.")
            return

        output_dir = self._output_dir()
        if output_dir is None:
            return
        audio_only = self.audio_switch.isChecked()
        options = [
            DownloadOptions(
                url=url,
                output_dir=output_dir,
                selector="bv*+ba/b",
                container=self.container_combo.currentData(),
                audio_only=audio_only,
                audio_format=self.audio_combo.currentData(),
                # Para não descartar itens quando a lista contém playlists.
                playlist=True,
                title=url,
            )
            for url in urls
        ]
        self.enqueue_many.emit(options)
        suffix = " (limitado a 500)" if len(URL_LIST_RE.findall(text)) > MAX_BATCH_URLS else ""
        Toast.success(
            "Lista importada",
            f"{len(options)} link(s) enviados para a fila{suffix}.",
            parent=self.window(),
            duration=6000,
        )

    def _profile_values(self) -> dict[str, object]:
        return {
            "container": str(self.container_combo.currentData()),
            "audio_only": self.audio_switch.isChecked(),
            "audio_format": str(self.audio_combo.currentData()),
        }

    def _refresh_profiles(self, selected_name: str = "") -> None:
        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        self.profile_combo.addItem("Sem perfil salvo", userData="")
        for profile in self.cfg.download_profiles:
            name = str(profile.get("name") or "").strip()
            if name:
                self.profile_combo.addItem(name, userData=name)
        if selected_name:
            self._select_data(self.profile_combo, selected_name)
        self.profile_combo.blockSignals(False)
        self.delete_profile_btn.setEnabled(bool(selected_name))

    def _save_profile(self) -> None:
        name, accepted = QInputDialog.getText(
            self, "Salvar perfil", "Nome do perfil (ex.: MP3, Melhor qualidade, Shorts):"
        )
        name = name.strip()
        if not accepted or not name:
            return
        profile = {"name": name, **self._profile_values()}
        profiles = [
            item for item in self.cfg.download_profiles
            if str(item.get("name") or "").casefold() != name.casefold()
        ]
        profiles.append(profile)
        self.cfg.download_profiles = profiles
        self.cfg.save()
        self._refresh_profiles(name)
        Toast.success(
            "Perfil salvo",
            f"“{name}” pode ser aplicado antes do próximo download.",
            parent=self.window(),
            duration=4500,
        )

    def _delete_profile(self) -> None:
        name = str(self.profile_combo.currentData() or "")
        if not name:
            return
        self.cfg.download_profiles = [
            item for item in self.cfg.download_profiles
            if str(item.get("name") or "") != name
        ]
        self.cfg.save()
        self._refresh_profiles()
        Toast.info(
            "Perfil excluído",
            f"“{name}” foi removido desta máquina.",
            parent=self.window(),
            duration=4000,
        )

    def _apply_profile(self, _index: int) -> None:
        name = str(self.profile_combo.currentData() or "")
        self.delete_profile_btn.setEnabled(bool(name))
        if not name:
            return
        profile = next(
            (item for item in self.cfg.download_profiles if item.get("name") == name),
            None,
        )
        if not profile:
            return
        self._select_data(self.container_combo, str(profile.get("container") or "mp4"))
        self._select_data(self.audio_combo, str(profile.get("audio_format") or "mp3"))
        self.audio_switch.setChecked(bool(profile.get("audio_only")))

    def _has_space_for_download(
        self,
        output_dir: str,
        *,
        audio_only: bool,
        selected_row: int,
    ) -> bool:
        """Bloqueia início quando a estimativa conhecida não cabe com margem de segurança."""
        if not self.info:
            return True
        if audio_only:
            estimated = max((row.estimated_size for row in self.info.rows if row.audio_only), default=0)
        elif selected_row > 0 and selected_row - 1 < len(self.info.rows):
            estimated = self.info.rows[selected_row - 1].estimated_size
        else:
            estimated = max((row.estimated_size for row in self.info.rows if not row.audio_only), default=0)
        if not estimated:
            return True
        try:
            free = shutil.disk_usage(output_dir).free
        except OSError:
            return True
        required = int(estimated * 1.25) + 100 * 1024 * 1024
        if free >= required:
            return True
        self._warn(
            "Espaço livre insuficiente para a estimativa deste download "
            f"({estimated / 1024**2:.0f} MB + margem)."
        )
        return False

    def _paste(self) -> None:
        text = (QApplication.clipboard().text() or "").strip()
        if text:
            self.url_edit.setText(text)

    def paste_and_analyze(self) -> None:
        self._paste()
        if self.url_edit.text().strip():
            self.analyze()

    def _toggle_audio(self, checked: bool) -> None:
        self.audio_combo.setEnabled(checked)
        self.container_combo.setEnabled(not checked)
        self.table.setEnabled(not checked)

    def _toggle_trim(self, checked: bool) -> None:
        self.start_edit.setEnabled(checked)
        self.end_edit.setEnabled(checked)
        self.trim_row.setVisible(checked)

    def _toggle_folder(self, checked: bool) -> None:
        self.folder_edit.setEnabled(checked)
        self.browse_btn.setEnabled(checked)
        self.cfg.ask_output_dir = bool(checked)
        self.cfg.save()
        self.folder_hint.setText(
            "" if checked else f"Usando a pasta padrão: {self.cfg.download_dir}")

    def _browse_folder(self) -> None:
        current = self.folder_edit.text().strip() or self.cfg.download_dir
        path = QFileDialog.getExistingDirectory(self, "Pasta de destino deste download", current)
        if path:
            self.folder_edit.setText(path)

    def _output_dir(self) -> str | None:
        """Pasta efetiva. Devolve None quando o caminho digitado não serve."""
        if not self.folder_check.isChecked():
            return self.cfg.download_dir
        path = self.folder_edit.text().strip()
        if not path:
            self._warn("Escolha a pasta ou desligue a opção para usar a padrão.")
            return None
        target = Path(path)
        try:
            target.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self._warn(f"Não deu para usar essa pasta: {exc}")
            return None
        self.cfg.last_output_dir = str(target)
        self.cfg.save()
        return str(target)

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

    def shutdown(self) -> None:
        """Encerra a análise em andamento antes da janela fechar.

        Sem isto, fechar o app durante uma análise destrói uma QThread ainda em
        execução: o Qt chama qFatal e o processo morre com fast-fail (0xc0000409),
        sem gravar traceback nenhum.
        """
        if not (self.worker and self.worker.isRunning()):
            return
        kill_running()
        if not self.worker.wait(5000):
            self.worker.terminate()
            self.worker.wait(1000)

    def _reset_analyze_button(self) -> None:
        self.busy.hide()
        self.analyze_btn.setEnabled(True)
        self.analyze_btn.setText("Analisar")

    def _on_probe_error(self, message: str) -> None:
        self._reset_analyze_button()
        Toast.error("Não deu para analisar", message, parent=self.window(), duration=8000)

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
        # Um único repaint no fim, em vez de um por célula inserida.
        self.table.setUpdatesEnabled(False)
        self.table.clearContents()
        self.table.setRowCount(len(rows) + 1)

        auto = [f"Automático — {info.best_label}", "—", "melhor", "melhor", "—", "—",
                "Deixa o yt-dlp escolher a melhor combinação"]
        for col, text in enumerate(auto):
            self.table.setItem(0, col, QTableWidgetItem(text))

        for r, row in enumerate(rows, start=1):
            quality = row.quality + ("  (só áudio)" if row.audio_only else "")
            cells = [quality, row.fps, row.vcodec, row.acodec, row.ext, row.size, row.note]
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if col in (1, 5):
                    item.setTextAlignment(int(Qt.AlignmentFlag.AlignRight
                                              | Qt.AlignmentFlag.AlignVCenter))
                self.table.setItem(r, col, item)

        self.table.selectRow(0)
        self.table.setUpdatesEnabled(True)

    def _emit_job(self) -> None:
        if not self.info:
            return
        output_dir = self._output_dir()
        if output_dir is None:
            return

        start, end = "", ""
        if self.trim_check.isChecked():
            start, end = self.start_edit.text().strip(), self.end_edit.text().strip()
            for value in (start, end):
                if value and not TIME_RE.match(value):
                    self._warn(f"Horário inválido: “{value}”. Use mm:ss ou hh:mm:ss.")
                    return
            if not start and not end:
                self._warn("Preencha ao menos um dos horários do trecho.")
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

        if not self._has_space_for_download(
                output_dir, audio_only=audio_only, selected_row=row_index):
            return

        opts = DownloadOptions(
            url=self.url_edit.text().strip(),
            output_dir=output_dir,
            selector=selector,
            container=self.container_combo.currentData(),
            audio_only=audio_only,
            audio_format=self.audio_combo.currentData(),
            playlist=self.info.is_playlist,
            title=self.info.title,
            section_start=start,
            section_end=end,
        )
        self.enqueue.emit(opts)

    def _warn(self, message: str) -> None:
        Toast.warning("Atenção", message, parent=self.window(), duration=4500)
