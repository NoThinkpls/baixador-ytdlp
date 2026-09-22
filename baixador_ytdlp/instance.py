"""Instância única multiplataforma com encaminhamento de argumentos via Qt."""
from __future__ import annotations

import getpass
import json
import re

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from .config import APP_ID


def server_name() -> str:
    user = re.sub(r"[^A-Za-z0-9_.-]", "_", getpass.getuser())
    return f"{APP_ID}-{user}"


def forward_to_running(arguments: list[str], timeout_ms: int = 400) -> bool:
    socket = QLocalSocket()
    socket.connectToServer(server_name())
    if not socket.waitForConnected(timeout_ms):
        return False
    payload = json.dumps(arguments, ensure_ascii=False).encode("utf-8")
    socket.write(payload)
    socket.flush()
    socket.waitForBytesWritten(timeout_ms)
    socket.disconnectFromServer()
    return True


class InstanceServer(QObject):
    arguments_received = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.server = QLocalServer(self)
        self.server.newConnection.connect(self._receive)

    def listen(self) -> bool:
        name = server_name()
        if self.server.listen(name):
            return True
        # Um socket abandonado após crash não deve bloquear a próxima abertura.
        QLocalServer.removeServer(name)
        return self.server.listen(name)

    def _receive(self) -> None:
        while socket := self.server.nextPendingConnection():
            if not socket.bytesAvailable():
                socket.waitForReadyRead(300)
            try:
                payload = json.loads(bytes(socket.readAll()).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                payload = []
            if isinstance(payload, list):
                self.arguments_received.emit([str(item) for item in payload])
            socket.disconnectFromServer()
