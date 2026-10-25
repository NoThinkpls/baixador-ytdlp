"""Modo de linha de comando: as funções do app sem abrir a janela.

Uso: ``baixador-ytdlp cli <comando> [opções]`` (``cli ajuda`` lista tudo). Serve para
scripts e para o Claude Code executar pedidos feitos no chat.

Contrato com quem chama:

* o andamento sai no stderr, uma linha por mudança relevante;
* o resultado sai no stdout como UM objeto JSON (``{"ok": true, ...}``), e também em
  ``--json-saida ARQ`` quando pedido (o executável Windows é de interface gráfica e
  alguns terminais não recebem a saída dele);
* código de saída 0 = sucesso, 1 = falha, 2 = uso incorreto, 130 = cancelado.

Os comandos reaproveitam os mesmos workers da interface, chamando ``run()`` numa thread
comum: a lógica de download, legenda, cortes e ferramentas é exatamente a do app. As
configurações salvas valem como padrão e nunca são regravadas por aqui.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import sys
import threading
import urllib.parse
from dataclasses import replace
from pathlib import Path

from .config import APP_VERSION, IS_WINDOWS

EXIT_OK, EXIT_FAILED, EXIT_USAGE, EXIT_CANCELLED = 0, 1, 2, 130
VIDEO_SUFFIXES = frozenset({".mp4", ".mkv", ".webm", ".mov", ".m4v", ".avi"})
MEDIA_SUFFIXES = VIDEO_SUFFIXES | frozenset({".mp3", ".m4a", ".opus", ".flac", ".wav", ".ogg",
                                              ".aac"})


class CliError(RuntimeError):
    """Falha esperada, com mensagem pronta para quem chamou."""


class _Cancelled(RuntimeError):
    pass


# ---------------------------------------------------------------- saída
def _reattach_windows_stdio() -> None:
    """Liga stdout/stderr do executável Windows ao terminal ou pipe de quem o chamou.

    O executável é de interface gráfica (sem console); o Python começa sem saída padrão
    mesmo quando o Git Bash ou o Claude Code passam pipes. Usamos o handle herdado e,
    sem ele, o console do processo pai. Só o modo CLI faz isso: a janela continua
    sem console e não morre ao fechar o terminal que a abriu.
    """
    import ctypes
    import io
    import msvcrt
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetStdHandle.restype = wintypes.HANDLE
    kernel32.GetStdHandle.argtypes = [wintypes.DWORD]
    kernel32.GetFileType.argtypes = [wintypes.HANDLE]
    invalid = wintypes.HANDLE(-1).value
    attached = False
    for number, name in ((-11, "stdout"), (-12, "stderr")):
        try:
            current = getattr(sys, name)
            if current is not None and current.fileno() >= 0:
                os.fstat(current.fileno())
                continue
        except (OSError, ValueError, AttributeError, io.UnsupportedOperation):
            pass
        handle = kernel32.GetStdHandle(number)
        stream = None
        if handle and handle != invalid and kernel32.GetFileType(handle) != 0:
            try:
                descriptor = msvcrt.open_osfhandle(handle, os.O_WRONLY)
                stream = open(descriptor, "w", encoding="utf-8", errors="replace",  # noqa: SIM115
                              buffering=1, closefd=False)
            except OSError:
                stream = None
        if stream is None:
            if not attached:
                attached = bool(kernel32.AttachConsole(-1))   # ATTACH_PARENT_PROCESS
            if not attached:
                continue
            try:
                stream = open("CONOUT$", "w", encoding="utf-8", errors="replace",  # noqa: SIM115
                              buffering=1)
            except OSError:
                continue
        setattr(sys, name, stream)
        setattr(sys, f"__{name}__", stream)


def _prepare_stdio() -> None:
    from .plataforma import execucao_empacotada

    if IS_WINDOWS and execucao_empacotada():
        _reattach_windows_stdio()
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            with contextlib.suppress(ValueError):
                reconfigure(encoding="utf-8", errors="replace", line_buffering=True)


def _emit(text: str) -> None:
    with contextlib.suppress(OSError, ValueError, AttributeError):
        print(text, file=sys.stderr, flush=True)


_TRAILING_PERCENT = re.compile(r"[\s…:—-]*\d{1,3}(?:[.,]\d+)?\s*%\s*$")


class _Reporter:
    """Andamento legível sem inundar o terminal: só mudanças de etapa ou de 5%."""

    def __init__(self) -> None:
        self._last_text = ""
        self._last_percent = -100

    def status(self, text: str) -> None:
        # "Processando na CPU… 37%" vira uma linha só; a porcentagem sai por percent().
        text = _TRAILING_PERCENT.sub("", " ".join(str(text or "").split()))
        if text and text != self._last_text:
            self._last_text = text
            _emit(f"… {text}")

    def percent(self, value: float, label: str = "") -> None:
        value = max(0, min(100, int(value)))
        if value >= 100 or value - self._last_percent >= 5 or value < self._last_percent:
            self._last_percent = value
            _emit(f"[{value:3d}%] {label}".rstrip())


# ------------------------------------------------------------- execução
def _on(signal, slot) -> None:
    """Conexão direta: o worker emite de uma thread comum, sem laço de eventos do Qt.

    Na conexão automática o Qt enfileiraria o sinal para a thread dona do objeto (a
    principal), que aqui nunca roda ``exec()``; o andamento e o resultado se perderiam.
    """
    from PySide6.QtCore import Qt

    signal.connect(slot, Qt.ConnectionType.DirectConnection)


def _run_worker(worker) -> None:
    """Executa ``worker.run()`` numa thread comum; Ctrl+C cancela como o botão da tela."""
    thread = threading.Thread(target=worker.run, name="baixador-cli", daemon=True)
    thread.start()
    try:
        while thread.is_alive():
            thread.join(0.2)
    except KeyboardInterrupt:
        _emit("Cancelando…")
        worker.cancel()
        thread.join(30)
        raise _Cancelled("Cancelado pelo usuário.") from None


def _settings(args):
    from .config import Settings

    cfg = Settings.load()
    overrides = {}
    if getattr(args, "cookies_navegador", None):
        overrides["cookies_browser"] = args.cookies_navegador
    if getattr(args, "cookies_arquivo", None):
        overrides["cookies_file"] = str(Path(args.cookies_arquivo).expanduser())
    if getattr(args, "legendas", None):
        overrides.update(write_subs=True, sub_langs=args.legendas)
    if getattr(args, "sponsorblock", False):
        overrides["sponsorblock"] = True
    return replace(cfg, **overrides) if overrides else cfg


def _toolchain(cfg, reporter: _Reporter, check_now: bool = False):
    """yt-dlp, FFmpeg, Deno e o motor do Whisper, como na tela de preparação."""
    from .config import ensure_dirs
    from .tools import ToolManager

    ensure_dirs()
    manager = ToolManager(runtime_check_hours=cfg.runtime_check_hours,
                          allow_system_tools=cfg.allow_system_tools,
                          ytdlp_channel=cfg.ytdlp_channel)
    toolchain = manager.ensure_all(
        lambda message, percent: reporter.status(message), check_now)
    return manager, toolchain


def _is_playlist_url(url: str) -> bool:
    """Mesma regra da página Baixar: só endereços que são explicitamente uma coleção."""
    path = urllib.parse.urlsplit(url).path.casefold()
    return ("/playlist" in path or "/channel/" in path or "/@" in path
            or "/c/" in path or "/user/" in path)


def _quality_selector(quality: str) -> str:
    quality = (quality or "melhor").strip().casefold().removesuffix("p")
    if quality in {"", "melhor", "best", "max"}:
        return "bv*+ba/b"
    if not quality.isdigit():
        raise CliError("Use --qualidade melhor, 2160, 1440, 1080, 720, 480, 360…")
    return f"bv*[height<={quality}]+ba/b[height<={quality}]/bv*+ba/b"


def _transcription_options(media: Path, args, cfg, output: Path | None = None):
    from .clips import available_destination
    from .transcription import FORMATS, TranscriptionOptions

    fmt = args.formato or cfg.transcription_format
    if fmt not in FORMATS:
        raise CliError(f"Formato de legenda desconhecido: {fmt}. Use {', '.join(FORMATS)}.")
    model = args.modelo or cfg.transcription_model
    task = "translate" if args.traduzir else "transcribe"
    if task == "translate" and model == "large-v3-turbo":
        raise CliError("O large-v3-turbo não traduz. Use --modelo large-v3 para traduzir.")
    extension = FORMATS[fmt][1]
    target = output or media.with_suffix(extension)
    return TranscriptionOptions(
        media_path=media,
        output_path=available_destination(target.with_suffix(extension)),
        language=args.idioma or cfg.transcription_language,
        model_size=model,
        output_format=fmt,
        aggressive_filter=bool(cfg.transcription_aggressive_filter),
        task=task,
        initial_prompt=args.prompt if args.prompt is not None else cfg.transcription_initial_prompt,
        max_chars_per_line=cfg.transcription_max_chars,
        min_duration=cfg.transcription_min_duration,
        max_duration=cfg.transcription_max_duration,
        batched=bool(cfg.transcription_batched),
        low_vram=bool(cfg.transcription_low_vram),
    )


def _transcribe(opts, toolchain, reporter: _Reporter) -> str:
    from .workers import TranscriptionWorker

    outcome: dict[str, str] = {}
    worker = TranscriptionWorker(opts, toolchain)
    _on(worker.status, reporter.status)
    _on(worker.progress, lambda value: reporter.percent(value, "legendando"))
    _on(worker.finished_ok, lambda path: outcome.update(ok=path))
    _on(worker.failed, lambda message: outcome.update(error=message))
    _on(worker.cancelled, lambda: outcome.update(cancelled="1"))
    _run_worker(worker)
    if "cancelled" in outcome:
        raise _Cancelled("Legenda cancelada.")
    if "error" in outcome:
        raise CliError(outcome["error"])
    if "ok" not in outcome:
        raise CliError("A transcrição terminou sem gerar o arquivo esperado.")
    return outcome["ok"]


# --------------------------------------------------------------- comandos
def cmd_preparar(args) -> dict:
    cfg = _settings(args)
    reporter = _Reporter()
    manager, tc = _toolchain(cfg, reporter, check_now=args.atualizar)
    return {"ytdlp": tc.ytdlp_version, "ffmpeg": tc.ffmpeg_version,
            "deno": tc.deno_version, "legendador": manager.runtime_info.summary,
            "pasta_binarios": str(tc.bin_dir)}


def cmd_status(args) -> dict:
    from .config import BIN_DIR, DATA_DIR, Settings
    from .diagnostics import log_path

    cfg = Settings.load()
    result: dict = {
        "versao": APP_VERSION, "pasta_dados": str(DATA_DIR), "pasta_binarios": str(BIN_DIR),
        "pasta_downloads": cfg.download_dir, "log": str(log_path("app.log")),
        "padroes": {
            "container": cfg.container, "formato_audio": cfg.audio_format,
            "legendas": cfg.sub_langs if cfg.write_subs else "",
            "sponsorblock": cfg.sponsorblock, "cookies_configurados": bool(
                cfg.cookies_browser or cfg.cookies_file),
            "idioma_legenda": cfg.transcription_language,
            "modelo_legenda": cfg.transcription_model,
            "formato_legenda": cfg.transcription_format,
            "enquadramento_cortes": cfg.clips_framing,
        },
    }
    if args.gpu:
        from .gpu import detect

        reporter = _Reporter()
        _manager, tc = _toolchain(cfg, reporter)
        info = detect(tc.ffmpeg)
        result["gpu"] = {"nome": info.name, "driver": info.driver, "encoders": info.encoders,
                         "resumo": info.summary}
    if args.exportar:
        from .diagnostics import export_diagnostics

        result["diagnostico"] = str(export_diagnostics(Path(args.exportar).expanduser(), cfg))
    return result


def cmd_info(args) -> dict:
    from .probe import friendly_error, probe

    cfg = _settings(args)
    reporter = _Reporter()
    _manager, tc = _toolchain(cfg, reporter)
    reporter.status("Analisando o link…")
    try:
        info = probe(args.url, tc.ytdlp, cfg.cookies_browser, cfg.cookies_file, cfg.proxy,
                     extractor_args=cfg.extractor_args, env=tc.env())
    except Exception as exc:  # noqa: BLE001 - a mensagem amigável é o resultado
        raise CliError(friendly_error(str(exc))) from exc
    result = {
        "titulo": info.title, "canal": info.uploader, "duracao": info.duration,
        "duracao_segundos": (info.raw or {}).get("duration"), "link": info.webpage_url,
        "playlist": info.is_playlist, "itens_playlist": info.playlist_count,
        "melhor_qualidade": info.best_label, "legendas": info.subtitles,
        "legendas_automaticas": info.auto_subtitles[:40], "idiomas_audio": info.audio_languages,
        "capitulos": [{"titulo": c.get("title", ""), "inicio": c.get("start_time"),
                       "fim": c.get("end_time")} for c in info.chapters],
    }
    if args.formatos:
        result["formatos"] = [
            {"id": row.format_id, "seletor": row.selector, "qualidade": row.quality,
             "fps": row.fps, "video": row.vcodec, "audio": row.acodec, "ext": row.ext,
             "tamanho": row.size, "so_audio": row.audio_only}
            for row in info.rows]
    return result


def cmd_baixar(args) -> dict:
    from .downloader import DownloadOptions, Progress
    from .workers import DownloadWorker

    cfg = _settings(args)
    if args.formato_id and args.qualidade:
        raise CliError("Use --qualidade ou --formato-id, não os dois.")
    output_dir = str(Path(args.pasta).expanduser()) if args.pasta else cfg.download_dir
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    selector = args.formato_id or _quality_selector(args.qualidade)
    reporter = _Reporter()
    _manager, tc = _toolchain(cfg, reporter)
    results: list[dict] = []
    for url in args.urls:
        playlist = args.playlist if args.playlist is not None else _is_playlist_url(url)
        opts = DownloadOptions(
            url=url, output_dir=output_dir, selector=selector,
            container=args.container or cfg.container, audio_only=args.audio,
            audio_format=args.formato_audio or cfg.audio_format, playlist=playlist, title=url,
            section_start=args.inicio or "", section_end=args.fim or "",
            playlist_items=args.itens or "", custom_name=args.nome or "",
        )
        outcome: dict = {}

        def on_progress(_job, progress: Progress) -> None:
            label = progress.stage or progress.status
            if progress.count > 1:
                label = f"item {progress.index} de {progress.count} · {label}"
            reporter.percent(progress.percent, label)

        worker = DownloadWorker(len(results) + 1, opts, cfg, tc)
        _on(worker.progress, on_progress)
        _on(worker.warning, lambda _job, text, outcome=outcome:
            outcome.setdefault("avisos", []).append(text))
        _on(worker.finished_ok, lambda _job, files, outcome=outcome:
            outcome.update(arquivos=files))
        _on(worker.failed, lambda _job, message, _tail, outcome=outcome:
            outcome.update(erro=message))
        _emit(f"Baixando {url}")
        _run_worker(worker)
        if outcome.get("erro") == "Cancelado":
            raise _Cancelled("Download cancelado.")
        if "erro" in outcome:
            from .probe import friendly_error

            raise CliError(friendly_error(outcome["erro"]))
        files = [str(path) for path in outcome.get("arquivos", [])]
        item: dict = {"url": url, "arquivos": files}
        if outcome.get("avisos"):
            item["avisos"] = outcome["avisos"]
        if args.legendar:
            item["legendas"] = [
                _transcribe(_transcription_options(Path(path), args, cfg), tc, reporter)
                for path in files if Path(path).suffix.casefold() in MEDIA_SUFFIXES]
        results.append(item)
    return {"pasta": output_dir, "downloads": results}


def cmd_legendar(args) -> dict:
    cfg = _settings(args)
    media = Path(args.arquivo).expanduser()
    if not media.is_file():
        raise CliError(f"Arquivo não encontrado: {media}")
    output = Path(args.saida).expanduser() if args.saida else None
    opts = _transcription_options(media, args, cfg, output)
    reporter = _Reporter()
    _manager, tc = _toolchain(cfg, reporter)
    path = _transcribe(opts, tc, reporter)
    return {"legenda": path, "modelo": opts.model_size, "idioma": opts.language,
            "formato": opts.output_format}


def _parse_clip(value: str):
    from .clips import ClipError, make_range

    span, _, title = value.partition("=")
    start, separator, end = span.strip().partition("-")
    if not separator:
        raise CliError(f"Corte inválido: “{value}”. Use INICIO-FIM ou INICIO-FIM=Título.")
    try:
        return make_range(start, end, title)
    except ClipError as exc:
        raise CliError(f"{exc} (corte “{value}”)") from exc


def _read_plan(value: str):
    """Plano da IA (``{"bx":1,…}``) colado direto ou num arquivo de texto."""
    from .clips import ClipError
    from .plano_ia import parse_plan

    path = Path(value).expanduser()
    try:
        text = path.read_text(encoding="utf-8") if path.is_file() else value
    except OSError as exc:
        raise CliError(f"Não foi possível ler o plano: {exc}") from exc
    try:
        return tuple(parse_plan(text))
    except ClipError as exc:
        raise CliError(str(exc)) from exc


def cmd_cortar(args) -> dict:
    from .clips import FRAMINGS, ANIMATIONS, CaptionStyle, ClipOptions, is_url
    from .workers import ClipWorker

    cfg = _settings(args)
    source = args.fonte if is_url(args.fonte) else str(Path(args.fonte).expanduser())
    ranges = tuple(_parse_clip(value) for value in args.corte or ())
    if args.plano:
        if ranges:
            raise CliError("Use --corte ou --plano, não os dois.")
        ranges = _read_plan(args.plano)
    if not ranges:
        raise CliError("Informe ao menos um --corte INICIO-FIM ou um --plano.")
    planned_sound = any(marker.sound for clip in ranges for marker in clip.markers)
    planned_zoom = any(marker.zoom for clip in ranges for marker in clip.markers)
    framing = args.enquadramento or cfg.clips_framing
    if framing not in FRAMINGS:
        raise CliError(f"Enquadramento desconhecido: {framing}. Use {', '.join(FRAMINGS)}.")
    animation = args.animacao or cfg.clips_animation
    if animation not in ANIMATIONS:
        raise CliError(f"Animação desconhecida: {animation}. Use {', '.join(ANIMATIONS)}.")
    if args.pasta:
        output_dir = Path(args.pasta).expanduser()
    elif is_url(source):
        output_dir = Path(cfg.download_dir)
    else:
        output_dir = Path(source).parent

    def flag(value, default):
        return default if value is None else value

    style = CaptionStyle(
        font=cfg.clips_font, size=cfg.clips_font_size, text_color=cfg.clips_text_color,
        highlight_color=args.cor_destaque or cfg.clips_highlight_color,
        position=cfg.clips_position, words=args.palavras or cfg.clips_words,
        uppercase=cfg.clips_uppercase, animation=animation, background=cfg.clips_background,
        title_position=(args.altura_titulo if args.altura_titulo is not None
                        else cfg.clips_title_position))
    sounds = args.pasta_sons if args.pasta_sons is not None else cfg.clips_sounds_folder
    options = ClipOptions(
        source=source, ranges=ranges, output_dir=output_dir, framing=framing,
        remove_pauses=flag(args.remover_pausas, cfg.clips_remove_pauses),
        min_pause=cfg.clips_min_pause, style=style,
        title_seconds=cfg.clips_title_seconds,
        language=args.idioma or cfg.transcription_language,
        model_size=args.modelo or cfg.transcription_model,
        zoom_cuts=flag(args.zoom_emendas, cfg.clips_zoom_cuts),
        progress_bar=flag(args.barra, cfg.clips_progress_bar),
        normalize_audio=flag(args.normalizar, cfg.clips_normalize_audio),
        save_srt=flag(args.srt, cfg.clips_save_srt),
        # Como na página: um plano com sons ou zooms liga a opção correspondente.
        sound_effects=flag(args.efeitos, planned_sound or cfg.clips_sound_effects),
        emphasis_zoom=flag(args.zoom_enfase, planned_zoom or cfg.clips_emphasis_zoom),
        sounds_folder=Path(sounds).expanduser() if sounds else None,
    )
    reporter = _Reporter()
    _manager, tc = _toolchain(cfg, reporter)
    outcome: dict = {}
    worker = ClipWorker(options, tc, cfg)
    _on(worker.progress, reporter.status)
    _on(worker.progress_value, lambda value: reporter.percent(value, "cortes"))
    _on(worker.clip_done, lambda path: _emit(f"Corte pronto: {path}"))
    _on(worker.finished_ok, lambda paths: outcome.update(ok=paths))
    _on(worker.failed, lambda message: outcome.update(erro=message))
    _run_worker(worker)
    if "erro" in outcome:
        raise CliError(outcome["erro"])
    return {"cortes": outcome.get("ok", []), "pasta": str(output_dir)}


TOOL_OPERATIONS = ("trim", "audio", "remux", "compress", "target_size", "shorts", "burn",
                   "soft_sub", "convert", "speed", "rotate", "mute", "normalize", "gif", "frame",
                   "extract_subs", "strip")


def cmd_ferramenta(args) -> dict:
    from .media_tools import MediaToolOptions, choice_of, default_destination
    from .workers import MediaToolWorker

    source = Path(args.arquivo).expanduser()
    if not source.is_file():
        raise CliError(f"Arquivo não encontrado: {source}")
    subtitles = Path(args.legenda).expanduser() if args.legenda else None
    if args.operacao in {"burn", "soft_sub"} and not (subtitles and subtitles.is_file()):
        raise CliError("Esta ferramenta precisa de --legenda com um arquivo .srt/.ass/.vtt.")
    choice = choice_of(args.operacao, args.escolha or "")
    destination = (Path(args.saida).expanduser() if args.saida
                   else default_destination(source, args.operacao, subtitles, choice))
    options = MediaToolOptions(
        source=source, destination=destination, operation=args.operacao,
        start=args.inicio or "", end=args.fim or "", subtitles=subtitles,
        subtitle_language=args.idioma_legenda or "", target_mb=args.tamanho_mb,
        shorts_blur=not args.sem_desfoque, fast_trim=args.rapido, choice=choice)
    cfg = _settings(args)
    reporter = _Reporter()
    _manager, tc = _toolchain(cfg, reporter)
    outcome: dict = {}
    worker = MediaToolWorker(options, tc)
    _on(worker.progress, reporter.status)
    _on(worker.progress_value, lambda value: reporter.percent(value, args.operacao))
    _on(worker.finished_ok, lambda path: outcome.update(ok=path))
    _on(worker.failed, lambda message: outcome.update(erro=message))
    _run_worker(worker)
    if "erro" in outcome:
        if outcome["erro"] == "Operação cancelada.":
            raise _Cancelled(outcome["erro"])
        raise CliError(outcome["erro"])
    if "ok" not in outcome:
        raise CliError("A ferramenta terminou sem informar o arquivo gerado.")
    return {"arquivo": outcome["ok"], "operacao": args.operacao}


def cmd_historico(args) -> dict:
    from .history import History

    entries = History().load().entries[: max(1, args.limite)]
    return {"itens": [
        {"tipo": entry.kind, "titulo": entry.title, "data": entry.date_label, "url": entry.url,
         "arquivo": entry.path, "pasta": str(entry.folder), "origem": entry.source,
         "operacao": entry.operation}
        for entry in entries]}


# ------------------------------------------------------------------ parser
class _Parser(argparse.ArgumentParser):
    def error(self, message: str):  # noqa: D401 - assinatura do argparse
        raise CliError(f"{message}\nUse “cli ajuda” para ver os comandos.")


def _bool_flag(parser, name: str, help_text: str) -> None:
    parser.add_argument(f"--{name}", dest=name.replace("-", "_"),
                        action=argparse.BooleanOptionalAction, default=None, help=help_text)


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(
        prog="baixador-ytdlp cli", allow_abbrev=False,
        description="Baixador-YTDLP sem interface: o resultado sai em JSON no stdout e o "
                    "andamento no stderr.")
    parser.add_argument("--json-saida", metavar="ARQ",
                        help="grava também o JSON do resultado neste arquivo (vale em "
                             "qualquer posição)")
    sub = parser.add_subparsers(dest="comando", metavar="COMANDO", parser_class=_Parser)

    sub.add_parser("ajuda", help="mostra esta ajuda")

    cookies = _Parser(add_help=False)
    cookies.add_argument("--cookies-navegador", metavar="NOME",
                         help="chrome, edge, firefox, brave… (só para login ou bot-check)")
    cookies.add_argument("--cookies-arquivo", metavar="ARQ", help="cookies.txt (Netscape)")

    p = sub.add_parser("preparar", help="baixa ou atualiza yt-dlp, FFmpeg e Deno")
    p.add_argument("--atualizar", action="store_true", help="consulta versões novas agora")
    p.set_defaults(handler=cmd_preparar)

    p = sub.add_parser("status", help="versão, pastas e padrões das Configurações")
    p.add_argument("--gpu", action="store_true", help="detecta GPU e encoders de hardware")
    p.add_argument("--exportar", metavar="ARQ", help="gera o ZIP de diagnóstico redigido")
    p.set_defaults(handler=cmd_status)

    p = sub.add_parser("info", parents=[cookies], help="analisa um link sem baixar")
    p.add_argument("url")
    p.add_argument("--formatos", action="store_true", help="lista os formatos disponíveis")
    p.set_defaults(handler=cmd_info)

    transcription = _Parser(add_help=False)
    transcription.add_argument("--idioma", help="pt, en, es… ou auto (padrão: Configurações)")
    transcription.add_argument("--modelo", choices=("tiny", "base", "small", "medium",
                                                    "large-v3-turbo", "large-v3"))
    transcription.add_argument("--formato", help="srt, vtt, ass, karaoke, txt ou json")
    transcription.add_argument("--traduzir", action="store_true", help="traduz para inglês")
    transcription.add_argument("--prompt", help="vocabulário/contexto para o Whisper")

    p = sub.add_parser("baixar", parents=[cookies, transcription],
                       help="baixa vídeo, áudio, playlist ou trecho")
    p.add_argument("urls", nargs="+", metavar="URL")
    p.add_argument("--pasta", help="destino (padrão: pasta de downloads das Configurações)")
    p.add_argument("--audio", action="store_true", help="só o áudio")
    p.add_argument("--formato-audio", choices=("mp3", "m4a", "opus", "flac", "wav"))
    p.add_argument("--qualidade", help="melhor (padrão), 2160, 1440, 1080, 720, 480…")
    p.add_argument("--formato-id", help="seletor -f exato (veja “info --formatos”)")
    p.add_argument("--container", choices=("mp4", "mkv", "webm", "original"))
    p.add_argument("--inicio", help="início do trecho (mm:ss ou hh:mm:ss)")
    p.add_argument("--fim", help="fim do trecho")
    p.add_argument("--playlist", action=argparse.BooleanOptionalAction, default=None,
                   help="baixa a playlist inteira (padrão: detecta pelo link)")
    p.add_argument("--itens", help="itens da playlist, ex.: 1-3,7")
    p.add_argument("--nome", help="nome do arquivo, sem extensão")
    p.add_argument("--legendas", metavar="IDIOMAS",
                   help="baixa legendas do site, ex.: pt,en")
    p.add_argument("--sponsorblock", action="store_true",
                   help="remove patrocínios (SponsorBlock)")
    p.add_argument("--legendar", action="store_true",
                   help="gera legenda com o Whisper depois de baixar")
    p.set_defaults(handler=cmd_baixar)

    p = sub.add_parser("legendar", parents=[transcription],
                       help="transcreve um arquivo local com o Whisper")
    p.add_argument("arquivo")
    p.add_argument("--saida", help="arquivo de saída (padrão: ao lado da mídia)")
    p.set_defaults(handler=cmd_legendar)

    p = sub.add_parser("cortar", parents=[cookies],
                       help="cria cortes verticais 9:16 com legenda animada")
    p.add_argument("fonte", help="arquivo local ou link")
    p.add_argument("--corte", action="append", metavar="INICIO-FIM[=TÍTULO]",
                   help="repita para vários cortes, ex.: --corte 1:20-2:05=Gancho")
    p.add_argument("--plano", metavar="JSON|ARQ",
                   help='plano da IA ({"bx":1,"c":[…]}, ver docs/PLANO-DA-IA.md), no lugar '
                        "de --corte")
    p.add_argument("--pasta-sons", metavar="DIR",
                   help="seus sons (whoosh, pop, impacto, ding, subida); vazio = os do app")
    p.add_argument("--altura-titulo", type=int, metavar="%",
                   help="centro do título em %% da altura (0 = automático)")
    p.add_argument("--pasta", help="destino dos cortes")
    p.add_argument("--enquadramento", help="blur, crop ou track (segue a pessoa)")
    p.add_argument("--animacao", help="highlight, color, karaoke, word, pop ou none")
    p.add_argument("--cor-destaque", metavar="#RRGGBB")
    p.add_argument("--palavras", type=int, help="palavras por legenda (1 a 4)")
    p.add_argument("--idioma")
    p.add_argument("--modelo", choices=("tiny", "base", "small", "medium",
                                        "large-v3-turbo", "large-v3"))
    _bool_flag(p, "remover-pausas", "corta silêncios longos")
    _bool_flag(p, "zoom-emendas", "aproxima a cada emenda")
    _bool_flag(p, "barra", "barra de progresso no vídeo")
    _bool_flag(p, "normalizar", "volume em -14 LUFS")
    _bool_flag(p, "srt", "salva também a legenda .srt")
    _bool_flag(p, "efeitos", "whoosh e pop automáticos")
    _bool_flag(p, "zoom-enfase", "zoom na palavra dita com mais força")
    p.set_defaults(handler=cmd_cortar)

    p = sub.add_parser("ferramenta", help="edita um arquivo local com o FFmpeg")
    p.add_argument("operacao", choices=TOOL_OPERATIONS)
    p.add_argument("arquivo")
    p.add_argument("--saida")
    p.add_argument("--inicio")
    p.add_argument("--fim")
    p.add_argument("--escolha", help="parâmetro da ferramenta (ex.: mp3, 2, cw, 640, -14)")
    p.add_argument("--legenda", help="legenda para burn/soft_sub")
    p.add_argument("--idioma-legenda", help="idioma da faixa em soft_sub (pt, en…)")
    p.add_argument("--tamanho-mb", type=int, default=25, help="limite do target_size")
    p.add_argument("--rapido", action="store_true", help="trim sem reencodar")
    p.add_argument("--sem-desfoque", action="store_true", help="shorts com barras pretas")
    p.set_defaults(handler=cmd_ferramenta)

    p = sub.add_parser("historico", help="últimos itens do histórico")
    p.add_argument("--limite", type=int, default=20)
    p.set_defaults(handler=cmd_historico)
    return parser


def _write_result(result: dict, json_path: str | None) -> None:
    text = json.dumps(result, ensure_ascii=False, indent=2, default=str)
    if json_path:
        target = Path(json_path).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    with contextlib.suppress(OSError, ValueError, AttributeError):
        print(text, flush=True)


def _split_json_path(argv: list[str]) -> tuple[list[str], str | None]:
    """Tira ``--json-saida`` de qualquer posição: quem chama não precisa saber a ordem."""
    rest: list[str] = []
    path = None
    index = 0
    while index < len(argv):
        value = argv[index]
        if value == "--json-saida" and index + 1 < len(argv):
            path, index = argv[index + 1], index + 2
            continue
        if value.startswith("--json-saida="):
            path = value.partition("=")[2]
        else:
            rest.append(value)
        index += 1
    return rest, path


def run_cli(argv: list[str]) -> int:
    """Ponto de entrada do modo CLI; ``argv`` vem sem o ``cli`` inicial."""
    _prepare_stdio()
    from .diagnostics import install_diagnostics, report_exception

    parser = build_parser()
    argv, json_path = _split_json_path(argv)
    try:
        args = parser.parse_args(argv)
        if args.comando in {None, "ajuda"}:
            _emit(parser.format_help())
            return EXIT_OK if args.comando else EXIT_USAGE
        install_diagnostics("cli")
        result = {"ok": True, "comando": args.comando, **args.handler(args)}
        code = EXIT_OK
    except CliError as exc:
        usage = "Use “cli ajuda”" in str(exc)
        result, code = {"ok": False, "erro": str(exc)}, EXIT_USAGE if usage else EXIT_FAILED
    except (_Cancelled, KeyboardInterrupt) as exc:
        result, code = {"ok": False, "erro": str(exc) or "Cancelado."}, EXIT_CANCELLED
    except SystemExit as exc:   # --help do argparse
        return int(exc.code or 0)
    except Exception as exc:  # noqa: BLE001 - quem chamou precisa do JSON mesmo assim
        report_exception("modo CLI", exc)
        from .probe import friendly_error

        result, code = {"ok": False, "erro": friendly_error(str(exc))}, EXIT_FAILED
    _write_result(result, json_path)
    return code
