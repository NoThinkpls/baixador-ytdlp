"""Biblioteca de sons dos cortes: os cinco efeitos mais comuns em vídeos curtos.

Os sons padrão são sintetizados aqui (ruído filtrado, senos e um reverb curto), sem
arquivos de terceiros. Quem preferir os sons de outro editor aponta uma pasta com
arquivos chamados pelo tipo (``whoosh.wav``, ``impacto.mp3``…) e eles têm prioridade.
"""
from __future__ import annotations

import wave
from collections.abc import Callable
from pathlib import Path

import numpy as np

SAMPLE_RATE = 48000
SOUNDS = ("whoosh", "pop", "impacto", "ding", "subida")
LABELS = {
    "whoosh": "Whoosh (transição)",
    "pop": "Pop (destaque)",
    "impacto": "Impacto (frase forte)",
    "ding": "Ding (ideia-chave)",
    "subida": "Subida (antes do clímax)",
}
# Volume de cada som na mistura: abaixo da voz, com o impacto um pouco mais presente.
GAIN = {"whoosh": 0.55, "pop": 0.5, "impacto": 0.7, "ding": 0.4, "subida": 0.45}
AUDIO_EXTENSIONS = (".wav", ".mp3", ".ogg", ".m4a", ".flac", ".aac", ".opus")
WHOOSH_SECONDS, WHOOSH_PEAK = 0.62, 0.58
SUBIDA_SECONDS = 1.6


def _rng(seed: int) -> np.random.Generator:
    return np.random.default_rng(seed)


