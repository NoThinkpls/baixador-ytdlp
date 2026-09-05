"""Utilitários Win32 independentes da interface Qt."""
from __future__ import annotations

HTLEFT, HTRIGHT, HTTOP, HTTOPLEFT, HTTOPRIGHT = 10, 11, 12, 13, 14
HTBOTTOM, HTBOTTOMLEFT, HTBOTTOMRIGHT = 15, 16, 17


def _resize_hit_test(left: int, top: int, right: int, bottom: int,
                     x: int, y: int, border: int) -> int | None:
    """Devolve a região Win32 de redimensionamento, se o cursor estiver nela."""
    on_left = x <= left + border
    on_right = x >= right - border - 1
    on_top = y <= top + border
    on_bottom = y >= bottom - border - 1
    if not (on_left or on_right or on_top or on_bottom):
        return None
    if on_left and on_top:
        return HTTOPLEFT
    if on_right and on_top:
        return HTTOPRIGHT
    if on_left and on_bottom:
        return HTBOTTOMLEFT
    if on_right and on_bottom:
        return HTBOTTOMRIGHT
    if on_top:
        return HTTOP
    if on_bottom:
        return HTBOTTOM
    return HTLEFT if on_left else HTRIGHT
