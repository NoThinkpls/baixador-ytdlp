"""Conjunto de ícones próprio, desenhado em traço fino.

O aplicativo não usa mais o conjunto Fluent da Microsoft. Estes ícones são
vetores simples (24x24, traço arredondado) no espírito dos SF Symbols da Apple
e da iconografia do Discord: geometria clara, peso uniforme e leitura boa em
tamanhos pequenos.

Cada ícone é gerado na cor pedida — não há PNG de cor fixa, então o mesmo
desenho serve para o tema claro e para o escuro sem recorte nem halo.
"""
from __future__ import annotations

from PySide6.QtCore import QByteArray, QSize, Qt
from PySide6.QtGui import QGuiApplication, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

# Corpo interno de cada SVG. O invólucro (viewBox, cor e espessura) é montado
# em _svg(); manter só o miolo aqui evita repetir o cabeçalho 40 vezes.
_BODY: dict[str, str] = {
    # ---------------------------------------------------------- navegação
    "download": '<path d="M12 3v11"/><path d="M7.5 10.5 12 15l4.5-4.5"/>'
                '<path d="M4 17.5v1.5A1.5 1.5 0 0 0 5.5 20.5h13a1.5 1.5 0 0 0 1.5-1.5v-1.5"/>',
    "queue": '<path d="M12 3 21 7.6 12 12.2 3 7.6 12 3Z"/><path d="M3 12.4 12 17l9-4.6"/>'
             '<path d="M3 16.8 12 21.4l9-4.6"/>',
    "captions": '<rect x="3" y="5" width="18" height="14" rx="3"/>'
                '<path d="M10 10.4a2.6 2.6 0 1 0 0 3.2"/><path d="M17 10.4a2.6 2.6 0 1 0 0 3.2"/>',
    "tools": '<path d="M4 7h7"/><path d="M16 7h4"/><path d="M4 12h3"/><path d="M12 12h8"/>'
             '<path d="M4 17h9"/><path d="M18 17h2"/><circle cx="13.5" cy="7" r="2.2"/>'
             '<circle cx="9.5" cy="12" r="2.2"/><circle cx="15.5" cy="17" r="2.2"/>',
    "history": '<path d="M3.5 12a8.5 8.5 0 1 0 2.6-6.1"/><path d="M3.2 4.6v4.2h4.2"/>'
               '<path d="M12 7.8V12l3 1.8"/>',
    "settings": '<circle cx="12" cy="12" r="3"/>'
                '<path d="M19.4 14.2a1.6 1.6 0 0 0 .32 1.77l.06.06a1.9 1.9 0 1 1-2.7 2.7l-.05-.06a1.6 1.6 0 0 0-1.78-.32 1.6 1.6 0 0 0-.97 1.47v.17a1.9 1.9 0 1 1-3.8 0v-.09a1.6 1.6 0 0 0-1.05-1.47 1.6 1.6 0 0 0-1.77.32l-.06.06a1.9 1.9 0 1 1-2.7-2.7l.06-.06a1.6 1.6 0 0 0 .32-1.77 1.6 1.6 0 0 0-1.47-.97H3.5a1.9 1.9 0 1 1 0-3.8h.09a1.6 1.6 0 0 0 1.47-1.05 1.6 1.6 0 0 0-.32-1.77l-.06-.06a1.9 1.9 0 1 1 2.7-2.7l.06.06a1.6 1.6 0 0 0 1.77.32h.08a1.6 1.6 0 0 0 .97-1.47V3.5a1.9 1.9 0 1 1 3.8 0v.09a1.6 1.6 0 0 0 .97 1.47 1.6 1.6 0 0 0 1.78-.32l.05-.06a1.9 1.9 0 1 1 2.7 2.7l-.06.06a1.6 1.6 0 0 0-.32 1.77v.08a1.6 1.6 0 0 0 1.47.97h.17a1.9 1.9 0 1 1 0 3.8h-.09a1.6 1.6 0 0 0-1.47.97Z"/>',
    # ------------------------------------------------------------- ações
    "search": '<circle cx="10.8" cy="10.8" r="6.3"/><path d="m20 20-4.7-4.7"/>',
    "paste": '<path d="M9 4.5h6M8 6.5H6.5A1.5 1.5 0 0 0 5 8v11.5A1.5 1.5 0 0 0 6.5 21h11a1.5 1.5 0 0 0 1.5-1.5V8a1.5 1.5 0 0 0-1.5-1.5H16"/>'
             '<rect x="8.5" y="2.8" width="7" height="3.7" rx="1.3"/>',
    "folder": '<path d="M3.5 7.2A1.7 1.7 0 0 1 5.2 5.5h3.4l2 2.4h8.2a1.7 1.7 0 0 1 1.7 1.7v8.2a1.7 1.7 0 0 1-1.7 1.7H5.2a1.7 1.7 0 0 1-1.7-1.7Z"/>',
    "save": '<path d="M12 3.5v9.5"/><path d="M8 9.5 12 13.5l4-4"/>'
            '<path d="M4.5 16v3A1.5 1.5 0 0 0 6 20.5h12a1.5 1.5 0 0 0 1.5-1.5v-3"/>',
    "trash": '<path d="M4 6.5h16"/><path d="M9.5 6.5V5a1.5 1.5 0 0 1 1.5-1.5h2A1.5 1.5 0 0 1 14.5 5v1.5"/>'
             '<path d="M6.5 6.5 7.4 19a1.6 1.6 0 0 0 1.6 1.5h6a1.6 1.6 0 0 0 1.6-1.5l.9-12.5"/>'
             '<path d="M10.5 10.5v6"/><path d="M13.5 10.5v6"/>',
    "close": '<path d="M6.5 6.5 17.5 17.5"/><path d="M17.5 6.5 6.5 17.5"/>',
    "refresh": '<path d="M20 12a8 8 0 1 1-2.4-5.7"/><path d="M20.3 3.6v4.2h-4.2"/>',
    "plus": '<path d="M12 5.5v13"/><path d="M5.5 12h13"/>',
    "check": '<path d="m5 12.8 4.6 4.4L19 6.6"/>',
    "info": '<circle cx="12" cy="12" r="8.5"/><path d="M12 11v5.2"/><circle cx="12" cy="7.9" r="1" fill="currentColor" stroke="none"/>',
    "help": '<circle cx="12" cy="12" r="8.5"/>'
            '<path d="M9.6 9.4a2.5 2.5 0 1 1 3.3 2.4c-.6.2-.9.8-.9 1.4v.5"/>'
            '<circle cx="12" cy="16.6" r="1" fill="currentColor" stroke="none"/>',
    "warning": '<path d="M10.6 4.2 2.9 17.4A1.6 1.6 0 0 0 4.3 19.9h15.4a1.6 1.6 0 0 0 1.4-2.5L13.4 4.2a1.6 1.6 0 0 0-2.8 0Z"/>'
               '<path d="M12 9.4v4"/><circle cx="12" cy="16.4" r="1" fill="currentColor" stroke="none"/>',
    "success": '<circle cx="12" cy="12" r="8.5"/><path d="m8.2 12.3 2.6 2.5 5-5.2"/>',
    "error": '<circle cx="12" cy="12" r="8.5"/><path d="M9.4 9.4 14.6 14.6"/><path d="M14.6 9.4 9.4 14.6"/>',
    "pause": '<rect x="8" y="5.5" width="3" height="13" rx="1.3"/>'
             '<rect x="13" y="5.5" width="3" height="13" rx="1.3"/>',
    "play": '<path d="M8.5 5.8v12.4a.8.8 0 0 0 1.22.68l9.6-6.2a.8.8 0 0 0 0-1.36l-9.6-6.2a.8.8 0 0 0-1.22.68Z"/>',
    "stop": '<rect x="6.5" y="6.5" width="11" height="11" rx="2.4"/>',
    "sweep": '<path d="M14.5 3.5 20 9"/><path d="m12.9 5.1 5.9 5.9-6.6 6.6a2.4 2.4 0 0 1-1.5.7l-5.2.5.5-5.2a2.4 2.4 0 0 1 .7-1.5Z"/>'
             '<path d="M3.5 20.5h8"/>',
    "update": '<path d="M12 20.5a8.5 8.5 0 1 0-8.5-8.5"/><path d="M3.2 7.5v4.2h4.2"/>'
              '<path d="M12 8.4v5.4"/><path d="m9.6 11.4 2.4 2.4 2.4-2.4"/>',
    "external": '<path d="M13.5 4.5H19.5V10.5"/><path d="m19.5 4.5-8 8"/>'
                '<path d="M18 14v4.8a1.7 1.7 0 0 1-1.7 1.7H5.7A1.7 1.7 0 0 1 4 18.8V8.2a1.7 1.7 0 0 1 1.7-1.7H10.5"/>',
    "document": '<path d="M13.5 3.5H7A1.8 1.8 0 0 0 5.2 5.3v13.4A1.8 1.8 0 0 0 7 20.5h10a1.8 1.8 0 0 0 1.8-1.8V8.8Z"/>'
                '<path d="M13.5 3.5v5.3h5.3"/><path d="M8.6 13h6.8"/><path d="M8.6 16.4h4.4"/>',
    "media": '<rect x="3" y="5" width="18" height="14" rx="2.6"/><path d="M3 9.2h18"/>'
             '<path d="M7.6 5v4.2"/><path d="M16.4 5v4.2"/>'
             '<path d="M10.4 12.4v4.2l3.8-2.1Z"/>',
    "chip": '<rect x="7" y="7" width="10" height="10" rx="2.2"/><rect x="3.6" y="3.6" width="16.8" height="16.8" rx="4" opacity="0"/>'
            '<path d="M9.6 3.8v3.2"/><path d="M14.4 3.8v3.2"/><path d="M9.6 17v3.2"/><path d="M14.4 17v3.2"/>'
            '<path d="M3.8 9.6h3.2"/><path d="M3.8 14.4h3.2"/><path d="M17 9.6h3.2"/><path d="M17 14.4h3.2"/>',
    "link": '<path d="M10.2 13.8a3.6 3.6 0 0 0 5.4.4l2.6-2.6a3.6 3.6 0 0 0-5.1-5.1L11.7 8"/>'
            '<path d="M13.8 10.2a3.6 3.6 0 0 0-5.4-.4l-2.6 2.6a3.6 3.6 0 0 0 5.1 5.1L12.3 16"/>',
    "chevron-down": '<path d="m6.5 9.5 5.5 5.5 5.5-5.5"/>',
    "chevron-right": '<path d="m9.5 6.5 5.5 5.5-5.5 5.5"/>',
    "sidebar-collapse": '<rect x="4" y="4" width="16" height="16" rx="3"/>'
                        '<path d="M9 4v16M13.5 9.2 10.7 12l2.8 2.8"/>',
    "sidebar-expand": '<rect x="4" y="4" width="16" height="16" rx="3"/>'
                      '<path d="M9 4v16m1.7-10.8 2.8 2.8-2.8 2.8"/>',
    "minus": '<path d="M5.5 12h13"/>',
    "sparkle": '<path d="M12 3.5 13.9 9 19.5 11l-5.6 2L12 18.5 10.1 13 4.5 11 10.1 9Z"/>'
               '<path d="M18.5 4v3"/><path d="M20 5.5h-3"/>',
    "cut": '<circle cx="6.4" cy="17.6" r="2.6"/><circle cx="17.6" cy="17.6" r="2.6"/>'
           '<path d="M8.3 15.7 18.5 4.5"/><path d="M15.7 15.7 5.5 4.5"/>',
}

