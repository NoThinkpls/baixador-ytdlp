"""Caminhos da aplicação e persistência de configurações."""
from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from .hardware import default_fragments, default_parallel_downloads

APP_NAME = "baixador-ytdlp"
APP_ID = "BaixadorYtdlp"
APP_VERSION = "1.3.0"
IS_WINDOWS = sys.platform.startswith("win")


def _data_root() -> Path:
    if IS_WINDOWS:
        base = os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local"
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return Path(base) / APP_ID


DATA_DIR = _data_root()
BIN_DIR = DATA_DIR / "bin"
LOG_DIR = DATA_DIR / "logs"
MODEL_DIR = DATA_DIR / "models"
RUNTIME_DIR = DATA_DIR / "runtime"
SETTINGS_PATH = DATA_DIR / "settings.json"
STATE_PATH = DATA_DIR / "tools_state.json"
HISTORY_PATH = DATA_DIR / "history.json"


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
    archive_enabled: bool = False    # não rebaixar o que já foi baixado
    theme: str = "auto"              # auto | light | dark
    mica: bool = True
    auto_update: bool = True
    update_check_hours: int = 12
    clipboard_watch: bool = True
    open_folder_on_finish: bool = False
    limit_rate: str = ""             # ex.: "5M"
    proxy: str = ""
    taskbar_progress: bool = True    # progresso no ícone da barra de tarefas
    history_enabled: bool = True
    history_limit: int = 200
    runtime_check_hours: int = 24    # intervalo entre checagens do runtime do Whisper
    # Transcodificação opcional por GPU (NVENC)
    transcode_enabled: bool = False
    transcode_codec: str = "hevc_nvenc"   # h264_nvenc | hevc_nvenc | av1_nvenc
    transcode_cq: int = 20
    transcode_preset: str = "p5"
    transcode_replace: bool = False       # apagar o original após converter
    # Legendas/transcrição (faster-whisper)
    transcription_language: str = "pt"
    transcription_model: str = "medium"
    transcription_format: str = "srt"    # srt | vtt | ass | txt | json
    transcription_aggressive_filter: bool = False

    @classmethod
    def load(cls) -> "Settings":
        try:
            raw = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        except Exception:
            return cls()
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in raw.items() if k in known})

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
    for path in (DATA_DIR, BIN_DIR, LOG_DIR, MODEL_DIR, RUNTIME_DIR):
        path.mkdir(parents=True, exist_ok=True)
