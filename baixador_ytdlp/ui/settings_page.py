"""Página 'Configurações': pastas, qualidade, aparência, GPU e dependências."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (BodyLabel, CaptionLabel, CardWidget, ComboBox,
                            FluentIcon as FIF, LineEdit, PrimaryPushButton, PushButton,
                            SmoothScrollArea, SpinBox, StrongBodyLabel, SubtitleLabel,
                            SwitchButton, Theme, TitleLabel, setTheme)

from ..config import Settings
from ..cookies import EXPORT_INSTRUCTIONS
from ..gpu import GpuInfo, NVENC_LABELS
from ..hardware import default_fragments, default_parallel_downloads, usable_cores

# A ordem e os rótulos são deliberados: no Windows só o Firefox funciona de fato.
# Os demais são navegadores Chromium, que desde o Chrome 127 não liberam mais os
# cookies para processos externos (App-Bound Encryption).
# Apenas navegadores que o yt-dlp REALMENTE aceita em --cookies-from-browser:
# brave, chrome, chromium, edge, firefox, opera, safari, vivaldi, whale.
# "librewolf" estava aqui por engano e o yt-dlp recusava com "unsupported browser".
BROWSERS = [("Não usar cookies", ""),
            ("Firefox — funciona", "firefox"),
            ("Chrome — não funciona no Windows", "chrome"),
            ("Edge — não funciona no Windows", "edge"),
            ("Brave — não funciona no Windows", "brave"),
            ("Chromium — não funciona no Windows", "chromium"),
            ("Vivaldi — não funciona no Windows", "vivaldi"),
            ("Opera — não funciona no Windows", "opera")]
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
    app_update_requested = Signal()
    theme_changed = Signal(str)
    download_dir_changed = Signal(str)

    def __init__(self, cfg: Settings, parent=None):
        super().__init__(parent)
        self.setObjectName("settingsPage")
        self.cfg = cfg
        self.gpu = GpuInfo()
        # settings.json é reescrito no máximo uma vez a cada 400 ms, mesmo que o
        # usuário arraste um SpinBox de ponta a ponta.
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(400)
        self._save_timer.timeout.connect(self.cfg.save)
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
        self._switch_row("Perguntar a pasta em cada download",
                         "Deixa a caixa 'Escolher a pasta de saída' já marcada na página Baixar.",
                         "ask_output_dir")
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
                       f"Acelera o download de cada vídeo. Para os {usable_cores()} núcleos "
                       f"desta máquina, {default_fragments()} é o equilíbrio calculado; acima "
                       "disso costuma trocar velocidade por disputa de CPU e disco.",
                       "concurrent_fragments", 1, 32)
        self._spin_row("Downloads simultâneos",
                       f"Quantos itens da fila rodam ao mesmo tempo (sugestão para esta "
                       f"máquina: {default_parallel_downloads()}).",
                       "max_parallel_downloads", 1, 6)
        self._line_row("Limite de banda", "Ex.: 5M para 5 MB/s. Vazio = sem limite.",
                       "limit_rate", "sem limite")

        self._section("Conteúdo extra")
        self._switch_row("Embutir capa", "Usa a thumbnail como capa do arquivo.",
                         "embed_thumbnail")
        self._switch_row("Embutir metadados",
                         "Título, canal e data dentro do arquivo.", "embed_metadata")
        self._switch_row("Embutir capítulos",
                         "Marcadores de capítulo navegáveis no player.", "embed_chapters")
        self._switch_row("Baixar legendas", "Inclui legendas manuais e automáticas.",
                         "write_subs")
        self._switch_row("Embutir as legendas no vídeo",
                         "Grava a legenda dentro do arquivo em vez de deixar um .srt ao lado. "
                         "Só vale quando 'Baixar legendas' está ligado.", "embed_subs")
        self._line_row("Idiomas das legendas", "Separados por vírgula.", "sub_langs",
                       "pt,pt-BR,en")
        self._switch_row("Remover trechos patrocinados",
                         "Usa o SponsorBlock para cortar patrocínio e autopromoção.",
                         "sponsorblock")
        self._cookies_file_row()
        self._combo_row("Cookies do navegador",
                        "Só é usado quando não há arquivo cookies.txt. No Windows funciona "
                        "apenas com Firefox e derivados — os navegadores Chromium criptografam "
                        "os cookies de um jeito que nenhum programa externo consegue abrir.",
                        BROWSERS, "cookies_browser")
        self._line_row("Ajustes do extrator (avançado)",
                       "Repassado ao yt-dlp como --extractor-args. Vazio na dúvida. "
                       "Ex.: youtube:player_client=default,web_safari",
                       "extractor_args", "vazio")

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
        self._switch_row("Mostrar o progresso na barra de tarefas",
                         "O ícone do app na barra de tarefas do Windows enche conforme o "
                         "download avança.", "taskbar_progress")

        self._section("Histórico")
        self._switch_row("Guardar o que foi baixado",
                         "Alimenta a página Histórico. Fica só na sua máquina.",
                         "history_enabled")
        self._spin_row("Itens guardados", "Os mais antigos são descartados.",
                       "history_limit", 20, 1000)

        self._section("Dependências")
        self.versions = CaptionLabel("—", self)
        self.versions.setWordWrap(True)
        update_btn = PrimaryPushButton(FIF.UPDATE, "Verificar componentes", self)
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

        self._section("Atualizações do aplicativo")
        app_update_btn = PrimaryPushButton(FIF.UPDATE, "Verificar agora", self)
        app_update_btn.clicked.connect(self.app_update_requested.emit)
        app_update_card = CardWidget(self)
        app_update_layout = QHBoxLayout(app_update_card)
        app_update_layout.setContentsMargins(16, 12, 16, 12)
        app_update_texts = QVBoxLayout()
        app_update_texts.addWidget(BodyLabel("Nova versão disponível?", app_update_card))
        app_update_texts.addWidget(CaptionLabel(
            "Consulta as Releases do GitHub e avisa na faixa inferior.", app_update_card))
        app_update_layout.addLayout(app_update_texts, 1)
        app_update_layout.addWidget(app_update_btn)
        self.box.addWidget(app_update_card)
        self._switch_row("Verificar novas versões ao abrir",
                         "Apenas procura atualizações. O download e a instalação só começam "
                         "quando você confirmar no aviso inferior.", "auto_update")
        self._spin_row("Intervalo entre checagens de atualização (horas)",
                       "Use 0 para consultar em toda abertura.", "update_check_hours", 0, 720)
        self._spin_row("Intervalo entre checagens do legendador (horas)",
                       "Dentro desse prazo, e estando tudo na versão certa, a abertura pula a "
                       "consulta ao pip — é o que mais pesa na inicialização.",
                       "runtime_check_hours", 0, 720)
        self.box.addStretch(1)

    # ---------------------------------------------------------- construtores
    def _section(self, title: str) -> None:
        label = SubtitleLabel(title, self)
        label.setContentsMargins(4, 12, 0, 2)
        self.box.addWidget(label)

    def _set(self, key: str, value) -> None:
        setattr(self.cfg, key, value)
        self._save_timer.start()

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

    def _cookies_file_row(self) -> None:
        """Arquivo cookies.txt: caminho, seletor e o passo a passo de exportação."""
        card = CardWidget(self)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        texts = QVBoxLayout()
        texts.setSpacing(1)
        texts.addWidget(BodyLabel("Arquivo cookies.txt (recomendado)", card))
        caption = CaptionLabel(
            "É o caminho que o YouTube aceita de forma confiável. Tem prioridade sobre o "
            "navegador e o conteúdo nunca é copiado para os logs.", card)
        caption.setWordWrap(True)
        texts.addWidget(caption)
        layout.addLayout(texts)

        row = QHBoxLayout()
        row.setSpacing(10)
        self.cookies_edit = LineEdit(card)
        self.cookies_edit.setPlaceholderText("Nenhum arquivo selecionado")
        self.cookies_edit.setText(str(self.cfg.cookies_file))
        self.cookies_edit.setClearButtonEnabled(True)
        self.cookies_edit.editingFinished.connect(
            lambda: self._set_cookies_file(self.cookies_edit.text().strip()))

        pick = PushButton(FIF.FOLDER, "Escolher", card)
        pick.clicked.connect(self._pick_cookies_file)

        # Ajuda embutida, não modal. Um diálogo modal aqui já travou o aplicativo:
        # o MessageBox do Fluent fixa a altura na construção e reflowa o texto a
        # cada resize, então um texto longo empurra os botões para fora do cartão
        # e a máscara modal deixa a tela inteira inacessível.
        self.howto_btn = PushButton(FIF.HELP, "Como exportar", card)
        self.howto_btn.setCheckable(True)
        self.howto_btn.toggled.connect(self._toggle_cookie_help)

        row.addWidget(self.cookies_edit, 1)
        row.addWidget(pick)
        row.addWidget(self.howto_btn)
        layout.addLayout(row)

        self.cookies_status = CaptionLabel("", card)
        self.cookies_status.setWordWrap(True)
        layout.addWidget(self.cookies_status)

        self.cookies_help = CaptionLabel(EXPORT_INSTRUCTIONS, card)
        self.cookies_help.setWordWrap(True)
        self.cookies_help.hide()
        layout.addWidget(self.cookies_help)

        self._refresh_cookies_status()
        self.box.addWidget(card)

    def _set_cookies_file(self, path: str) -> None:
        self._set("cookies_file", path)
        self._refresh_cookies_status()

    def _pick_cookies_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Selecionar cookies.txt", self.cfg.cookies_file or "",
            "Cookies Netscape (*.txt);;Todos os arquivos (*.*)")
        if path:
            self.cookies_edit.setText(path)
            self._set_cookies_file(path)

    def _refresh_cookies_status(self) -> None:
        """Valida o arquivo na hora de escolher, não na hora de baixar."""
        path = (self.cfg.cookies_file or "").strip()
        if not path:
            self.cookies_status.setText("")
            return
        target = Path(path)
        if not target.is_file():
            self.cookies_status.setText("⚠ Arquivo não encontrado neste caminho.")
            return
        try:
            head = target.read_text(encoding="utf-8", errors="replace")[:4096]
        except OSError as exc:
            self.cookies_status.setText(f"⚠ Não deu para ler o arquivo: {exc}")
            return
        if "netscape http cookie file" not in head.lower() and "\t" not in head:
            self.cookies_status.setText(
                "⚠ Não parece um cookies.txt no formato Netscape. Reexporte com uma "
                "extensão que gere esse formato.")
            return
        domains = "youtube.com" in head or "google.com" in head
        self.cookies_status.setText(
            "✓ Arquivo válido, com cookies do YouTube." if domains
            else "✓ Formato válido, mas sem cookies de youtube.com — confira a exportação.")

    def _toggle_cookie_help(self, shown: bool) -> None:
        self.cookies_help.setVisible(shown)
        self.howto_btn.setText("Ocultar ajuda" if shown else "Como exportar")

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
                self.download_dir_changed.emit(path)

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

    def hideEvent(self, event):  # noqa: N802 - assinatura do Qt
        """Não deixa uma alteração recente pendente se o usuário sair da aba."""
        if self._save_timer.isActive():
            self._save_timer.stop()
            self.cfg.save()
        super().hideEvent(event)

    def set_versions(self, ytdlp: str, ffmpeg: str, transcription_runtime: str = "") -> None:
        text = f"yt-dlp {ytdlp or '—'} · FFmpeg {ffmpeg or '—'}"
        if transcription_runtime:
            text += f"\n{transcription_runtime}"
        self.versions.setText(text)
