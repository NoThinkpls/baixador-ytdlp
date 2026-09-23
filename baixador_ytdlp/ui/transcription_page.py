"""Página 'Legendar': transcrição local de áudio e vídeo com faster-whisper."""
from __future__ import annotations

from collections import deque
from pathlib import Path

from PySide6.QtCore import QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from ..config import Settings
from ..diagnostics import log_event
from ..media_tools import MediaToolOptions, available_destination, default_destination
from ..transcription import FORMATS, TranscriptionOptions
from ..workers import MediaToolWorker, TranscriptionWorker
from .components import (Button, Card, Divider, Headline, InsetGroup, LogView, Muted,
                         PageHeader, PrimaryButton, ProgressBar, ScrollColumn,
                         SectionLabel, Select, SettingRow, Stepper, Switch, TextField, Toast)
from .model_manager import ModelManagerDialog

LANGUAGES = [("Português", "pt"), ("Inglês", "en"), ("Espanhol", "es"),
             ("Francês", "fr"), ("Alemão", "de"), ("Italiano", "it"),
             ("Japonês", "ja"), ("Coreano", "ko"), ("Chinês", "zh"),
             ("Detectar automaticamente", "auto")]
MODELS = [("tiny — mais rápido", "tiny"), ("base — rápido", "base"),
          ("small — equilibrado", "small"), ("medium — recomendado", "medium"),
          ("large-v3-turbo — rápido e preciso", "large-v3-turbo"),
          ("large-v3 — mais preciso", "large-v3")]
TASKS = [("Transcrever no idioma original", "transcribe"),
         ("Traduzir para inglês", "translate")]
MEDIA_FILTER = ("Mídias (*.mp4 *.mkv *.mov *.avi *.webm *.m4v *.flv *.wmv *.mpeg *.mp3 "
                "*.wav *.flac *.aac *.ogg *.m4a *.opus *.m4b);;Todos os arquivos (*.*)")


