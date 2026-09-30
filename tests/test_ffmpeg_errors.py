"""Erros do FFmpeg, do disco e do sistema de arquivos chegam ao usuário em português claro."""
from __future__ import annotations

import unittest

from baixador_ytdlp.probe import friendly_error
from baixador_ytdlp.workers import _failure_log_text


class FfmpegErrorTests(unittest.TestCase):
    def test_codigo_de_dados_invalidos_do_ffmpeg(self) -> None:
        # 3199971767 = 0xBEBBB1B7 = AVERROR_INVALIDDATA
        message = friendly_error("ERROR: ffmpeg exited with code 3199971767")
        self.assertIn("dados inválidos", message)
        self.assertNotIn("3199971767", message)
        self.assertIn("dados inválidos", friendly_error(
            "in.mp4: Invalid data found when processing input"))
        self.assertIn("dados inválidos", friendly_error("moov atom not found"))

    def test_outro_codigo_do_ffmpeg_mostra_o_codigo_e_a_saida(self) -> None:
        message = friendly_error("ERROR: ffmpeg exited with code 1")
        self.assertIn("FFmpeg terminou com erro (código 1)", message)
        self.assertIn("diagnóstico", message)

    def test_ferramenta_em_arquivo_sem_a_faixa_necessaria(self) -> None:
        for text in ("Stream map '0:v:0' matches no streams.",
                     "Output file #0 does not contain any stream"):
            self.assertIn("não tem a faixa", friendly_error(text), text)

    def test_disco_cheio(self) -> None:
        for text in ("OSError: [Errno 28] No space left on device",
                     "[WinError 112] There is not enough space on the disk",
                     "ERROR: unable to write data: disk full"):
            self.assertIn("sem espaço", friendly_error(text), text)

    def test_caminho_longo_demais(self) -> None:
        for text in ("OSError: [Errno 36] File name too long: 'x'",
                     "[WinError 206] The filename or extension is too long"):
            self.assertIn("longo demais", friendly_error(text), text)

    def test_sem_permissao(self) -> None:
        self.assertIn("permissão", friendly_error("PermissionError: [Errno 13] Permission denied"))

    def test_erros_do_ytdlp_continuam_como_antes(self) -> None:
        self.assertIn("restrição de idade", friendly_error(
            "ERROR: [youtube] x: Sign in to confirm your age."))
        self.assertEqual(friendly_error("ERROR: algo inesperado"), "algo inesperado")


class FailureLogTests(unittest.TestCase):
    def test_mensagem_sem_traceback_nao_deixa_o_log_vazio(self) -> None:
        text = _failure_log_text("O motor de transcrição encerrou inesperadamente.", "")
        self.assertIn("encerrou inesperadamente", text)
        self.assertTrue(text.strip())

    def test_mensagem_e_traceback_juntos(self) -> None:
        text = _failure_log_text("Falha", "Traceback (most recent call last):\n  ...")
        self.assertTrue(text.startswith("Falha\n"))
        self.assertIn("Traceback", text)
        self.assertEqual(_failure_log_text("", ""), "(sem detalhe)")


if __name__ == "__main__":
    unittest.main()
