"""Regressões do backend MLX para transcrição no Apple Silicon."""
from __future__ import annotations

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
        with patch.dict(sys.modules, {"mlx_whisper": SimpleNamespace(transcribe=transcribe)}):
            raw, info = transcriber._decode(Path("entrada.wav"), options, duration=10)

        self.assertEqual(info.language, "pt")
        self.assertEqual(raw[0]["text"], "Olá, ação!")
        self.assertEqual(raw[0]["words"][1]["text"], ",")
        self.assertEqual(calls[0][1]["path_or_hf_repo"],
                         "/modelos/whisper-medium-mlx-fixado")
        self.assertTrue(calls[0][1]["word_timestamps"])

    def test_model_download_uses_an_immutable_revision(self) -> None:
        downloads = []

        def snapshot_download(**kwargs):
            downloads.append(kwargs)
            return str(Path(kwargs["cache_dir"]) / "model")

        with tempfile.TemporaryDirectory() as temporary_dir, patch.dict(sys.modules, {
            "huggingface_hub": SimpleNamespace(snapshot_download=snapshot_download),
        }), patch("baixador_ytdlp.transcription.MODEL_DIR", Path(temporary_dir)):
            path = Transcriber._pinned_model_path("medium", mlx=False)

        self.assertEqual(path, Path(temporary_dir) / "ctranslate2" / "model")
        self.assertEqual(downloads[0]["repo_id"], "Systran/faster-whisper-medium")
        self.assertRegex(downloads[0]["revision"], r"^[0-9a-f]{40}$")


if __name__ == "__main__":
    unittest.main()
