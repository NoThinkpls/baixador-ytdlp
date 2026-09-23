"""Caminhos da aplicação e persistência de configurações."""
from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from .hardware import default_fragments, default_parallel_downloads

APP_NAME = "baixador-ytdlp"
APP_ID = "BaixadorYtdlp"
APP_VERSION = "1.8.1"
IS_WINDOWS = sys.platform.startswith("win")


def _system_data_root() -> Path:
    if IS_WINDOWS:
        base = os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local"
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return Path(base) / APP_ID


def _app_bundle(executable_dir: Path) -> Path | None:
    """Devolve o ``.app`` que contém o executável no macOS."""
    for parent in (executable_dir, *executable_dir.parents):
        if parent.suffix == ".app":
            return parent
    return None


def _writable(directory: Path) -> bool:
    try:
        directory.mkdir(parents=True, exist_ok=True)
        probe = directory / f".write-test-{os.getpid()}"
        probe.write_bytes(b"")
        probe.unlink()
        return True
    except OSError:
        return False


def _portable_root() -> Path | None:
    """Pasta de dados do modo portable, ou ``None`` quando ele não se aplica.

    No macOS os dados ficam AO LADO do ``.app``: escrever dentro do pacote
    quebra a assinatura, some ao atualizar e falha quando o Gatekeeper executa
    o app de um volume somente leitura (App Translocation).
    """
    executable_dir = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) \
        else Path(__file__).resolve().parents[1]
    bundle = _app_bundle(executable_dir) if sys.platform == "darwin" else None
    markers = [executable_dir / "portable.txt"]
    if bundle is not None:
        markers.append(bundle.parent / "portable.txt")
    if not any(marker.is_file() for marker in markers):
        return None
    if bundle is not None:
        return bundle.parent / f"{APP_ID}-data"
    return executable_dir / "data"


PORTABLE_FALLBACK_REASON = ""


def _data_root() -> Path:
    global PORTABLE_FALLBACK_REASON
    portable = _portable_root()
    if portable is not None:
        if _writable(portable):
            return portable
        # Pasta somente leitura (Program Files, pendrive protegido, App
        # Translocation). Abrir com os dados no perfil é melhor que cair.
        PORTABLE_FALLBACK_REASON = (
            f"A pasta do modo portable não permite gravação ({portable}); "
            "os dados foram mantidos no perfil do usuário."
        )
    return _system_data_root()


DATA_DIR = _data_root()
BIN_DIR = DATA_DIR / "bin"
LOG_DIR = DATA_DIR / "logs"
MODEL_DIR = DATA_DIR / "models"
COOKIES_DIR = DATA_DIR / "cookies"
RUNTIME_DIR = DATA_DIR / "runtime"
UPDATE_DIR = DATA_DIR / "updates"
SETTINGS_PATH = DATA_DIR / "settings.json"
STATE_PATH = DATA_DIR / "tools_state.json"
HISTORY_PATH = DATA_DIR / "history.json"
QUEUE_STATE_PATH = DATA_DIR / "download_queue.json"


def default_download_dir() -> str:
    """Pasta padrão de saída: Vídeos/baixador-ytdlp (ou ~/Videos fora do Windows)."""
    if IS_WINDOWS:
        try:
            import ctypes.wintypes as wt
            import ctypes

            buf = ctypes.create_unicode_buffer(wt.MAX_PATH)
            # FOLDERID_Videos via CSIDL_MYVIDEO (14)
            ctypes.windll.shell32.SHGetFolderPathW(None, 14, None, 0, buf)
            if buf.value:
                return str(Path(buf.value) / APP_NAME)
        except Exception:
            pass
    return str(Path.home() / "Videos" / APP_NAME)


