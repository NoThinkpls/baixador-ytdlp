"""Detecção de encoders acelerados: NVENC, AMD AMF e VideoToolbox."""
from __future__ import annotations

import platform
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .tools import run_hidden

GPU_ENCODER_LABELS = {
    "h264_nvenc": "H.264 (NVENC) — compatível com tudo",
    "hevc_nvenc": "HEVC / H.265 (NVENC) — melhor qualidade por bit",
    "av1_nvenc": "AV1 (NVENC) — exclusivo das RTX 40, arquivos menores",
    "h264_videotoolbox": "H.264 (VideoToolbox) — Apple Silicon",
    "hevc_videotoolbox": "HEVC / H.265 (VideoToolbox) — Apple Silicon",
    "h264_amf": "H.264 (AMD AMF) — compatível com tudo",
    "hevc_amf": "HEVC / H.265 (AMD AMF) — melhor qualidade por bit",
    "av1_amf": "AV1 (AMD AMF) — placas AMD compatíveis",
}


@dataclass
class GpuInfo:
    name: str = ""
    driver: str = ""
    encoders: list[str] = field(default_factory=list)
    decoders_cuda: bool = False
    decoders_videotoolbox: bool = False
    decoders_d3d11: bool = False

    @property
    def available(self) -> bool:
        return bool(self.encoders)

    @property
    def summary(self) -> str:
        if sys.platform == "darwin" and not self.encoders:
            return "Apple Silicon detectado — conversão acelerada indisponível neste FFmpeg."
        if not self.name and not self.encoders:
            return "Nenhum encoder de GPU detectado — a conversão usaria a CPU."
        codecs = ", ".join(e.replace("_nvenc", "").replace("_videotoolbox", "").replace("_amf", "").upper()
                           for e in self.encoders)
        if any(e.endswith("_videotoolbox") for e in self.encoders):
            backend = "VideoToolbox"
        elif any(e.endswith("_amf") for e in self.encoders):
            backend = "AMD AMF"
        else:
            backend = "NVENC"
        return f"{self.name or 'GPU'} · {backend}: {codecs or 'indisponível'}"


def detect(ffmpeg: Path) -> GpuInfo:
    info = GpuInfo()
    if sys.platform == "darwin":
        machine = platform.machine().lower()
        info.name = "Apple Silicon" if machine in ("arm64", "aarch64") else "Mac"
        if ffmpeg and Path(ffmpeg).exists():
            try:
                enc = run_hidden([str(ffmpeg), "-hide_banner", "-encoders"], timeout=30).stdout
                info.encoders = [codec for codec in ("h264_videotoolbox", "hevc_videotoolbox")
                                 if re.search(rf"\b{codec}\b", enc)]
                hw = run_hidden([str(ffmpeg), "-hide_banner", "-hwaccels"], timeout=20).stdout
                info.decoders_videotoolbox = "videotoolbox" in hw
            except Exception:
                pass
        return info
    try:
        out = run_hidden(
            ["nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader"], timeout=15
        ).stdout.strip()
        if out:
            first = out.splitlines()[0]
            parts = [part.strip() for part in first.split(",")]
            info.name = parts[0]
            if len(parts) > 1:
                info.driver = parts[1]
    except Exception:
        pass
    if ffmpeg and Path(ffmpeg).exists():
        try:
            enc = run_hidden([str(ffmpeg), "-hide_banner", "-encoders"], timeout=30).stdout
            info.encoders = [codec for codec in (
                "h264_nvenc", "hevc_nvenc", "av1_nvenc",
                "h264_amf", "hevc_amf", "av1_amf",
            )
                             if re.search(rf"\b{codec}\b", enc)]
            hw = run_hidden([str(ffmpeg), "-hide_banner", "-hwaccels"], timeout=20).stdout
            info.decoders_cuda = "cuda" in hw
            info.decoders_d3d11 = "d3d11va" in hw
        except Exception:
            pass
    if any(codec.endswith("_amf") for codec in info.encoders):
        # AMF é a confirmação mais confiável: alguns drivers não expõem nome via
        # nvidia-smi (obviamente) e o FFmpeg ainda consegue codificar normalmente.
        info.name = info.name or "GPU AMD"
    if info.encoders and not info.name:
        # O FFmpeg consegue testar o encoder diretamente. Não esconder uma
        # NVENC funcional só porque nvidia-smi não está no PATH ou foi bloqueado
        # por política corporativa.
        info.name = "GPU detectada"
    return info
