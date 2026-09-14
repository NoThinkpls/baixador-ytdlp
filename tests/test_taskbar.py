"""Testes sem Windows para a camada isolada da barra de tarefas."""
from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from baixador_ytdlp.taskbar import (
    TBPF_NOPROGRESS,
    TBPF_NORMAL,
    TaskbarProgress,
    _hresult_failed,
)


class TaskbarProgressTests(unittest.TestCase):
    def test_hresults_keep_the_high_bit_semantics(self) -> None:
        self.assertFalse(_hresult_failed(0))
        self.assertFalse(_hresult_failed(1))
        self.assertTrue(_hresult_failed(0x80004005))

    def test_progress_is_clamped_and_uses_normal_state(self) -> None:
        taskbar = TaskbarProgress()
        taskbar._failed = False
        taskbar._call = Mock(return_value=True)

        taskbar.set_value(123, 180)

        self.assertEqual(taskbar._state, TBPF_NORMAL)
        self.assertEqual(taskbar._call.call_args_list[0].args[0], 10)
        self.assertEqual(taskbar._call.call_args_list[1].args[0], 9)
        self.assertEqual(taskbar._call.call_args_list[1].args[-2].value, 100)

    def test_clear_resets_the_native_state(self) -> None:
        taskbar = TaskbarProgress()
        taskbar._failed = False
        taskbar._call = Mock(return_value=True)
        taskbar.set_value(123, 25)

        taskbar.clear(123)

        self.assertEqual(taskbar._state, TBPF_NOPROGRESS)
        self.assertEqual(taskbar._call.call_args_list[-1].args[0], 10)

    def test_completion_uses_full_progress_and_flashes(self) -> None:
        taskbar = TaskbarProgress()
        with patch.object(taskbar, "set_value") as set_value, \
                patch.object(taskbar, "flash") as flash:
            taskbar.complete(321)

        set_value.assert_called_once_with(321, 100)
        flash.assert_called_once_with(321)


if __name__ == "__main__":
    unittest.main()
