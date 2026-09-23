"""Página 'Configurações': pastas, qualidade, aparência, GPU e dependências.

As opções ficam em listas agrupadas — um bloco arredondado por assunto, com
linhas separadas por fios finos. É o padrão dos Ajustes da Apple e substitui o
cartão flutuante por opção, que empilhava dezenas de retângulos na tela.
"""
from __future__ import annotations

import re

import subprocess
from pathlib import Path

from PySide6.QtCore import QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QVBoxLayout, QWidget

from ..config import APP_VERSION, Settings
from ..cookies import EXPORT_INSTRUCTIONS, cookie_age_days, import_cookie_file
from ..filename_preview import render_filename_preview
from ..gpu import GPU_ENCODER_LABELS, GpuInfo
from ..hardware import default_fragments, default_parallel_downloads, usable_cores
from . import theme
from .components import (Button, Headline, InsetGroup, Muted, PageHeader, PrimaryButton,
                         ScrollColumn, SectionLabel, Select, SettingRow, Stepper, Switch,
                         TextField)

# A ordem e os rótulos são deliberados: no Windows só o Firefox funciona de fato.
# Os demais são navegadores Chromium, que desde o Chrome 127 não liberam mais os
# cookies para processos externos (App-Bound Encryption).
BROWSERS = [("Não usar cookies", ""),
            ("Firefox — funciona", "firefox"),
            ("Chrome — não funciona no Windows", "chrome"),
            ("Edge — não funciona no Windows", "edge"),
            ("Brave — não funciona no Windows", "brave"),
            ("Chromium — não funciona no Windows", "chromium"),
            ("Vivaldi — não funciona no Windows", "vivaldi"),
            ("Opera — não funciona no Windows", "opera")]
THEMES = [("Seguir o sistema", "auto"), ("Claro", "light"), ("Escuro", "dark")]
UI_LANGUAGES = [("Português (Brasil)", "pt-BR"), ("English", "en")]
PRESETS = [("p1 — mais rápido", "p1"), ("p4 — equilibrado", "p4"),
           ("p5 — recomendado", "p5"), ("p7 — mais lento e melhor", "p7")]


