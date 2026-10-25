"""Efeitos automáticos dos cortes: "whoosh" nas emendas e "pop" + zoom rápido na ênfase.

São os recursos mais comuns em vídeos curtos editados à mão. O cuidado aqui é não
exagerar: o efeito só entra onde a fala pede (uma mudança clara de assunto, uma
palavra dita mais alto) e sempre com distância mínima do anterior.

Os sons são sintetizados aqui mesmo (ruído filtrado e um seno curto): nenhum arquivo
de terceiros, nenhuma licença a acompanhar e nada a baixar.
"""
from __future__ import annotations

import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np

SAMPLE_RATE = 48000
WHOOSH_SECONDS = 0.45
WHOOSH_PEAK = 0.6           # fração do som em que o whoosh atinge o máximo
POP_SECONDS = 0.09
EFFECT_VOLUME = 0.5         # os sons ficam abaixo da voz
CUT_GAP = 1.0               # pausa removida a partir disso marca troca de assunto
CUT_SPACING = 4.0           # dois whooshes nunca a menos de 4 s
EMPHASIS_DB = 6.0           # palavra pelo menos 6 dB acima da mediana do corte
EMPHASIS_EVERY = 7.0        # no máximo uma ênfase a cada 7 s de vídeo
EFFECT_SPACING = 1.5        # whoosh e pop nunca encavalados
EDGE = 0.8                  # nada colado no começo nem no fim do corte
PUNCH = 1.15                # aproximação rápida na palavra enfatizada
PUNCH_SECONDS = 0.6


@dataclass(frozen=True)
class Effect:
    time: float     # início do som no vídeo final, em segundos
    kind: str       # "whoosh" | "pop"


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
                 total: float) -> list[Effect]:
    """Whoosh nas emendas que trocam de assunto e pop nas ênfases (tempos do vídeo final)."""
    effects: list[Effect] = []
    last_whoosh = -CUT_SPACING
    lead = WHOOSH_SECONDS * WHOOSH_PEAK   # o pico do whoosh cai em cima da emenda
    for point, gap in cut_points(intervals):
        if gap < CUT_GAP or point < EDGE or point > total - EDGE:
            continue
        if point - last_whoosh < CUT_SPACING:
            continue
        effects.append(Effect(round(max(0.0, point - lead), 3), "whoosh"))
        last_whoosh = point
    for word in emphasis:
        start = max(0.0, word["start"] - 0.01)
        if any(abs(start - effect.time) < EFFECT_SPACING for effect in effects):
            continue
        effects.append(Effect(round(start, 3), "pop"))
    return sorted(effects, key=lambda effect: effect.time)


def punch_windows(emphasis: list[dict], total: float) -> list[tuple[float, float]]:
    return [(round(word["start"], 3), round(min(total, word["start"] + PUNCH_SECONDS), 3))
            for word in emphasis]


def whoosh_sound(rate: int = SAMPLE_RATE, seed: int = 7) -> np.ndarray:
    """Ruído com filtro que abre e fecha: o "vuuush" de transição."""
    count = int(WHOOSH_SECONDS * rate)
    noise = np.random.default_rng(seed).uniform(-1.0, 1.0, count).astype(np.float32)
    position = np.linspace(0.0, 1.0, count, dtype=np.float32)
    # Frequência de corte sobe até o pico e desce depois (passa-baixas de um polo).
    sweep = np.where(position < WHOOSH_PEAK, position / WHOOSH_PEAK,
                     (1.0 - position) / (1.0 - WHOOSH_PEAK))
    cutoff = 300.0 + 5200.0 * sweep ** 2
    alpha = 1.0 - np.exp(-2.0 * np.pi * cutoff / rate)
    out = np.empty(count, dtype=np.float32)
    state = 0.0
    for index in range(count):
        state += float(alpha[index]) * (float(noise[index]) - state)
        out[index] = state
    envelope = sweep ** 1.5
    out *= envelope
    return out / max(1e-6, float(np.abs(out).max())) * 0.8


def pop_sound(rate: int = SAMPLE_RATE) -> np.ndarray:
    """Seno curto que cai de tom: o "pop" de destaque."""
    count = int(POP_SECONDS * rate)
    seconds = np.arange(count, dtype=np.float32) / rate
    frequency = 300.0 + 700.0 * np.exp(-seconds * 40.0)
    phase = 2.0 * np.pi * np.cumsum(frequency) / rate
    envelope = np.exp(-seconds * 45.0) * np.minimum(1.0, seconds * rate / 48.0)
    return (np.sin(phase) * envelope * 0.8).astype(np.float32)


def write_wav(path: Path, samples: np.ndarray, rate: int = SAMPLE_RATE) -> Path:
    data = (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(rate)
        stream.writeframes(data.tobytes())
    return path


def write_sounds(folder: Path, effects: list[Effect]) -> dict[str, Path]:
    """Grava só os sons usados neste corte; devolve ``tipo -> arquivo``."""
    makers = {"whoosh": whoosh_sound, "pop": pop_sound}
    kinds = sorted({effect.kind for effect in effects})
    return {kind: write_wav(folder / f"efeito-{kind}.wav", makers[kind]()) for kind in kinds}
