"""Detecção da GPU NVIDIA e dos encoders NVENC disponíveis no FFmpeg."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .tools import run_hidden

NVENC_LABELS = {
    "h264_nvenc": "H.264 (NVENC) — compatível com tudo",
    "hevc_nvenc": "HEVC / H.265 (NVENC) — melhor qualidade por bit",
    "av1_nvenc": "AV1 (NVENC) — exclusivo das RTX 40, arquivos menores",
}


@dataclass
class GpuInfo:
    name: str = ""
    driver: str = ""
    encoders: list[str] = field(default_factory=list)
    decoders_cuda: bool = False

    @property
    def available(self) -> bool:
        return bool(self.encoders)

    @property
    def summary(self) -> str:
        if not self.name and not self.encoders:
            return "Nenhuma GPU NVIDIA detectada — a conversão usaria a CPU."
        codecs = ", ".join(e.replace("_nvenc", "").upper() for e in self.encoders)
        return f"{self.name or 'GPU NVIDIA'} · NVENC: {codecs or 'indisponível'}"


def detect(ffmpeg: Path) -> GpuInfo:
    info = GpuInfo()

    try:
        out = run_hidden(
            ["nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader"], timeout=15
        ).stdout.strip()
        if out:
            first = out.splitlines()[0]
            parts = [p.strip() for p in first.split(",")]
            info.name = parts[0]
            if len(parts) > 1:
                info.driver = parts[1]
    except Exception:
        pass

    if ffmpeg and Path(ffmpeg).exists():
        try:
            enc = run_hidden([str(ffmpeg), "-hide_banner", "-encoders"], timeout=30).stdout
            info.encoders = [c for c in NVENC_LABELS if re.search(rf"\b{c}\b", enc)]
            hw = run_hidden([str(ffmpeg), "-hide_banner", "-hwaccels"], timeout=20).stdout
            info.decoders_cuda = "cuda" in hw
        except Exception:
            pass

    # Sem driver NVIDIA presente, os encoders listados pelo FFmpeg não funcionam.
    if not info.name:
        info.encoders = []
    return info
