"""Detecção de encoders acelerados: NVENC, AMD AMF, Intel Quick Sync, VAAPI e VideoToolbox."""
from __future__ import annotations

import glob
import os
import platform
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from .plataforma import is_apple_silicon, is_macos
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
    "h264_qsv": "H.264 (Intel Quick Sync) — compatível com tudo",
    "hevc_qsv": "HEVC / H.265 (Intel Quick Sync) — melhor qualidade por bit",
    "av1_qsv": "AV1 (Intel Quick Sync) — Arc e iGPUs recentes",
    "h264_vaapi": "H.264 (VAAPI) — AMD e Intel no Linux",
    "hevc_vaapi": "HEVC / H.265 (VAAPI) — AMD e Intel no Linux",
    "av1_vaapi": "AV1 (VAAPI) — GPUs recentes no Linux",
}

BACKEND_NAMES = {
    "nvenc": "NVENC", "amf": "AMD AMF", "qsv": "Intel Quick Sync",
    "vaapi": "VAAPI", "videotoolbox": "VideoToolbox",
}
UPLOAD_FILTER = "format=nv12,hwupload"


def backend_of(codec: str) -> str:
    """``h264_nvenc`` → ``nvenc``; vazio quando não é um encoder de GPU conhecido."""
    backend = codec.rsplit("_", 1)[-1]
    return backend if backend in BACKEND_NAMES else ""


def vaapi_device() -> str:
    """Primeiro nó de renderização do Linux que o usuário consegue abrir, ou vazio."""
    if not sys.platform.startswith("linux"):
        return ""
    nodes = sorted(glob.glob("/dev/dri/renderD*"))
    # Em máquina com duas GPUs, o primeiro nó pode ser de uma placa sem permissão.
    return next((node for node in nodes if os.access(node, os.R_OK | os.W_OK)), "")


def vaapi_unavailable_reason() -> str:
    """Explica por que não há dispositivo VAAPI: sem GPU ou sem permissão de acesso."""
    if glob.glob("/dev/dri/renderD*"):
        return ("Sem permissão para abrir /dev/dri/renderD*. Adicione seu usuário ao grupo "
                "\"render\" (sudo usermod -aG render $USER) e entre na sessão de novo.")
    return "Nenhum dispositivo de renderização (/dev/dri/renderD*) disponível."


def device_args(codec: str) -> list[str]:
    """Argumentos de entrada que o backend exige antes do ``-i`` (VAAPI precisa do dispositivo)."""
    if backend_of(codec) == "vaapi":
        device = vaapi_device()
        return ["-vaapi_device", device] if device else []
    return []


def quality_args(codec: str, quality: int) -> list[str]:
    """Qualidade constante equivalente ao CRF ``quality`` para cada backend."""
    backend = backend_of(codec)
    if backend == "nvenc":
        return ["-cq", str(quality), "-b:v", "0"]
    if backend == "videotoolbox":
        return ["-q:v", "65"]
    if backend == "qsv":
        return ["-global_quality", str(quality)]
    if backend == "vaapi":
        return ["-rc_mode", "CQP", "-qp", str(quality)]
    return ["-rc", "cqp", "-qp_i", str(quality), "-qp_p", str(quality)]

# Mantemos apenas confirmações positivas. Uma negativa pode ser transitória
# (driver ainda inicializando, notebook trocando de GPU, retorno do macOS), e
# não deve impedir a tentativa real do recorte pelo resto da sessão.
_ENCODER_CACHE: dict[tuple[str, int, int], tuple[str, ...]] = {}
# "Nenhum encoder funciona" vale por alguns minutos: sem isto, cada operação das
# Ferramentas testava até seis encoders de novo em PCs sem GPU (segundos de
# espera antes de começar). O prazo curto ainda permite a GPU "voltar".
_NEGATIVE_CACHE: dict[tuple[str, int, int], float] = {}
NEGATIVE_TTL = 600.0


def _cache_key(ffmpeg: Path) -> tuple[str, int, int] | None:
    try:
        stat = ffmpeg.stat()
        return str(ffmpeg.resolve()), stat.st_mtime_ns, stat.st_size
    except OSError:
        return None


