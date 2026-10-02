"""Regressões achadas numa caça a bugs em 01/10/2026 (cada teste falha no código anterior)."""
from __future__ import annotations

import http.client
import json
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import MagicMock, patch

from baixador_ytdlp import config as config_module
from baixador_ytdlp.config import Settings
from baixador_ytdlp.cookies import merge_cookie_text
from baixador_ytdlp.downloader import (
    DownloadOptions, DownloadRunner, Progress, _time_seconds,
)
from baixador_ytdlp.security import redact_sensitive
from baixador_ytdlp.updater import AppUpdater, UpdateError


class RedacaoDeSegredosTests(unittest.TestCase):
    """O log inteiro passa por ``redact_sensitive``; o que ela deixa passar vai para o disco."""

    def test_token_bearer_e_basic_somem_por_inteiro(self) -> None:
        self.assertNotIn("abc123secret", redact_sensitive("Authorization: Bearer abc123secret"))
        self.assertNotIn("dXNlcjpwYXNz", redact_sensitive("authorization=Basic dXNlcjpwYXNz"))

    def test_cabecalho_passado_ao_ytdlp_some_por_inteiro(self) -> None:
        for flag in ("--add-headers", "--headers"):
            texto = redact_sensitive(f"yt-dlp {flag} 'Authorization: Bearer abc123secret' -- url")
            self.assertNotIn("abc123secret", texto)
            self.assertNotIn("Bearer", texto)
            self.assertTrue(texto.endswith("-- url"))

    def test_cabecalho_cookie_com_varios_pares(self) -> None:
        texto = redact_sensitive("Cookie: SID=aaa; HSID=bbb; SSID=ccc")
        for valor in ("aaa", "bbb", "ccc"):
            self.assertNotIn(valor, texto)

    def test_parametros_de_consulta_com_prefixo_sensivel(self) -> None:
        for chave in ("access_token", "refresh_token", "id_token", "password", "client_secret",
                      "po_token", "visitor_data"):
            texto = redact_sensitive(f"https://exemplo.com/v?a=1&{chave}=SEGREDO&b=2")
            self.assertNotIn("SEGREDO", texto, chave)
            self.assertIn("b=2", texto)

    def test_extractor_args_do_youtube_com_po_token(self) -> None:
        texto = redact_sensitive("--extractor-args youtube:po_token=web+SEGREDO;player_client=web")
        self.assertNotIn("SEGREDO", texto)

    def test_texto_comum_continua_intacto(self) -> None:
        original = "ERROR: [youtube] abc: Video unavailable. https://youtu.be/abc?t=30"
        self.assertEqual(original, redact_sensitive(original))


class RedirecionamentoDaMiniaturaTests(unittest.TestCase):
    """A checagem de IP privado só valia para a URL inicial; um 302 a contornava."""

    def test_redirect_para_rede_local_e_recusado(self) -> None:
        from baixador_ytdlp.workers import _SafeRedirectHandler

        handler = _SafeRedirectHandler()
        request = urllib.request.Request("https://cdn.exemplo.com/a.jpg")
        for destino in ("https://127.0.0.1/segredo.jpg", "http://cdn.exemplo.com/a.jpg",
                        "https://localhost/a.jpg"):
            with self.assertRaises(urllib.error.URLError, msg=destino):
                handler.redirect_request(request, MagicMock(), 302, "Found", {}, destino)

    def test_redirect_publico_em_https_continua_permitido(self) -> None:
        from baixador_ytdlp.workers import _SafeRedirectHandler

        request = urllib.request.Request("https://cdn.exemplo.com/a.jpg")
        with patch("baixador_ytdlp.workers._is_private_host", return_value=False):
            novo = _SafeRedirectHandler().redirect_request(
                request, MagicMock(), 302, "Found", {}, "https://img.exemplo.com/b.jpg")
        self.assertIsNotNone(novo)


class AtualizadorErrosDeRedeTests(unittest.TestCase):
    """IncompleteRead não é OSError: escapava como exceção crua em vez de UpdateError."""

    def test_consulta_truncada_vira_update_error(self) -> None:
        resposta = MagicMock()
        resposta.__enter__.return_value.read.side_effect = http.client.IncompleteRead(b"x")
        with patch("baixador_ytdlp.updater.urlopen", return_value=resposta):
            with self.assertRaises(UpdateError):
                AppUpdater._request_text("https://api.github.com/x")

    def test_conexao_resetada_na_consulta_vira_update_error(self) -> None:
        with patch("baixador_ytdlp.updater.urlopen", side_effect=ConnectionResetError()):
            with self.assertRaises(UpdateError):
                AppUpdater._request_text("https://api.github.com/x")

    def test_download_truncado_vira_update_error_e_apaga_o_parcial(self) -> None:
        from baixador_ytdlp.updater import ReleaseInfo

        resposta = MagicMock()
        resposta.__enter__.return_value.headers = {"Content-Length": "10"}
        resposta.__enter__.return_value.read.side_effect = http.client.IncompleteRead(b"x")
        release = ReleaseInfo("1.0.0", "v1.0.0", "https://x", "setup.exe", "https://x/setup.exe", "0" * 64)
        with tempfile.TemporaryDirectory() as pasta, \
                patch("baixador_ytdlp.updater.IS_WINDOWS", True), \
                patch("baixador_ytdlp.updater.UPDATE_DIR", Path(pasta)), \
                patch("baixador_ytdlp.updater.urlopen", return_value=resposta):
            with self.assertRaises(UpdateError):
                AppUpdater().download(release)
            self.assertEqual([], list(Path(pasta).iterdir()))


