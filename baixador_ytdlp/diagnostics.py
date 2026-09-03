"""Registro de diagnóstico e captura de falhas do aplicativo.

Os motores de transcrição usam extensões nativas (CTranslate2/CUDA). Um
erro de acesso nessas bibliotecas pode encerrar o processo antes de o Python
conseguir levantar uma exceção. Por isso os logs normais e o ``faulthandler``
escrevem em arquivos diferentes e persistentes.
"""
from __future__ import annotations

import faulthandler
import logging
import logging.handlers
import platform
import sys
import threading
import traceback
from pathlib import Path
from .config import APP_NAME, APP_VERSION, LOG_DIR

LOG_NAME = "baixador_ytdlp"
APP_LOG_NAME = "app.log"
CRASH_LOG_NAME = "crash.log"
FAULT_LOG_NAME = "native-fault.log"

_configured = False
_fault_file = None


def log_path(name: str) -> Path:
    """Retorna um arquivo de diagnóstico no diretório de dados do usuário."""
    return LOG_DIR / name


def get_logger() -> logging.Logger:
    return logging.getLogger(LOG_NAME)


def _formatter() -> logging.Formatter:
    return logging.Formatter(
        "%(asctime)s.%(msecs)03d %(levelname)-8s [pid=%(process)d thread=%(threadName)s] "
        "%(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _add_rotating_handler(logger: logging.Logger, path: Path, level: int) -> None:
    handler = logging.handlers.RotatingFileHandler(
        path, maxBytes=2 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    handler.setLevel(level)
    handler.setFormatter(_formatter())
    logger.addHandler(handler)


def _enable_fault_handler() -> None:
    """Registra falhas nativas (por exemplo, access violation em DLL CUDA)."""
    global _fault_file
    try:
        # O arquivo precisa continuar aberto até o encerramento do processo.
        _fault_file = open(log_path(FAULT_LOG_NAME), "a", encoding="utf-8")
        faulthandler.enable(file=_fault_file, all_threads=True)
    except (OSError, RuntimeError):
        # Diagnóstico nunca pode impedir a abertura do aplicativo.
        _fault_file = None


def report_exception(context: str, exc: BaseException) -> None:
    """Salva uma exceção completa, inclusive quando ela foi tratada pela UI."""
    details = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    get_logger().error("Falha em %s:\n%s", context, details.rstrip())


def install_diagnostics(process_name: str = "app") -> logging.Logger:
    """Ativa logs, hooks globais e o capturador de falhas nativas uma vez."""
    global _configured
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = get_logger()

    if not _configured:
        logger.setLevel(logging.DEBUG)
        logger.propagate = False
        _add_rotating_handler(logger, log_path(APP_LOG_NAME), logging.DEBUG)
        _add_rotating_handler(logger, log_path(CRASH_LOG_NAME), logging.ERROR)
        logging.captureWarnings(True)
        _enable_fault_handler()
        _configured = True

    def exception_hook(exc_type, exc, tb) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            return sys.__excepthook__(exc_type, exc, tb)
        logger.critical(
            "Exceção não tratada em %s:\n%s",
            process_name,
            "".join(traceback.format_exception(exc_type, exc, tb)).rstrip(),
        )
        return None

    def threading_exception_hook(args: threading.ExceptHookArgs) -> None:
        if args.exc_type is not None and issubclass(args.exc_type, KeyboardInterrupt):
            return
        logger.critical(
            "Exceção não tratada na thread %s:\n%s",
            getattr(args.thread, "name", "desconhecida"),
            "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)).rstrip(),
        )

    sys.excepthook = exception_hook
    threading.excepthook = threading_exception_hook
    logger.info(
        "Sessão iniciada (%s): app=%s versão=%s python=%s plataforma=%s",
        process_name, APP_NAME, APP_VERSION, sys.version.split()[0], platform.platform(),
    )
    return logger


def install_qt_logging() -> None:
    """Encaminha avisos do Qt para ``app.log`` sem depender do console oculto."""
    try:
        from PySide6.QtCore import QtMsgType, qInstallMessageHandler
    except ImportError:
        return

    logger = get_logger()
    levels = {
        QtMsgType.QtDebugMsg: logging.DEBUG,
        QtMsgType.QtInfoMsg: logging.INFO,
        QtMsgType.QtWarningMsg: logging.WARNING,
        QtMsgType.QtCriticalMsg: logging.ERROR,
        QtMsgType.QtFatalMsg: logging.CRITICAL,
    }

    def handler(mode, context, message) -> None:
        location = ""
        if context and context.file:
            location = f" ({context.file}:{context.line})"
        logger.log(levels.get(mode, logging.WARNING), "Qt: %s%s", message, location)

    qInstallMessageHandler(handler)


def log_event(message: str, *args) -> None:
    get_logger().info(message, *args)
