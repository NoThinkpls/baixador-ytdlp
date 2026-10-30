"""Conversor de formatos (1.16): vídeo, áudio, imagem e legenda, com o FFmpeg do app.

Até a 1.15 o "Converter formato" só aceitava vídeo e só gerava MP4 ou WebM. Aqui ficam os
comandos por tipo de origem, as recusas cedo com mensagem clara e as proteções de
segurança (protocolos e caminhos) que valem para todas as ferramentas.
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from baixador_ytdlp.media_tools import (CHOICES, CONVERT_FORMATS, MediaToolError,
                                        MediaToolOptions, build_command, convert_choice,
                                        default_destination, operation_duration,
                                        resolve_options, source_kind, stream_types, uses_gpu)
from baixador_ytdlp.tools import Toolchain

FFMPEG, FFPROBE = shutil.which("ffmpeg"), shutil.which("ffprobe")


def _toolchain(root: Path) -> Toolchain:
    return Toolchain(ytdlp=root / "yt-dlp", ffmpeg=Path(FFMPEG or root / "ffmpeg"),
                     ffprobe=Path(FFPROBE or root / "ffprobe"), bin_dir=root)


class ComandosTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.tc = Toolchain(self.root / "yt-dlp", self.root / "ffmpeg", self.root / "ffprobe",
                            self.root)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def source(self, name: str) -> Path:
        path = self.root / name
        path.write_bytes(b"x")
        return path

    def command(self, source: str, destination: str, **kwargs) -> list[str]:
        return build_command(MediaToolOptions(self.source(source), self.root / destination,
                                              "convert", **kwargs), self.tc)

    def test_tipo_da_origem_pela_extensao(self) -> None:
        for name, kind in (("a.MP4", "video"), ("a.gif", "video"), ("a.ts", "video"),
                           ("a.sem_ext", "video"), ("a.mp3", "audio"), ("a.FLAC", "audio"),
                           ("a.wma", "audio"), ("a.png", "image"), ("a.JPEG", "image"),
                           ("a.tif", "image"), ("a.srt", "subtitle"), ("a.ass", "subtitle"),
                           ("a.vtt", "subtitle")):
            self.assertEqual(source_kind(Path(name)), kind, name)

    def test_formatos_do_tipo_e_padrao(self) -> None:
        self.assertEqual(convert_choice(Path("v.mp4")), "mp4")      # reencodar para H.264
        self.assertEqual(convert_choice(Path("v.mkv"), "avi"), "avi")
        self.assertEqual(convert_choice(Path("f.png")), "jpg")       # o primeiro que muda algo
        self.assertEqual(convert_choice(Path("f.jpeg")), "png")
        self.assertEqual(convert_choice(Path("m.mp3")), "m4a")
        self.assertEqual(convert_choice(Path("m.wav")), "mp3")
        self.assertEqual(convert_choice(Path("l.srt")), "ass")
        self.assertEqual(convert_choice(Path("f.png"), "mp4"), "jpg")   # vídeo não serve p/ imagem
        every = {value for values in CONVERT_FORMATS.values() for value in values}
        self.assertEqual(every, set(CHOICES["convert"]))

    def test_nome_sugerido_segue_o_tipo(self) -> None:
        self.assertEqual(default_destination(self.source("foto.png"), "convert").name,
                         "foto_convertido.jpg")
        self.assertEqual(default_destination(self.source("foto.png"), "convert",
                                             choice="webp").name, "foto_convertido.webp")
        self.assertEqual(default_destination(self.source("musica.wav"), "convert").name,
                         "musica_convertido.mp3")
        self.assertEqual(default_destination(self.source("leg.srt"), "convert",
                                             choice="vtt").name, "leg_convertido.vtt")

    def test_video_para_cada_conteiner(self) -> None:
        for target, video, audio in (("mp4", "libx264", "aac"), ("mkv", "libx264", "aac"),
                                     ("mov", "libx264", "aac"), ("webm", "libvpx-vp9", "libopus"),
                                     ("avi", "mpeg4", "libmp3lame")):
            command = self.command("v.mkv", f"o.{target}")
            self.assertEqual(command[command.index("-c:v") + 1], video, target)
            self.assertEqual(command[command.index("-c:a") + 1], audio, target)
            self.assertIn("scale=trunc(iw/2)*2:trunc(ih/2)*2", command)   # GIF de largura ímpar
        self.assertIn("+faststart", self.command("v.mkv", "o.mov"))
        self.assertNotIn("-movflags", self.command("v.mp4", "o.mkv"))     # MKV recusa a opção

    def test_video_ou_audio_para_audio_pega_so_o_som(self) -> None:
        for source in ("v.mp4", "m.flac"):
            for target, codec in (("mp3", "libmp3lame"), ("ogg", "libvorbis"),
                                  ("aiff", "pcm_s16be"), ("opus", "libopus")):
                command = self.command(source, f"o.{target}")
                self.assertEqual(command[command.index("-c:a") + 1], codec, (source, target))
                self.assertIn("-vn", command)
                self.assertEqual(command[command.index("-map") + 1], "0:a:0")

    def test_imagem_um_quadro_e_nome_com_porcento(self) -> None:
        for target in ("jpg", "jpeg", "webp", "bmp", "tiff", "tif", "png"):
            command = self.command("foto%03d.png", f"saida%d.{target}")
            self.assertIn("-update", command, target)            # saída nunca vira sequência
            self.assertEqual(command[command.index("-frames:v") + 1], "1")
            # Entrada com % no nome não é tratada como sequência de imagens.
            self.assertEqual(command[command.index("-pattern_type") + 1], "none")
            self.assertLess(command.index("-pattern_type"), command.index("-i"))

    def test_legenda_para_legenda(self) -> None:
        for target, codec in (("srt", "srt"), ("ass", "ass"), ("vtt", "webvtt")):
            command = self.command("l.ass", f"o.{target}")
            self.assertEqual(command[command.index("-c:s") + 1], codec)
            self.assertEqual(command[command.index("-map") + 1], "0:s:0")

    def test_formato_que_nao_serve_para_a_origem_e_recusado(self) -> None:
        for source, destination in (("f.png", "o.mp4"), ("m.mp3", "o.mp4"), ("l.srt", "o.mp3"),
                                    ("v.mp4", "o.srt"), ("v.mp4", "o.png"), ("m.wav", "o.xyz")):
            with self.subTest(source=source, destination=destination):
                with self.assertRaises(MediaToolError):
                    self.command(source, destination)

    def test_gpu_so_em_h264(self) -> None:
        def gpu(source: str, destination: str) -> bool:
            return uses_gpu(MediaToolOptions(Path(source), Path(destination), "convert"))

        for destination in ("o.mp4", "o.mkv", "o.mov"):
            self.assertTrue(gpu("v.webm", destination), destination)
        for source, destination in (("v.mp4", "o.webm"), ("v.mp4", "o.avi"), ("v.mp4", "o.mp3"),
                                    ("f.png", "o.jpg"), ("l.srt", "o.vtt")):
            self.assertFalse(gpu(source, destination), destination)
        # Antes o AVI recebia h264_nvenc no lugar do mpeg4 e falhava na GPU.
        command = build_command(MediaToolOptions(self.source("v.mp4"), self.root / "o.avi",
                                                 "convert"), self.tc, video_encoder="h264_nvenc")
        self.assertNotIn("h264_nvenc", command)

    def test_imagem_e_legenda_nao_medem_duracao(self) -> None:
        with patch("baixador_ytdlp.media_tools.media_duration") as duration:
            for source in ("f.png", "l.srt"):
                options = MediaToolOptions(self.source(source), self.root / "o.x", "convert")
                self.assertEqual(operation_duration(options, self.tc), 0.0)
            duration.assert_not_called()

    def test_recusa_cedo_video_sem_imagem_ou_sem_som(self) -> None:
        def resolve(destination: str, types: set[str] | None) -> None:
            options = MediaToolOptions(self.source("v.webm"), self.root / destination, "convert")
            with patch("baixador_ytdlp.media_tools.stream_types", return_value=types):
                resolve_options(options, self.tc)

        with self.assertRaisesRegex(MediaToolError, "só tem áudio"):
            resolve("o.mp4", {"audio"})
        with self.assertRaisesRegex(MediaToolError, "não tem áudio"):
            resolve("o.mp3", {"video"})
        resolve("o.mp3", {"audio"})
        resolve("o.mp4", {"video"})
        resolve("o.mp4", None)    # ffprobe falhou: o FFmpeg decide

    def test_capa_embutida_nao_conta_como_video(self) -> None:
        payload = json.dumps({"streams": [
            {"codec_type": "audio"},
            {"codec_type": "video", "disposition": {"attached_pic": 1}}]})
        done = subprocess.CompletedProcess([], 0, stdout=payload, stderr="")
        with patch("baixador_ytdlp.media_tools.subprocess.run", return_value=done) as run:
            self.assertEqual(stream_types(Path("m.mka"), self.tc), {"audio"})
        self.assertIn("-protocol_whitelist", run.call_args.args[0])


class SegurancaDosArgumentosTests(unittest.TestCase):
    """O FFmpeg trata nomes como opções (``-y``) e protocolos (``http:``, ``concat:``)."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.tc = Toolchain(self.root / "yt-dlp", self.root / "ffmpeg", self.root / "ffprobe",
                            self.root)
        self._cwd = os.getcwd()
        os.chdir(self.root)

    def tearDown(self) -> None:
        os.chdir(self._cwd)
        self._tmp.cleanup()

    def test_caminho_relativo_que_parece_opcao_vira_absoluto(self) -> None:
        Path("-y.mp4").write_bytes(b"x")
        Path("-i.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\nx\n", encoding="utf-8")
        for operation, extra in (("convert", {}), ("trim", {"start": "1"}),
                                 ("soft_sub", {"subtitles": Path("-i.srt")})):
            command = build_command(MediaToolOptions(Path("-y.mp4"), Path("-f.mkv"), operation,
                                                     **extra), self.tc)
            inputs = [command[index + 1] for index, arg in enumerate(command) if arg == "-i"]
            for value in (*inputs, command[-1]):
                self.assertTrue(Path(value).is_absolute(), (operation, value))
                self.assertFalse(value.startswith("-"), (operation, value))

    def test_toda_entrada_so_aceita_arquivo_local(self) -> None:
        Path("v.mp4").write_bytes(b"x")
        Path("l.srt").write_text("x", encoding="utf-8")
        for operation, extra in (("convert", {}), ("remux", {}), ("audio", {}),
                                 ("soft_sub", {"subtitles": Path("l.srt")})):
            command = build_command(MediaToolOptions(Path("v.mp4"), Path("o.mkv" if operation != "audio" else "o.mp3"),
                                                     operation, **extra), self.tc)
            for index, arg in enumerate(command):
                if arg == "-i":
                    self.assertEqual(command[index - 2:index], ["-protocol_whitelist", "file"],
                                     operation)


