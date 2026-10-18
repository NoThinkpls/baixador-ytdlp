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

    def _fake_mlx(self, transcriber, frames: int = 18000, on_window=None):
        """mlx_whisper falso que, como o 0.4.3, só devolve o resultado no fim."""
        seen = []
        module = SimpleNamespace(tqdm=SimpleNamespace(tqdm=None))

        def transcribe(*_args, **_kwargs):
            with module.tqdm.tqdm(total=frames, unit="frames", disable=True) as bar:
                for _ in range(frames // 3000):
                    bar.update(3000)
                    seen.append(list(progress))
                    if on_window:
                        on_window()
            return {"language": "pt", "segments": [
                {"start": 0.0, "end": frames / 100.0, "text": "fim", "words": []}]}

        progress: list[int] = []
        statuses: list[str] = []
        transcriber.progress = progress.append
        transcriber.status = statuses.append
        package = SimpleNamespace(transcribe=transcribe)
        modules = {"mlx_whisper": package, "mlx_whisper.transcribe": module}
        return modules, progress, statuses, seen

    def _mlx_transcriber(self) -> Transcriber:
        transcriber = Transcriber(SimpleNamespace(), lambda _m: None, lambda _p: None, force_cpu=True)
        transcriber.backend = "mlx"
        transcriber._model_path = Path("/modelos/mlx")
        return transcriber

    def test_mlx_progress_moves_while_the_audio_is_being_decoded(self) -> None:
        transcriber = self._mlx_transcriber()
        modules, progress, statuses, seen = self._fake_mlx(transcriber)
        options = TranscriptionOptions(Path("e.wav"), Path("s.srt"), model_size="large-v3")
        with patch.dict(sys.modules, modules), \
                patch("baixador_ytdlp.transcription._load_wav_samples", return_value="x"):
            transcriber._decode(Path("e.wav"), options, duration=0)
        # Antes a barra só andava depois de transcribe() terminar o áudio inteiro.
        self.assertEqual(seen[0], [28])
        self.assertEqual(seen[-1][-1], 90)
        self.assertEqual(progress, sorted(progress))
        self.assertIn("Transcrevendo: 0:30 de 3:00 do áudio", statuses[0])
        # O tqdm original volta ao lugar depois da chamada.
        self.assertIsNone(modules["mlx_whisper.transcribe"].tqdm.tqdm)

    def test_mlx_cancel_takes_effect_in_the_middle_of_the_audio(self) -> None:
        from baixador_ytdlp.transcription import TranscriptionCancelled

        transcriber = self._mlx_transcriber()
        modules, _progress, _statuses, seen = self._fake_mlx(
            transcriber, on_window=lambda: transcriber.cancel())
        options = TranscriptionOptions(Path("e.wav"), Path("s.srt"))
        with patch.dict(sys.modules, modules), \
                patch("baixador_ytdlp.transcription._load_wav_samples", return_value="x"), \
                self.assertRaises(TranscriptionCancelled):
            transcriber._decode(Path("e.wav"), options, duration=180)
        self.assertEqual(len(seen), 1)

    def test_mlx_preparation_ends_at_15_with_the_model_ready(self) -> None:
        transcriber = self._mlx_transcriber()
        progress: list[int] = []
        statuses: list[str] = []
        transcriber.progress = progress.append
        transcriber.status = statuses.append
        with patch("baixador_ytdlp.transcription.download_model_snapshot",
                   return_value=Path("/modelos/mlx")), \
                patch.object(Transcriber, "_preload_mlx_weights") as preload:
            transcriber._prepare_mlx("medium")
        preload.assert_called_once_with()
        self.assertEqual(progress[-1], 15)
        self.assertTrue(statuses[-1].startswith("Modelo pronto:"))

    def test_decode_progress_estimates_time_left_from_the_real_pace(self) -> None:
        from baixador_ytdlp.transcription import DecodeProgress

        now = [0.0]
        progress: list[int] = []
        statuses: list[str] = []
        tracker = DecodeProgress(statuses.append, progress.append, 600, clock=lambda: now[0])
        now[0] = 40.0
        tracker.update(120)     # 2 min de áudio em 40 s: faltam 8 min de áudio, ~160 s
        tracker.update(60)      # tempo repetido não faz a barra voltar
        self.assertEqual(progress, [16 + int(74 * 120 / 600)])
        self.assertEqual(statuses, ["Transcrevendo: 2:00 de 10:00 do áudio · cerca de 3 min restantes"])

if __name__ == "__main__":
    unittest.main()
