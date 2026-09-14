"""Integração nativa com o botão da barra de tarefas do Windows.

Qt 6 não expõe ``QWinTaskbarButton``. Este módulo usa ``ITaskbarList3``
diretamente, mantendo a integração isolada e opcional: fora do Windows, ou se
o shell não estiver disponível, todos os métodos simplesmente não fazem nada.
"""
from __future__ import annotations

import ctypes
from ctypes import POINTER, byref, c_int, c_ulonglong, c_void_p
from ctypes.wintypes import BOOL, DWORD, HWND, UINT
from pathlib import Path

from .config import IS_WINDOWS

# TBPFLAG (ITaskbarList3)
TBPF_NOPROGRESS = 0
TBPF_INDETERMINATE = 0x1
TBPF_NORMAL = 0x2
TBPF_ERROR = 0x4
TBPF_PAUSED = 0x8

_CLSID_TASKBAR_LIST = "{56FDF344-FD6D-11d0-958A-006097C9A090}"
_IID_TASKBAR_LIST3 = "{EA1AFB91-9E28-4B86-90E9-9E9F8A5EEFAF}"
_CLSCTX_INPROC_SERVER = 0x1
_COINIT_APARTMENTTHREADED = 0x2
_RPC_E_CHANGED_MODE = 0x80010106

_WM_SETICON = 0x0080
_ICON_SMALL = 0
_ICON_BIG = 1
_IMAGE_ICON = 1
_LR_LOADFROMFILE = 0x0010

_FLASHW_TRAY = 0x00000002


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_uint32),
        ("Data2", ctypes.c_uint16),
        ("Data3", ctypes.c_uint16),
        ("Data4", ctypes.c_ubyte * 8),
    ]


class _FLASHWINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", UINT),
        ("hwnd", HWND),
        ("dwFlags", DWORD),
        ("uCount", UINT),
        ("dwTimeout", DWORD),
    ]


def _hresult_failed(result: int) -> bool:
    """Avalia HRESULT sem depender do tamanho de ``c_long`` da plataforma."""
    return bool(int(result) & 0x80000000)


