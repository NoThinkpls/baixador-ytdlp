"""Regressões para encerramento de árvores de subprocessos."""
from __future__ import annotations

import signal
import unittest
from unittest.mock import Mock, patch

from baixador_ytdlp.processes import terminate_process_tree


class ProcessTreeTests(unittest.TestCase):
    def test_posix_cancels_the_whole_process_group(self) -> None:
        process = Mock(pid=4321)
        process.poll.return_value = None
        sigkill = getattr(signal, "SIGKILL", 9)
        sigterm = getattr(signal, "SIGTERM", 15)

        # Estes atributos POSIX não existem nos módulos do runner Windows.
        with patch("baixador_ytdlp.processes.IS_WINDOWS", False), \
                patch("baixador_ytdlp.processes.signal.SIGKILL", sigkill, create=True), \
                patch("baixador_ytdlp.processes.os.killpg", create=True) as kill_group, \
                patch("baixador_ytdlp.processes.threading.Thread") as thread:
            terminate_process_tree(process)
            kill_group.assert_called_once_with(4321, sigterm)
            force_target = thread.call_args.kwargs["target"]
            with patch("baixador_ytdlp.processes.time.sleep"):
                force_target()
            self.assertEqual(kill_group.call_args_list[-1].args, (4321, sigkill))
        process.kill.assert_not_called()

    def test_windows_uses_taskkill_for_descendants(self) -> None:
        process = Mock(pid=8765)
        process.poll.return_value = None

        with patch("baixador_ytdlp.processes.IS_WINDOWS", True), \
                patch("baixador_ytdlp.processes.subprocess.Popen") as popen, \
                patch("baixador_ytdlp.processes.threading.Thread") as thread:
            terminate_process_tree(process)
            process.send_signal.assert_called_once()
            force_target = thread.call_args.kwargs["target"]
            with patch("baixador_ytdlp.processes.time.sleep"):
                force_target()
            command = popen.call_args.args[0]
        self.assertEqual(command, ["taskkill", "/T", "/F", "/PID", "8765"])


if __name__ == "__main__":
    unittest.main()
