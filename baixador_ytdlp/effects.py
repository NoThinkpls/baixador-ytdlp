"""Onde entram os efeitos dos cortes: sons e zoom rápido na ênfase.

Há duas fontes de decisão:

* o **plano da IA** (``plano_ia``): quem leu a transcrição inteira diz em que palavra
  entra cada som. O app só encaixa: procura a palavra no tempo exato do Whisper, puxa
  o whoosh para a emenda mais próxima e converte para o tempo do vídeo já sem pausas;
* sem plano, uma regra simples pelo áudio: whoosh na emenda de uma pausa longa e pop na
  palavra dita bem mais alto, sempre com distância mínima entre eles.

Em qualquer caso, som só entra junto de algo que acontece na imagem, a regra de edição
de vídeo curto ("o som acompanha o corte, o zoom, o texto que aparece"): o whoosh fica
na emenda (o salto da imagem) e os outros sons vêm com o zoom rápido naquele ponto.
Som solto, sem nada mudando na tela, soa como ruído que "não bate" com o vídeo.

Os sons em si ficam em ``sfx``.
"""
from __future__ import annotations

import re
import unicodedata
import wave
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np

CUT_GAP = 1.0               # pausa removida a partir disso marca troca de assunto
CUT_SPACING = 6.0           # regra automática: dois whooshes nunca a menos de 6 s
EMPHASIS_DB = 6.0           # palavra pelo menos 6 dB acima da mediana do corte
EMPHASIS_EVERY = 8.0        # regra automática: no máximo uma ênfase a cada 8 s
EFFECT_SPACING = 1.5        # regra automática: sons nunca encavalados
EDGE = 0.8                  # regra automática: nada colado no começo nem no fim
PUNCH = 1.15                # aproximação rápida na palavra enfatizada
PUNCH_SECONDS = 0.6
WORD_WINDOW = 6.0           # o plano da IA vem do SRT: a palavra é procurada ±6 s em volta
SNAP_TO_CUT = 1.5           # whoosh do plano a até 1,5 s de uma emenda vai para ela
SOUND_GAP = 3.0             # dois sons quaisquer nunca a menos de 3 s
TRANSITION = "whoosh"       # o único som que acompanha a emenda; os outros pedem zoom


@dataclass(frozen=True)
class Effect:
    time: float     # no vídeo final, em segundos: o instante que importa (ou, depois de
                    # ``schedule``, o início do som)
    kind: str       # um de ``sfx.SOUNDS``


@dataclass(frozen=True)
class Marker:
    """Um ponto do plano da IA, no tempo do vídeo original (o mesmo do SRT)."""
    time: float
    sound: str = ""     # "" = só zoom
    word: str = ""      # palavra dita nesse momento, para achar o tempo exato
    zoom: bool = False


def cut_points(intervals: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """``(instante da emenda no vídeo final, duração da pausa removida)``."""
    points, cursor = [], 0.0
    for previous, current in zip(intervals, intervals[1:], strict=False):
        cursor += previous[1] - previous[0]
        points.append((cursor, current[0] - previous[1]))
    return points


def read_wav(path: Path) -> tuple[np.ndarray, int]:
    """WAV PCM 16 bits (o áudio que vai para o Whisper) como float mono."""
    with wave.open(str(path), "rb") as stream:
        rate, channels = stream.getframerate(), stream.getnchannels()
        if stream.getsampwidth() != 2:
            raise ValueError("WAV sem PCM de 16 bits")
        data = np.frombuffer(stream.readframes(stream.getnframes()), dtype="<i2")
    samples = data.astype(np.float32) / 32768.0
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)
    return samples, rate


def word_loudness(samples: np.ndarray, rate: int, words: list[dict]) -> list[float]:
    """Volume (dBFS, RMS) de cada palavra no áudio do trecho."""
    levels = []
    for word in words:
        start = max(0, int(word["start"] * rate))
        end = min(len(samples), max(start + 1, int(word["end"] * rate)))
        chunk = samples[start:end]
        rms = float(np.sqrt(np.mean(chunk * chunk))) if chunk.size else 0.0
        levels.append(20 * np.log10(max(rms, 1e-6)))
    return levels


