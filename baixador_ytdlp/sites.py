"""Plataformas além do YouTube que o yt-dlp cobre, e o que muda em cada uma.

O yt-dlp tem extrator próprio para todas elas; o que o app acrescenta é a
identificação do site (pela URL ou pela etiqueta ``[Site]`` das mensagens de erro)
para que os avisos falem do site certo e digam quando é preciso um login.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Site:
    key: str                 # etiqueta do extrator, em minúsculas: "[Instagram]"
    name: str                # nome mostrado ao usuário
    hosts: tuple[str, ...]   # domínios (inclui subdomínios)
    login: str               # quando o site exige conta: "sempre", "às vezes" ou ""
    note: str = ""           # dica curta específica do site


SITES: tuple[Site, ...] = (
    Site("youtube", "YouTube", ("youtube.com", "youtu.be", "youtube-nocookie.com"), ""),
    Site("instagram", "Instagram", ("instagram.com", "instagr.am"), "às vezes",
         "Reels e posts públicos costumam abrir sem login; stories e perfis privados exigem."),
    Site("twitter", "X (Twitter)", ("x.com", "twitter.com", "t.co"), "às vezes",
         "Vídeos sensíveis ou de contas protegidas exigem login."),
    Site("tiktok", "TikTok", ("tiktok.com",), "",
         "Links curtos (vm.tiktok.com) funcionam; o site limita IPs de datacenter."),
    Site("facebook", "Facebook", ("facebook.com", "fb.watch", "fb.com"), "às vezes",
         "Vídeos públicos abrem sem login; grupos e páginas privadas exigem."),
    Site("reddit", "Reddit", ("reddit.com", "redd.it"), "às vezes",
         "O Reddit bloqueia muitos IPs sem login."),
    Site("vimeo", "Vimeo", ("vimeo.com",), "às vezes",
         "Vídeos com senha ou só para quem segue exigem login."),
    Site("twitch", "Twitch", ("twitch.tv",), "", "VODs e clipes; assinantes exigem login."),
    Site("kick", "Kick", ("kick.com",), ""),
    Site("dailymotion", "Dailymotion", ("dailymotion.com", "dai.ly"), ""),
    Site("soundcloud", "SoundCloud", ("soundcloud.com",), ""),
    Site("bilibili", "Bilibili", ("bilibili.com", "b23.tv"), "às vezes",
         "Qualidades acima de 480p exigem login."),
    Site("pinterest", "Pinterest", ("pinterest.com", "pin.it"), ""),
    Site("linkedin", "LinkedIn", ("linkedin.com",), "sempre"),
    Site("bluesky", "Bluesky", ("bsky.app",), ""),
    Site("threads", "Threads", ("threads.net", "threads.com"), "às vezes"),
)

_BY_KEY = {site.key: site for site in SITES}
_TAG_RE = re.compile(r"\[([A-Za-z0-9:_-]+)\]")


def _host_matches(host: str, domain: str) -> bool:
    return host == domain or host.endswith("." + domain)


def site_from_url(url: str) -> Site | None:
    try:
        host = (urlsplit((url or "").strip()).hostname or "").lower()
    except ValueError:
        return None
    if not host:
        return None
    return next((site for site in SITES
                 if any(_host_matches(host, domain) for domain in site.hosts)), None)


def site_from_error(detail: str) -> Site | None:
    """Acha o site pela etiqueta do extrator: ``ERROR: [Instagram] abc: ...``."""
    for match in _TAG_RE.finditer(detail or ""):
        # "[twitter:broadcast]" e afins pertencem ao mesmo site.
        site = _BY_KEY.get(match.group(1).lower().split(":")[0])
        if site:
            return site
    return None


def login_hint(site: Site) -> str:
    """Instrução para sites que travam sem conta, na mesma linha dos avisos do YouTube."""
    return (f"{site.name} pediu login para este conteúdo. Em Configurações, selecione o Firefox "
            "ou aponte um arquivo cookies.txt de uma conta com acesso e tente de novo.")


def rate_limit_hint(site: Site) -> str:
    return (f"{site.name} limitou as requisições deste IP. Espere alguns minutos antes de "
            "tentar de novo, ou configure um proxy.")


LOGIN_MARKERS = (
    "login required", "log in", "sign in", "please log in", "requiring login",
    "use --cookies", "cookies are needed", "authentication", "nsfw", "protected tweet",
    "rate-limit reached or login required", "this content is only available for registered",
)
