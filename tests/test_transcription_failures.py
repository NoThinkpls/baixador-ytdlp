"""Contratos para falhas do runtime de transcrição.

Estes testes não carregam pesos nem requerem GPU: eles garantem que erros de
empacotamento e VAD não sejam mascarados como um fallback de CUDA.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from baixador_ytdlp.transcription import (
    Transcriber,
    TranscriptionOptions,
    _is_cuda_failure,
    _snapshot_download_with_symlink_retry,
    friendly_transcription_error,
)


class TranscriptionFailureTests(unittest.TestCase):
    @staticmethod
    def _onnx_no_such_file(message: str) -> BaseException:
        error_type = type("NoSuchFile", (RuntimeError,), {"__module__": "onnxruntime.capi"})
        return error_type(message)

    @staticmethod
    def _transcriber(status=None) -> Transcriber:
        return Transcriber(
            SimpleNamespace(), status or (lambda _message: None), lambda _progress: None, force_cpu=True,
        )

    def test_classifica_somente_falhas_reais_de_cuda(self) -> None:
        self.assertFalse(_is_cuda_failure(self._onnx_no_such_file("silero_decoder_v5.onnx missing")))
        self.assertFalse(_is_cuda_failure(FileNotFoundError("silero_decoder_v5.onnx missing")))
        self.assertFalse(_is_cuda_failure(TypeError("bad VAD parameter")))
        self.assertTrue(_is_cuda_failure(RuntimeError("Library cublas64_12.dll is not found")))

    def test_erro_do_vad_na_gpu_nao_dispara_fallback_para_cpu(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            media, audio = root / "input.wav", root / "audio.wav"
            media.write_bytes(b"input")
            audio.write_bytes(b"audio")
            transcriber = self._transcriber()
            transcriber.device = "cuda"
            opts = TranscriptionOptions(media, root / "output.srt")
            error = self._onnx_no_such_file("silero_decoder_v5.onnx: File doesn't exist")
            with patch.object(transcriber, "_prepare_model_for"), \
                    patch.object(transcriber, "_extract_audio", return_value=audio), \
                    patch.object(transcriber, "_duration", return_value=0), \
                    patch.object(transcriber, "_decode", side_effect=error), \
                    patch.object(transcriber, "_switch_to_cpu") as fallback:
                with self.assertRaises(type(error)):
                    transcriber.run(opts)
        fallback.assert_not_called()

    def test_falha_cuda_na_decodificacao_dispara_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            media, audio = root / "input.wav", root / "audio.wav"
            media.write_bytes(b"input")
            audio.write_bytes(b"audio")
            transcriber = self._transcriber()
            transcriber.device = "cuda"
            opts = TranscriptionOptions(media, root / "output.srt")
            info = SimpleNamespace(language="pt", language_probability=0.0)
            with patch.object(transcriber, "_prepare_model_for"), \
                    patch.object(transcriber, "_extract_audio", return_value=audio), \
                    patch.object(transcriber, "_duration", return_value=0), \
                    patch.object(
                        transcriber,
                        "_decode",
                        side_effect=[RuntimeError("Library cublas64_12.dll is not found"), ([], info)],
                    ), patch.object(transcriber, "_switch_to_cpu") as fallback, \
                    patch.object(transcriber, "_write"):
                transcriber.run(opts)
        fallback.assert_called_once()

    def test_mensagem_de_asset_ausente_orienta_reinstalacao(self) -> None:
        message = friendly_transcription_error(
            self._onnx_no_such_file("silero_decoder_v5.onnx failed: File doesn't exist")
        )
        self.assertIn("instalação está incompleta", message)
        self.assertIn("silero_decoder_v5.onnx", message)

    def test_winerror_1314_e_retentado_uma_vez(self) -> None:
        calls = []
        error = OSError("symlink denied")
        error.winerror = 1314

        def snapshot_download(**kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                raise error
            return "cache/model"

        self.assertEqual(
            _snapshot_download_with_symlink_retry(snapshot_download, repo_id="owner/model"),
            "cache/model",
        )
        self.assertEqual(len(calls), 2)

    def test_fallback_por_oom_tenta_gpu_no_proximo_item(self) -> None:
        messages: list[str] = []
        transcriber = self._transcriber(messages.append)
        transcriber._cuda_profile = ("faster-whisper", "cuda", "float16", "CUDA — teste")
        transcriber._retry_cuda_after_oom = True
        with patch.object(transcriber, "_discard_model") as discard:
            transcriber._restore_cuda_after_oom()
        discard.assert_called_once()
        self.assertEqual((transcriber.backend, transcriber.device, transcriber.compute_type),
                         ("faster-whisper", "cuda", "float16"))
        self.assertTrue(any("Tentando a GPU novamente" in message for message in messages))


if __name__ == "__main__":
    unittest.main()