@unittest.skipUnless(FFMPEG and FFPROBE, "FFmpeg/ffprobe não instalados")
class ConversaoRealTests(unittest.TestCase):
    """Cada par origem → formato oferecido precisa sair um arquivo que o ffprobe lê."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls._tmp.name)
        cls.tc = _toolchain(cls.root)
        run = lambda *args: subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y",  # noqa: E731
                                            *args], check=True, capture_output=True)
        # Largura e altura ímpares: o H.264 em yuv420p recusava sem o ajuste de tamanho.
        cls.video = cls.root / "clipe.mkv"
        run("-f", "lavfi", "-i", "testsrc=duration=2:size=321x181:rate=15", "-f", "lavfi",
            "-i", "sine=duration=2", "-c:v", "libx264", "-pix_fmt", "yuv444p", "-c:a", "aac",
            "-shortest", str(cls.video))
        cls.gif = cls.root / "anim.gif"
        run("-f", "lavfi", "-i", "testsrc=duration=1:size=101x75:rate=10", str(cls.gif))
        cls.audio = cls.root / "som.wav"
        run("-f", "lavfi", "-i", "sine=duration=2", str(cls.audio))
        cls.audio_webm = cls.root / "so_audio.webm"
        run("-f", "lavfi", "-i", "sine=duration=2", "-c:a", "libopus", str(cls.audio_webm))
        cls.image = cls.root / "foto%d [1].png"
        run("-f", "lavfi", "-i", "testsrc=size=99x77", "-vf", "format=rgba", "-frames:v", "1",
            "-update", "1", str(cls.image))
        cls.subtitle = cls.root / "legenda.srt"
        cls.subtitle.write_text("1\n00:00:00,000 --> 00:00:01,000\nOlá, mundo\n", encoding="utf-8")

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def convert(self, source: Path, target: str) -> Path:
        destination = self.root / f"{source.stem}_{target}.{target}"
        options = resolve_options(MediaToolOptions(source, destination, "convert"), self.tc)
        operation_duration(options, self.tc)
        result = subprocess.run(build_command(options, self.tc), capture_output=True, text=True,
                                timeout=120)
        self.assertEqual(0, result.returncode, result.stderr[-600:])
        self.assertGreater(destination.stat().st_size, 0)
        return destination

    def test_todos_os_formatos_oferecidos(self) -> None:
        for source in (self.video, self.gif, self.audio, self.image, self.subtitle):
            formats = CONVERT_FORMATS[source_kind(source)]
            if source == self.gif:
                formats = tuple(value for value in formats if value in {"mp4", "webm", "avi"})
            formats = tuple(value for value in formats if value != "pdf")   # Qt (test_documentos)
            for target in formats:
                with self.subTest(source=source.name, target=target):
                    destination = self.convert(source, target)
                    # O ffprobe também leria "%d" do nome como sequência de imagens.
                    literal = (["-f", "image2", "-pattern_type", "none"]
                               if source == self.image else [])
                    probe = subprocess.run([FFPROBE, "-v", "error", *literal, "-show_format",
                                            str(destination)], capture_output=True, text=True)
                    self.assertEqual(0, probe.returncode, probe.stderr)
        self.assertIn("Olá", (self.root / "legenda_vtt.vtt").read_text(encoding="utf-8"))

    def test_webm_so_de_audio_vai_para_audio_e_recusa_video(self) -> None:
        self.convert(self.audio_webm, "mp3")
        with self.assertRaisesRegex(MediaToolError, "só tem áudio"):
            self.convert(self.audio_webm, "mp4")

    def test_playlist_disfarcada_nao_acessa_a_rede(self) -> None:
        """Uma playlist HLS aberta como "vídeo" pedia segmentos por HTTP (SSRF/rastreio)."""
        hits: list[bytes] = []
        server = socket.socket()
        server.bind(("127.0.0.1", 0))
        server.listen(4)
        server.settimeout(10)
        port = server.getsockname()[1]

        def accept() -> None:
            try:
                while True:
                    connection, _ = server.accept()
                    hits.append(connection.recv(200))
                    connection.close()
            except OSError:
                pass

        threading.Thread(target=accept, daemon=True).start()
        playlist = self.root / "video.m3u8"
        playlist.write_text("#EXTM3U\n#EXT-X-TARGETDURATION:1\n#EXTINF:1,\n"
                            f"http://127.0.0.1:{port}/segmento.ts\n#EXT-X-ENDLIST\n",
                            encoding="utf-8")
        options = MediaToolOptions(playlist, self.root / "rede.mp4", "convert")
        result = subprocess.run(build_command(options, self.tc), capture_output=True, text=True,
                                timeout=60)
        server.close()
        self.assertNotEqual(0, result.returncode)
        self.assertIn("not on whitelist", result.stderr)
        self.assertEqual(hits, [])


class PaginaDoConversorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_lista_de_formatos_acompanha_o_arquivo(self) -> None:
        from baixador_ytdlp.config import Settings
        from baixador_ytdlp.ui.media_tools_page import MediaToolsPage

        page = MediaToolsPage(Settings())
        try:
            with tempfile.TemporaryDirectory() as directory:
                video = Path(directory) / "clipe.mp4"
                image = Path(directory) / "foto.png"
                for path in (video, image):
                    path.write_bytes(b"x")
                page._open_tool("convert")
                page.set_media(str(video))
                values = [page.choice_combo.itemData(i) for i in range(page.choice_combo.count())]
                self.assertEqual(tuple(values), CONVERT_FORMATS["video"])
                self.assertTrue(page.destination_edit.text().endswith("clipe_convertido.mp4"))
                page.set_media(str(image))
                values = [page.choice_combo.itemData(i) for i in range(page.choice_combo.count())]
                self.assertEqual(tuple(values), CONVERT_FORMATS["image"])
                self.assertTrue(page.destination_edit.text().endswith("foto_convertido.jpg"))
                page.choice_combo.setCurrentIndex(page.choice_combo.findData("webp"))
                self.assertTrue(page.destination_edit.text().endswith("foto_convertido.webp"))
                page._open_tool("frame")     # outra ferramenta volta à lista dela
                self.assertEqual(page.choice_combo.count(), len(CHOICES["frame"]))
        finally:
            page.deleteLater()

    def test_textos_do_conversor_tem_traducao(self) -> None:
        from baixador_ytdlp.ui import i18n
        from baixador_ytdlp.ui.media_tools_page import CONVERT_HINTS, CONVERT_LABELS

        self.assertEqual(set(CONVERT_LABELS), set(CHOICES["convert"]))
        texts = [*CONVERT_LABELS.values(), *CONVERT_HINTS.values(),
                 "Arquivo de vídeo, áudio, imagem, legenda ou documento"]
        self.assertEqual([text for text in texts if text not in i18n.EN], [])


if __name__ == "__main__":
    unittest.main()
