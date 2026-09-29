"""VP9 dentro de MP4 vira MKV, sem recodificar (o DaVinci abre o MP4 com partes offline)."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from baixador_ytdlp.config import Settings
from baixador_ytdlp.downloader import vp9_mp4_to_mkv


def _fake(codec: str, ffmpeg_ok: bool = True):
    calls = []

    def run(args, timeout=60):
        calls.append(args)
        if "ffprobe" in args[0]:
            return SimpleNamespace(returncode=0, stdout=codec + "\n", stderr="")
        if ffmpeg_ok:
            Path(args[-1]).write_bytes(b"mkv")
        return SimpleNamespace(returncode=0 if ffmpeg_ok else 1, stdout="", stderr="erro")
    return run, calls


class Vp9ToMkvTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.tc = SimpleNamespace(ffmpeg=Path("ffmpeg"), ffprobe=Path("ffprobe"))
        self.mp4 = self.tmp / "video [id].mp4"
        self.mp4.write_bytes(b"mp4")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_vp9_in_mp4_is_remuxed_without_reencoding(self) -> None:
        run, calls = _fake("vp9")
        with patch("baixador_ytdlp.downloader.run_hidden", side_effect=run):
            result = vp9_mp4_to_mkv(self.mp4, self.tc)
        self.assertEqual(result, self.tmp / "video [id].mkv")
        self.assertTrue(result.is_file())
        self.assertFalse(self.mp4.exists())
        remux = calls[-1]
        self.assertEqual(remux[remux.index("-c") + 1], "copy")

    def test_other_codecs_and_containers_are_left_alone(self) -> None:
        for codec in ("h264", "av1", "hevc"):
            run, calls = _fake(codec)
            with patch("baixador_ytdlp.downloader.run_hidden", side_effect=run):
                self.assertEqual(vp9_mp4_to_mkv(self.mp4, self.tc), self.mp4)
            self.assertEqual(len(calls), 1)   # só o ffprobe
        mkv = self.tmp / "x.mkv"
        mkv.write_bytes(b"x")
        with patch("baixador_ytdlp.downloader.run_hidden", side_effect=AssertionError("nada")):
            self.assertEqual(vp9_mp4_to_mkv(mkv, self.tc), mkv)

    def test_failure_keeps_the_original_mp4(self) -> None:
        run, _ = _fake("vp9", ffmpeg_ok=False)
        with patch("baixador_ytdlp.downloader.run_hidden", side_effect=run):
            self.assertEqual(vp9_mp4_to_mkv(self.mp4, self.tc), self.mp4)
        self.assertTrue(self.mp4.exists())
        self.assertFalse((self.tmp / "video [id].mkv").exists())

    def test_existing_mkv_is_not_overwritten(self) -> None:
        (self.tmp / "video [id].mkv").write_bytes(b"antigo")
        run, _ = _fake("vp9")
        with patch("baixador_ytdlp.downloader.run_hidden", side_effect=run):
            result = vp9_mp4_to_mkv(self.mp4, self.tc)
        self.assertEqual(result.name, "video [id] (2).mkv")
        self.assertEqual((self.tmp / "video [id].mkv").read_bytes(), b"antigo")

    def test_setting_is_on_by_default_and_h264_off(self) -> None:
        cfg = Settings()
        self.assertTrue(cfg.vp9_in_mkv)
        self.assertFalse(cfg.prefer_h264)


if __name__ == "__main__":
    unittest.main()