class TaskbarProgress:
    """Controla ícone, progresso e alerta do botão da barra de tarefas."""

    def __init__(self) -> None:
        self._ptr: c_void_p | None = None
        self._vtable = None
        self._failed = not IS_WINDOWS
        self._state = TBPF_NOPROGRESS
        self._hwnd = HWND(0)
        self._icon_hwnd = 0
        self._icon_handles: list[int] = []
        self._com_initialized = False

    # ------------------------------------------------------------------ COM
    def _ensure(self) -> bool:
        if self._ptr is not None:
            return True
        if self._failed:
            return False

        # Uma falha é definitiva para esta sessão: não vale repetir uma chamada
        # COM a cada atualização de progresso da interface.
        self._failed = True
        try:
            ole32 = ctypes.windll.ole32
            ole32.CLSIDFromString.argtypes = (ctypes.c_wchar_p, POINTER(_GUID))
            ole32.CLSIDFromString.restype = ctypes.c_long
            ole32.IIDFromString.argtypes = (ctypes.c_wchar_p, POINTER(_GUID))
            ole32.IIDFromString.restype = ctypes.c_long
            ole32.CoInitializeEx.argtypes = (c_void_p, DWORD)
            ole32.CoInitializeEx.restype = ctypes.c_long
            ole32.CoCreateInstance.argtypes = (
                POINTER(_GUID), c_void_p, DWORD, POINTER(_GUID), POINTER(c_void_p),
            )
            ole32.CoCreateInstance.restype = ctypes.c_long

            clsid, iid = _GUID(), _GUID()
            if _hresult_failed(ole32.CLSIDFromString(_CLSID_TASKBAR_LIST, byref(clsid))):
                return False
            if _hresult_failed(ole32.IIDFromString(_IID_TASKBAR_LIST3, byref(iid))):
                return False

            # O Qt normalmente já inicializa a thread de UI. RPC_E_CHANGED_MODE
            # só informa que ela usa outro apartamento, o que ainda permite usar
            # o objeto criado abaixo nessa mesma thread.
            hr = ole32.CoInitializeEx(None, _COINIT_APARTMENTTHREADED)
            if _hresult_failed(hr) and (int(hr) & 0xFFFFFFFF) != _RPC_E_CHANGED_MODE:
                return False
            self._com_initialized = not _hresult_failed(hr)

            ptr = c_void_p()
            if _hresult_failed(ole32.CoCreateInstance(
                byref(clsid), None, _CLSCTX_INPROC_SERVER, byref(iid), byref(ptr),
            )) or not ptr.value:
                return False

            vtable = ctypes.cast(ptr, POINTER(POINTER(c_void_p))).contents
            hr_init = ctypes.WINFUNCTYPE(ctypes.c_long, c_void_p)(vtable[3])  # HrInit
            if _hresult_failed(hr_init(ptr)):
                return False

            self._ptr = ptr
            self._vtable = vtable
            self._failed = False
            return True
        except Exception:
            self._ptr = None
            return False

    def _call(self, slot: int, argtypes: tuple, *args) -> bool:
        if not self._ensure():
            return False
        try:
            fn = ctypes.WINFUNCTYPE(ctypes.c_long, c_void_p, *argtypes)(self._vtable[slot])
            if _hresult_failed(fn(self._ptr, *args)):
                self._failed, self._ptr = True, None
                return False
            return True
        except Exception:
            self._failed, self._ptr = True, None
            return False

    def _set_state(self, hwnd: int, state: int) -> bool:
        native_hwnd = HWND(hwnd)
        if state == self._state and native_hwnd.value == self._hwnd.value:
            return True
        if self._call(10, (HWND, c_int), native_hwnd, state):  # SetProgressState
            self._hwnd = native_hwnd
            self._state = state
            return True
        return False

    # -------------------------------------------------------------- progresso
    def set_value(self, hwnd: int, percent: float) -> None:
        """Mostra o percentual de uma operação ativa (valor sempre entre 0 e 100)."""
        if not hwnd:
            return
        if percent < 0:
            self.clear(hwnd)
            return
        if not self._set_state(hwnd, TBPF_NORMAL):
            return
        value = max(0, min(100, round(percent)))
        self._call(9, (HWND, c_ulonglong, c_ulonglong),  # SetProgressValue
                   HWND(hwnd), c_ulonglong(value), c_ulonglong(100))

    def set_indeterminate(self, hwnd: int) -> None:
        """Exibe atividade sem um percentual confiável, como preparação de mídia."""
        if hwnd:
            self._set_state(hwnd, TBPF_INDETERMINATE)

    def set_error(self, hwnd: int) -> None:
        if hwnd:
            self._set_state(hwnd, TBPF_ERROR)

    def clear(self, hwnd: int) -> None:
        if hwnd:
            self._set_state(hwnd, TBPF_NOPROGRESS)

    # ----------------------------------------------------------- notificações
    def complete(self, hwnd: int) -> None:
        """Confirma a conclusão no botão: 100% verde e três piscadas discretas."""
        self.set_value(hwnd, 100)
        self.flash(hwnd)

    @staticmethod
    def flash(hwnd: int, count: int = 3) -> None:
        """Pisca o botão da barra de tarefas sem trazer a janela para a frente."""
        if not IS_WINDOWS or not hwnd:
            return
        try:
            user32 = ctypes.windll.user32
            user32.FlashWindowEx.argtypes = (POINTER(_FLASHWINFO),)
            user32.FlashWindowEx.restype = BOOL
            info = _FLASHWINFO(
                ctypes.sizeof(_FLASHWINFO), HWND(hwnd), _FLASHW_TRAY,
                max(1, int(count)), 0,
            )
            user32.FlashWindowEx(byref(info))
        except Exception:
            pass

    # --------------------------------------------------------------- ícone HWND
    def apply_window_icon(self, hwnd: int, icon_path: Path | None) -> bool:
        """Força o mesmo .ico do executável no HWND criado pelo qframelesswindow.

        O qframelesswindow recria a janela nativa durante o primeiro ``show`` em
        algumas máquinas. Nessa situação o ícone definido apenas pelo Qt pode
        voltar ao padrão genérico; WM_SETICON evita essa regressão.
        """
        if not IS_WINDOWS or not hwnd or not icon_path or not icon_path.is_file():
            return False
        if self._icon_hwnd == hwnd and self._icon_handles:
            return True
        self._release_window_icons()
        try:
            user32 = ctypes.windll.user32
            user32.LoadImageW.argtypes = (c_void_p, ctypes.c_wchar_p, UINT, c_int, c_int, UINT)
            user32.LoadImageW.restype = c_void_p
            user32.SendMessageW.argtypes = (HWND, UINT, c_void_p, c_void_p)
            user32.SendMessageW.restype = c_void_p

            flags = _LR_LOADFROMFILE
            small = user32.LoadImageW(None, str(icon_path), _IMAGE_ICON, 16, 16, flags)
            big = user32.LoadImageW(None, str(icon_path), _IMAGE_ICON, 48, 48, flags)
            if not small and not big:
                return False
            if small:
                user32.SendMessageW(HWND(hwnd), _WM_SETICON, _ICON_SMALL, small)
                self._icon_handles.append(int(small))
            if big:
                user32.SendMessageW(HWND(hwnd), _WM_SETICON, _ICON_BIG, big)
                self._icon_handles.append(int(big))
            self._icon_hwnd = hwnd
            return True
        except Exception:
            self._release_window_icons()
            return False

    def _release_window_icons(self) -> None:
        if not self._icon_handles:
            return
        try:
            user32 = ctypes.windll.user32
            if self._icon_hwnd:
                user32.SendMessageW(HWND(self._icon_hwnd), _WM_SETICON, _ICON_SMALL, None)
                user32.SendMessageW(HWND(self._icon_hwnd), _WM_SETICON, _ICON_BIG, None)
            for handle in self._icon_handles:
                user32.DestroyIcon(c_void_p(handle))
        except Exception:
            pass
        self._icon_handles.clear()
        self._icon_hwnd = 0

    def shutdown(self, hwnd: int = 0) -> None:
        """Libera os recursos nativos no encerramento normal da janela."""
        self.clear(hwnd)
        self._release_window_icons()
        if self._ptr is not None and self._vtable is not None:
            try:
                release = ctypes.WINFUNCTYPE(ctypes.c_ulong, c_void_p)(self._vtable[2])
                release(self._ptr)
            except Exception:
                pass
        self._ptr = None
        self._vtable = None
        if self._com_initialized:
            try:
                ctypes.windll.ole32.CoUninitialize()
            except Exception:
                pass
        self._com_initialized = False
