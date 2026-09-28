"""Página 'Configurações': pastas, qualidade, aparência, GPU e dependências.

As opções ficam em listas agrupadas — um bloco arredondado por assunto, com
linhas separadas por fios finos. É o padrão dos Ajustes da Apple e substitui o
cartão flutuante por opção, que empilhava dezenas de retângulos na tela.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime

import subprocess
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QPainter, QPen
from PySide6.QtWidgets import (QAbstractButton, QFileDialog, QGridLayout, QHBoxLayout,
                               QLabel, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget)

from ..config import APP_VERSION, Settings
from ..cookies import EXPORT_INSTRUCTIONS, cookie_age_days, import_cookie_file
from ..filename_preview import render_filename_preview
from ..gpu import GPU_ENCODER_LABELS, GpuInfo
from ..hardware import default_fragments, default_parallel_downloads, usable_cores
from . import icons, theme
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


def _search_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.casefold())
    return "".join(char for char in normalized if not unicodedata.combining(char))


class CategoryCard(QAbstractButton):
    """Cartão de navegação com título e resumo, sem lógica de configuração."""

    def __init__(self, title: str, icon_name: str, parent=None):
        super().__init__(parent)
        self.setObjectName("settingsCategoryCard")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAccessibleName(title)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(76)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(12)
        self.icon_label = QLabel(self)
        self.icon_label.setObjectName("settingsCategoryIcon")
        self.icon_label.setFixedSize(36, 36)
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.icon_label)
        labels = QVBoxLayout()
        labels.setSpacing(3)
        labels.addWidget(Headline(title, self))
        self.summary = Muted("", self)
        self.summary.setWordWrap(False)
        self.summary.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        labels.addWidget(self.summary)
        layout.addLayout(labels, 1)
        arrow = QLabel(self)
        arrow.setPixmap(icons.pixmap("chevron-right", theme.color("text_tertiary"), 16))
        layout.addWidget(arrow)
        self.icon_name = icon_name
        self.refresh_icon()

    def refresh_icon(self) -> None:
        self.icon_label.setPixmap(icons.pixmap(self.icon_name, theme.color("accent_text"), 19))

    def paintEvent(self, _event):  # noqa: N802 - assinatura do Qt
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = "surface_active" if self.isDown() else (
            "surface_hover" if self.underMouse() or self.hasFocus() else "surface")
        painter.setBrush(theme.qcolor(color))
        painter.setPen(QPen(theme.qcolor("accent" if self.hasFocus() else "border"), 1))
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), theme.RADIUS_CARD,
                                theme.RADIUS_CARD)


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
        self._gpu_detected = False
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
        outer.setSpacing(0)
        self.pages = QStackedWidget(self)
        outer.addWidget(self.pages)
        self._categories: list[tuple[str, str, CategoryCard, ScrollColumn]] = []
        self._search_rows: list[tuple[int, str, str, QWidget]] = []

        self.landing = ScrollColumn(self, spacing=18)
        self.pages.addWidget(self.landing)
        self.landing.add(PageHeader(
            "Configurações", "Tudo fica salvo nesta máquina, no seu perfil de usuário.", self))
        self.search_edit = TextField("Buscar uma opção — ex.: proxy, legendas, tema", self)
        self.search_edit.setObjectName("settingsSearch")
        self.search_edit.setAccessibleName("Buscar nas configurações")
        self.search_edit.setMaximumWidth(480)
        self.search_edit.textChanged.connect(self._filter_settings)
        self.landing.add(self.search_edit)
        self.results = QWidget(self)
        self.results_layout = QVBoxLayout(self.results)
        self.results_layout.setContentsMargins(0, 0, 0, 0)
        self.results_layout.setSpacing(8)
        self.results.hide()
        self.landing.add(self.results)
        self.cards_host = QWidget(self)
        self.cards_layout = QGridLayout(self.cards_host)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.setHorizontalSpacing(10)
        self.cards_layout.setVerticalSpacing(10)
        self.landing.add(self.cards_host)
        self.landing.add_stretch()

        self._category("Downloads", "O que acontece com cada arquivo que você baixa.", "download")
        self._section("Onde salvar")
        self._folder_row()
        self._switch_row("Perguntar a pasta em cada download",
                         "Deixa a opção “Escolher a pasta” já ligada na página Baixar.",
                         "ask_output_dir")
        self._section("Arquivo")
        self._filename_template_row()
        self._combo_row("Formato padrão do vídeo",
                        "Container usado quando você não muda nada na página Baixar.",
                        [("MP4", "mp4"), ("MKV", "mkv"), ("WebM", "webm"),
                         ("Manter original", "original")],
                        "container")
        self._switch_row("Priorizar compatibilidade (H.264)",
                         "Escolhe H.264/AAC em vez do melhor codec. Roda em qualquer TV, "
                         "mas com qualidade um pouco menor no mesmo tamanho.", "prefer_h264")
        self._section("Fila")
        self._switch_row("Retomar a fila ao reabrir",
                         "Itens interrompidos voltam como pendentes e continuam os arquivos .part.",
                         "resume_queue")

        self._category("Rede e desempenho", "Velocidade, limites e falhas de conexão.", "queue")
        self._section("Velocidade")
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
        self._section("Quando a conexão falhar")
        self._line_row(
            "Proxy",
            "Opcional. Ex.: http://127.0.0.1:8080. Credenciais são ocultadas nos logs.",
            "proxy", "sem proxy",
        )
        self._spin_row("Retentativas automáticas",
                       "Para quedas de rede, limite temporário do site e respostas 5xx. "
                       "Erros de link, conta ou conteúdo removido não são repetidos.",
                       "auto_retry_attempts", 0, 5)
        self._spin_row("Espera entre retentativas (segundos)",
                       "A cada nova tentativa a espera aumenta um pouco, para não sobrecarregar o site.",
                       "auto_retry_delay", 1, 60)

        self._category("Legendas e extras", "Capas, metadados e legendas.", "captions")
        self._section("Extras do arquivo")
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
        self._section("Legendas e cortes")
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

        self._category("Contas e cookies", "Acesso a conteúdo restrito.", "link")
        self._section("Acesso a conteúdo restrito")
        self._cookies_file_row()
        self._combo_row("Cookies do navegador",
                        "Só é usado quando não há arquivo cookies.txt. No Windows funciona "
                        "apenas com Firefox e derivados — os navegadores Chromium criptografam "
                        "os cookies de um jeito que nenhum programa externo consegue abrir.",
                        BROWSERS, "cookies_browser")
        self._category("Conversão por GPU", "Muda codec e tamanho, sem melhorar a fonte.", "chip")
        self._section("Placa de vídeo")
        self._gpu_row()
        self._section("Conversão")
        self._switch_row("Converter após baixar (GPU)",
                         "Aplica a conversão ao arquivo final de cada download.", "transcode_enabled")
        self.conversion_hint = Muted(
            "Desligada: os arquivos ficam exatamente como vieram do site.", self)
        self.conversion_hint.setContentsMargins(16, 0, 0, 0)
        self.page.add(self.conversion_hint)
        self._section("Ajustes da conversão")
        self.conversion_label = self._section_label
        self.conversion_group = self._group
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

        self._category("Aparência e notificações", "Visual e avisos do aplicativo.", "settings")
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

        self._category("Atualizações e sobre", "Componentes e novas versões.", "update")
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
        self._category("Avançado", "Extrator, histórico e ferramentas.", "document")
        self._section("Extrator e ferramentas")
        self._line_row("Ajustes do extrator (avançado)",
                       "Repassado ao yt-dlp como --extractor-args. Vazio na dúvida. "
                       "Ex.: youtube:player_client=default,web_safari",
                       "extractor_args", "vazio")
        self._switch_row(
            "Usar ferramentas instaladas no sistema",
            "Permite procurar yt-dlp e FFmpeg no PATH quando a cópia verificada do app não existe. "
            "Mantenha desligado para maior segurança.",
            "allow_system_tools",
        )
        self._section("Histórico")
        self._switch_row("Guardar o que foi baixado",
                         "Alimenta a página Histórico. Fica só na sua máquina.",
                         "history_enabled")
        self._spin_row("Itens guardados", "Os mais antigos são descartados.",
                       "history_limit", 20, 1000)
        self.page.add_stretch()
        self._layout_cards()
        self.pages.setCurrentWidget(self.landing)
        self._refresh_summaries()
        self._toggle_conversion(self.cfg.transcode_enabled)

    def _category(self, title: str, description: str, icon_name: str) -> None:
        if self._categories:
            self.page.add_stretch()
        index = len(self._categories)
        card = CategoryCard(title, icon_name, self.cards_host)
        card.clicked.connect(lambda _checked=False, i=index: self._show_category(i))
        detail = QWidget(self)
        layout = QVBoxLayout(detail)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        breadcrumb = QHBoxLayout()
        breadcrumb.setSpacing(8)
        back = Button("Configurações", "chevron-left", "ghost", detail)
        back.setAccessibleName("Voltar para Configurações")
        back.clicked.connect(self._show_landing)
        breadcrumb.addWidget(back)
        breadcrumb.addWidget(Muted("›", detail))
        breadcrumb.addWidget(Headline(title, detail), 1)
        layout.addLayout(breadcrumb)
        layout.addWidget(Muted(description, detail))
        self.page = ScrollColumn(detail, spacing=10)
        layout.addWidget(self.page, 1)
        self.pages.addWidget(detail)
        self._categories.append((title, description, card, self.page))
        self._group = None

    def _show_landing(self) -> None:
        self._refresh_summaries()
        self.pages.setCurrentWidget(self.landing)

    def _show_category(self, index: int, row: QWidget | None = None) -> None:
        if index < 0 or index >= len(self._categories):
            return
        self.pages.setCurrentIndex(index + 1)
        if row is not None:
            if (self.conversion_group.isAncestorOf(row) and
                    not self.cfg.transcode_enabled):
                row = next(candidate for category, title, _subtitle, candidate in self._search_rows
                           if category == index and title == "Converter após baixar (GPU)")
            scroll = self._categories[index][3]
            QTimer.singleShot(0, lambda: scroll.ensureWidgetVisible(row, 0, 24))

    def _layout_cards(self) -> None:
        # O viewport pode manter a largura antiga até o próximo ciclo do Qt.
        # A largura da página já foi atualizada neste resizeEvent.
        width = self.width() - 56
        columns = 2 if width >= 720 else 1
        rows = (len(self._categories) + columns - 1) // columns
        self.cards_host.setFixedHeight(rows * 76 + (rows - 1) * 10)
        self.cards_host.setMaximumWidth(max(320, width - 24))
        while self.cards_layout.count():
            self.cards_layout.takeAt(0)
        order = (0, 2, 4, 5, 1, 3, 6, 7)
        for position, index in enumerate(order):
            card = self._categories[index][2]
            self.cards_layout.addWidget(card, position // columns, position % columns)
        for column in range(2):
            self.cards_layout.setColumnStretch(column, 1 if column < columns else 0)
        self.cards_layout.invalidate()
        self.cards_host.updateGeometry()
        self.cards_layout.activate()
        self.landing.column.invalidate()
        self.landing.column.activate()

    def resizeEvent(self, event):  # noqa: N802 - assinatura do Qt
        super().resizeEvent(event)
        QTimer.singleShot(0, self._layout_cards)

    def _refresh_summaries(self) -> None:
        cfg = self.cfg
        name = Path(cfg.download_dir).name or cfg.download_dir
        subtitles = (
            f"{cfg.container.upper()} · {name} · "
            "repetições sob confirmação",
            f"Até {cfg.max_parallel_downloads} {'download' if cfg.max_parallel_downloads == 1 else 'downloads'} · "
            f"{'sem limite de banda' if not cfg.limit_rate else 'limite ' + cfg.limit_rate}",
            "Capa e metadados · " + ("legendas ligadas" if cfg.write_subs else "legendas desligadas"),
            "Sem cookies" if not cfg.cookies_file and not cfg.cookies_browser else
            ("Arquivo cookies.txt" if cfg.cookies_file else f"Navegador {cfg.cookies_browser}"),
            ("Ligada" if cfg.transcode_enabled else "Desligada") + " · " +
            ("GPU disponível" if self.gpu.encoders else
             ("sem encoder disponível" if self._gpu_detected else "detecção pendente")),
            {"auto": "Seguir o sistema", "light": "Claro", "dark": "Escuro"}.get(cfg.theme, cfg.theme)
            + " · " + ("notificações ligadas" if cfg.tray_notifications else "notificações desligadas"),
            f"Versão {APP_VERSION} · yt-dlp {'nightly' if cfg.ytdlp_channel == 'nightly' else 'estável'}",
            "Extrator, histórico e ferramentas",
        )
        for (_title, _desc, card, _scroll), summary in zip(self._categories, subtitles):
            card.summary.setText(summary)
            card.refresh_icon()

    def _filter_settings(self, query: str) -> None:
        while self.results_layout.count():
            item = self.results_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        terms = _search_key(query).split()
        self.results.setVisible(bool(terms))
        self.cards_host.setVisible(not terms)
        if not terms:
            return
        title_matches = [(index, title, row) for index, title, _subtitle, row in self._search_rows
                         if all(term in _search_key(title) for term in terms)]
        matches = title_matches or [
            (index, title, row) for index, title, subtitle, row in self._search_rows
            if all(term in _search_key(f"{title} {subtitle} {self._categories[index][0]}")
                   for term in terms)
        ]
        for index, title, row in matches:
            category = self._categories[index][0]
            hint = " · ative a conversão" if (
                self.conversion_group.isAncestorOf(row) and not self.cfg.transcode_enabled) else ""
            button = Button(f"{title}{hint}  ›  {category}", "search", "secondary", self.results)
            button.setAccessibleName(f"Abrir {title} em {category}")
            button.clicked.connect(lambda _checked=False, i=index, target=row:
                                   self._show_category(i, target))
            self.results_layout.addWidget(button)
        if not matches:
            self.results_layout.addWidget(Muted("Nenhuma opção encontrada.", self.results))

    def _toggle_conversion(self, enabled: bool) -> None:
        self.conversion_hint.setVisible(not enabled)
        self.conversion_label.setVisible(enabled)
        self.conversion_group.setVisible(enabled)

    # ---------------------------------------------------------- construtores
    def _section(self, title: str) -> None:
        """Abre um novo bloco agrupado; as linhas seguintes entram nele."""
        label = SectionLabel(title, self)
        label.setContentsMargins(4, 14, 0, 2)
        label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.page.add(label)
        self._section_label = label
        self._group = InsetGroup(self)
        self._group.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        self.page.add(self._group)

    def _add_row(self, row: QWidget) -> QWidget:
        if self._group is None:
            self._section("Geral")
        title = row.property("settingsTitle") or getattr(getattr(row, "title", None), "text", lambda: "")()
        subtitle = row.property("settingsSubtitle") or getattr(
            getattr(row, "subtitle", None), "text", lambda: "")()
        if title:
            self._search_rows.append((len(self._categories) - 1, title, subtitle, row))
        return self._group.add_row(row)

    def _custom_row(self, title: str, subtitle: str = "") -> tuple[QWidget, QVBoxLayout]:
        """Linha alta: título, explicação e conteúdo livre embaixo."""
        row = QWidget(self._group)
        row.setProperty("settingsTitle", title)
        row.setProperty("settingsSubtitle", subtitle)
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
        if key == "transcode_enabled":
            switch.checkedChanged.connect(self._toggle_conversion)
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
        self.filename_template_edit = TextField("%(title)s.%(ext)s", self)
        self.filename_template_edit.setMinimumWidth(240)
        self.filename_template_edit.setText(self.cfg.filename_template)
        self.filename_template_edit.textChanged.connect(self._refresh_template_preview)
        self.filename_template_edit.editingFinished.connect(
            lambda: self._set("filename_template", self.filename_template_edit.text().strip())
        )
        row = SettingRow("Nome do arquivo", "Prévia do nome do arquivo", self.filename_template_edit, self)
        # A prévia acompanha o campo sem abrir uma seção alta de botões.
        self.filename_template_preview = row.subtitle
        self.filename_template_preview.setAccessibleName("Prévia do nome do arquivo")
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
            "Downloads e trechos usam yt-dlp/FFmpeg sem aceleração forçada. A GPU pode ser "
            "usada na conversão após baixar e nas ferramentas locais de vídeo.")
        line = QHBoxLayout()
        self.gpu_label = Muted("A detecção será feita ao abrir Configurações.", row)
        line.addWidget(self.gpu_label, 1)
        detect = Button("Detectar de novo", "refresh", "secondary", row)
        detect.clicked.connect(self._detect_gpu_again)
        line.addWidget(detect)
        column.addLayout(line)
        self._add_row(row)

    def _detect_gpu_again(self) -> None:
        self.gpu_label.setText("Detectando a GPU…")
        self.gpu_detection_requested.emit()

    def _dependencies_row(self) -> None:
        row, column = self._custom_row(
            "Componentes",
            "yt-dlp, FFmpeg e Deno vêm das fontes oficiais com SHA-256 conferido; "
            "o motor do Whisper acompanha o instalador.")
        self.versions = Muted("—", row)
        line = QHBoxLayout()
        line.setSpacing(12)
        line.addWidget(self.versions, 1)
        button = PrimaryButton("Verificar agora", "update", row)
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
        line = QHBoxLayout()
        line.setSpacing(12)
        self.app_update_status = Muted("", row)
        line.addWidget(self.app_update_status, 1)
        column.addLayout(line)
        self.refresh_update_status()
        self._add_row(row)

    def refresh_update_status(self) -> None:
        checked_at = self.cfg.app_update_checked_at
        last = (datetime.fromtimestamp(checked_at).strftime("%d/%m/%Y %H:%M")
                if checked_at else "ainda não verificado")
        self.app_update_status.setText(f"Versão instalada: {APP_VERSION} · Última checagem: {last}")

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
        self._refresh_summaries()
        self.theme_changed.emit(value)

    def _apply_language(self, value: str) -> None:
        self.language_changed.emit(value)

    def set_gpu(self, gpu: GpuInfo) -> None:
        self.gpu = gpu
        self._gpu_detected = True
        self._refresh_summaries()
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
            from .. import runtime

            if not runtime.embedded_cuda_available():
                transcription_runtime = re.sub(r"\(CUDA\)", "(CPU)", transcription_runtime)
                transcription_runtime += " · CUDA indisponível: DLLs ausentes ou incompatíveis"
            text += f"\n{transcription_runtime}"
        self.versions.setText(text)

