"""Página 'Configurações': pastas, qualidade, aparência, GPU e dependências."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (BodyLabel, CaptionLabel, CardWidget, CheckBox, ComboBox,
                            FluentIcon as FIF, InfoBar, InfoBarPosition, LineEdit,
                            PrimaryPushButton, PushButton, SmoothScrollArea, SpinBox,
                            StrongBodyLabel, SubtitleLabel, SwitchButton, TitleLabel, setTheme,
                            Theme)

from ..config import Settings
from ..gpu import GpuInfo, NVENC_LABELS

BROWSERS = [("Não usar cookies", ""), ("Chrome", "chrome"), ("Edge", "edge"),
            ("Firefox", "firefox"), ("Brave", "brave"), ("Opera", "opera")]
THEMES = [("Seguir o Windows", "auto"), ("Claro", "light"), ("Escuro", "dark")]
PRESETS = [("p1 — mais rápido", "p1"), ("p4 — equilibrado", "p4"),
           ("p5 — recomendado", "p5"), ("p7 — mais lento e melhor", "p7")]


class Row(CardWidget):
    """Uma linha de configuração: título, explicação e o controle à direita."""

    def __init__(self, title: str, subtitle: str, control: QWidget, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(16)

        texts = QVBoxLayout()
        texts.setSpacing(1)
        texts.addWidget(BodyLabel(title, self))
        if subtitle:
            caption = CaptionLabel(subtitle, self)
            caption.setWordWrap(True)
            texts.addWidget(caption)
        layout.addLayout(texts, 1)
        layout.addWidget(control, 0, Qt.AlignmentFlag.AlignVCenter)


class SettingsPage(QWidget):
    update_requested = Signal()
    theme_changed = Signal(str)

    def __init__(self, cfg: Settings, parent=None):
        super().__init__(parent)
        self.setObjectName("settingsPage")
        self.cfg = cfg
        self.gpu = GpuInfo()
        self._build_ui()

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 16, 28, 12)
        outer.addWidget(TitleLabel("Configurações", self))

        scroll = SmoothScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        body = QWidget(scroll)
        body.setStyleSheet("background: transparent;")
        self.box = QVBoxLayout(body)
        self.box.setContentsMargins(0, 8, 12, 8)
        self.box.setSpacing(8)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        self._section("Downloads")
        self._folder_row()
        self._template_row()
        self._combo_row("Formato padrão do vídeo",
                        "Container usado quando você não muda nada na página Baixar.",
                        [("MP4", "mp4"), ("MKV", "mkv"), ("WebM", "webm"),
                         ("Manter original", "original")],
                        "container")
        self._switch_row("Priorizar compatibilidade (H.264)",
                         "Escolhe H.264/AAC em vez do melhor codec. Roda em qualquer TV, "
                         "mas com qualidade um pouco menor no mesmo tamanho.", "prefer_h264")
        self._spin_row("Fragmentos simultâneos",
                       "Acelera o download de cada vídeo. 8 é um bom equilíbrio.",
                       "concurrent_fragments", 1, 32)
        self._spin_row("Downloads simultâneos", "Quantos itens da fila rodam ao mesmo tempo.",
                       "max_parallel_downloads", 1, 6)
        self._line_row("Limite de banda", "Ex.: 5M para 5 MB/s. Vazio = sem limite.",
                       "limit_rate", "sem limite")

        self._section("Conteúdo extra")
        self._switch_row("Embutir capa", "Usa a thumbnail como capa do arquivo.",
                         "embed_thumbnail")
        self._switch_row("Embutir metadados e capítulos",
                         "Título, canal, data e marcadores de capítulo.", "embed_metadata")
        self._switch_row("Baixar legendas", "Inclui legendas manuais e automáticas.",
                         "write_subs")
        self._line_row("Idiomas das legendas", "Separados por vírgula.", "sub_langs",
                       "pt,pt-BR,en")
        self._switch_row("Remover trechos patrocinados",
                         "Usa o SponsorBlock para cortar patrocínio e autopromoção.",
                         "sponsorblock")
        self._combo_row("Cookies do navegador",
                        "Necessário para conteúdo com login ou restrição de idade. "
                        "O yt-dlp lê o perfil local do navegador.",
                        BROWSERS, "cookies_browser")

        self._section("GPU e conversão")
        self.gpu_label = CaptionLabel("Detectando a GPU…", self)
        self.gpu_label.setWordWrap(True)
        gpu_card = CardWidget(self)
        gpu_layout = QVBoxLayout(gpu_card)
        gpu_layout.setContentsMargins(16, 12, 16, 12)
        gpu_layout.addWidget(StrongBodyLabel("Placa detectada", gpu_card))
        gpu_layout.addWidget(self.gpu_label)
        note = CaptionLabel(
            "O download em si não usa a GPU — é rede e cópia de arquivo. A placa entra "
            "quando você converte o vídeo depois de baixar. Toda conversão perde qualidade "
            "em relação ao original; ative só se precisar de compatibilidade ou de arquivo menor.",
            gpu_card)
        note.setWordWrap(True)
        gpu_layout.addWidget(note)
        self.box.addWidget(gpu_card)

        self._switch_row("Converter após baixar (NVENC)",
                         "Reencoda o arquivo final usando a GPU.", "transcode_enabled")
        self.codec_combo = ComboBox(self)
        self.codec_row = Row("Codec da conversão", "Depende do que a sua placa suporta.",
                             self.codec_combo, self)
        self.codec_combo.currentIndexChanged.connect(
            lambda: self._set("transcode_codec", self.codec_combo.currentData()))
        self.box.addWidget(self.codec_row)
        self._combo_row("Preset do NVENC", "Mais lento = melhor compressão.", PRESETS,
                        "transcode_preset")
        self._spin_row("Qualidade (CQ)", "Menor = melhor qualidade e arquivo maior. 20 é bom.",
                       "transcode_cq", 10, 40)
        self._switch_row("Substituir o arquivo original",
                         "Apaga o arquivo baixado depois de converter.", "transcode_replace")

        self._section("Aparência")
        self._combo_row("Tema", "", THEMES, "theme", on_change=self._apply_theme)
        self._switch_row("Efeito Mica na janela",
                         "Fundo translúcido do Windows 11. Requer reiniciar o app.", "mica")
        self._switch_row("Detectar link na área de transferência",
                         "Preenche o campo sozinho quando você volta para a janela.",
                         "clipboard_watch")
        self._switch_row("Abrir a pasta ao terminar", "", "open_folder_on_finish")

        self._section("Dependências")
        self.versions = CaptionLabel("—", self)
        self.versions.setWordWrap(True)
        update_btn = PrimaryPushButton(FIF.UPDATE, "Verificar agora", self)
        update_btn.clicked.connect(self.update_requested.emit)
        deps_card = CardWidget(self)
        deps_layout = QHBoxLayout(deps_card)
        deps_layout.setContentsMargins(16, 12, 16, 12)
        texts = QVBoxLayout()
        texts.addWidget(BodyLabel("yt-dlp e FFmpeg", deps_card))
        texts.addWidget(self.versions)
        deps_layout.addLayout(texts, 1)
        deps_layout.addWidget(update_btn)
        self.box.addWidget(deps_card)

        self._switch_row("Atualizar sozinho ao abrir",
                         "Checa e instala novas versões na inicialização.", "auto_update")
        self.box.addStretch(1)

    # ---------------------------------------------------------- construtores
    def _section(self, title: str) -> None:
        label = SubtitleLabel(title, self)
        label.setContentsMargins(4, 12, 0, 2)
        self.box.addWidget(label)

    def _set(self, key: str, value) -> None:
        setattr(self.cfg, key, value)
        self.cfg.save()

    def _switch_row(self, title: str, subtitle: str, key: str) -> None:
        switch = SwitchButton(self)
        switch.setOnText("Ligado")
        switch.setOffText("Desligado")
        switch.setChecked(bool(getattr(self.cfg, key)))
        switch.checkedChanged.connect(lambda v, k=key: self._set(k, bool(v)))
        self.box.addWidget(Row(title, subtitle, switch, self))

    def _combo_row(self, title: str, subtitle: str, items, key: str, on_change=None) -> None:
        combo = ComboBox(self)
        for label, value in items:
            combo.addItem(label, userData=value)
        current = getattr(self.cfg, key)
        for i in range(combo.count()):
            if combo.itemData(i) == current:
                combo.setCurrentIndex(i)
                break

        def changed():
            self._set(key, combo.currentData())
            if on_change:
                on_change(combo.currentData())

        combo.currentIndexChanged.connect(changed)
        self.box.addWidget(Row(title, subtitle, combo, self))

    def _spin_row(self, title: str, subtitle: str, key: str, lo: int, hi: int) -> None:
        spin = SpinBox(self)
        spin.setRange(lo, hi)
        spin.setValue(int(getattr(self.cfg, key)))
        spin.valueChanged.connect(lambda v, k=key: self._set(k, int(v)))
        self.box.addWidget(Row(title, subtitle, spin, self))

    def _line_row(self, title: str, subtitle: str, key: str, placeholder: str) -> None:
        edit = LineEdit(self)
        edit.setFixedWidth(220)
        edit.setPlaceholderText(placeholder)
        edit.setText(str(getattr(self.cfg, key)))
        edit.editingFinished.connect(lambda k=key, e=edit: self._set(k, e.text().strip()))
        self.box.addWidget(Row(title, subtitle, edit, self))

    def _folder_row(self) -> None:
        button = PushButton(FIF.FOLDER, "Escolher", self)
        self.folder_label = CaptionLabel(self.cfg.download_dir, self)
        self.folder_label.setWordWrap(True)

        def choose():
            path = QFileDialog.getExistingDirectory(self, "Pasta de destino",
                                                    self.cfg.download_dir)
            if path:
                self._set("download_dir", path)
                self.folder_label.setText(path)

        button.clicked.connect(choose)
        card = CardWidget(self)
        layout = QHBoxLayout(card)
        layout.setContentsMargins(16, 12, 16, 12)
        texts = QVBoxLayout()
        texts.addWidget(BodyLabel("Pasta de destino", card))
        texts.addWidget(self.folder_label)
        layout.addLayout(texts, 1)
        layout.addWidget(button)
        self.box.addWidget(card)

    def _template_row(self) -> None:
        self._line_row("Nome do arquivo",
                       "Modelo do yt-dlp. Ex.: %(title)s [%(id)s].%(ext)s",
                       "filename_template", "%(title)s.%(ext)s")

    # --------------------------------------------------------------- estado
    def _apply_theme(self, value: str) -> None:
        setTheme({"light": Theme.LIGHT, "dark": Theme.DARK}.get(value, Theme.AUTO))
        self.theme_changed.emit(value)

    def set_gpu(self, gpu: GpuInfo) -> None:
        self.gpu = gpu
        self.gpu_label.setText(gpu.summary)
        self.codec_combo.clear()
        for codec in gpu.encoders:
            self.codec_combo.addItem(NVENC_LABELS[codec], userData=codec)
        if not gpu.encoders:
            self.codec_combo.addItem("Nenhum encoder NVENC disponível", userData="")
            self.codec_row.setEnabled(False)
        else:
            for i in range(self.codec_combo.count()):
                if self.codec_combo.itemData(i) == self.cfg.transcode_codec:
                    self.codec_combo.setCurrentIndex(i)
                    break

    def set_versions(self, ytdlp: str, ffmpeg: str, transcription_runtime: str = "") -> None:
        text = f"yt-dlp {ytdlp or '—'} · FFmpeg {ffmpeg or '—'}"
        if transcription_runtime:
            text += f"\n{transcription_runtime}"
        self.versions.setText(text)
