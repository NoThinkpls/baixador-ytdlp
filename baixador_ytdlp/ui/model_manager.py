"""Gerenciador dos modelos Whisper armazenados no perfil do usuário."""
from __future__ import annotations

from PySide6.QtWidgets import QDialog, QHBoxLayout, QMessageBox, QVBoxLayout, QWidget

from ..transcription import (MODEL_ORDER, cached_model_path, model_cache_size,
                             preferred_model_backend)
from ..workers import ModelCacheWorker
from .components import Button, Headline, InsetGroup, Muted, ProgressBar, SettingRow


def _size_label(size: int) -> str:
    if size <= 0:
        return "Não baixado"
    return f"Baixado · {size / 1024 ** 3:.2f} GB"


class ModelManagerDialog(QDialog):
    def __init__(self, current_model: str, parent=None):
        super().__init__(parent)
        self.current_model = current_model
        self.mlx = preferred_model_backend()
        self.worker: ModelCacheWorker | None = None
        self._status_labels: dict[str, object] = {}
        self._download_buttons: dict[str, Button] = {}
        self._remove_buttons: dict[str, Button] = {}
        self._build_ui()
        self._refresh()

    def _build_ui(self) -> None:
        self.setWindowTitle("Modelos Whisper")
        self.resize(660, 520)
        self.setMinimumSize(560, 440)
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 22)
        root.setSpacing(12)
        root.addWidget(Headline("Modelos Whisper", self))
        backend = "MLX para Apple Silicon" if self.mlx else "CTranslate2 para CPU/CUDA"
        root.addWidget(Muted(
            f"Backend ativo: {backend}. Os pesos ficam somente nesta máquina e podem ser "
            "baixados antes da primeira transcrição.",
            self,
        ))

        group = InsetGroup(self)
        labels = {
            "tiny": "Tiny — menor e mais rápido",
            "base": "Base — rápido",
            "small": "Small — equilibrado",
            "medium": "Medium — recomendado",
            "large-v3-turbo": "Large v3 Turbo — rápido e preciso",
            "large-v3": "Large v3 — máxima precisão",
        }
        for model in MODEL_ORDER:
            controls = QWidget(group)
            line = QHBoxLayout(controls)
            line.setContentsMargins(0, 0, 0, 0)
            line.setSpacing(6)
            status = Muted("Verificando…", controls)
            status.setWordWrap(False)
            download = Button("Baixar", "download", "secondary", controls)
            remove = Button("Remover", "trash", "ghost", controls)
            download.clicked.connect(
                lambda _checked=False, value=model: self._start("download", value)
            )
            remove.clicked.connect(
                lambda _checked=False, value=model: self._confirm_remove(value)
            )
            line.addWidget(status)
            line.addWidget(download)
            line.addWidget(remove)
            title = labels[model] + (" · em uso" if model == self.current_model else "")
            group.add_row(SettingRow(title, "Revisão fixada e verificada pelo aplicativo.", controls, group))
            self._status_labels[model] = status
            self._download_buttons[model] = download
            self._remove_buttons[model] = remove
        root.addWidget(group, 1)

        self.progress = ProgressBar(self)
        self.progress.hide()
        self.status = Muted("", self)
        root.addWidget(self.progress)
        root.addWidget(self.status)

        actions = QHBoxLayout()
        actions.addStretch(1)
        self.close_button = Button("Fechar", "close", "secondary", self)
        self.close_button.clicked.connect(self.accept)
        actions.addWidget(self.close_button)
        root.addLayout(actions)

    def _refresh(self) -> None:
        for model in MODEL_ORDER:
            cached = cached_model_path(model, mlx=self.mlx) is not None
            size = model_cache_size(model, mlx=self.mlx) if cached else 0
            self._status_labels[model].setText(_size_label(size))
            self._download_buttons[model].setEnabled(not cached and self.worker is None)
            self._remove_buttons[model].setEnabled(cached and self.worker is None)

    def _set_busy(self, busy: bool) -> None:
        self.close_button.setEnabled(not busy)
        for button in (*self._download_buttons.values(), *self._remove_buttons.values()):
            button.setEnabled(not busy)
        self.progress.setVisible(busy)
        if busy:
            self.progress.setValue(0)

    def _start(self, action: str, model: str) -> None:
        if self.worker and self.worker.isRunning():
            return
        worker = ModelCacheWorker(action, model, self.mlx, self)
        self.worker = worker
        worker.status.connect(self.status.setText)
        worker.progress.connect(self.progress.setValue)
        worker.finished_ok.connect(
            lambda value, changed, requested=action: self._done(requested, value, changed)
        )
        worker.failed.connect(self._failed)
        worker.finished.connect(worker.deleteLater)
        worker.start()
        self._set_busy(True)

    def _confirm_remove(self, model: str) -> None:
        answer = QMessageBox.question(
            self,
            "Remover modelo?",
            f"Remover o modelo {model} desta máquina? Ele poderá ser baixado novamente depois.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._start("remove", model)

    def _done(self, action: str, model: str, changed: int) -> None:
        self._set_busy(False)
        self.worker = None
        verb = "baixado" if action == "download" else "removido"
        self.status.setText(f"Modelo {model} {verb} · {changed / 1024 ** 3:.2f} GB.")
        self._refresh()

    def _failed(self, message: str) -> None:
        self._set_busy(False)
        self.worker = None
        self.status.setText(f"Não foi possível concluir: {message}")
        self._refresh()

    def reject(self) -> None:
        if self.worker and self.worker.isRunning():
            self.status.setText("Aguarde o download ou a remoção terminar.")
            return
        super().reject()
