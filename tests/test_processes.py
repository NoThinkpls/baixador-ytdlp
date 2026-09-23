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

    def test_windows_without_job_calls_taskkill_before_anything_else(self) -> None:
        """Sem Job Object, a árvore precisa ser morta enquanto o pai ainda vive.

        A versão 1.8.0 tentava CTRL_BREAK (que falha num app sem console),
        caía em terminate() do pai e nunca chamava o taskkill: o filho real do
        yt-dlp.exe onefile e o FFmpeg ficavam órfãos.
        """
        process = Mock(pid=8765)
        process.poll.return_value = None
        process.send_signal.side_effect = OSError(6, "sem console")

        with patch("baixador_ytdlp.processes.IS_WINDOWS", True), \
                patch("baixador_ytdlp.processes.subprocess.Popen") as popen:
            terminate_process_tree(process)
        command = popen.call_args.args[0]
        self.assertTrue(command[0].lower().endswith("taskkill.exe"))
        self.assertEqual(command[1:], ["/T", "/F", "/PID", "8765"])
        process.send_signal.assert_not_called()
        process.terminate.assert_not_called()

    def test_windows_with_job_terminates_the_job(self) -> None:
        process = Mock(pid=1)
        kernel = Mock()
        with patch("baixador_ytdlp.processes.IS_WINDOWS", True), \
                patch.dict("baixador_ytdlp.processes._JOBS", {process: 1234}, clear=True), \
                patch("baixador_ytdlp.processes._kernel32", return_value=kernel), \
                patch("baixador_ytdlp.processes.subprocess.Popen") as popen:
            terminate_process_tree(process)
        kernel.TerminateJobObject.assert_called_once_with(1234, 1)
        popen.assert_not_called()

if __name__ == "__main__":
    unittest.main()