class TranscriptionPage(QWidget):
    # saída (a legenda) e origem (a mídia) — alimentam o histórico
    transcription_finished = Signal(str, str)
    # -1 informa que não há nenhuma transcrição ativa.
    taskbar_progress = Signal(float)
    embedded_finished = Signal(str)

    def __init__(self, cfg: Settings, parent=None):
        super().__init__(parent)
        self.setObjectName("transcriptionPage")
        self.cfg = cfg
        self.toolchain = None
        self.worker: TranscriptionWorker | None = None
        self.mux_worker: MediaToolWorker | None = None
        self._pending: deque[tuple[str, bool]] = deque()
        self._current_embed = False
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

        manage_models = Button("Gerenciar modelos", "settings", "secondary", group)
        manage_models.clicked.connect(self._manage_models)
        group.add_row(SettingRow(
            "Modelos no disco",
            "Baixe antes de usar, confira o espaço ocupado ou remova pesos antigos.",
            manage_models,
            group,
        ))

        self.task = self._combo(TASKS, self.cfg.transcription_task, group)
        self.task.currentIndexChanged.connect(
            lambda: self._save("transcription_task", self.task.currentData()))
        group.add_row(SettingRow(
            "Tarefa",
            "A tradução gera texto em inglês; o modelo Turbo é apenas para transcrição.",
            self.task,
            group,
        ))

        self.initial_prompt = TextField("Nomes próprios, siglas e termos técnicos", group)
        self.initial_prompt.setText(self.cfg.transcription_initial_prompt)
        self.initial_prompt.editingFinished.connect(
            lambda: self._save("transcription_initial_prompt", self.initial_prompt.text().strip()))
        group.add_row(SettingRow(
            "Vocabulário de contexto",
            "Ajuda o Whisper com nomes próprios e termos esperados; não é enviado à internet.",
            self.initial_prompt,
            group,
        ))

        self.max_chars = Stepper(group)
        self.max_chars.setRange(20, 100)
        self.max_chars.setValue(int(self.cfg.transcription_max_chars))
        self.max_chars.valueChanged.connect(
            lambda value: self._save("transcription_max_chars", int(value)))
        group.add_row(SettingRow(
            "Caracteres por linha",
            "Controla a largura máxima antes de quebrar a legenda.",
            self.max_chars,
            group,
        ))

        duration_controls = QWidget(group)
        duration_row = QHBoxLayout(duration_controls)
        duration_row.setContentsMargins(0, 0, 0, 0)
        duration_row.setSpacing(8)
        self.min_duration = TextField("mín. 0,8 s", duration_controls)
        self.max_duration = TextField("máx. 4,5 s", duration_controls)
        self.min_duration.setFixedWidth(105)
        self.max_duration.setFixedWidth(105)
        self.min_duration.setText(str(self.cfg.transcription_min_duration).replace(".", ","))
        self.max_duration.setText(str(self.cfg.transcription_max_duration).replace(".", ","))
        self.min_duration.editingFinished.connect(self._save_durations)
        self.max_duration.editingFinished.connect(self._save_durations)
        duration_row.addWidget(self.min_duration)
        duration_row.addWidget(self.max_duration)
        group.add_row(SettingRow(
            "Duração dos blocos",
            "Limites em segundos para evitar flashes curtos ou legendas longas demais.",
            duration_controls,
            group,
        ))

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

    def _save_durations(self) -> None:
        try:
            minimum = float(self.min_duration.text().strip().replace(",", "."))
            maximum = float(self.max_duration.text().strip().replace(",", "."))
        except ValueError:
            minimum = self.cfg.transcription_min_duration
            maximum = self.cfg.transcription_max_duration
        minimum = max(0.2, min(5.0, minimum))
        maximum = max(minimum, min(15.0, maximum))
        self.cfg.transcription_min_duration = minimum
        self.cfg.transcription_max_duration = maximum
        self.cfg.save()
        self.min_duration.setText(str(minimum).replace(".", ","))
        self.max_duration.setText(str(maximum).replace(".", ","))

    def set_toolchain(self, toolchain) -> None:
        self.toolchain = toolchain

    def _manage_models(self) -> None:
        dialog = ModelManagerDialog(str(self.model.currentData()), self.window())
        dialog.exec()

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

    def enqueue_media(self, path: str, embed: bool = False) -> None:
        """Enfileira uma mídia vinda de um download sem interromper a atual."""
        request = (path, bool(embed))
        if ((self.worker and self.worker.isRunning())
                or (self.mux_worker and self.mux_worker.isRunning())):
            self._pending.append(request)
            self._status(f"Adicionado à fila de transcrição: {Path(path).name}")
            return
        self._start_request(*request)

    def _start_request(self, path: str, embed: bool) -> None:
        self._current_embed = bool(embed)
        self.set_media(path)
        self.start(automatic=True)

    def start(self, automatic: bool = False) -> None:
        if self.worker and self.worker.isRunning():
            return
        if not automatic:
            self._current_embed = False
        if not self.toolchain:
            self._warn("As dependências ainda estão sendo verificadas.")
            return
        media = Path(self.media_edit.text().strip())
        if not media.is_file():
            self._warn("Selecione um arquivo de áudio ou vídeo existente.")
            return
        if self.task.currentData() == "translate" and self.model.currentData() == "large-v3-turbo":
            self._warn("O Large v3 Turbo não foi treinado para tradução. Escolha o Large v3.")
            return
        fmt = self.output_format.currentData()
        output = available_destination(Path(
            self.output_edit.text().strip() or str(media.with_suffix(FORMATS[fmt][1]))
        ).with_suffix(FORMATS[fmt][1]))
        self.output_edit.setText(str(output))
        opts = TranscriptionOptions(
            media_path=media,
            output_path=output,
            language=self.language.currentData(),
            model_size=self.model.currentData(),
            output_format=fmt,
            aggressive_filter=self.aggressive.isChecked(),
            task=self.task.currentData(),
            initial_prompt=self.initial_prompt.text().strip(),
            max_chars_per_line=self.max_chars.value(),
            min_duration=self.cfg.transcription_min_duration,
            max_duration=self.cfg.transcription_max_duration,
        )
        self.log.clear()
        self.progress.setValue(0)
        self.taskbar_progress.emit(0.0)
        self.progress_label.setText("Iniciando…")
        self.start_btn.setEnabled(False)
        self.pause_btn.setEnabled(True)
        self.cancel_btn.setEnabled(True)
        worker = TranscriptionWorker(opts, self.toolchain, self)
        self.worker = worker
        worker.status.connect(self._status)
        worker.progress.connect(self._set_progress)
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

    def _set_progress(self, value: int) -> None:
        """Atualiza a tela e o progresso nativo sem executar trabalho extra."""
        percent = max(0, min(100, int(value)))
        self.progress.setValue(percent)
        self.taskbar_progress.emit(float(percent))

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
        source = self.media_edit.text().strip()
        self.transcription_finished.emit(path, source)
        Toast.success("Transcrição concluída", f"Legenda salva em {Path(path).name}",
                      parent=self.window(), duration=6000)
        if self._current_embed:
            self._start_soft_subtitle(source, path)

    def _clear_finished_worker(self) -> None:
        """Não retém uma referência Qt já destruída entre duas execuções."""
        worker = self.sender()
        if worker is self.worker:
            self.worker = None
        if not (self.mux_worker and self.mux_worker.isRunning()):
            QTimer.singleShot(0, self._start_next_pending)

    def _cancelled(self) -> None:
        self._finish_controls()
        self._status("Transcrição cancelada.")
        self._current_embed = False

    def _failed(self, error: str) -> None:
        self._finish_controls()
        self._status(f"Erro: {error}")
        Toast.error("Falha na transcrição", error, parent=self.window(), duration=9000)
        self._current_embed = False

    def _start_soft_subtitle(self, source: str, subtitle: str) -> None:
        media = Path(source)
        caption = Path(subtitle)
        if not self.toolchain or not media.is_file() or not caption.is_file():
            self._status("Legenda criada, mas não foi possível iniciar a incorporação automática.")
            self._current_embed = False
            return
        destination = default_destination(media, "soft_sub")
        worker = MediaToolWorker(
            MediaToolOptions(
                source=media,
                destination=destination,
                operation="soft_sub",
                subtitles=caption,
            ),
            self.toolchain,
            self,
        )
        self.mux_worker = worker
        worker.progress.connect(self._status)
        worker.progress_value.connect(self._set_progress)
        worker.finished_ok.connect(self._mux_done)
        worker.failed.connect(self._mux_failed)
        worker.finished.connect(worker.deleteLater)
        worker.finished.connect(lambda w=worker: self._clear_mux_worker(w))
        self._status("Incorporando a legenda como faixa, sem reencodar o vídeo…")
        worker.start()

    def _mux_done(self, output: str) -> None:
        self.embedded_finished.emit(output)
        self._status(f"Cópia legendada criada: {Path(output).name}")
        Toast.success(
            "Legenda incorporada",
            f"Arquivo salvo em {Path(output).name}",
            parent=self.window(),
            duration=6500,
        )

    def _mux_failed(self, error: str) -> None:
        self._status(f"A legenda foi criada, mas não foi possível incorporá-la: {error}")
        Toast.warning(
            "Legenda criada sem incorporação",
            error,
            parent=self.window(),
            duration=7500,
        )

    def _clear_mux_worker(self, worker: MediaToolWorker) -> None:
        if self.mux_worker is worker:
            self.mux_worker = None
        self._current_embed = False
        self.taskbar_progress.emit(-1.0)
        QTimer.singleShot(0, self._start_next_pending)

    def _start_next_pending(self) -> None:
        if ((self.worker and self.worker.isRunning())
                or (self.mux_worker and self.mux_worker.isRunning())
                or not self._pending):
            return
        path, embed = self._pending.popleft()
        self._start_request(path, embed)

    def _finish_controls(self) -> None:
        self.start_btn.setEnabled(True)
        self.pause_btn.setEnabled(False)
        self.pause_btn.setText("Pausar")
        self.cancel_btn.setEnabled(False)
        self._paused = False
        self.taskbar_progress.emit(-1.0)

    def shutdown(self) -> None:
        """Finaliza o worker antes de o Qt destruir a janela principal."""
        worker = self.worker
        if worker is not None and worker.isRunning():
            self._status("Encerrando transcrição antes de fechar o aplicativo…")
            worker.cancel()
            if not worker.wait(5000):
                worker.force_stop()
                worker.wait(2000)
        mux = self.mux_worker
        if mux is not None and mux.isRunning():
            mux.cancel()
            mux.wait(3000)

    def open_output_folder(self) -> None:
        path = Path(self.output_edit.text().strip() or self.media_edit.text().strip())
        folder = path.parent if path else Path.home()
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def _warn(self, message: str) -> None:
        Toast.warning("Atenção", message, parent=self.window(), duration=5000)
