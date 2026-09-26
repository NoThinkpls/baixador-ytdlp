"""Ponto de entrada do baixador-ytdlp."""
from __future__ import annotations

import ctypes
import json
import multiprocessing
import os
import sys
import tempfile
import traceback
import wave
from pathlib import Path

# Um argumento continua útil para a execução manual. No CI, porém, usamos a
# variável de ambiente: alguns binários GUI não preservam argumentos de linha
# de comando ao serem iniciados pelo shell do runner.
_SELF_TEST_ENV = "BAIXADOR_YTDLP_SELF_TEST_REPORT"
_SELF_TEST_REQUESTED = sys.argv[1:2] == ["--self-test"] or bool(os.environ.get(_SELF_TEST_ENV))
_SELF_TEST_REPORT = (
    sys.argv[2] if sys.argv[1:2] == ["--self-test"] and len(sys.argv) == 3
    else os.environ.get(_SELF_TEST_ENV)
)

# Persistir o primeiro marco do autoteste permite diferenciar uma queda no
# bootstrap nativo do executável de uma falha em uma de suas dependências.
if _SELF_TEST_REPORT:
    Path(_SELF_TEST_REPORT).write_text(
        json.dumps({"ok": False, "stage": "bootstrap"}), encoding="utf-8"
    )

# O huggingface_hub envia telemetria de uso por padrão; nada além dos pesos
# fixados precisa sair desta máquina. Vale também para o processo do Whisper,
# que herda o ambiente.
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

from baixador_ytdlp.plataforma import pasta_do_executavel  # noqa: E402


def asset(name: str) -> Path:
    """Resolve arquivos empacotados tanto no modo script quanto congelado."""
    return pasta_do_executavel() / "assets" / name


def _self_test_vad_child(events) -> None:
    """Exercita a carga do VAD dentro de um filho ``spawn``."""
    try:
        from faster_whisper.vad import get_vad_model

        get_vad_model()
    except BaseException as exc:  # o resultado precisa voltar ao processo pai
        events.put({"ok": False, "error": f"{type(exc).__name__}: {exc}"})
        raise
    else:
        events.put({"ok": True})