@dataclass
class Settings:
    """Preferências do usuário — gravadas em settings.json."""

    settings_schema_version: int = 5
    download_dir: str = field(default_factory=default_download_dir)
    ask_output_dir: bool = False     # liberar a escolha de pasta na página Baixar
    last_output_dir: str = ""        # última pasta escolhida por download
    container: str = "mp4"           # mp4 | mkv | webm | original
    audio_format: str = "mp3"        # mp3 | m4a | opus | flac | wav
    prefer_h264: bool = False        # prioriza compatibilidade em vez de qualidade
    embed_thumbnail: bool = True
    embed_metadata: bool = True
    embed_chapters: bool = True
    write_subs: bool = False
    embed_subs: bool = True
    sub_langs: str = "pt,pt-BR,en"
    sponsorblock: bool = False
    # Padrões calculados na primeira execução a partir da máquina do usuário.
    concurrent_fragments: int = field(default_factory=default_fragments)
    max_parallel_downloads: int = field(default_factory=default_parallel_downloads)
    cookies_browser: str = ""        # "", chrome, edge, firefox, brave...
    cookies_file: str = ""           # cookies.txt Netscape; tem prioridade sobre o navegador
    extractor_args: str = ""         # ex.: youtube:player_client=default,web_safari
    filename_template: str = "%(title).180B [%(id)s].%(ext)s"
    # Perfis de saída salvos na página Baixar; somente preferências, nunca credenciais.
    download_profiles: list[dict[str, object]] = field(default_factory=list)
    # Ativado por padrão: o arquivo de histórico do yt-dlp por pasta evita
    # baixar novamente o mesmo ID quando ele já foi concluído.
    archive_enabled: bool = True
    resume_queue: bool = True        # restaura itens interrompidos ao reabrir
    auto_retry_attempts: int = 2     # tentativas extras para falhas transitórias
    auto_retry_delay: int = 5        # espera base entre tentativas, em segundos
    organize_audio_by_uploader: bool = False
    theme: str = "auto"              # auto | light | dark
    # Todas as superfícies do app são opacas: o Mica só aparecia em falhas de
    # repintura (bordas claras). Desligado por padrão desde a 1.8.1.
    mica: bool = False
    sidebar_collapsed: bool = False
    # Atualizações do aplicativo: a checagem é automática, mas instalação é sempre confirmada.
    auto_update: bool = True
    update_check_hours: int = 12
    app_update_checked_at: float = 0.0
    update_dismissed_version: str = ""
    clipboard_watch: bool = True
    open_folder_on_finish: bool = False
    limit_rate: str = ""             # ex.: "5M"
    proxy: str = ""
    taskbar_progress: bool = True    # progresso no ícone da barra de tarefas
    tray_notifications: bool = True # conclusão também aparece na bandeja do sistema
    close_to_tray: bool = False      # fechar esconde a janela e mantém tarefas ativas
    history_enabled: bool = True
    history_limit: int = 200
    runtime_check_hours: int = 24    # intervalo entre checagens do runtime do Whisper
    allow_system_tools: bool = False # PATH só entra quando a pessoa opta explicitamente
    # Transcodificação opcional por GPU (NVENC no Windows, VideoToolbox no macOS)
    transcode_enabled: bool = False
    transcode_codec: str = "hevc_nvenc"   # NVENC ou VideoToolbox, conforme a plataforma
    transcode_cq: int = 20
    transcode_preset: str = "p5"
    transcode_replace: bool = False       # apagar o original após converter
    # Legendas/transcrição (faster-whisper)
    transcription_language: str = "pt"
    transcription_model: str = "medium"
    transcription_format: str = "srt"    # srt | vtt | ass | txt | json
    transcription_aggressive_filter: bool = False
    transcription_task: str = "transcribe"  # transcribe | translate
    transcription_initial_prompt: str = ""
    transcription_max_chars: int = 50
    transcription_min_duration: float = 0.8
    transcription_max_duration: float = 4.5
    window_geometry: str = ""        # legado (blob do Qt); ignorado desde a 1.8.1
    window_rect: list[int] = field(default_factory=list)  # x, y, largura, altura
    window_maximized: bool = False
    ytdlp_channel: str = "stable"    # stable | nightly
    transcription_batched: bool = False   # BatchedInferencePipeline na GPU
    transcription_low_vram: bool = False  # int8_float16 em placas com pouca VRAM

    @staticmethod
    def _coerce(value, default):
        """Converte valores antigos/editados à mão sem deixar o erro vazar."""
        if isinstance(default, bool):
            if isinstance(value, bool):
                return value
            if isinstance(value, str) and value.strip().casefold() in {"true", "1", "yes", "sim"}:
                return True
            if isinstance(value, str) and value.strip().casefold() in {"false", "0", "no", "não", "nao"}:
                return False
            raise ValueError("booleano inválido")
        if isinstance(default, list):
            if not isinstance(value, list):
                raise ValueError("lista inválida")
            return value
        if isinstance(default, dict):
            if not isinstance(value, dict):
                raise ValueError("objeto inválido")
            return value
        if isinstance(value, type(default)):
            return value
        return type(default)(value)

    @classmethod
    def load(cls) -> "Settings":
        try:
            raw = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("a raiz das configurações precisa ser um objeto")
        except FileNotFoundError:
            return cls()
        except (OSError, ValueError, json.JSONDecodeError):
            try:
                backup = SETTINGS_PATH.with_name(
                    f"{SETTINGS_PATH.stem}.corrompido-{int(time.time())}{SETTINGS_PATH.suffix}"
                )
                SETTINGS_PATH.replace(backup)
            except OSError:
                pass
            return cls()
        known = {f.name for f in fields(cls)}
        defaults = cls()
        values = {}
        for key, value in raw.items():
            if key not in known:
                continue
            try:
                values[key] = cls._coerce(value, getattr(defaults, key))
            except (TypeError, ValueError):
                continue
        # Até 1.5.x a chave de archive era interna, sem controle na interface,
        # e o valor salvo padrão era false. Na migração 1.6 ela passa a evitar
        # repetição por padrão; após o primeiro save, a escolha feita na nova UI
        # permanece intacta.
        try:
            schema = int(raw.get("settings_schema_version") or 0)
        except (TypeError, ValueError):
            schema = 0
        if schema < 2:
            values["archive_enabled"] = True
            values["resume_queue"] = True
            values["settings_schema_version"] = 2
        if schema < 3:
            values["settings_schema_version"] = 3
        if schema < 4:
            values["settings_schema_version"] = 4
        if schema < 5:
            # 1.8.1: o Mica só servia para expor artefatos de repintura, e o blob
            # do saveGeometry() não é confiável numa janela sem moldura nativa.
            values["mica"] = False
            values["window_geometry"] = ""
            values["settings_schema_version"] = 5
        return cls(**values)

    def save(self) -> None:
        """Grava de forma atômica. Nunca deixa o app cair por falha de disco."""
        try:
            SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
            tmp = SETTINGS_PATH.with_suffix(".tmp")
            tmp.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False),
                           encoding="utf-8")
            tmp.replace(SETTINGS_PATH)
        except OSError:
            pass


def ensure_dirs() -> None:
    for path in (DATA_DIR, BIN_DIR, LOG_DIR, MODEL_DIR, COOKIES_DIR, RUNTIME_DIR, UPDATE_DIR):
        path.mkdir(parents=True, exist_ok=True)
