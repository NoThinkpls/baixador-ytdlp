from __future__ import annotations

import unittest

from baixador_ytdlp.ui.windowing import (
    HTBOTTOMRIGHT,
    HTLEFT,
    HTTOP,
    _resize_hit_test,
)


class WindowResizeTests(unittest.TestCase):
    def test_edges_and_corners_have_native_resize_regions(self) -> None:
        self.assertEqual(_resize_hit_test(100, 100, 900, 700, 100, 400, 12), HTLEFT)
        self.assertEqual(_resize_hit_test(100, 100, 900, 700, 400, 100, 12), HTTOP)
        self.assertEqual(_resize_hit_test(100, 100, 900, 700, 899, 699, 12), HTBOTTOMRIGHT)

    def test_center_is_not_a_resize_region(self) -> None:
        self.assertIsNone(_resize_hit_test(100, 100, 900, 700, 500, 400, 12))