class SettingsPage(QWidget):
    update_requested = Signal()
    ytdlp_channel_changed = Signal(str)
    diagnostics_export_requested = Signal()
    app_update_requested = Signal()
    gpu_detection_requested = Signal()
    theme_changed = Signal(str)
    language_changed = Signal(str)
    download_dir_changed = Signal(str)

    def __init__(self, cfg: Settings, parent=None):
        super().__init__(parent)
        self.setObjectName("settingsPage")
        self.cfg = cfg
        self.gpu = GpuInfo()
        self._gpu_requested = False
        # settings.json é reescrito no máximo uma vez a cada 400 ms, mesmo que o
        # usuário arraste um contador de ponta a ponta.
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(400)
        self._save_timer.timeout.connect(self.cfg.save)
        self._group: InsetGroup | None = None
        self._build_ui()

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 20, 28, 16)
        outer.setSpacing(16)
        outer.addWidget(PageHeader(
            "Configurações", "Tudo fica salvo nesta máquina, no seu perfil de usuário.", self))

        self.page = ScrollColumn(self, spacing=10)
        outer.addWidget(self.page, 1)

        self._section("Downloads")
        self._folder_row()
        self._switch_row("Perguntar a pasta em cada download",
                         "Deixa a opção “Escolher a pasta” já ligada na página Baixar.",
                         "ask_output_dir")
        self._filename_template_row()
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
                       "concurrent_fragments", 1, 16)
        self._spin_row("Downloads simultâneos",
                       f"Quantos itens da fila rodam ao mesmo tempo (sugestão para esta "
                       f"máquina: {default_parallel_downloads()}).",
                       "max_parallel_downloads", 1, 6)
        self._line_row("Limite de banda", "Ex.: 5M para 5 MB/s. Vazio = sem limite.",
                       "limit_rate", "sem limite")
        self._line_row(
            "Proxy",
            "Opcional. Ex.: http://127.0.0.1:8080. Credenciais são ocultadas nos logs.",
            "proxy", "sem proxy",
        )
        self._switch_row("Evitar baixar a mesma mídia novamente",
                         "Guarda os IDs concluídos por pasta. Um item repetido é ignorado "
                         "sem gastar banda; desligue temporariamente para refazer outro formato.",
                         "archive_enabled")
        self._switch_row("Retomar a fila ao reabrir",
                         "Itens interrompidos voltam como pendentes. Os arquivos .part são "
                         "continuados do ponto onde o yt-dlp parou.", "resume_queue")
        self._spin_row("Retentativas automáticas",
                       "Para quedas de rede, limite temporário do site e respostas 5xx. "
                       "Erros de link, conta ou conteúdo removido não são repetidos.",
                       "auto_retry_attempts", 0, 5)
        self._spin_row("Espera entre retentativas (segundos)",
                       "A cada nova tentativa a espera aumenta um pouco, para não sobrecarregar o site.",
                       "auto_retry_delay", 1, 60)

        self._section("Conteúdo extra")
        self._switch_row("Embutir capa", "Usa a thumbnail como capa do arquivo.",
                         "embed_thumbnail")
        self._switch_row("Embutir metadados",
                         "Título, canal e data dentro do arquivo.", "embed_metadata")
        self._switch_row("Embutir capítulos",
                         "Marcadores de capítulo navegáveis no player.", "embed_chapters")
        self._switch_row("Organizar áudio por canal",
                         "Em downloads de áudio, cria uma pasta por canal/artista antes do nome "
                         "definido acima. Capa, metadados e capítulos usam as opções deste bloco.",
                         "organize_audio_by_uploader")
        self._switch_row("Baixar legendas", "Inclui legendas manuais e automáticas.",
                         "write_subs")
        self._switch_row("Embutir as legendas no vídeo",
                         "Grava a legenda dentro do arquivo em vez de deixar um .srt ao lado. "
                         "Só vale quando “Baixar legendas” está ligado.", "embed_subs")
        self._line_row("Idiomas das legendas", "Separados por vírgula.", "sub_langs",
                       "pt,pt-BR,en")
        self._switch_row("Remover trechos patrocinados",
                         "Usa o SponsorBlock para cortar patrocínio e autopromoção.",
                         "sponsorblock")

        self._section("Acesso a conteúdo restrito")
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
        self._gpu_row()
        self._switch_row("Converter após baixar (GPU)",
                         "Reencoda o arquivo final usando a GPU.", "transcode_enabled")
        self.codec_combo = Select(self)
        self.codec_combo.setMinimumWidth(230)
        self.codec_row = SettingRow("Codec da conversão",
                                    "Depende do que a sua placa suporta.",
                                    self.codec_combo, self)
        self.codec_combo.currentIndexChanged.connect(
            lambda: self._set("transcode_codec", self.codec_combo.currentData()))
        self._add_row(self.codec_row)
        self._combo_row("Preset NVIDIA", "Usado somente por NVENC. Mais lento = melhor compressão.", PRESETS,
                        "transcode_preset")
        self._spin_row("Qualidade (CQ)", "Menor = melhor qualidade e arquivo maior. 20 é bom.",
                       "transcode_cq", 10, 40)
        self._switch_row("Substituir o arquivo original",
                         "Depois de validar a conversão, move o original para a Lixeira.",
                         "transcode_replace")

        self._section("Aparência")
        self._combo_row("Tema", "Claro, escuro ou o que o sistema estiver usando.",
                        THEMES, "theme", on_change=self._apply_theme)
        self._combo_row(
            "Idioma da interface",
            "Aplique na próxima abertura para não interromper downloads ou transcrições em andamento.",
            UI_LANGUAGES,
            "ui_language",
            on_change=self._apply_language,
        )
        self._switch_row("Efeito Mica na janela",
                         "Experimental. As superfícies do app são opacas, então o material quase "
                         "não aparece; mantenha desligado se notar bordas claras. Requer reiniciar.",
                         "mica")
        self._switch_row("Detectar link na área de transferência",
                         "Preenche o campo sozinho quando você volta para a janela.",
                         "clipboard_watch")
        self._switch_row("Abrir a pasta ao terminar",
                         "Mostra o arquivo no Explorer assim que o download fecha.",
                         "open_folder_on_finish")
        self._switch_row("Mostrar o progresso na barra de tarefas",
                         "O ícone do app na barra de tarefas do Windows enche conforme o "
                         "download ou a transcrição avança e pisca ao concluir.",
                         "taskbar_progress")
        self._switch_row("Notificações na bandeja",
                         "Avisa quando downloads, legendas e ferramentas terminam.",
                         "tray_notifications")
        self._switch_row("Fechar para a bandeja",
                         "O botão fechar esconde a janela e mantém as tarefas em andamento. "
                         "Use Sair no ícone da bandeja para encerrar.",
                         "close_to_tray")

        self._section("Atalhos de teclado")
        shortcuts, _shortcut_layout = self._custom_row(
            "Navegação e ações",
            "Ctrl+1…5 muda de página; Ctrl+, abre Configurações; Ctrl+L foca o link; "
            "Ctrl+O importa uma lista; Ctrl+Enter inicia; Esc cancela a tarefa atual; "
            "F1 abre o guia.",
        )
        self._add_row(shortcuts)

        self._section("Histórico")
        self._switch_row("Guardar o que foi baixado",
                         "Alimenta a página Histórico. Fica só na sua máquina.",
                         "history_enabled")
        self._spin_row("Itens guardados", "Os mais antigos são descartados.",
                       "history_limit", 20, 1000)

        self._section("Componentes e atualizações")
        self._dependencies_row()
        self._app_update_row()
        self._diagnostics_row()
        self._switch_row("Verificar novas versões ao abrir",
                         "Apenas procura atualizações. O download e a instalação só começam "
                         "quando você confirmar no aviso inferior.", "auto_update")
        self._spin_row("Intervalo entre checagens de atualização (horas)",
                       "Use 0 para consultar em toda abertura.", "update_check_hours", 0, 720)
        self._combo_row(
            "Canal do yt-dlp",
            "Estável é o padrão. Nightly recebe correções de sites (como o YouTube) dias "
            "antes; troque se um link parar de funcionar. Também tem SHA-256 conferido.",
            [("Estável (recomendado)", "stable"), ("Nightly — correções mais rápidas", "nightly")],
            "ytdlp_channel",
            on_change=self._ytdlp_channel_changed,
        )
        self._switch_row(
            "Usar ferramentas instaladas no sistema",
            "Permite procurar yt-dlp e FFmpeg no PATH quando a cópia verificada do app não existe. "
            "Mantenha desligado para maior segurança.",
            "allow_system_tools",
        )
        self.page.add_stretch()

    # ---------------------------------------------------------- construtores
    def _section(self, title: str) -> None:
        """Abre um novo bloco agrupado; as linhas seguintes entram nele."""
        label = SectionLabel(title, self)
        label.setContentsMargins(4, 14, 0, 2)
        self.page.add(label)
        self._group = InsetGroup(self)
        self.page.add(self._group)

    def _add_row(self, row: QWidget) -> QWidget:
        if self._group is None:
            self._section("Geral")
        return self._group.add_row(row)

    def _custom_row(self, title: str, subtitle: str = "") -> tuple[QWidget, QVBoxLayout]:
        """Linha alta: título, explicação e conteúdo livre embaixo."""
        row = QWidget(self._group)
        column = QVBoxLayout(row)
        column.setContentsMargins(16, 12, 16, 14)
        column.setSpacing(8)
        column.addWidget(Headline(title, row))
        if subtitle:
            column.addWidget(Muted(subtitle, row))
        return row, column

    def _set(self, key: str, value) -> None:
        setattr(self.cfg, key, value)
        self._save_timer.start()

    def _switch_row(self, title: str, subtitle: str, key: str) -> None:
        switch = Switch(self)
        switch.setChecked(bool(getattr(self.cfg, key)))
        switch.checkedChanged.connect(lambda v, k=key: self._set(k, bool(v)))
        self._add_row(SettingRow(title, subtitle, switch, self))

    def _combo_row(self, title: str, subtitle: str, items, key: str, on_change=None) -> None:
        combo = Select(self)
        for label, value in items:
            combo.addItem(label, userData=value)
        current = getattr(self.cfg, key)
        for i in range(combo.count()):
            if combo.itemData(i) == current:
                combo.setCurrentIndex(i)
                break
        combo.setMinimumWidth(230)

        def changed():
            self._set(key, combo.currentData())
            if on_change:
                on_change(combo.currentData())

        combo.currentIndexChanged.connect(changed)
        self._add_row(SettingRow(title, subtitle, combo, self))

    def _spin_row(self, title: str, subtitle: str, key: str, lo: int, hi: int) -> None:
        stepper = Stepper(self)
        stepper.setRange(lo, hi)
        stepper.setValue(int(getattr(self.cfg, key)))
        stepper.valueChanged.connect(lambda v, k=key: self._set(k, int(v)))
        self._add_row(SettingRow(title, subtitle, stepper, self))

    def _line_row(self, title: str, subtitle: str, key: str, placeholder: str) -> None:
        edit = TextField(placeholder, self)
        edit.setFixedWidth(240)
        edit.setText(str(getattr(self.cfg, key)))
        edit.editingFinished.connect(lambda k=key, e=edit: self._set(k, e.text().strip()))
        self._add_row(SettingRow(title, subtitle, edit, self))

    # ------------------------------------------------------------ linhas altas
    def _folder_row(self) -> None:
        row, column = self._custom_row("Pasta de destino")
        line = QHBoxLayout()
        line.setSpacing(10)
        self.folder_label = Muted(self.cfg.download_dir, row)
        button = Button("Escolher", "folder", "secondary", row)
        line.addWidget(self.folder_label, 1)
        line.addWidget(button)
        column.addLayout(line)

        def choose():
            path = QFileDialog.getExistingDirectory(self, "Pasta de destino",
                                                    self.cfg.download_dir)
            if path:
                self._set("download_dir", path)
                self.folder_label.setText(path)
                self.download_dir_changed.emit(path)

        button.clicked.connect(choose)
        self._add_row(row)

    def _ytdlp_channel_changed(self, channel: str) -> None:
        self.ytdlp_channel_changed.emit(str(channel))

    def _filename_template_row(self) -> None:
        row, column = self._custom_row(
            "Nome do arquivo",
            "Modelo do yt-dlp. A prévia usa dados de exemplo e não acessa a rede.",
        )
        self.filename_template_edit = TextField("%(title)s.%(ext)s", row)
        self.filename_template_edit.setText(self.cfg.filename_template)
        self.filename_template_edit.textChanged.connect(self._refresh_template_preview)
        self.filename_template_edit.editingFinished.connect(
            lambda: self._set("filename_template", self.filename_template_edit.text().strip())
        )
        column.addWidget(self.filename_template_edit)

        tokens = QHBoxLayout()
        tokens.setSpacing(6)
        for label, value in (
            ("Título", "%(title)s"), ("Canal", "%(uploader)s"),
            ("Data", "%(upload_date)s"), ("ID", "%(id)s"),
            ("Resolução", "%(height)sp"),
        ):
            button = Button(label, "plus", "ghost", row)
            button.setToolTip(f"Inserir {value}")
            button.clicked.connect(lambda _checked=False, token=value: self._insert_template_token(token))
            tokens.addWidget(button)
        tokens.addStretch(1)
        column.addLayout(tokens)
        self.filename_template_preview = Muted("", row)
        self.filename_template_preview.setAccessibleName("Prévia do nome do arquivo")
        column.addWidget(self.filename_template_preview)
        self._refresh_template_preview()
        self._add_row(row)

    def _insert_template_token(self, token: str) -> None:
        self.filename_template_edit.insert(token)
        self.filename_template_edit.setFocus()

    def _refresh_template_preview(self) -> None:
        if not hasattr(self, "filename_template_preview"):
            return
        self.filename_template_preview.setText(
            "Prévia: " + render_filename_preview(self.filename_template_edit.text(), None, "mp4")
        )

    def _gpu_row(self) -> None:
        row, column = self._custom_row(
            "Placa detectada",
            "Downloads normais são rede e cópia de arquivo. A GPU entra em recortes exatos "
            "e na conversão após baixar; nesses casos o vídeo precisa ser reencodado.")
        self.gpu_label = Muted("A detecção será feita ao abrir Configurações.", row)
        column.addWidget(self.gpu_label)
        self._add_row(row)

    def _dependencies_row(self) -> None:
        row, column = self._custom_row(
            "Componentes",
            "yt-dlp, FFmpeg e Deno vêm das fontes oficiais com SHA-256 conferido; "
            "o motor do Whisper acompanha o instalador.")
        self.versions = Muted("—", row)
        line = QHBoxLayout()
        line.setSpacing(12)
        line.addWidget(self.versions, 1)
        button = PrimaryButton("Verificar componentes", "update", row)
        button.clicked.connect(self.update_requested.emit)
        line.addWidget(button)
        column.addLayout(line)
        self._add_row(row)

    def _diagnostics_row(self) -> None:
        row, column = self._custom_row(
            "Diagnóstico",
            "Gera um ZIP com os logs para anexar a uma issue. Cookies, senhas de proxy, "
            "tokens de URL e a sua pasta de usuário são removidos antes.")
        line = QHBoxLayout()
        line.setSpacing(12)
        line.addStretch(1)
        button = Button("Exportar diagnóstico", "download", "secondary", row)
        button.clicked.connect(self.diagnostics_export_requested.emit)
        line.addWidget(button)
        column.addLayout(line)
        self._add_row(row)

    def _app_update_row(self) -> None:
        row, column = self._custom_row(
            "Nova versão do aplicativo",
            "Consulta as Releases do GitHub e avisa na faixa inferior da janela.")
        # Mesmo arranjo da linha "Componentes": texto à esquerda, botão à direita
        # na mesma altura — antes o botão descia sozinho e criava um vão.
        line = QHBoxLayout()
        line.setSpacing(12)
        line.addWidget(Muted(f"Versão instalada: {APP_VERSION}", row), 1)
        button = PrimaryButton("Verificar agora", "update", row)
        button.clicked.connect(self.app_update_requested.emit)
        line.addWidget(button)
        column.addLayout(line)
        self._add_row(row)

    def _cookies_file_row(self) -> None:
        """Arquivo cookies.txt: caminho, seletor e o passo a passo de exportação."""
        row, column = self._custom_row(
            "Arquivo cookies.txt (recomendado)",
            "É o caminho que o YouTube aceita de forma confiável. Tem prioridade sobre o "
            "navegador e o conteúdo nunca é copiado para os logs.")

        line = QHBoxLayout()
        line.setSpacing(10)
        self.cookies_edit = TextField("Nenhum arquivo selecionado", row)
        self.cookies_edit.setText(str(self.cfg.cookies_file))
        self.cookies_edit.setClearButtonEnabled(True)
        self.cookies_edit.editingFinished.connect(
            lambda: self._set_cookies_file(self.cookies_edit.text().strip()))

        pick = Button("Escolher", "folder", "secondary", row)
        pick.clicked.connect(self._pick_cookies_file)
        import_button = Button("Importar para o app", "download", "secondary", row)
        import_button.setToolTip("Cria uma cópia privada e protegida nos dados do aplicativo")
        import_button.clicked.connect(self._import_cookies_file)

        # Ajuda embutida, não modal: um diálogo modal com texto longo já travou o
        # aplicativo no passado, porque a máscara deixava a tela inacessível.
        self.howto_btn = Button("Como exportar", "help", "ghost", row)
        self.howto_btn.setCheckable(True)
        self.howto_btn.toggled.connect(self._toggle_cookie_help)

        line.addWidget(self.cookies_edit, 1)
        line.addWidget(pick)
        line.addWidget(import_button)
        line.addWidget(self.howto_btn)
        column.addLayout(line)

        self.cookies_status = Muted("", row)
        column.addWidget(self.cookies_status)

        self.cookies_help = Muted(EXPORT_INSTRUCTIONS, row)
        self.cookies_help.hide()
        column.addWidget(self.cookies_help)

        self.cookies_guide_btn = Button("Abrir guia do yt-dlp", "external", "secondary", row)
        self.cookies_guide_btn.setToolTip("Abre o guia oficial do yt-dlp no navegador")
        self.cookies_guide_btn.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl("https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp")))
        extension_btn = Button("Instalar Get cookies.txt LOCALLY", "external", "secondary", row)
        extension_btn.setToolTip("Extensão recomendada para Chrome, Edge e navegadores Chromium")
        extension_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(
            "https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc")))
        actions = QWidget(row)
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(8)
        actions_layout.addWidget(self.cookies_guide_btn)
        actions_layout.addWidget(extension_btn)
        actions_layout.addStretch(1)
        column.addWidget(actions)

        self._refresh_cookies_status()
        self._add_row(row)

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

    def _import_cookies_file(self) -> None:
        source = Path(self.cookies_edit.text().strip())
        try:
            destination, warning = import_cookie_file(source)
        except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
            self._set_status(f"Não foi possível proteger a cópia: {exc}", ok=False)
            return
        self.cookies_edit.setText(str(destination))
        self._set_cookies_file(str(destination))
        self._set_status(
            warning or "Cópia privada criada. Você já pode apagar o original da pasta Downloads.",
            ok=not warning,
        )

    def _refresh_cookies_status(self) -> None:
        """Valida o arquivo na hora de escolher, não na hora de baixar."""
        path = (self.cfg.cookies_file or "").strip()
        if not path:
            self.cookies_status.setText("")
            return
        target = Path(path)
        if not target.is_file():
            self._set_status("Arquivo não encontrado neste caminho.", ok=False)
            return
        try:
            head = target.read_text(encoding="utf-8", errors="replace")[:4096]
        except OSError as exc:
            self._set_status(f"Não deu para ler o arquivo: {exc}", ok=False)
            return
        if "netscape http cookie file" not in head.lower() and "\t" not in head:
            self._set_status(
                "Não parece um cookies.txt no formato Netscape. Reexporte com uma "
                "extensão que gere esse formato.", ok=False)
            return
        domains = "youtube.com" in head or "google.com" in head
        age = cookie_age_days(target)
        if age > 14:
            self._set_status(
                f"O arquivo tem {age} dias e pode ter expirado; faça uma nova exportação.",
                ok=False,
            )
        else:
            self._set_status(
                (f"Arquivo válido, com cookies do YouTube (há {age} dia(s))." if domains
                 else "Formato válido, mas sem cookies de youtube.com — confira a exportação."),
                ok=True,
            )

    def _set_status(self, message: str, ok: bool) -> None:
        self.cookies_status.setText(("✓ " if ok else "⚠ ") + message)
        self.cookies_status.setStyleSheet(
            f"color: {theme.color('success' if ok else 'warning')};")

    def _toggle_cookie_help(self, shown: bool) -> None:
        self.cookies_help.setVisible(shown)
        self.howto_btn.setText("Ocultar ajuda" if shown else "Como exportar")

    # --------------------------------------------------------------- estado
    def _apply_theme(self, value: str) -> None:
        theme.set_mode(value)
        self.theme_changed.emit(value)

    def _apply_language(self, value: str) -> None:
        self.language_changed.emit(value)

    def set_gpu(self, gpu: GpuInfo) -> None:
        self.gpu = gpu
        self.gpu_label.setText(gpu.summary)
        self.codec_combo.clear()
        for codec in gpu.encoders:
            self.codec_combo.addItem(GPU_ENCODER_LABELS[codec], userData=codec)
        if not gpu.encoders:
            self.codec_combo.addItem("Nenhum encoder de GPU disponível", userData="")
            self.codec_row.setEnabled(False)
        else:
            for i in range(self.codec_combo.count()):
                if self.codec_combo.itemData(i) == self.cfg.transcode_codec:
                    self.codec_combo.setCurrentIndex(i)
                    break

    def request_gpu_detection(self) -> None:
        """Agenda a detecção uma única vez, quando há alguém para vê-la."""
        if not self._gpu_requested:
            self._gpu_requested = True
            self.gpu_label.setText("Detectando a GPU…")
            self.gpu_detection_requested.emit()

    def showEvent(self, event):  # noqa: N802 - assinatura do Qt
        super().showEvent(event)
        self.request_gpu_detection()

    def hideEvent(self, event):  # noqa: N802 - assinatura do Qt
        """Não deixa uma alteração recente pendente se o usuário sair da aba."""
        if self._save_timer.isActive():
            self._save_timer.stop()
            self.cfg.save()
        super().hideEvent(event)

    @staticmethod
    def friendly_ffmpeg_version(version: str) -> str:
        """``N-126716-g3faf…-20260920`` → ``build de desenvolvimento (20/09/2026)``."""
        match = re.match(r"^N-\d+-g[0-9a-f]+-(\d{4})(\d{2})(\d{2})$", version or "")
        if match:
            year, month, day = match.groups()
            return f"build de desenvolvimento ({day}/{month}/{year})"
        match = re.match(r"^n?(\d+\.\d+(?:\.\d+)?)", version or "")
        return match.group(1) if match else (version or "—")

    def set_versions(self, ytdlp: str, ffmpeg: str, transcription_runtime: str = "") -> None:
        text = f"yt-dlp {ytdlp or '—'} · FFmpeg {self.friendly_ffmpeg_version(ffmpeg)}"
        if transcription_runtime:
            text += f"\n{transcription_runtime}"
        self.versions.setText(text)

