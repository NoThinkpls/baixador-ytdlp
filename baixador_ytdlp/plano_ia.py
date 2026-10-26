"""Plano de cortes vindo de uma IA (o Criador de Títulos), em uma linha de JSON.

A IA lê a transcrição inteira e entende o contexto; o app só executa. O formato é
compacto de propósito, para colar num campo só:

    {"bx":1,"c":[["12:03","12:58","TÍTULO DO CORTE",[["12:10","graça","i",1]]]]}

* ``c``: lista de cortes ``[início, fim, título, efeitos]``;
* cada efeito: ``[tempo, palavra, som, zoom]``. O tempo vem do SRT (vídeo inteiro),
  a palavra é a que está sendo dita (o app procura o tempo exato dela), o som é uma
  letra (``w`` whoosh, ``p`` pop, ``i`` impacto, ``d`` ding, ``s`` subida, ``""`` só
  zoom) e o zoom é 1 ou 0;
* opcionais, valendo para todos os cortes: ``t`` é o tipo de título (``"f"`` fixo no
  topo, ``"a"`` animado) e ``l`` a linha pequena acima do título fixo. Sem eles, a
  página fica como está.

A linha pode vir no meio da resposta inteira da IA: o app acha o ``{"bx"`` sozinho.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

from .clips import (MAX_CLIP_SECONDS, MIN_CLIP_SECONDS, ClipError, ClipRange, format_clock,
                    parse_time)
from .effects import Marker
from .sfx import SOUNDS

MAX_CUTS = 20
MAX_EFFECTS = 40            # por corte
MAX_LABEL = 80
TITLE_CODES = {"f": "banner", "fixo": "banner", "a": "animated", "animado": "animated"}
SOUND_CODES = {"w": "whoosh", "p": "pop", "i": "impacto", "d": "ding", "s": "subida"}
_START = re.compile(r'\{\s*"bx"\s*:')
# Celular, Word e o próprio chat da IA trocam as aspas retas por curvas ao copiar; o JSON
# só aceita as retas.
_QUOTES = str.maketrans({"\u201c": '"', "\u201d": '"', "\u201e": '"', "\u201f": '"',
                         "\u2033": '"', "\uff02": '"', "\u00ab": '"', "\u00bb": '"'})


def normalize_quotes(text: str) -> str:
    return (text or "").translate(_QUOTES).replace("&#34;", '"').replace("&quot;", '"')


def _repair_inner_quotes(text: str, start: int) -> str:
    """O objeto a partir de ``start`` com as aspas de dentro dos textos escapadas.

    Título entre aspas ("ISSO É MEDO?") vem da IA com aspas curvas dentro do texto; depois
    de ``normalize_quotes`` elas viram retas e fecham o texto no meio. No formato do plano,
    uma aspa só fecha o texto quando a seguinte coisa é ``,`` ``]`` ``}`` ou ``:``; as
    outras são do próprio texto e ganham a barra invertida.
    """
    out: list[str] = []
    depth, inside, index = 0, False, start
    while index < len(text):
        char = text[index]
        if inside:
            if char == "\\" and index + 1 < len(text):
                out.append(text[index:index + 2])
                index += 2
                continue
            if char == '"':
                after = index + 1
                while after < len(text) and text[after].isspace():
                    after += 1
                if text[after:after + 1] in {",", "]", "}", ":"}:
                    inside = False
                    out.append(char)
                else:
                    out.append('\\"')
                index += 1
                continue
            out.append(char)
        else:
            out.append(char)
            if char == '"':
                inside = True
            elif char in "{[":
                depth += 1
            elif char in "}]":
                depth -= 1
                if depth == 0:
                    break
        index += 1
    return "".join(out)


class PlanError(ClipError):
    """O texto colado não traz um plano que o app consiga usar."""


def _time(value) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    try:
        return parse_time(str(value))
    except ClipError as exc:
        raise PlanError(f"Tempo inválido no plano: {value!r}.") from exc


def _sound(value) -> str:
    text = str(value or "").strip().casefold()
    if text in SOUND_CODES:
        return SOUND_CODES[text]
    return text if text in SOUNDS else ""


def find_plan(text: str) -> dict:
    """O primeiro objeto ``{"bx": …}`` do texto, mesmo dentro de um bloco ```json."""
    text = normalize_quotes(text)
    match = _START.search(text)
    if not match:
        raise PlanError(
            'Não encontrei o plano no texto colado. Ele é uma linha que começa com {"bx":1, '
            "no fim da resposta da IA.")
    try:
        plan, _end = json.JSONDecoder().raw_decode(text, match.start())
    except json.JSONDecodeError:
        try:
            plan = json.loads(_repair_inner_quotes(text, match.start()))
        except json.JSONDecodeError as exc:
            raise PlanError(
                "O plano está incompleto ou com erro de digitação (JSON inválido). Copie a "
                "linha inteira de novo.") from exc
    if not isinstance(plan, dict):
        raise PlanError("O plano colado não está no formato esperado.")
    return plan


def parse_plan(text: str) -> list[ClipRange]:
    """Cortes com título e pontos de efeito; pontos fora do próprio corte são ignorados."""
    plan = find_plan(text)
    cuts = plan.get("c")
    if not isinstance(cuts, list) or not cuts:
        raise PlanError('O plano não traz nenhum corte (lista "c" vazia).')
    ranges: list[ClipRange] = []
    for number, cut in enumerate(cuts[:MAX_CUTS], start=1):
        if not isinstance(cut, list) or len(cut) < 2:
            raise PlanError(f"O corte {number} do plano está incompleto.")
        start, end = _time(cut[0]), _time(cut[1])
        if end - start < MIN_CLIP_SECONDS or end - start > MAX_CLIP_SECONDS:
            raise PlanError(
                f"O corte {number} ({format_clock(start)} a {format_clock(end)}) precisa ter "
                f"entre 1 segundo e {MAX_CLIP_SECONDS // 60} minutos.")
        title = " ".join(str(cut[2] if len(cut) > 2 and cut[2] else "").split())
        markers: list[Marker] = []
        effects = cut[3] if len(cut) > 3 and isinstance(cut[3], list) else []
        for item in effects[:MAX_EFFECTS]:
            if not isinstance(item, list) or not item:
                continue
            try:
                moment = _time(item[0])
            except PlanError:
                continue   # um ponto ruim não derruba o plano inteiro
            word = " ".join(str(item[1] if len(item) > 1 and item[1] else "").split())
            sound = _sound(item[2] if len(item) > 2 else "")
            zoom = bool(item[3]) if len(item) > 3 else False
            if (sound or zoom) and start - 1 <= moment <= end + 1:
                markers.append(Marker(moment, sound, word[:60], zoom))
        ranges.append(ClipRange(start, end, title, tuple(markers)))
    return ranges


@dataclass(frozen=True)
class PlanLook:
    """Escolhas de visual que o plano pode trazer; vazio/None = a página decide."""
    title_mode: str = ""            # "banner" (fixo no topo), "animated" ou ""
    label: str | None = None        # linha de cima do título fixo


def parse_look(text: str) -> PlanLook:
    """Tipo de título (``t``) e linha de cima (``l``) do plano; valores estranhos são ignorados."""
    plan = find_plan(text)
    mode = TITLE_CODES.get(str(plan.get("t") or "").strip().casefold(), "")
    label = plan.get("l")
    return PlanLook(mode, " ".join(label.split())[:MAX_LABEL] if isinstance(label, str)
                    else None)


def markers_text(markers: tuple[Marker, ...]) -> str:
    """Resumo para a dica da linha do corte: "12:10 impacto em “graça” + zoom"."""
    lines = []
    for marker in markers:
        what = marker.sound or "zoom"
        if marker.sound and marker.zoom:
            what += " + zoom"
        where = f" em “{marker.word}”" if marker.word else ""
        lines.append(f"{format_clock(marker.time)} {what}{where}")
    return "\n".join(lines)
