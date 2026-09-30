"""Trecho longo do YouTube em partes paralelas."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from baixador_ytdlp.config import Settings
from baixador_ytdlp.downloader import DownloadOptions, DownloadRunner, Progress
from baixador_ytdlp.parallel_section import (
    ParallelSectionRunner, create_runner, plan_pieces,
)

URL = "https://www.youtube.com/live/example"


def _opts(**kwargs) -> DownloadOptions:
    return DownloadOptions(kwargs.pop("url", URL), kwargs.pop("output_dir", "downloads"), **kwargs)


class PlanTests(unittest.TestCase):
    def test_long_section_is_split_into_contiguous_pieces(self) -> None:
        pieces = plan_pieces(_opts(section_start="00:53:45", section_end="02:16:30"), Settings())
        self.assertEqual(len(pieces), 4)  # padrão: 4 partes simultâneas
        self.assertEqual(pieces[0][0], 3225)
        self.assertEqual(pieces[-1][1], 8190)
        for (_, end), (start, _) in zip(pieces, pieces[1:], strict=False):
            self.assertEqual(end, start)

    def test_number_of_parts_follows_the_setting(self) -> None:
        long_cut = _opts(section_start="0", section_end="7200")
        for parts, expected in ((1, 0), (2, 2), (3, 3), (8, 8), (50, 8), (0, 0), (-3, 0)):
            pieces = plan_pieces(long_cut, Settings(section_parallel_parts=parts))
            self.assertEqual(len(pieces), expected, parts)

    def test_parts_never_exceed_what_the_length_allows(self) -> None:
        ten_minutes = _opts(section_start="0", section_end="900")
        self.assertEqual(len(plan_pieces(ten_minutes, Settings(section_parallel_parts=8))), 3)

    def test_short_or_unsupported_cases_stay_in_a_single_process(self) -> None:
        cfg = Settings()
        self.assertEqual(plan_pieces(_opts(section_start="0", section_end="300"), cfg), [])
        long_cut = dict(section_start="0", section_end="3600")
        self.assertEqual(plan_pieces(_opts(url="https://example.invalid/v", **long_cut), cfg), [])
        self.assertEqual(plan_pieces(_opts(audio_only=True, **long_cut), cfg), [])
        self.assertEqual(plan_pieces(_opts(playlist=True, **long_cut), cfg), [])
        self.assertEqual(plan_pieces(_opts(**long_cut), Settings(sponsorblock=True)), [])
        self.assertEqual(plan_pieces(_opts(section_start="10:00"), cfg), [])  # sem fim nem duração
        self.assertNotEqual(plan_pieces(_opts(section_start="10:00", media_duration=4000.0), cfg), [])

    def test_factory_returns_plain_runner_without_a_plan(self) -> None:
        tools = SimpleNamespace(ytdlp=Path("yt-dlp"), bin_dir=Path("bin"), ffmpeg=Path("ffmpeg"))
        self.assertIsInstance(create_runner(_opts(), Settings(), tools), DownloadRunner)
        long_cut = _opts(section_start="0", section_end="3600")
        self.assertIsInstance(create_runner(long_cut, Settings(), tools), ParallelSectionRunner)


class _FakeSub:
    """Cada parte grava um arquivo com o nome que o yt-dlp usaria."""

    def __init__(self, opts, cfg, tc, fail: bool = False):
        self.opts, self.cfg, self.fail = opts, cfg, fail
        self.files: list[Path] = []
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True

    def run(self, on_progress):
        if self.fail:
            raise RuntimeError("falha de rede")
        folder = Path(self.opts.output_dir)
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / "Titulo [id].mp4"
        path.write_bytes(b"x")
        on_progress(Progress(status="finished", percent=100.0))
        self.files = [path]
        return self.files

    def tail(self, lines: int = 40) -> str:
        return ""


def _fake_ffmpeg(first_pts: str = "-2.0"):
    """ffprobe devolve a sobra antes do quadro-chave; o concat grava o arquivo final."""
    def run(args, timeout=60):
        if "ffprobe" in args[0]:
            return SimpleNamespace(returncode=0, stdout=first_pts + ",", stderr="")
        Path(args[-1]).write_bytes(b"joined")
        return SimpleNamespace(returncode=0, stderr="")
    return run


class RunnerTests(unittest.TestCase):
    def _runner(self, out: str) -> ParallelSectionRunner:
        tools = SimpleNamespace(ytdlp=Path("yt-dlp"), bin_dir=Path("bin"),
                                ffmpeg=Path("ffmpeg"), ffprobe=Path("ffprobe"))
        opts = _opts(output_dir=out, section_start="0", section_end="1800")
        cfg = Settings(section_parallel_parts=6)
        return ParallelSectionRunner(opts, cfg, tools, plan_pieces(opts, cfg))

    def test_pieces_are_aligned_to_keyframes_joined_and_cleaned_up(self) -> None:
        seen = []

        class Recording(_FakeSub):
            def __init__(self, opts, cfg, tc):
                super().__init__(opts, cfg, tc)
                seen.append((opts.section_start, opts.section_end))

        with tempfile.TemporaryDirectory() as tmp:
            runner = self._runner(tmp)
            events = []
            with patch("baixador_ytdlp.parallel_section.DownloadRunner", Recording),                     patch("baixador_ytdlp.parallel_section.run_hidden",
                          side_effect=_fake_ffmpeg()) as ffmpeg:
                files = runner.run(events.append)
            self.assertEqual(files, [Path(tmp) / "Titulo [id].mp4"])
            self.assertEqual(files[0].read_bytes(), b"joined")
            args = ffmpeg.call_args.args[0]
            self.assertIn("concat", args)
            self.assertEqual(args[args.index("-c") + 1], "copy")
            self.assertEqual([p.name for p in Path(tmp).iterdir()], ["Titulo [id].mp4"])
            self.assertEqual(events[-1].status, "finished")
            # 6 partes de 300 s: as emendas recuam 2 s até o quadro-chave e as partes se tocam
            parts = [pair for pair in seen if float(pair[1]) - float(pair[0]) > 10]
            self.assertEqual(parts, [
                ("0.000", "297.980"), ("298.000", "597.980"), ("598.000", "897.980"),
                ("898.000", "1197.980"), ("1198.000", "1497.980"), ("1498.000", "1800.000")])
            # sondas de 1 s nas cinco emendas
            probes = [pair for pair in seen if float(pair[1]) - float(pair[0]) == 1.0]
            self.assertEqual(len(probes), 5)

    def test_failed_piece_falls_back_to_a_single_process(self) -> None:
        calls = []

        class Flaky(_FakeSub):
            def __init__(self, opts, cfg, tc):
                super().__init__(opts, cfg, tc,
                                 fail=float(opts.section_end) - float(opts.section_start) > 200
                                 and opts.section_start not in ("0", "0.000"))
                calls.append(opts.section_start)

        with tempfile.TemporaryDirectory() as tmp:
            runner = self._runner(tmp)
            with patch("baixador_ytdlp.parallel_section.DownloadRunner", Flaky),                     patch("baixador_ytdlp.parallel_section.run_hidden",
                          side_effect=_fake_ffmpeg()):
                files = runner.run(lambda progress: None)
            self.assertEqual(len(files), 1)
            self.assertEqual(calls[-1], "0")   # o processo único usa o intervalo inteiro
            self.assertEqual([p.name for p in Path(tmp).iterdir()], ["Titulo [id].mp4"])

    def test_cancel_before_start_does_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runner = self._runner(tmp)
            runner.cancel()
            self.assertEqual(runner.run(lambda progress: None), [])
            self.assertTrue(runner.cancelled)


if __name__ == "__main__":
    unittest.main()
