from __future__ import annotations

import ctypes
from ctypes import wintypes

import psutil

from fixer.utils import normalize_process_name


class _User32:
    def __init__(self) -> None:
        self._user32 = ctypes.windll.user32

    def foreground_pid(self) -> int | None:
        hwnd = self._user32.GetForegroundWindow()
        if not hwnd:
            return None

        pid = wintypes.DWORD()
        self._user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == 0:
            return None
        return int(pid.value)


_USER32 = _User32()


def get_foreground_process_name() -> str | None:
    pid = _USER32.foreground_pid()
    if pid is None:
        return None

    try:
        return normalize_process_name(psutil.Process(pid).name())
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return None
