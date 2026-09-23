"""Instância única multiplataforma com encaminhamento de argumentos via Qt.

Exclusividade e canal de mensagens são coisas separadas:

* um ``QLockFile`` na pasta de dados garante que só exista uma instância —
  inclusive no Windows, onde ``QLocalServer`` aceita vários *named pipes* com o
  mesmo nome e a exclusividade dependia só do encaminhamento dar certo;
* o ``QLocalServer`` só transporta as URLs, com acesso restrito ao usuário e,
  no Linux, dentro de ``$XDG_RUNTIME_DIR`` (0700) em vez de ``/tmp``, onde outro
  usuário poderia criar o socket antes (*squatting*) e receber os links.
"""
from __future__ import annotations

import getpass
import json
import os
import re
import sys
from pathlib import Path

from PySide6.QtCore import QLockFile, QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from .config import APP_ID, DATA_DIR

MAX_PAYLOAD_BYTES = 64 * 1024


def server_name() -> str:
    user = re.sub(r"[^A-Za-z0-9_.-]", "_", getpass.getuser())
    name = f"{APP_ID}-{user}"
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR", "")
    if sys.platform.startswith("linux") and runtime_dir and Path(runtime_dir).is_dir():
        return str(Path(runtime_dir) / f"{name}.sock")
    return name


def forward_to_running(arguments: list[str], timeout_ms: int = 1500) -> bool:
    socket = QLocalSocket()
    socket.connectToServer(server_name())
    if not socket.waitForConnected(timeout_ms):
        return False
    payload = json.dumps(arguments, ensure_ascii=False).encode("utf-8")[:MAX_PAYLOAD_BYTES]
    socket.write(payload)
    socket.flush()
    socket.waitForBytesWritten(timeout_ms)
    socket.disconnectFromServer()
    return True


class InstanceLock:
    """Trava exclusiva por usuário; sobrevive a crash (lock obsoleto é detectado)."""

    def __init__(self, directory: Path = DATA_DIR):
        directory.mkdir(parents=True, exist_ok=True)
        self.lock = QLockFile(str(directory / "instance.lock"))
        self.lock.setStaleLockTime(0)  # usa PID + hostname para detectar crash

    def acquire(self) -> bool:
        if self.lock.tryLock(100):
            return True
        # O dono morreu sem liberar: remove e tenta de novo uma única vez.
        if self.lock.removeStaleLockFile():
            return self.lock.tryLock(100)
        return False


class InstanceServer(QObject):
    arguments_received = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.server = QLocalServer(self)
        self.server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        self.server.newConnection.connect(self._receive)

    def listen(self) -> bool:
        """Só deve ser chamado por quem já detém o :class:`InstanceLock`."""
        name = server_name()
        if self.server.listen(name):
            return True
        # Com o lock em mãos, um socket existente é sobra de crash — nunca de
        # uma instância viva — e pode ser removido com segurança.
        QLocalServer.removeServer(name)
        return self.server.listen(name)

    def _receive(self) -> None:
        while socket := self.server.nextPendingConnection():
            if not socket.bytesAvailable():
                socket.waitForReadyRead(300)
            data = bytes(socket.read(MAX_PAYLOAD_BYTES))
            try:
                payload = json.loads(data.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                payload = []
            if isinstance(payload, list):
                self.arguments_received.emit([str(item) for item in payload[:32]])
            socket.disconnectFromServer()