def _run_self_test(report_path: Path) -> int:
    """Valida o runtime embarcado sem abrir Qt nem baixar pesos do Whisper."""
    report: dict[str, object] = {"ok": False}

    def checkpoint(stage: str) -> None:
        report["stage"] = stage
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    try:
        checkpoint("self_test_entered")
        import importlib.metadata

        checkpoint("import_onnxruntime")
        import onnxruntime
        checkpoint("import_av")
        import av
        checkpoint("import_ctranslate2")
        import ctranslate2
        checkpoint("import_faster_whisper")
        import faster_whisper
        checkpoint("import_huggingface_hub")
        import huggingface_hub
        checkpoint("import_tokenizers")
        import tokenizers
        checkpoint("import_faster_whisper_audio")
        from faster_whisper.audio import decode_audio
        checkpoint("import_faster_whisper_utils")
        from faster_whisper.utils import get_assets_path
        checkpoint("import_faster_whisper_vad")
        from faster_whisper.vad import get_vad_model
        checkpoint("import_runtime")
        from baixador_ytdlp.runtime import activate_embedded_cuda

        checkpoint("activate_embedded_cuda")
        activate_embedded_cuda()
        report["versions"] = {
            distribution: importlib.metadata.version(distribution)
            for distribution in (
                "faster-whisper", "ctranslate2", "av", "onnxruntime",
                "tokenizers", "huggingface-hub",
            )
        }
        report["imports"] = [
            faster_whisper.__name__, ctranslate2.__name__, av.__name__,
            onnxruntime.__name__, tokenizers.__name__, huggingface_hub.__name__,
        ]
        checkpoint("load_vad")
        report["vad_assets"] = str(Path(get_assets_path()).resolve())
        get_vad_model()
        checkpoint("probe_cuda")
        try:
            report["cuda_devices"] = ctranslate2.get_cuda_device_count()
        except Exception as exc:  # uma máquina sem driver deve continuar válida
            report["cuda_devices"] = 0
            report["cuda_probe_error"] = f"{type(exc).__name__}: {exc}"

        checkpoint("decode_audio")
        with tempfile.TemporaryDirectory(prefix="baixador-self-test-") as temporary:
            wav_path = Path(temporary) / "silence.wav"
            with wave.open(str(wav_path), "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(16000)
                wav.writeframes(b"\x00\x00" * 1600)
            decoded = decode_audio(str(wav_path), sampling_rate=16000)
            if len(decoded) != 1600:
                raise RuntimeError(f"PyAV devolveu {len(decoded)} amostras; esperado 1600.")

        checkpoint("spawn_vad_child")
        context = multiprocessing.get_context("spawn")
        events = context.Queue()
        child = context.Process(target=_self_test_vad_child, args=(events,))
        child.start()
        child.join(30)
        if child.is_alive():
            child.terminate()
            child.join()
            raise RuntimeError("O processo filho do VAD excedeu 30 segundos.")
        if child.exitcode != 0:
            raise RuntimeError(f"O processo filho do VAD encerrou com código {child.exitcode}.")
        child_result = events.get(timeout=5)
        if not child_result.get("ok"):
            raise RuntimeError(str(child_result.get("error", "Falha desconhecida no VAD filho.")))
        report["ok"] = True
        checkpoint("completed")
    except BaseException as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        report["traceback"] = traceback.format_exc()
    finally:
        checkpoint(str(report.get("stage", "failed")))
    return 0 if report["ok"] else 1


def main() -> int:
    if _SELF_TEST_REQUESTED:
        if not _SELF_TEST_REPORT:
            return 2
        return _run_self_test(Path(_SELF_TEST_REPORT))

    # O autoteste não precisa carregar configuração, diagnósticos, Qt nem a
    # árvore da interface. Isso o mantém útil para detectar problemas do
    # runtime empacotado antes da inicialização normal do aplicativo.
    from baixador_ytdlp.config import APP_ID, APP_NAME, IS_WINDOWS, Settings, ensure_dirs
    from baixador_ytdlp.diagnostics import install_diagnostics, install_qt_logging, log_event

    # Os imports Qt ficam aqui: o processo auxiliar do multiprocessing entra
    # por freeze_support antes de carregar qualquer componente de interface.
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication

    from baixador_ytdlp.tools import ToolManager
    from baixador_ytdlp.instance import InstanceLock, InstanceServer, forward_to_running
    from baixador_ytdlp.ui.main_window import MainWindow

    ensure_dirs()
    install_diagnostics()

    if IS_WINDOWS:
        # Agrupa a janela sob o ícone certo na barra de tarefas.
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    instance_lock = InstanceLock()
    if not instance_lock.acquire():
        if forward_to_running(sys.argv[1:]):
            log_event("Argumentos encaminhados para a instância já aberta")
        else:
            log_event("Outra instância detém a trava, mas não respondeu ao encaminhamento")
        return 0
    instance_server = InstanceServer(app)
    if not instance_server.listen():
        log_event("Encerrando: não foi possível reservar o canal da instância única")
        return 1
    # A folha de estilo entra antes de qualquer janela: assim a tela de
    # preparação já abre com a identidade visual do aplicativo.
    from baixador_ytdlp.ui import theme
    theme.apply(app)
    install_qt_logging()
    app.setApplicationName(APP_NAME)
    app.setQuitOnLastWindowClosed(True)

    icon_path = asset("icon.ico" if IS_WINDOWS else "icon.png")
    icon = QIcon(str(icon_path)) if icon_path.exists() else QIcon()
    app.setWindowIcon(icon)

    try:  # pesos de versões ≤ 1.7: só renomeia pastas no mesmo volume
        from baixador_ytdlp.transcription import migrate_legacy_model_cache
        moved = migrate_legacy_model_cache()
        if moved:
            log_event("Modelos Whisper migrados para o cache novo: %s", ", ".join(moved))
    except Exception as exc:  # noqa: BLE001 - migração é conveniência
        log_event("Migração de modelos ignorada: %s", exc)

    cfg = Settings.load()
    # A árvore de widgets é construída já no idioma escolhido. Trocas feitas
    # na tela de Configurações entram na próxima abertura, sem recriar a UI no
    # meio de uma fila ativa.
    from baixador_ytdlp.ui.i18n import set_language
    set_language(cfg.ui_language)
    window = MainWindow(
        cfg,
        ToolManager(runtime_check_hours=cfg.runtime_check_hours,
                    allow_system_tools=cfg.allow_system_tools,
                    ytdlp_channel=cfg.ytdlp_channel),
        icon,
        icon_path,
    )
    window.show()
    instance_server.arguments_received.connect(window.handle_external_arguments)
    # macOS entrega baixador://… como QFileOpenEvent, não em sys.argv.
    from PySide6.QtCore import QEvent, QObject

    class _UrlOpenFilter(QObject):
        def eventFilter(self, _watched, event):  # noqa: N802 - assinatura do Qt
            if event.type() == QEvent.Type.FileOpen and event.url().isValid():
                window.handle_external_arguments([event.url().toString()])
                return True
            return False

    url_filter = _UrlOpenFilter(app)
    app.installEventFilter(url_filter)

    if not window.run_setup() and window.toolchain is None:
        log_event("Encerrando: preparação inicial não foi concluída")
        return 1

    window.handle_external_arguments(sys.argv[1:])

    result = app.exec()
    log_event("Sessão encerrada normalmente: código=%s", result)
    return result


if __name__ == "__main__":
    # O processo principal do autoteste não cria filhos antes de executar
    # suas verificações. Evitar ``freeze_support`` aqui impede que Nuitka
    # interprete esse argumento interno como um processo ``spawn``. O filho
    # criado pelo autoteste não recebe ``--self-test`` e continua passando
    # pelo fluxo abaixo.
    if _SELF_TEST_REQUESTED:
        if not _SELF_TEST_REPORT:
            raise SystemExit(2)
        raise SystemExit(_run_self_test(Path(_SELF_TEST_REPORT)))

    # Obrigatório para que o modo spawn no Windows execute somente o alvo do
    # processo auxiliar, sem abrir uma segunda janela Qt.
    multiprocessing.freeze_support()
    raise SystemExit(main())
