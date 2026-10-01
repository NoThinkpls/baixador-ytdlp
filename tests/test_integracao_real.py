"""Integração com as ferramentas de verdade (yt-dlp como biblioteca e FFmpeg/ffprobe do sistema).

Os testes unitários só olham a lista de argumentos; aqui o próprio yt-dlp valida as opções
que o app monta e o FFmpeg executa cada ferramenta da página de mídia. Pulados quando a
ferramenta não está instalada.
"""
from __future__ import annotations

import itertools
import optparse
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from baixador_ytdlp.config import Settings
from baixador_ytdlp.downloader import DownloadOptions, build_args
from baixador_ytdlp.media_tools import (
    CHOICES, MediaToolOptions, build_command, operation_duration, resolve_options,
)
from baixador_ytdlp.tools import Toolchain

try:
    import yt_dlp
except ImportError:  # pragma: no cover
    yt_dlp = None

FFMPEG, FFPROBE = shutil.which("ffmpeg"), shutil.which("ffprobe")


def _toolchain(root: Path) -> Toolchain:
    return Toolchain(ytdlp=root / "yt-dlp", ffmpeg=Path(FFMPEG or "ffmpeg"),
                     ffprobe=Path(FFPROBE or "ffprobe"), bin_dir=root)


@unittest.skipIf(yt_dlp is None, "yt-dlp não instalado")
class OpcoesAceitasPeloYtDlpTests(unittest.TestCase):
    """Uma opção inventada ou mal formada só aparecia no primeiro download real."""

    def test_toda_combinacao_de_opcoes_e_aceita_pelo_parser(self) -> None:
        root = Path(tempfile.gettempdir())
        tc = _toolchain(root)
        casos = 0
        for audio, container, section, playlist in itertools.product(
                (False, True), ("mp4", "mkv", "webm", "original"),
                ((), ("0:30", "2:00"), ("", "1:00"), ("10", "")), (False, True)):
            for flags in ({}, {"prefer_h264": True, "sponsorblock": True, "write_subs": True},
                          {"embed_thumbnail": True, "embed_chapters": True,
                           "organize_audio_by_uploader": True, "limit_rate": "5M",
                           "extractor_args": "youtube:player_client=default"}):
                cfg = Settings(**flags)
                opts = DownloadOptions(
                    url="https://www.youtube.com/watch?v=abc", output_dir=str(root),
                    container=container, audio_only=audio, playlist=playlist,
                    playlist_items="1-3,7" if playlist else "",
                    section_start=section[0] if section else "",
                    section_end=section[1] if section else "")
                args = build_args(opts, cfg, tc)[1:]   # sem o executável
                with self.subTest(audio=audio, container=container, section=section,
                                  playlist=playlist, flags=flags):
                    try:
                        parsed = yt_dlp.parse_options(args)
                    except (SystemExit, optparse.OptParseError, ValueError) as exc:
                        self.fail(f"yt-dlp recusou as opções ({exc}): {args}")
                    self.assertEqual(opts.url, parsed.urls[0])
                    casos += 1
        self.assertGreater(casos, 100)

    def test_url_que_comeca_com_hifen_nunca_vira_opcao(self) -> None:
        tc = _toolchain(Path(tempfile.gettempdir()))
        opts = DownloadOptions(url="--exec=calc https://x.com/a", output_dir="/tmp")
        with self.assertRaises(ValueError):
            build_args(opts, Settings(), tc)


