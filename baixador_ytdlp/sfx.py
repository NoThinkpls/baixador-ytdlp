"""Biblioteca de sons dos cortes: os cinco efeitos mais comuns em vídeos curtos.

Os sons padrão são sintetizados aqui (ruído filtrado, senos e um reverb curto), sem
arquivos de terceiros. Quem preferir os sons de outro editor aponta uma pasta com
arquivos chamados pelo tipo (``whoosh.wav``, ``impacto.mp3``…) e eles têm prioridade.

O volume de cada som é medido e acertado em relação à voz do corte (``matched_gains``):
como num editor, o efeito fica alguns dB abaixo da fala, seja a gravação baixa ou alta,
seja o som do app ou o da pessoa. Antes era um ganho fixo sobre um som normalizado no
pico, e o grave do impacto chegava perto do volume máximo, acima da própria voz.
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
# Volume de cada som na mistura quando não dá para medir a voz (ganho fixo de reserva).
GAIN = {"whoosh": 0.3, "pop": 0.3, "impacto": 0.35, "ding": 0.2, "subida": 0.25}
# Quantos dB abaixo da voz cada som fica (medidos do mesmo jeito: pedaço mais forte, sem
# o grave que o celular nem toca). Referência de mixagem de vídeo curto: efeito de 8 a
# 15 dB abaixo da fala; o whoosh cai numa pausa cortada e pode ficar mais perto.
BELOW_VOICE = {"whoosh": 9.0, "pop": 12.0, "impacto": 8.0, "ding": 14.0, "subida": 12.0}
PEAK_LIMIT = 0.5                 # -6 dBFS: nenhum efeito passa disso, nem em voz alta
AUDIO_EXTENSIONS = (".wav", ".mp3", ".ogg", ".m4a", ".flac", ".aac", ".opus")
WHOOSH_SECONDS, WHOOSH_PEAK = 0.62, 0.58
SUBIDA_SECONDS = 1.2
LOUD_WINDOW = 0.3                # janela (s) do pedaço mais forte de um som


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


def _highpass(signal: np.ndarray, cutoff: float, rate: int = SAMPLE_RATE) -> np.ndarray:
    spectrum = np.fft.rfft(signal)
    freqs = np.fft.rfftfreq(len(signal), 1 / rate)
    ratio = (freqs / cutoff) ** 4
    return np.fft.irfft(spectrum * np.sqrt(ratio / (1 + ratio)), len(signal))


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
    """Toque curto e seco (um "tum" de madeira), sem o tom subindo de desenho animado."""
    count = int(0.16 * rate)
    seconds = np.arange(count) / rate
    frequency = 150.0 + 110.0 * np.exp(-seconds * 60.0)    # 260 Hz → 150 Hz
    body = np.sin(2 * np.pi * np.cumsum(frequency) / rate) * np.exp(-seconds * 32.0)
    click = _lowpass(_rng(5).standard_normal(count) * np.exp(-seconds * 700.0), 3500.0, rate)
    mono = _fade(body * np.minimum(1.0, seconds * rate / 24.0) + click * 0.35, rate, 2.0)
    wet = _reverb(mono, 0.25, 0.15, 31, rate)
    return _stereo(wet, wet)


def impacto(rate: int = SAMPLE_RATE) -> np.ndarray:
    """Batida grave de trailer: corpo médio-grave que se ouve no celular e cauda curta.

    O de antes era quase só subgrave (40 a 110 Hz) saturado: no fone virava um ronco
    alto e no celular um "barulhinho" sem corpo.
    """
    count = int(0.9 * rate)
    seconds = np.arange(count) / rate
    frequency = 58.0 + 50.0 * np.exp(-seconds * 14.0)     # 108 Hz → 58 Hz
    sub = np.sin(2 * np.pi * np.cumsum(frequency) / rate) * np.exp(-seconds * 9.0)
    body = _band_noise(count, np.full(count, 180.0), 0.7, seed=7, rate=rate) * np.exp(-seconds * 10.0)
    knock = _band_noise(count, np.full(count, 450.0), 0.6, seed=9, rate=rate) * np.exp(-seconds * 30.0)
    crack = _lowpass(_rng(8).standard_normal(count), 6000.0, rate) * np.exp(-seconds * 160.0)
    attack = np.minimum(1.0, seconds * rate / 48)
    mono = np.tanh(1.2 * (0.35 * sub + 2.5 * body + 0.8 * knock + 0.18 * crack)) * attack
    mono = _highpass(mono, 38.0, rate)
    left = _reverb(_fade(mono.copy(), rate), 0.8, 0.22, 41, rate)
    right = _reverb(_fade(mono.copy(), rate), 0.8, 0.22, 42, rate)
    return _stereo(left, right)


def ding(rate: int = SAMPLE_RATE) -> np.ndarray:
    """Sino pequeno: parciais de sino (não harmônicos) com decaimentos diferentes."""
    count = int(2.0 * rate)                                # até sumir: sem estalo no fim
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
    """Prato ao contrário: chiado que cresce e clareia até parar no ponto marcado.

    Sem tom nem vibrato: o tom subindo soava como efeito de ficção científica.
    """
    count = int(SUBIDA_SECONDS * rate)
    position = np.linspace(0.0, 1.0, count)
    centers = 900.0 * (8.0 ** position)                   # 900 Hz → 7,2 kHz
    swell = position ** 3.0
    left = _band_noise(count, centers, 0.9, seed=61, rate=rate) * swell
    right = _band_noise(count, centers, 0.9, seed=62, rate=rate) * swell
    end = int(0.012 * rate)
    for channel in (left, right):
        channel[-end:] *= np.linspace(1.0, 0.0, end)
    return _stereo(left, right)


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


def _short_term_db(samples: np.ndarray, rate: int) -> np.ndarray:
    """Volume (dB) em janelas de ``LOUD_WINDOW`` a cada 0,1 s, sem o grave abaixo de 120 Hz.

    O celular quase não toca esse grave; medido junto, um impacto pareceria baixo e
    subiria até virar ronco no fone.
    """
    data = np.asarray(samples, dtype=np.float64)
    mono = data if data.ndim == 1 else data.mean(axis=1)
    if mono.size == 0:
        return np.array([-120.0])
    weighted = _highpass(mono, 120.0, rate) ** 2
    window, hop = max(1, int(LOUD_WINDOW * rate)), max(1, int(0.1 * rate))
    total = np.concatenate(([0.0], np.cumsum(weighted)))
    starts = np.arange(0, max(1, mono.size - window + 1), hop)
    ends = np.minimum(starts + window, mono.size)
    power = (total[ends] - total[starts]) / np.maximum(1, ends - starts)
    return 10 * np.log10(np.maximum(power, 1e-12))


def voice_level(samples: np.ndarray, rate: int) -> float | None:
    """Volume típico da fala (mediana das janelas com voz); ``None`` em silêncio."""
    levels = _short_term_db(samples, rate)
    voiced = levels[levels > levels.max() - 30.0]
    if levels.max() < -60.0 or voiced.size == 0:
        return None
    return float(np.median(voiced))


def read_sound(path: Path) -> tuple[np.ndarray, int]:
    """Som de efeito como float (-1 a 1): WAV direto, os outros formatos pelo PyAV."""
    if path.suffix.casefold() == ".wav":
        try:
            with wave.open(str(path), "rb") as stream:
                rate, channels = stream.getframerate(), stream.getnchannels()
                if stream.getsampwidth() == 2:
                    data = np.frombuffer(stream.readframes(stream.getnframes()), dtype="<i2")
                    samples = data.astype(np.float32) / 32768.0
                    return samples.reshape(-1, channels) if channels > 1 else samples, rate
        except (wave.Error, EOFError):
            pass                      # WAV em float ou outro codec: o PyAV lê
    import av

    with av.open(str(path)) as container:
        stream = container.streams.audio[0]
        resampler = av.AudioResampler(format="flt", layout="mono", rate=SAMPLE_RATE)
        chunks = [frame.to_ndarray().reshape(-1)
                  for packet in container.decode(stream)
                  for frame in resampler.resample(packet)]
    return (np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.float32)), SAMPLE_RATE


def matched_gains(sounds: dict[str, Path], voice: float | None) -> dict[str, float]:
    """Ganho de cada som para ficar ``BELOW_VOICE`` dB abaixo da voz, sem passar do teto.

    ``voice`` é ``voice_level`` do áudio do corte; sem ele (ou som ilegível) vale o
    ``GAIN`` fixo.
    """
    gains: dict[str, float] = {}
    for kind, path in sounds.items():
        gain = GAIN.get(kind, 0.3)
        try:
            samples, rate = read_sound(path)
            peak = float(np.abs(samples).max()) if samples.size else 0.0
            if voice is not None and peak > 0:
                level = float(_short_term_db(samples, rate).max())
                gain = 10 ** ((voice - BELOW_VOICE.get(kind, 12.0) - level) / 20)
            if peak > 0:
                gain = min(gain, PEAK_LIMIT / peak)
        except Exception:  # noqa: BLE001 - som que não abre fica com o ganho fixo
            pass
        gains[kind] = round(max(0.01, min(gain, 4.0)), 4)
    return gains


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