def emphasis_words(words: list[dict], total: float) -> list[dict]:
    """Palavras que a pessoa disse com mais força, espaçadas como num corte editado.

    ``words`` já no tempo do vídeo final, cada uma com ``level`` (dBFS de
    ``word_loudness``). Conta como ênfase a palavra com pelo menos 3 letras dita 6 dB
    acima da mediana do corte, ou terminada em "!". Ficam as mais fortes, uma a cada
    ``EMPHASIS_EVERY`` segundos.
    """
    levels = [float(word["level"]) for word in words if "level" in word]
    if not levels:
        return []
    median = float(np.median(levels))
    candidates = []
    for word in words:
        if "level" not in word:
            continue
        text = str(word.get("text", "")).strip()
        letters = sum(char.isalnum() for char in text)
        score = float(word["level"]) - median
        if text.endswith("!"):
            score = max(score, EMPHASIS_DB)
        if letters >= 3 and score >= EMPHASIS_DB and EDGE <= word["start"] <= total - EDGE:
            candidates.append((score, word))
    limit = max(1, int(total // EMPHASIS_EVERY))
    chosen: list[dict] = []
    for _score, word in sorted(candidates, key=lambda item: -item[0]):
        if all(abs(word["start"] - other["start"]) >= EMPHASIS_EVERY for other in chosen):
            chosen.append(word)
        if len(chosen) >= limit:
            break
    return sorted(chosen, key=lambda word: word["start"])


def plan_effects(intervals: list[tuple[float, float]], emphasis: list[dict],
                 total: float, *, pops: bool = True) -> list[Effect]:
    """Regra automática: whoosh nas emendas que trocam de assunto e pop nas ênfases.

    ``pops`` falso (zoom na ênfase desligado): sem pop, que ficaria sem nada na imagem.
    """
    effects: list[Effect] = []
    last_whoosh = -CUT_SPACING
    for point, gap in cut_points(intervals):
        if gap < CUT_GAP or point < EDGE or point > total - EDGE:
            continue
        if point - last_whoosh < CUT_SPACING:
            continue
        effects.append(Effect(round(point, 3), "whoosh"))
        last_whoosh = point
    for word in emphasis if pops else []:
        if any(abs(word["start"] - effect.time) < EFFECT_SPACING for effect in effects):
            continue
        effects.append(Effect(round(word["start"], 3), "pop"))
    return sorted(effects, key=lambda effect: effect.time)


def punch_windows(emphasis: list[dict], total: float) -> list[tuple[float, float]]:
    return windows_at([word["start"] for word in emphasis], total)


def windows_at(times: list[float], total: float) -> list[tuple[float, float]]:
    windows: list[tuple[float, float]] = []
    for start in sorted(times):
        end = min(total, start + PUNCH_SECONDS)
        if end - start < 0.1 or (windows and start < windows[-1][1]):
            continue
        windows.append((round(start, 3), round(end, 3)))
    return windows


def _norm(text: str) -> str:
    """Palavra comparável: sem acento, pontuação nem maiúsculas."""
    plain = unicodedata.normalize("NFKD", text.casefold())
    plain = "".join(char for char in plain if not unicodedata.combining(char))
    return re.sub(r"[^\w]", "", plain)


def find_word(words: list[dict], word: str, near: float) -> dict | None:
    """A ocorrência de ``word`` mais perto de ``near`` (tempos relativos ao trecho).

    Com mais de uma palavra ("graça de Deus"), vale a sequência inteira começando ali.
    """
    wanted = [_norm(part) for part in word.split() if _norm(part)]
    if not wanted:
        return None
    best, best_distance = None, WORD_WINDOW
    tokens = [_norm(str(item.get("text", ""))) for item in words]
    for index, token in enumerate(tokens):
        if token != wanted[0]:
            continue
        if tokens[index:index + len(wanted)] != wanted:
            continue
        distance = abs(words[index]["start"] - near)
        if distance <= best_distance:
            best, best_distance = words[index], distance
    return best


def _join_times(intervals: list[tuple[float, float]]) -> list[tuple[float, float, float]]:
    """``(fim do trecho anterior, início do próximo, instante da emenda no vídeo final)``."""
    joins, cursor = [], 0.0
    for previous, current in zip(intervals, intervals[1:], strict=False):
        cursor += previous[1] - previous[0]
        joins.append((previous[1], current[0], cursor))
    return joins


def place_markers(markers: list[Marker], clip_start: float, words: list[dict],
                  intervals: list[tuple[float, float]], total: float,
                  remap: Callable[[float, list[tuple[float, float]]], float],
                  ) -> tuple[list[Effect], list[tuple[float, float]]]:
    """Plano da IA → sons e janelas de zoom no tempo do vídeo final.

    ``words`` são as palavras do Whisper com tempo relativo ao início do trecho, antes
    de tirar as pausas; ``remap`` é ``clips.remap_time``.
    """
    length = intervals[-1][1] if intervals else 0.0
    effects: list[Effect] = []
    zooms: list[float] = []
    for marker in markers:
        relative = marker.time - clip_start
        found = find_word(words, marker.word, relative) if marker.word else None
        if found is not None:
            relative = float(found["start"])
        if relative < -0.5 or relative > length + 0.5:
            continue   # ponto de outro corte, ou fora do trecho
        relative = min(max(relative, 0.0), length)
        moment = remap(relative, intervals)
        sound = marker.sound
        if sound == TRANSITION:
            # A troca de assunto que a IA viu quase sempre é uma pausa que o app cortou.
            # Sem emenda perto não há transição na imagem: o whoosh ficaria solto.
            near = [(min(abs(relative - end), abs(relative - start)), at)
                    for end, start, at in _join_times(intervals)
                    if end - SNAP_TO_CUT <= relative <= start + SNAP_TO_CUT]
            if near:
                moment = min(near)[1]
            else:
                sound = ""
        moment = round(min(max(moment, 0.0), total), 3)
        if sound and all(_apart(effect, sound, moment) for effect in effects):
            effects.append(Effect(moment, sound))
            if sound != TRANSITION:
                zooms.append(moment)        # o som vem com o zoom: algo acontece na tela
        if marker.zoom:
            zooms.append(moment)
    return sorted(effects, key=lambda effect: effect.time), windows_at(zooms, total)


def _apart(effect: Effect, sound: str, moment: float) -> bool:
    """Longe o bastante de um som já posto; a subida que termina no golpe é a exceção."""
    if "subida" in (effect.kind, sound) and effect.kind != sound \
            and abs(effect.time - moment) < 0.3:
        return True                   # subida que desemboca no impacto: um efeito só
    return abs(effect.time - moment) >= SOUND_GAP


def with_visuals(planned: list[Effect], zoom: bool) -> list[Effect]:
    """Com o zoom na ênfase desligado, só o whoosh (que tem a emenda) continua."""
    return [effect for effect in planned if zoom or effect.kind == TRANSITION]


def schedule(effects: list[Effect], leads: dict[str, float]) -> list[Effect]:
    """Do instante marcado para o início de cada som (o pico do whoosh cai na emenda)."""
    return [Effect(round(max(0.0, effect.time - leads.get(effect.kind, 0.0)), 3), effect.kind)
            for effect in effects if effect.kind in leads]