class ConfiguracaoNulaTests(unittest.TestCase):
    def test_null_em_texto_nao_vira_a_string_none(self) -> None:
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "settings.json"
            caminho.write_text(json.dumps({
                "settings_schema_version": 6, "proxy": None, "cookies_browser": None,
                "limit_rate": None, "extractor_args": None,
            }), encoding="utf-8")
            with patch.object(config_module, "SETTINGS_PATH", caminho):
                cfg = Settings.load()
        self.assertEqual("", cfg.proxy)
        self.assertEqual("", cfg.cookies_browser)
        self.assertEqual("", cfg.limit_rate)
        self.assertEqual("", cfg.extractor_args)

    def test_booleano_nao_vira_inteiro(self) -> None:
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "settings.json"
            caminho.write_text(json.dumps({
                "settings_schema_version": 6, "concurrent_fragments": True,
            }), encoding="utf-8")
            with patch.object(config_module, "SETTINGS_PATH", caminho):
                cfg = Settings.load()
        self.assertEqual(Settings().concurrent_fragments, cfg.concurrent_fragments)


class TempoDoTrechoTests(unittest.TestCase):
    def test_virgula_decimal_do_teclado_brasileiro(self) -> None:
        self.assertEqual(90.5, _time_seconds("1:30,5"))
        self.assertEqual(1.5, _time_seconds("1,5"))

    def test_valores_sem_sentido_valem_zero(self) -> None:
        for texto in ("nan", "inf", "-5", "1e999", ""):
            self.assertEqual(0.0, _time_seconds(texto), texto)


class ProgressoDoFfmpegTests(unittest.TestCase):
    def _runner(self) -> DownloadRunner:
        opts = DownloadOptions(url="https://youtu.be/x", output_dir="/tmp",
                               section_start="0", section_end="100")
        return DownloadRunner(opts, Settings(), MagicMock())

    def test_out_time_na_nao_conta_como_nova_passada(self) -> None:
        runner = self._runner()
        prog = Progress()
        runner._apply_ffmpeg_progress("out_time=00:00:50.000000", prog)
        runner._apply_ffmpeg_progress("out_time=N/A", prog)
        runner._apply_ffmpeg_progress("out_time_us=N/A", prog)
        self.assertEqual(0, runner._section_pass)
        self.assertEqual(50.0, runner._section_elapsed)

    def test_tempo_negativo_do_ffmpeg_e_ignorado(self) -> None:
        runner = self._runner()
        prog = Progress()
        runner._apply_ffmpeg_progress("out_time=-00:00:00.040000", prog)
        self.assertEqual(0.0, prog.percent)
        self.assertEqual(0.0, runner._section_elapsed)


class MesclaDeCookiesTests(unittest.TestCase):
    def _linha(self, dominio: str, nome: str = "a") -> str:
        return f"{dominio}\tTRUE\t/\tTRUE\t0\t{nome}\tv"

    def test_sufixo_com_dois_rotulos_nao_apaga_outros_sites(self) -> None:
        antigo = "\n".join([self._linha(".exemplo.co.uk"), self._linha(".outro.co.uk", "b")])
        novo = self._linha(".bbc.co.uk", "c")
        mesclado = merge_cookie_text(antigo, novo)
        self.assertIn("exemplo.co.uk", mesclado)
        self.assertIn("outro.co.uk", mesclado)
        self.assertIn("bbc.co.uk", mesclado)

    def test_mesmo_site_e_substituido(self) -> None:
        antigo = self._linha(".youtube.com", "velho")
        novo = self._linha(".youtube.com", "novo")
        mesclado = merge_cookie_text(antigo, novo)
        self.assertIn("novo", mesclado)
        self.assertNotIn("velho", mesclado)


class HistoricoCorrompidoTests(unittest.TestCase):
    def test_entrada_com_tipos_errados_nao_derruba_o_carregamento(self) -> None:
        from baixador_ytdlp.history import History

        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "history.json"
            caminho.write_text(json.dumps([
                {"title": "ok", "when": 1.0},
                {"title": "when ruim", "when": "ontem"},
                {"title": "files ruim", "files": None},
                "lixo",
            ]), encoding="utf-8")
            historico = History(caminho).load()
        self.assertEqual("ok", historico.entries[0].title)
        for entrada in historico.entries:
            self.assertIsInstance(entrada.date_label, str)

    def test_limite_negativo_nao_apaga_o_historico_inteiro(self) -> None:
        from baixador_ytdlp.history import History, HistoryEntry

        historico = History(Path(tempfile.gettempdir()) / "nao-grava.json", limit=-3)
        historico.add(HistoryEntry(title="a"))
        historico.add(HistoryEntry(title="b"))
        self.assertGreaterEqual(len(historico.entries), 1)


if __name__ == "__main__":
    unittest.main()
