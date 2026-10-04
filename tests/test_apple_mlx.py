"""Regressões do backend MLX para transcrição no Apple Silicon."""
from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from baixador_ytdlp.transcription import Transcriber, TranscriptionOptions


class AppleMlxTests(unittest.TestCase):
    def test_apple_silicon_prefers_mlx_when_the_runtime_is_present(self) -> None:
        with patch("baixador_ytdlp.transcription._is_apple_silicon", return_value=True), \
                patch("baixador_ytdlp.transcription._mlx_available", return_value=True):
            backend, device, compute, label = Transcriber._detect_hardware()
        self.assertEqual((backend, device, compute), ("mlx", "metal", "float16"))
        self.assertIn("MLX", label)

    def test_mlx_result_is_normalized_like_faster_whisper(self) -> None:
        calls = []

        def transcribe(*args, **kwargs):
            calls.append((args, kwargs))
            return {
                "language": "pt",
                "segments": [{
                    "start": 0.0, "end": 2.0, "text": "Olá, ação!",
                    "avg_logprob": -0.1, "no_speech_prob": 0.01,
                    "words": [
                        {"word": " Olá", "start": 0.0, "end": 0.8},
                        {"word": ",", "start": 0.8, "end": 0.9},
                        {"word": " ação!", "start": 0.9, "end": 2.0},
                    ],
                }],
            }

        transcriber = Transcriber(SimpleNamespace(), lambda _message: None, lambda _progress: None,
                                  force_cpu=True)
        transcriber.backend = "mlx"
        transcriber._model_path = Path("/modelos/whisper-medium-mlx-fixado")
        options = TranscriptionOptions(Path("entrada.wav"), Path("saida.srt"), model_size="medium")
        with patch.dict(sys.modules, {"mlx_whisper": SimpleNamespace(transcribe=transcribe)}), \
                patch("baixador_ytdlp.transcription._load_wav_samples", return_value="amostras"):
            raw, info = transcriber._decode(Path("entrada.wav"), options, duration=10)
        self.assertEqual(calls[0][0][0], "amostras")

        self.assertEqual(info.language, "pt")
        self.assertEqual(raw[0]["text"], "Olá, ação!")
        self.assertEqual(raw[0]["words"][1]["text"], ",")
        self.assertEqual(calls[0][1]["path_or_hf_repo"],
                         str(Path("/modelos/whisper-medium-mlx-fixado")))
        self.assertTrue(calls[0][1]["word_timestamps"])

    def test_mlx_does_not_receive_beam_search_options(self) -> None:
        calls = []

        def transcribe(*args, **kwargs):
            calls.append(kwargs)
            return {"language": "pt", "segments": []}

        transcriber = Transcriber(SimpleNamespace(), lambda _message: None, lambda _progress: None,
                                  force_cpu=True)
        transcriber.backend = "mlx"
        transcriber._model_path = Path("/modelos/mlx")
        for model in ("medium", "large-v3"):
            options = TranscriptionOptions(Path("e.wav"), Path("s.srt"), model_size=model)
            with patch.dict(sys.modules, {"mlx_whisper": SimpleNamespace(transcribe=transcribe)}), \
                    patch("baixador_ytdlp.transcription._load_wav_samples", return_value="x"):
                transcriber._decode(Path("e.wav"), options, duration=10)
        for kwargs in calls:
            self.assertNotIn("beam_size", kwargs)
            self.assertNotIn("patience", kwargs)

    def test_faster_whisper_gets_samples_instead_of_decoding_with_pyav(self) -> None:
        with patch("baixador_ytdlp.transcription._load_wav_samples", return_value="amostras"):
            self.assertEqual(Transcriber._audio_input(Path("a.wav")), "amostras")

    def test_helper_process_sees_the_app_ffmpeg_on_path(self) -> None:
        import os

        with tempfile.TemporaryDirectory() as folder, \
                patch.dict(os.environ, {"PATH": "/usr/bin"}):
            Transcriber(SimpleNamespace(ffmpeg=Path(folder) / "ffmpeg"),
                        lambda _m: None, lambda _p: None, force_cpu=True)
            self.assertEqual(os.environ["PATH"].split(os.pathsep)[0], folder)

    def test_common_failures_become_plain_portuguese(self) -> None:
        from baixador_ytdlp.transcription import friendly_transcription_error

        cases = {
            "[Errno 2] No such file or directory: 'ffmpeg'": "FFmpeg",
            "[Errno 28] No space left on device": "espaço",
            "open() got an unexpected keyword argument 'metadata_errors'": "desatualizado",
            "<urlopen error [SSL: CERTIFICATE_VERIFY_FAILED]>": "conexão",
        }
        for raw, expected in cases.items():
            message = friendly_transcription_error(RuntimeError(raw))
            self.assertIn(expected, message)
            self.assertIn(raw, message)

    def test_mlx_fallback_logs_the_cause_with_traceback(self) -> None:
        transcriber = Transcriber(SimpleNamespace(), lambda _message: None, lambda _progress: None,
                                  force_cpu=True)
        transcriber.backend = "mlx"
        with patch.object(Transcriber, "_load_model") as load, \
                self.assertLogs("baixador_ytdlp", level="WARNING") as captured:
            transcriber._switch_mlx_to_cpu("medium", FileNotFoundError("ffmpeg"))
        load.assert_called_once_with("medium")
        self.assertEqual(transcriber.backend, "faster-whisper")
        self.assertIn("FileNotFoundError", captured.output[0])
        self.assertIsNotNone(captured.records[0].exc_info)

    @unittest.skipUnless(importlib.util.find_spec("numpy"), "numpy ausente")
    def test_wav_is_loaded_in_memory_without_needing_ffmpeg_on_path(self) -> None:
        import wave

        from baixador_ytdlp.transcription import _load_wav_samples

        with tempfile.TemporaryDirectory() as temporary_dir:
            path = Path(temporary_dir) / "audio.wav"
            with wave.open(str(path), "wb") as handle:
                handle.setnchannels(1)
                handle.setsampwidth(2)
                handle.setframerate(16000)
                handle.writeframes(b"\x00\x00\x00\x40\x00\xc0")
            samples = _load_wav_samples(path)

        self.assertEqual(samples.dtype.name, "float32")
        self.assertEqual(samples.tolist(), [0.0, 0.5, -0.5])

    def test_model_download_uses_an_immutable_revision(self) -> None:
        downloads = []

        def snapshot_download(**kwargs):
            downloads.append(kwargs)
            return str(Path(kwargs["cache_dir"]) / "model")

        with tempfile.TemporaryDirectory() as temporary_dir, patch.dict(sys.modules, {
            "huggingface_hub": SimpleNamespace(snapshot_download=snapshot_download),
        }), patch("baixador_ytdlp.models.MODEL_DIR", Path(temporary_dir)):
            path = Transcriber._pinned_model_path("medium", mlx=False)

        self.assertEqual(path, Path(temporary_dir) / "ctranslate2" / "model")
        self.assertEqual(downloads[0]["repo_id"], "Systran/faster-whisper-medium")
        self.assertRegex(downloads[0]["revision"], r"^[0-9a-f]{40}$")


if __name__ == "__main__":
    unittest.main()
