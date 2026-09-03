"""Progresso no ícone da barra de tarefas do Windows (ITaskbarList3).

O Qt 6 não expõe mais o QWinTaskbarButton, então a interface COM é chamada
diretamente por ctypes. Em qualquer falha o módulo vira um no-op: nenhuma
funcionalidade do aplicativo depende disto.
"""
from __future__ import annotations

import ctypes
from ctypes import POINTER, byref, c_int, c_ulonglong, c_void_p
from ctypes.wintypes import HWND

from .config import IS_WINDOWS

# TBPFLAG
TBPF_NOPROGRESS = 0
TBPF_INDETERMINATE = 0x1
TBPF_NORMAL = 0x2
TBPF_ERROR = 0x4
TBPF_PAUSED = 0x8

_CLSID_TaskbarList = "{56FDF344-FD6D-11d0-958A-006097C9A090}"
_IID_ITaskbarList3 = "{EA1AFB91-9E28-4B86-90E9-9E9F8A5EEFAF}"


class _GUID(ctypes.Structure):
    _fields_ = [("Data1", ctypes.c_uint32), ("Data2", ctypes.c_uint16),
                ("Data3", ctypes.c_uint16), ("Data4", ctypes.c_ubyte * 8)]


class TaskbarProgress:
    """Wrapper mínimo. Instancia o COM na primeira vez que é realmente usado."""

    def __init__(self) -> None:
        self._ptr: c_void_p | None = None
        self._vtable = None
        self._failed = not IS_WINDOWS
        self._state = TBPF_NOPROGRESS

    # ------------------------------------------------------------------ COM
    def _ensure(self) -> bool:
        if self._ptr is not None:
            return True
        if self._failed:
            return False
        self._failed = True  # só tenta uma vez; falha vira no-op permanente
        try:
            ole32 = ctypes.oledll.ole32
            clsid, iid = _GUID(), _GUID()
            ole32.CLSIDFromString(_CLSID_TaskbarList, byref(clsid))
            ole32.IIDFromString(_IID_ITaskbarList3, byref(iid))
            ole32.CoInitialize(None)
            ptr = c_void_p()
            ole32.CoCreateInstance(byref(clsid), None, 1, byref(iid), byref(ptr))

            vtable = ctypes.cast(ptr, POINTER(POINTER(c_void_p))).contents
            hr_init = ctypes.WINFUNCTYPE(c_int, c_void_p)(vtable[3])  # HrInit
            hr_init(ptr)
            self._ptr = ptr
            self._vtable = vtable
            self._failed = False
            return True
        except Exception:
            self._ptr = None
            return False

    def _call(self, slot: int, argtypes: tuple, *args) -> None:
        if not self._ensure():
            return
        try:
            fn = ctypes.WINFUNCTYPE(c_int, c_void_p, *argtypes)(self._vtable[slot])
            fn(self._ptr, *args)
        except Exception:
            self._failed, self._ptr = True, None

    # ------------------------------------------------------------------ API
    def set_state(self, state: int) -> None:
        if state == self._state:
            return
        self._state = state
        self._call(10, (HWND, c_int), self._hwnd, state)   # SetProgressState

    def set_value(self, hwnd: int, percent: float) -> None:
        """Percentual de 0 a 100. Chamar com -1 limpa a barra."""
        self._hwnd = HWND(hwnd)
        if percent < 0:
            self.set_state(TBPF_NOPROGRESS)
            return
        if self._state != TBPF_NORMAL:
            self.set_state(TBPF_NORMAL)
        value = max(0, min(100, int(percent)))
        self._call(9, (HWND, c_ulonglong, c_ulonglong),      # SetProgressValue
                   self._hwnd, c_ulonglong(value), c_ulonglong(100))

    def set_error(self, hwnd: int) -> None:
        self._hwnd = HWND(hwnd)
        self.set_state(TBPF_ERROR)

    def clear(self, hwnd: int) -> None:
        self._hwnd = HWND(hwnd)
        self.set_state(TBPF_NOPROGRESS)

    _hwnd = HWND(0)