_TEMPLATE = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
    'stroke="{color}" stroke-width="{width}" stroke-linecap="round" '
    'stroke-linejoin="round" color="{color}">{body}</svg>'
)

_CACHE: dict[tuple, QIcon] = {}


def _svg(name: str, color: str, width: float) -> bytes:
    body = _BODY.get(name, _BODY["info"])
    return _TEMPLATE.format(color=color, width=width, body=body).encode("utf-8")


def icon(name: str, color: str, size: int = 20, width: float = 1.7) -> QIcon:
    """Devolve o ícone já rasterizado na cor e no tamanho pedidos."""
    key = (name, color, size, width)
    cached = _CACHE.get(key)
    if cached is not None:
        return cached

    ratio = 2.0
    app = QGuiApplication.instance()
    if app is not None:
        ratio = max(2.0, float(app.devicePixelRatio()))

    renderer = QSvgRenderer(QByteArray(_svg(name, color, width)))
    pixmap = QPixmap(QSize(int(size * ratio), int(size * ratio)))
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    renderer.render(painter)
    painter.end()
    pixmap.setDevicePixelRatio(ratio)

    result = QIcon(pixmap)
    _CACHE[key] = result
    return result


def pixmap(name: str, color: str, size: int = 20, width: float = 1.7) -> QPixmap:
    """Mesma arte, quando o destino é um QLabel em vez de um botão."""
    return icon(name, color, size, width).pixmap(QSize(size, size))


def clear_cache() -> None:
    """Chamado na troca de tema: as cores mudaram, os ícones precisam ser refeitos."""
    _CACHE.clear()