def _candidate_encoders() -> tuple[str, ...]:
    if is_macos(sys.platform):
        return "h264_videotoolbox", "hevc_videotoolbox"
    candidates = (
        "h264_nvenc", "hevc_nvenc", "av1_nvenc",
        "h264_amf", "hevc_amf", "av1_amf",
        "h264_qsv", "hevc_qsv", "av1_qsv",
    )
    if sys.platform.startswith("linux"):
        candidates += ("h264_vaapi", "hevc_vaapi", "av1_vaapi")
    return candidates


def _advertised_encoders(advertised: str) -> list[str]:
    return [
        codec for codec in _candidate_encoders()
        if re.search(rf"\b{codec}\b", advertised)
    ]


def _encoder_probe(ffmpeg: Path, codec: str) -> tuple[bool, str]:
    """Faz uma codificação mínima; listar o encoder não prova que há uma GPU.

    Builds completas do FFmpeg anunciam NVENC e AMF mesmo em máquinas sem a
    placa/driver correspondente. O quadro sintético evita oferecer um backend
    que só falharia depois de começar um vídeo real.
    """
    backend = backend_of(codec)
    if backend == "vaapi" and not vaapi_device():
        return False, vaapi_unavailable_reason()
    # QSV e VAAPI recebem quadros NV12 (o VAAPI, já enviados à GPU); os demais, YUV 4:2:0.
    frame_args = (["-vf", UPLOAD_FILTER] if backend == "vaapi"
                  else ["-vf", "format=nv12"] if backend == "qsv"
                  else ["-pix_fmt", "yuv420p"])
    try:
        result = run_hidden([
            str(ffmpeg), "-hide_banner", "-loglevel", "error", *device_args(codec),
            "-f", "lavfi", "-i", "color=size=256x256:rate=1",
            "-frames:v", "1", "-an", *frame_args,
            "-c:v", codec, "-f", "null", "-",
        ], timeout=20)
        if getattr(result, "returncode", 0) == 0:
            return True, ""
        detail = (getattr(result, "stderr", "") or getattr(result, "stdout", "") or "").strip()
        return False, detail[-500:]
    except Exception as exc:
        return False, str(exc)


def forget_negative_cache() -> None:
    """Uma detecção pedida pela pessoa sempre testa de novo."""
    _NEGATIVE_CACHE.clear()


def _usable_encoders(ffmpeg: Path, advertised: str) -> tuple[list[str], dict[str, str]]:
    candidates = _advertised_encoders(advertised)
    key = _cache_key(ffmpeg)
    if key is not None and key in _ENCODER_CACHE:
        return list(_ENCODER_CACHE[key]), {}
    if key is not None and time.monotonic() - _NEGATIVE_CACHE.get(key, -NEGATIVE_TTL) < NEGATIVE_TTL:
        return [], {}
    usable: list[str] = []
    errors: dict[str, str] = {}
    for codec in candidates:
        works, detail = _encoder_probe(ffmpeg, codec)
        if works:
            usable.append(codec)
        else:
            errors[codec] = detail
    # Não cachear uma lista vazia: uma falha no teste curto não é suficiente
    # para declarar uma GPU indisponível durante toda a execução do app.
    if key is not None and usable:
        _ENCODER_CACHE.clear()  # só há um FFmpeg ativo por sessão
        _ENCODER_CACHE[key] = tuple(usable)
        _NEGATIVE_CACHE.pop(key, None)
    elif key is not None and candidates:
        _NEGATIVE_CACHE[key] = time.monotonic()
    return usable, errors


