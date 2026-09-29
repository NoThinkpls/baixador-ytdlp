"""Ferramentas de mídia adicionadas na 1.13: comandos, validações e resultado real no FFmpeg."""
from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from baixador_ytdlp.media_tools import (CHOICES, DEFAULT_CHOICE, MediaToolError,
                                        MediaToolOptions, build_command, choice_of,
                                        default_destination, operation_duration,
                                        resolve_options, uses_gpu)
from baixador_ytdlp.tools import Toolchain

ALL_NEW = ("speed", "rotate", "mute", "normalize", "gif", "frame", "extract_subs", "strip",
           "convert")


def _toolchain(root: Path) -> Toolchain:
    return Toolchain(ytdlp=root / "yt-dlp", ffmpeg=root / "ffmpeg", ffprobe=root / "ffprobe",
                     bin_dir=root)


class CommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.source = self.root / "video.mp4"
        self.source.write_bytes(b"x")
        self.tc = _toolchain(self.root)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def command(self, operation: str, destination: str, **kwargs) -> list[str]:
        options = MediaToolOptions(self.source, self.root / destination, operation, **kwargs)
        return build_command(options, self.tc)

    def test_todas_as_ferramentas_novas_geram_comando(self) -> None:
        for operation, destination in (
                ("speed", "o.mp4"), ("rotate", "o.mp4"), ("mute", "o.mp4"),
                ("normalize", "o.mp4"), ("gif", "o.gif"), ("frame", "o.png"),
                ("extract_subs", "o.srt"), ("strip", "o.mp4"), ("convert", "o.mp4")):
            command = self.command(operation, destination)
            self.assertEqual(command[-1], str(self.root / destination), operation)
            self.assertIn("-progress", command, operation)

    def test_velocidade_encadeia_atempo_fora_do_limite_de_0_5_a_2(self) -> None:
        def audio_filter(choice: str) -> str:
            command = self.command("speed", "o.mp4", choice=choice)
            return command[command.index("-af") + 1]

        self.assertEqual(audio_filter("2"), "atempo=2")
        self.assertEqual(audio_filter("4"), "atempo=2,atempo=2")
        self.assertEqual(audio_filter("3"), "atempo=2,atempo=1.5")
        self.assertEqual(audio_filter("0.25"), "atempo=0.5,atempo=0.5")
        self.assertEqual(audio_filter("1.25"), "atempo=1.25")
        command = self.command("speed", "o.mp4", choice="4")
        self.assertEqual(command[command.index("-vf") + 1], "setpts=PTS/4")
        self.assertIn("-fpsmax", command)                      # 4x não vira 240 fps
        self.assertNotIn("-fpsmax", self.command("speed", "o.mp4", choice="0.5"))

    def test_escolha_desconhecida_cai_no_padrao_da_ferramenta(self) -> None:
        self.assertEqual(choice_of("speed", "999"), DEFAULT_CHOICE["speed"])
        self.assertEqual(choice_of("speed", ""), DEFAULT_CHOICE["speed"])
        self.assertEqual(choice_of("trim", "qualquer"), "")
        command = self.command("rotate", "o.mp4", choice="; rm -rf /")
        self.assertEqual(command[command.index("-vf") + 1], "transpose=1")

    def test_padroes_pertencem_as_escolhas(self) -> None:
        for operation, values in CHOICES.items():
            self.assertIn(DEFAULT_CHOICE[operation], values, operation)

    def test_progresso_da_velocidade_mede_a_saida(self) -> None:
        options = MediaToolOptions(self.source, self.root / "o.mp4", "speed", choice="4")
        with patch("baixador_ytdlp.media_tools.media_duration", return_value=120.0):
            self.assertAlmostEqual(operation_duration(options, self.tc), 30.0)

    def test_giro_e_espelho(self) -> None:
        expected = {"cw": "transpose=1", "ccw": "transpose=2", "180": "hflip,vflip",
                    "flip_h": "hflip", "flip_v": "vflip"}
        for choice, video_filter in expected.items():
            command = self.command("rotate", "o.mp4", choice=choice)
            self.assertEqual(command[command.index("-vf") + 1], video_filter)

    def test_gif_recusa_trecho_longo_e_exige_duracao(self) -> None:
        def duration(total: float, start: str = "", end: str = "") -> float:
            options = MediaToolOptions(self.source, self.root / "o.gif", "gif", start, end)
            with patch("baixador_ytdlp.media_tools.media_duration", return_value=total):
                return operation_duration(options, self.tc)

        self.assertAlmostEqual(duration(20.0), 20.0)
        self.assertAlmostEqual(duration(600.0, "10", "25"), 15.0)
        with self.assertRaisesRegex(MediaToolError, "30 s"):
            duration(600.0)
        with self.assertRaisesRegex(MediaToolError, "30 s"):
            duration(600.0, "0", "45")
        with self.assertRaisesRegex(MediaToolError, "duração"):
            duration(0.0)

    def test_gif_usa_paleta_propria_e_recorte_antes_da_entrada(self) -> None:
        command = self.command("gif", "o.gif", start="5", end="9", choice="480")
        self.assertLess(command.index("-ss"), command.index("-i"))
        self.assertEqual(command[command.index("-t") + 1], "4.000000")
        graph = command[command.index("-vf") + 1]
        self.assertIn("palettegen", graph)
        self.assertIn("paletteuse", graph)
        self.assertIn("min(480,iw)", graph)
        self.assertIn("-an", command)
        with self.assertRaisesRegex(MediaToolError, "posterior"):
            self.command("gif", "o.gif", start="9", end="5")
        with self.assertRaisesRegex(MediaToolError, "mm:ss"):
            self.command("gif", "o.gif", start="abc")

    def test_quadro_usa_o_momento_e_a_extensao_de_saida(self) -> None:
        command = self.command("frame", "o.jpg", start="00:01:30")
        self.assertLess(command.index("-ss"), command.index("-i"))
        self.assertEqual(command[command.index("-frames:v") + 1], "1")
        self.assertIn("-q:v", command)
        self.assertNotIn("-q:v", self.command("frame", "o.png"))
        self.assertNotIn("-ss", self.command("frame", "o.png"))
        with self.assertRaisesRegex(MediaToolError, r"\.png, \.jpg"):
            self.command("frame", "o.bmp")

    def test_audio_segue_a_extensao_de_saida(self) -> None:
        for suffix, codec in ((".mp3", "libmp3lame"), (".m4a", "aac"), (".opus", "libopus"),
                              (".flac", "flac"), (".wav", "pcm_s16le")):
            command = self.command("audio", f"o{suffix}")
            self.assertEqual(command[command.index("-c:a") + 1], codec, suffix)
            self.assertIn("-vn", command)
        with self.assertRaisesRegex(MediaToolError, r"\.mp3"):
            self.command("audio", "o.xyz")

    def test_converter_usa_vp9_so_para_webm(self) -> None:
        webm = self.command("convert", "o.webm")
        self.assertEqual(webm[webm.index("-c:v") + 1], "libvpx-vp9")
        self.assertEqual(webm[webm.index("-c:a") + 1], "libopus")
        mp4 = self.command("convert", "o.mp4")
        self.assertEqual(mp4[mp4.index("-c:v") + 1], "libx264")
        self.assertIn("yuv420p", mp4)
        with self.assertRaisesRegex(MediaToolError, r"\.mp4"):
            self.command("convert", "o.avi")

    def test_gpu_so_onde_existe_encoder(self) -> None:
        def gpu(operation: str, destination: str) -> bool:
            return uses_gpu(MediaToolOptions(self.source, self.root / destination, operation))

        for operation in ("speed", "rotate"):
            self.assertTrue(gpu(operation, "o.mp4"), operation)
            command = build_command(MediaToolOptions(
                self.source, self.root / "o.mp4", operation), self.tc, video_encoder="h264_nvenc")
            self.assertEqual(command[command.index("-c:v") + 1], "h264_nvenc", operation)
            self.assertNotIn("-crf", command)
        self.assertTrue(gpu("convert", "o.mp4"))
        self.assertFalse(gpu("convert", "o.webm"))            # VP9 não tem encoder de GPU
        for operation, destination in (("mute", "o.mp4"), ("strip", "o.mp4"),
                                       ("normalize", "o.mp4"), ("gif", "o.gif"),
                                       ("frame", "o.png"), ("extract_subs", "o.srt")):
            self.assertFalse(gpu(operation, destination), operation)
            command = build_command(MediaToolOptions(
                self.source, self.root / destination, operation), self.tc,
                video_encoder="h264_nvenc")
            self.assertNotIn("h264_nvenc", command, operation)

    def test_remover_audio_copia_a_imagem(self) -> None:
        command = self.command("mute", "o.mp4")
        self.assertEqual(command[command.index("-c") + 1], "copy")
        self.assertEqual(command[command.index("-map") + 1], "0:v")
        self.assertNotIn("0:a", command)
        self.assertIn("+faststart", command)
        self.assertNotIn("-movflags", self.command("mute", "o.mkv"))   # MKV recusa a opção

    def test_nivelar_volume_copia_a_imagem_e_fixa_48k(self) -> None:
        command = self.command("normalize", "o.mp4", choice="-14")
        self.assertIn("loudnorm=I=-14:TP=-1.5:LRA=11", command)
        self.assertEqual(command[command.index("-c:v") + 1], "copy")
        self.assertEqual(command[command.index("-ar") + 1], "48000")
        audio = self.command("normalize", "o.mp3")
        self.assertIn("-vn", audio)
        self.assertEqual(audio[audio.index("-c:a") + 1], "libmp3lame")
        webm = self.command("normalize", "o.webm")
        self.assertEqual(webm[webm.index("-c:a") + 1], "libopus")

    def test_limpar_metadados_nao_reencoda_e_apaga_as_etiquetas(self) -> None:
        command = self.command("strip", "o.mp4")
        self.assertEqual(command[command.index("-c") + 1], "copy")
        self.assertEqual(command[command.index("-map_metadata") + 1], "-1")
        self.assertEqual(command[command.index("-map_chapters") + 1], "-1")
        self.assertIn("+bitexact", command)
        self.assertNotIn("0:s?", command)                      # legenda arbitrária não cabe em MP4
        self.assertIn("0:s?", self.command("strip", "o.mkv"))

    def test_extrair_legendas_usa_a_faixa_resolvida(self) -> None:
        command = self.command("extract_subs", "o.srt", stream_index=3)
        self.assertEqual(command[command.index("-map") + 1], "0:3")
        self.assertEqual(command[command.index("-c:s") + 1], "srt")
        for suffix, codec in ((".ass", "ass"), (".vtt", "webvtt")):
            other = self.command("extract_subs", f"o{suffix}")
            self.assertEqual(other[other.index("-c:s") + 1], codec)
        self.assertIn("0:s:0", self.command("extract_subs", "o.srt"))
        with self.assertRaisesRegex(MediaToolError, r"\.srt"):
            self.command("extract_subs", "o.sub")

    def test_extrair_legendas_recusa_cedo_o_que_nao_da_certo(self) -> None:
        options = MediaToolOptions(self.source, self.root / "o.srt", "extract_subs")
        with patch("baixador_ytdlp.media_tools.subtitle_streams", return_value=[]):
            with self.assertRaisesRegex(MediaToolError, "não tem legendas"):
                resolve_options(options, self.tc)
        bitmap = [{"index": 2, "codec_name": "hdmv_pgs_subtitle"}]
        with patch("baixador_ytdlp.media_tools.subtitle_streams", return_value=bitmap):
            with self.assertRaisesRegex(MediaToolError, "imagens"):
                resolve_options(options, self.tc)
        mixed = bitmap + [{"index": 4, "codec_name": "subrip"}, {"index": 5, "codec_name": "ass"}]
        with patch("baixador_ytdlp.media_tools.subtitle_streams", return_value=mixed):
            self.assertEqual(resolve_options(options, self.tc).stream_index, 4)
        other = MediaToolOptions(self.source, self.root / "o.mp4", "mute")
        self.assertIs(resolve_options(other, self.tc), other)   # as demais nem chamam o ffprobe

    def test_nomes_sugeridos(self) -> None:
        def name(operation: str, source: str = "video.mp4", choice: str = "") -> str:
            return default_destination(self.root / source, operation, choice=choice).name

        self.assertEqual(name("audio"), "video_audio.mp3")
        self.assertEqual(name("audio", choice="flac"), "video_audio.flac")
        self.assertEqual(name("convert", choice="webm"), "video_convertido.webm")
        self.assertEqual(name("frame", choice="jpg"), "video_quadro.jpg")
        self.assertEqual(name("gif"), "video_animado.gif")
        self.assertEqual(name("speed"), "video_velocidade.mp4")
        self.assertEqual(name("rotate"), "video_girado.mp4")
        self.assertEqual(name("extract_subs", choice="vtt"), "video.vtt")   # legenda "ao lado"
        self.assertEqual(name("mute", "clip.mkv"), "clip_sem_audio.mkv")
        self.assertEqual(name("mute", "clip.avi"), "clip_sem_audio.mkv")    # AVI não recebe cópia
        self.assertEqual(name("strip", "clip.webm"), "clip_limpo.webm")
        self.assertEqual(name("normalize", "song.flac"), "song_normalizado.flac")
        self.assertEqual(name("normalize", "song.aac"), "song_normalizado.m4a")
        self.assertEqual(name("normalize", "clip.mp4"), "clip_normalizado.mp4")

    def test_nome_da_legenda_nao_sobrescreve_uma_existente(self) -> None:
        (self.root / "video.srt").write_text("x")
        self.assertEqual(default_destination(self.root / "video.mp4", "extract_subs").name,
                         "video (2).srt")


