"""Tradução das mensagens do yt-dlp para instruções que resolvem o problema."""
from __future__ import annotations

import unittest

from baixador_ytdlp.probe import friendly_error

YT = "ERROR: [youtube] abc123XYZ00: "


class FriendlyErrorTests(unittest.TestCase):
    def assertMentions(self, message: str, expected: str) -> None:
        self.assertIn(expected, friendly_error(message), message)

    def test_restricao_de_idade_nao_vira_pedido_de_robo(self) -> None:
        self.assertMentions(
            YT + "Sign in to confirm your age. This video may be inappropriate for some users.",
            "restrição de idade")

    def test_confirmacao_de_robo(self) -> None:
        self.assertMentions(YT + "Sign in to confirm you’re not a bot. Use --cookies…", "robô")
        self.assertMentions(YT + "Sign in to confirm you're not a bot.", "robô")

    def test_bloqueio_regional_nao_vira_video_removido(self) -> None:
        self.assertMentions(
            YT + "Video unavailable. The uploader has not made this video available in your country",
            "região")

    def test_servidor_instavel_nao_vira_video_removido(self) -> None:
        self.assertMentions("ERROR: HTTP Error 503: Service Unavailable", "instável")
        self.assertMentions("ERROR: Unable to download webpage: temporarily unavailable", "instável")

    def test_video_removido(self) -> None:
        self.assertMentions(YT + "Video unavailable. This video has been removed by the uploader",
                            "removido")

    def test_palavras_com_age_nao_disparam_restricao(self) -> None:
        for message in ("ERROR: unable to extract image; please report this issue",
                        "ERROR: storage quota confirmation failed"):
            self.assertNotIn("idade", friendly_error(message), message)

    def test_mensagens_existentes_continuam(self) -> None:
        self.assertMentions("ERROR: Failed to decrypt with DPAPI", "cookies do Chrome")
        self.assertMentions(YT + "The page needs to be reloaded.", "Deno")
        self.assertMentions("ERROR: HTTP Error 429: Too Many Requests", "limitou")
        self.assertMentions("ERROR: Requested format is not available", "formato")
        self.assertMentions("ERROR: Unsupported URL: https://example.com", "não é suportado")


if __name__ == "__main__":
    unittest.main()