@dataclass
class GpuInfo:
    name: str = ""
    driver: str = ""
    encoders: list[str] = field(default_factory=list)
    advertised_encoders: list[str] = field(default_factory=list)
    probe_errors: dict[str, str] = field(default_factory=dict)
    decoders_cuda: bool = False
    decoders_videotoolbox: bool = False
    decoders_d3d11: bool = False

    @property
    def available(self) -> bool:
        return bool(self.encoders)

    @property
    def section_encoders(self) -> list[str]:
        """Encoders que podem ser tentados no recorte real.

        Um teste de 128 px é útil para a tela de configurações, mas não é mais
        confiável que o próprio FFmpeg abrindo a mídia. O recorte tem fallback
        seguro, portanto também pode tentar um encoder anunciado pelo binário.
        """
        return self.encoders or self.advertised_encoders

    @property
    def summary(self) -> str:
        if is_macos(sys.platform) and not self.section_encoders:
            return "Apple Silicon detectado — conversão acelerada indisponível neste FFmpeg."
        if not self.section_encoders:
            if self.name:
                return f"{self.name} detectada, mas este FFmpeg não expõe um encoder utilizável."
            return "Nenhum encoder de GPU detectado — a conversão usaria a CPU."
        encoders = self.section_encoders
        codecs = ", ".join(e.rsplit("_", 1)[0].upper() for e in encoders)
        backend = BACKEND_NAMES.get(backend_of(encoders[0]), "GPU")
        if self.encoders:
            return f"{self.name or 'GPU'} · {backend}: {codecs or 'indisponível'}"
        return (f"{self.name or 'GPU'} · {backend} anunciado pelo FFmpeg: {codecs}. "
                "O recorte tentará a GPU e usará CPU apenas se ela recusar a mídia.")


def detect(
    ffmpeg: Path,
    *,
    verify: bool = True,
    query_device: bool = True,
) -> GpuInfo:
    """Lê os backends do FFmpeg e, quando pedido, testa sua abertura real.

    A tela de configurações chama o modo completo. O início de um recorte usa
    somente a lista anunciada, pois o próprio recorte já tem fallback em
    camadas e não deve aguardar vários testes sintéticos antes de começar.
    """
    info = GpuInfo()
    if is_macos(sys.platform):
        machine = platform.machine().lower()
        info.name = "Apple Silicon" if is_apple_silicon(sys.platform, machine) else "Mac"
        if ffmpeg and Path(ffmpeg).exists():
            try:
                enc = run_hidden([str(ffmpeg), "-hide_banner", "-encoders"], timeout=30).stdout
                info.advertised_encoders = _advertised_encoders(enc)
                if verify:
                    info.encoders, info.probe_errors = _usable_encoders(Path(ffmpeg), enc)
                hw = run_hidden([str(ffmpeg), "-hide_banner", "-hwaccels"], timeout=20).stdout
                info.decoders_videotoolbox = "videotoolbox" in hw
            except Exception:
                pass
        return info
    if query_device:
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
            info.advertised_encoders = _advertised_encoders(enc)
            if verify:
                info.encoders, info.probe_errors = _usable_encoders(Path(ffmpeg), enc)
            hw = run_hidden([str(ffmpeg), "-hide_banner", "-hwaccels"], timeout=20).stdout
            info.decoders_cuda = "cuda" in hw
            info.decoders_d3d11 = "d3d11va" in hw
        except Exception:
            pass
    if any(codec.endswith("_amf") for codec in info.section_encoders):
        # AMF é a confirmação mais confiável: alguns drivers não expõem nome via
        # nvidia-smi (obviamente) e o FFmpeg ainda consegue codificar normalmente.
        info.name = info.name or "GPU AMD"
    if info.section_encoders and not info.name:
        # O FFmpeg consegue testar o encoder diretamente. Não esconder uma
        # NVENC funcional só porque nvidia-smi não está no PATH ou foi bloqueado
        # por política corporativa.
        info.name = "GPU detectada"
    return info


def select_section_encoder(ffmpeg: Path, preferred: str = "") -> str:
    """Escolhe encoder funcional para o recorte, priorizando H.264.

    A execução real confirma o backend e cai em CPU de modo seguro. Assim um
    teste curto não transforma uma GPU momentaneamente ocupada em "ausente".
    """
    # A lista anunciada inclui NVENC até em PCs sem NVIDIA. Confirmar um
    # quadro evita escolher NVENC em máquinas AMD e cair direto na CPU.
    encoders = detect(ffmpeg, verify=True, query_device=False).section_encoders
    if preferred and preferred in encoders:
        return preferred
    for codec in ("h264_nvenc", "h264_amf", "h264_qsv", "h264_vaapi", "h264_videotoolbox"):
        if codec in encoders:
            return codec
    return ""