def _ffmpeg() -> str | None:
    return shutil.which("ffmpeg")


def _probe(ffmpeg: str, path: Path) -> str:
    """Saída de ``ffmpeg -i`` (só depende do ffmpeg; o ffprobe nem sempre está no PATH)."""
    return subprocess.run([ffmpeg, "-hide_banner", "-i", str(path)],
                          capture_output=True, text=True).stderr


def _seconds(info: str) -> float:
    match = re.search(r"Duration: (\d+):(\d+):([\d.]+)", info)
    assert match, info
    return int(match[1]) * 3600 + int(match[2]) * 60 + float(match[3])


@unittest.skipUnless(_ffmpeg(), "FFmpeg ausente")
class RealFfmpegTests(unittest.TestCase):
    """Roda os comandos de verdade: um argumento errado só aparece assim."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls._tmp.name)
        cls.ffmpeg = _ffmpeg() or ""
        cls.tc = Toolchain(cls.root / "yt-dlp", Path(cls.ffmpeg), cls.root / "ffprobe", cls.root)
        cls.source = cls.root / "src.mp4"
        cls.subtitled = cls.root / "sub.mkv"
        srt = cls.root / "a.srt"
        srt.write_text("1\n00:00:00,000 --> 00:00:01,500\nOlá\n\n2\n00:00:02,000 --> 00:00:03,000\nMundo\n",
                       encoding="utf-8")
        subprocess.run([
            cls.ffmpeg, "-v", "error", "-f", "lavfi", "-i", "testsrc=s=320x240:r=30:d=6",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=6", "-c:v", "libx264",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-metadata", "title=SEGREDO",
            "-metadata", "location=+10.0+20.0/", str(cls.source)], check=True, capture_output=True)
        subprocess.run([
            cls.ffmpeg, "-v", "error", "-i", str(cls.source), "-i", str(srt), "-map", "0",
            "-map", "1", "-c", "copy", "-c:s", "srt", str(cls.subtitled)],
            check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def run_tool(self, operation: str, name: str, source: Path | None = None, **kwargs) -> tuple[Path, str]:
        destination = self.root / name
        options = MediaToolOptions(source or self.source, destination, operation, **kwargs)
        command = build_command(options, self.tc)
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertGreater(destination.stat().st_size, 0)
        return destination, _probe(self.ffmpeg, destination)

    def test_girar_troca_largura_e_altura(self) -> None:
        _, info = self.run_tool("rotate", "girado.mp4", choice="cw")
        self.assertIn("240x320", info)
        _, info = self.run_tool("rotate", "espelhado.mp4", choice="flip_h")
        self.assertIn("320x240", info)

    def test_velocidade_muda_a_duracao(self) -> None:
        self.assertAlmostEqual(_seconds(self.run_tool("speed", "v2.mp4", choice="2")[1]), 3.0, delta=0.1)
        self.assertAlmostEqual(_seconds(self.run_tool("speed", "v4.mp4", choice="4")[1]), 1.5, delta=0.1)
        self.assertAlmostEqual(_seconds(self.run_tool("speed", "v05.mp4", choice="0.5")[1]), 12.0, delta=0.2)

    def test_remover_audio(self) -> None:
        _, info = self.run_tool("mute", "mudo.mp4")
        self.assertIn("Video:", info)
        self.assertNotIn("Audio:", info)

    def test_extrair_audio_em_cada_formato(self) -> None:
        for suffix, marker in ((".mp3", "mp3"), (".m4a", "aac"), (".opus", "opus"),
                               (".flac", "flac"), (".wav", "pcm_s16le")):
            _, info = self.run_tool("audio", f"som{suffix}")
            self.assertIn(marker, info, suffix)
            self.assertNotIn("Video:", info, suffix)

    def test_nivelar_volume_chega_ao_alvo(self) -> None:
        destination, _ = self.run_tool("normalize", "nivelado.mp4", choice="-16")
        measured = subprocess.run(
            [self.ffmpeg, "-hide_banner", "-i", str(destination), "-af", "ebur128", "-f", "null", "-"],
            capture_output=True, text=True).stderr
        loudness = float(re.findall(r"I:\s+(-?[\d.]+) LUFS", measured)[-1])
        self.assertAlmostEqual(loudness, -16.0, delta=1.0)

    def test_gif_respeita_o_trecho(self) -> None:
        _, info = self.run_tool("gif", "trecho.gif", start="1", end="4", choice="480")
        self.assertIn("gif", info)
        self.assertAlmostEqual(_seconds(info), 3.0, delta=0.2)

    def test_capturar_quadro(self) -> None:
        for suffix, marker in ((".png", "png"), (".jpg", "mjpeg"), (".webp", "webp")):
            _, info = self.run_tool("frame", f"quadro{suffix}", start="2")
            self.assertIn(marker, info, suffix)
            self.assertIn("320x240", info, suffix)

    def test_converter_para_webm(self) -> None:
        _, info = self.run_tool("convert", "saida.webm")
        self.assertIn("vp9", info)
        self.assertIn("opus", info)

    def test_extrair_legendas(self) -> None:
        for suffix in (".srt", ".ass", ".vtt"):
            destination, _ = self.run_tool("extract_subs", f"legenda{suffix}",
                                           source=self.subtitled, stream_index=2)
            self.assertIn("Olá", destination.read_text(encoding="utf-8"), suffix)

    def test_limpar_metadados_apaga_titulo_e_localizacao(self) -> None:
        _, before = self.source, _probe(self.ffmpeg, self.source)
        self.assertIn("SEGREDO", before)
        destination, after = self.run_tool("strip", "limpo.mp4")
        for secret in ("SEGREDO", "location", "+10.0000"):
            self.assertNotIn(secret, after)
        self.assertIn("h264", after)
        self.assertIn("aac", after)
        self.assertNotIn(b"SEGREDO", destination.read_bytes())


if __name__ == "__main__":
    unittest.main()