@unittest.skipUnless(FFMPEG and FFPROBE, "FFmpeg/ffprobe não instalados")
class FerramentasDeMidiaComFfmpegRealTests(unittest.TestCase):
    """Cada operação da página Ferramentas precisa gerar um arquivo que o ffprobe lê."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.tc = _toolchain(cls.root)
        cls.video = cls.root / "clipe.mp4"
        subprocess.run([
            FFMPEG, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
            "testsrc=duration=4:size=320x180:rate=15", "-f", "lavfi", "-i",
            "sine=frequency=440:duration=4", "-c:v", "libx264", "-g", "15", "-c:a", "aac",
            "-shortest", str(cls.video)], check=True)
        cls.srt = cls.root / "legenda.srt"
        cls.srt.write_text("1\n00:00:00,000 --> 00:00:02,000\nOlá, mundo\n", encoding="utf-8")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def _executa(self, nome: str, **kwargs) -> Path:
        destino = self.root / nome
        opts = MediaToolOptions(source=self.video, destination=destino, **kwargs)
        opts = resolve_options(opts, self.tc)
        operation_duration(opts, self.tc)
        comando = build_command(opts, self.tc)
        resultado = subprocess.run(comando, capture_output=True, text=True, timeout=120)
        self.assertEqual(0, resultado.returncode, resultado.stderr[-600:])
        self.assertTrue(destino.is_file() and destino.stat().st_size > 0, nome)
        probe = subprocess.run([FFPROBE, "-v", "error", "-show_format", str(destino)],
                               capture_output=True, text=True)
        self.assertEqual(0, probe.returncode, f"{nome}: {probe.stderr}")
        return destino

    def test_operacoes_sem_escolha(self) -> None:
        casos = {
            "trim": ("a.mkv", dict(start="0:01", end="0:03")),
            "trim_rapido": ("b.mkv", dict(start="0:01", end="0:03", fast_trim=True)),
            "remux": ("c.mkv", {}),
            "compress": ("d.mp4", {}),
            "target_size": ("e.mp4", dict(target_mb=5)),
            "mute": ("f.mp4", {}),
            "strip": ("g.mp4", {}),
            "shorts": ("h.mp4", dict(shorts_blur=True)),
            "shorts_sem_desfoque": ("i.mp4", dict(shorts_blur=False)),
            "burn": ("j.mp4", dict(subtitles=self.srt)),
            "soft_sub": ("k.mkv", dict(subtitles=self.srt, subtitle_language="pt")),
        }
        for rotulo, (nome, extra) in casos.items():
            with self.subTest(rotulo):
                operacao = {"trim_rapido": "trim", "shorts_sem_desfoque": "shorts"}.get(rotulo, rotulo)
                self._executa(nome, operation=operacao, **extra)

    def test_operacoes_com_escolha_em_todas_as_opcoes(self) -> None:
        extensao = {"audio": "{c}", "convert": "{c}", "frame": "{c}", "extract_subs": "{c}"}
        for operacao, valores in CHOICES.items():
            for valor in valores:
                if operacao == "extract_subs":
                    continue   # o clipe de teste não tem legenda embutida (coberto à parte)
                with self.subTest(operacao=operacao, valor=valor):
                    if operacao in extensao:
                        nome = f"{operacao}_{valor}.{valor}"
                    else:
                        nome = f"{operacao}_{valor.replace('-', 'n')}.mp4"
                    extra = dict(start="0:01") if operacao in {"frame", "gif"} else {}
                    self._executa(nome, operation=operacao, choice=valor, **extra)

    def test_extrair_legenda_de_arquivo_sem_legenda_e_recusado(self) -> None:
        from baixador_ytdlp.media_tools import MediaToolError

        opts = MediaToolOptions(source=self.video, destination=self.root / "x.srt",
                                operation="extract_subs", choice="srt")
        with self.assertRaises(MediaToolError):
            resolve_options(opts, self.tc)

    def test_legenda_com_caracteres_especiais_no_caminho(self) -> None:
        """O filtro ``subtitles`` tem regras próprias de escape (:, vírgula, colchetes, aspa)."""
        pasta = self.root / "pasta [1], a;b 'c' João|x=1%"
        pasta.mkdir()
        legenda = pasta / "it's leg,enda: [x] ação.srt"
        legenda.write_text(self.srt.read_text(encoding="utf-8"), encoding="utf-8")
        self._executa("especial.mp4", operation="burn", subtitles=legenda)

    def test_velocidade_extrema_mantem_duracao_proporcional(self) -> None:
        saida = self._executa("v4.mp4", operation="speed", choice="4")
        duracao = float(subprocess.run(
            [FFPROBE, "-v", "error", "-show_entries", "format=duration", "-of",
             "default=nw=1:nk=1", str(saida)], capture_output=True, text=True).stdout)
        self.assertAlmostEqual(1.0, duracao, delta=0.4)   # 4 s a 4x


if __name__ == "__main__":
    unittest.main()