def _band_noise(count: int, centers: np.ndarray, width: float, seed: int,
                rate: int = SAMPLE_RATE) -> np.ndarray:
    """Ruído branco com um passa-faixa que acompanha ``centers`` (Hz por amostra).

    Feito por blocos com FFT e sobreposição (Hann, 75%): um filtro que varia no tempo
    sem laço por amostra em Python.
    """
    size, hop = 2048, 512
    noise = _rng(seed).standard_normal(count + size).astype(np.float64)
    window = np.hanning(size)
    freqs = np.fft.rfftfreq(size, 1 / rate)
    out = np.zeros(count + size)
    norm = np.zeros(count + size)
    for begin in range(0, count, hop):
        center = float(centers[min(count - 1, begin + size // 2)])
        # Faixa em escala logarítmica: soa igual em grave e agudo.
        octave = np.log2(np.maximum(freqs, 20.0) / max(center, 20.0))
        mask = np.exp(-0.5 * (octave / width) ** 2)
        block = np.fft.irfft(np.fft.rfft(noise[begin:begin + size] * window) * mask, size)
        out[begin:begin + size] += block * window
        norm[begin:begin + size] += window ** 2
    return (out / np.maximum(norm, 1e-6))[:count]


def _lowpass(signal: np.ndarray, cutoff: float, rate: int = SAMPLE_RATE) -> np.ndarray:
    spectrum = np.fft.rfft(signal)
    freqs = np.fft.rfftfreq(len(signal), 1 / rate)
    return np.fft.irfft(spectrum / np.sqrt(1 + (freqs / cutoff) ** 4), len(signal))


def _reverb(signal: np.ndarray, seconds: float, mix: float, seed: int,
            rate: int = SAMPLE_RATE) -> np.ndarray:
    """Sala curta: resposta de ruído com decaimento exponencial, por convolução FFT."""
    length = int(seconds * rate)
    impulse = _rng(seed).standard_normal(length) * np.exp(-6.9 * np.arange(length) / length)
    impulse = _lowpass(impulse, 5000.0, rate)
    impulse /= np.sqrt(np.sum(impulse ** 2)) or 1.0
    size = len(signal) + length
    wet = np.fft.irfft(np.fft.rfft(signal, size) * np.fft.rfft(impulse, size), size)
    dry = np.pad(signal, (0, length))
    return dry * (1 - mix) + wet * mix


def _stereo(left: np.ndarray, right: np.ndarray) -> np.ndarray:
    stereo = np.stack([left, right], axis=1)
    peak = float(np.abs(stereo).max()) or 1.0
    return (stereo / peak * 0.89).astype(np.float32)   # -1 dBFS


def _fade(signal: np.ndarray, rate: int = SAMPLE_RATE, ms: float = 4.0) -> np.ndarray:
    count = min(len(signal) // 2, int(rate * ms / 1000))
    if count:
        ramp = np.linspace(0.0, 1.0, count)
        signal[:count] *= ramp
        signal[-count:] *= ramp[::-1]
    return signal


def whoosh(rate: int = SAMPLE_RATE) -> np.ndarray:
    """Ar passando: faixa de ruído que sobe e desce de tom, cruzando da esquerda à direita."""
    count = int(WHOOSH_SECONDS * rate)
    position = np.linspace(0.0, 1.0, count)
    rise = np.where(position < WHOOSH_PEAK, position / WHOOSH_PEAK,
                    (1 - position) / (1 - WHOOSH_PEAK))
    centers = 350.0 * (9.0 ** rise)                       # 350 Hz → ~3,1 kHz → 350 Hz
    body = _band_noise(count, centers, 0.55, seed=11, rate=rate)
    air = _band_noise(count, centers * 2.4, 0.35, seed=12, rate=rate) * 0.35
    envelope = np.where(position < WHOOSH_PEAK, rise ** 2.2, rise ** 1.3)
    mono = (body + air) * envelope
    pan = np.clip(position * 1.2 - 0.1, 0.0, 1.0)         # esquerda → direita
    left = _reverb(_fade(mono * np.cos(pan * np.pi / 2), rate), 0.35, 0.18, 21, rate)
    right = _reverb(_fade(mono * np.sin(pan * np.pi / 2), rate), 0.35, 0.18, 22, rate)
    return _stereo(left, right)


def pop(rate: int = SAMPLE_RATE) -> np.ndarray:
    """Bolha que estoura: tom curto que sobe rápido, com estalo no começo."""
    count = int(0.11 * rate)
    seconds = np.arange(count) / rate
    frequency = 380.0 + 900.0 * (1 - np.exp(-seconds * 55.0))
    tone = np.sin(2 * np.pi * np.cumsum(frequency) / rate)
    envelope = np.exp(-seconds * 38.0) * np.minimum(1.0, seconds * rate / 60.0)
    click = _lowpass(_rng(5).standard_normal(count) * np.exp(-seconds * 900.0), 6000.0, rate)
    mono = _fade(tone * envelope + click * 0.25, rate, 2.0)
    wet = _reverb(mono, 0.18, 0.12, 31, rate)
    return _stereo(wet, wet)


def impacto(rate: int = SAMPLE_RATE) -> np.ndarray:
    """Boom de cinema: grave que cai de tom, ataque de ruído e cauda de sala."""
    count = int(1.4 * rate)
    seconds = np.arange(count) / rate
    frequency = 42.0 + 70.0 * np.exp(-seconds * 9.0)      # 112 Hz → 42 Hz
    sub = np.sin(2 * np.pi * np.cumsum(frequency) / rate) * np.exp(-seconds * 2.6)
    knock = _lowpass(_rng(7).standard_normal(count), 900.0, rate) * np.exp(-seconds * 30.0)
    crack = _lowpass(_rng(8).standard_normal(count), 7000.0, rate) * np.exp(-seconds * 120.0)
    mono = np.tanh(1.8 * (sub + 0.9 * knock + 0.25 * crack)) * np.minimum(1.0, seconds * rate / 24)
    left = _reverb(_fade(mono.copy(), rate), 1.1, 0.25, 41, rate)
    right = _reverb(_fade(mono.copy(), rate), 1.1, 0.25, 42, rate)
    return _stereo(left, right)


def ding(rate: int = SAMPLE_RATE) -> np.ndarray:
    """Sino pequeno: parciais de sino (não harmônicos) com decaimentos diferentes."""
    count = int(1.3 * rate)
    seconds = np.arange(count) / rate
    base = 1318.5                                          # mi 6
    partials = ((1.0, 1.0, 3.2), (2.0, 0.45, 4.5), (2.76, 0.3, 6.0), (5.4, 0.16, 9.0),
                (8.93, 0.08, 13.0))
    channels = []
    for detune in (0.0, 1.6):                              # leve batimento entre os canais
        tone = sum(amplitude * np.sin(2 * np.pi * (base * ratio + detune) * seconds)
                   * np.exp(-seconds * decay) for ratio, amplitude, decay in partials)
        tone = np.asarray(tone) * np.minimum(1.0, seconds * rate / 90.0)
        channels.append(_reverb(_fade(tone, rate), 0.6, 0.2, 51 + len(channels), rate))
    return _stereo(channels[0], channels[1])


def subida(rate: int = SAMPLE_RATE) -> np.ndarray:
    """Riser: ruído e tom subindo juntos, crescendo até parar seco no ponto marcado."""
    count = int(SUBIDA_SECONDS * rate)
    position = np.linspace(0.0, 1.0, count)
    centers = 250.0 * (24.0 ** position)                  # 250 Hz → 6 kHz
    noise = _band_noise(count, centers, 0.5, seed=61, rate=rate)
    frequency = 180.0 * (6.0 ** position)
    tone = np.sin(2 * np.pi * np.cumsum(frequency) / rate) * 0.35
    vibrato = 1.0 + 0.15 * np.sin(2 * np.pi * (4 + 10 * position) * position)
    mono = (noise + tone) * (position ** 2.4) * vibrato
    mono[-int(0.008 * rate):] *= np.linspace(1.0, 0.0, int(0.008 * rate))
    spread = _band_noise(count, centers * 1.5, 0.5, seed=62, rate=rate) * position ** 2.4 * 0.4
    return _stereo(mono + spread, mono - spread)


MAKERS: dict[str, Callable[..., np.ndarray]] = {
    "whoosh": whoosh, "pop": pop, "impacto": impacto, "ding": ding, "subida": subida}


def write_wav(path: Path, samples: np.ndarray, rate: int = SAMPLE_RATE) -> Path:
    data = np.asarray(samples, dtype=np.float32)
    channels = 1 if data.ndim == 1 else data.shape[1]
    pcm = (np.clip(data, -1.0, 1.0) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(channels)
        stream.setsampwidth(2)
        stream.setframerate(rate)
        stream.writeframes(pcm.tobytes())
    return path


def custom_sound(folder: Path | None, kind: str) -> Path | None:
    """Arquivo da pessoa para este tipo de som (``impacto.mp3``, ``Whoosh.WAV``…)."""
    if not folder or not folder.is_dir():
        return None
    for path in sorted(folder.iterdir()):
        if path.is_file() and path.stem.casefold() == kind and \
                path.suffix.casefold() in AUDIO_EXTENSIONS:
            return path
    return None


def lead_seconds(kind: str, duration: float = 0.0) -> float:
    """Quanto antes do instante marcado o som precisa começar.

    O pico do whoosh e o fim da subida caem em cima do ponto; os demais começam nele.
    Sem ``duration``, vale o som padrão (a cauda de reverb não conta).
    """
    if kind == "whoosh":
        return duration * 0.5 if duration else WHOOSH_SECONDS * WHOOSH_PEAK
    if kind == "subida":
        return duration or SUBIDA_SECONDS
    return 0.01


def prepare(folder: Path, kinds: set[str], custom: Path | None = None,
            duration_of: Callable[[Path], float] | None = None) -> dict[str, tuple[Path, float]]:
    """``tipo -> (arquivo, antecedência)`` para os sons usados neste corte."""
    result = {}
    for kind in sorted(kinds & set(SOUNDS)):
        own = custom_sound(custom, kind)
        if own is not None and duration_of is not None:
            try:
                duration = float(duration_of(own))
            except Exception:  # noqa: BLE001 - arquivo ilegível volta ao som padrão
                duration = 0.0
            if duration > 0:
                result[kind] = (own, lead_seconds(kind, duration))
                continue
        path = write_wav(folder / f"efeito-{kind}.wav", MAKERS[kind]())
        result[kind] = (path, lead_seconds(kind))
    return result
