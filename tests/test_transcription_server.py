"""Servidor de transcrição: nada de cancelamento perdido nem resultado descartado."""
from __future__ import annotations

import importlib.util
import os
import queue
import unittest
from unittest.mock import MagicMock, patch

HAS_QT = importlib.util.find_spec("PySide6") is not None

if HAS_QT:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QCoreApplication

    from baixador_ytdlp.workers import PersistentTranscriptionWorker


class _DeadProcess:
    """Processo que termina logo após enviar o resultado."""

    pid = 0

    def start(self) -> None:
        pass

    def is_alive(self) -> bool:
        return False

    def join(self, _timeout=None) -> None:
        pass

    def close(self) -> None:
        pass


@unittest.skipUnless(HAS_QT, "requer PySide6")
class PersistentWorkerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def test_resultado_enviado_antes_da_saida_nao_vira_falha(self) -> None:
        worker = PersistentTranscriptionWorker(MagicMock())
        worker._context = MagicMock()
        worker._context.Process.return_value = _DeadProcess()
        worker._events = queue.Queue()
        worker._active_job = 1
        worker._busy = True
        worker._events.put((1, "finished", "saida.srt"))
        finished, failed = [], []
        worker.finished_ok.connect(finished.append)
        worker.failed.connect(failed.append)
        with patch("baixador_ytdlp.workers.attach_pid_to_kill_job", return_value=0), \
                patch("baixador_ytdlp.workers.release_job"):
            worker.run()
        self.assertEqual(finished, ["saida.srt"])
        self.assertEqual(failed, [])

    def test_servidor_troca_item_ativo_sob_trava(self) -> None:
        # O cancelamento e a troca de item precisam usar a mesma trava; a ordem
        # antiga (define o item e só depois limpa o evento) perdia o cancelamento.
        import inspect

        from baixador_ytdlp import transcription

        source = inspect.getsource(transcription.transcription_server_main).replace("\r", "")
        self.assertIn(
            "with state_lock:\n"
            "                cancel_event.clear()\n"
            "                pause_event.clear()\n"
            "                active_job[0] = int(job_id)", source)


if __name__ == "__main__":
    unittest.main()
