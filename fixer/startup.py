from __future__ import annotations

import subprocess
import sys
import winreg
from pathlib import Path

RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "FixerOptimizer"


def build_startup_command(config_path: str | Path, dry_run: bool, learning_mode: bool) -> str:
    command_parts = [
        sys.executable,
        "-m",
        "fixer",
        "tray",
        "--config",
        str(Path(config_path).resolve()),
    ]
    if dry_run:
        command_parts.append("--dry-run")
    if learning_mode:
        command_parts.append("--learning-mode")

    return subprocess.list2cmdline(command_parts)


def install_startup(config_path: str | Path, dry_run: bool, learning_mode: bool) -> str:
    command = build_startup_command(config_path=config_path, dry_run=dry_run, learning_mode=learning_mode)
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, command)
    return command


def remove_startup() -> bool:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_SET_VALUE) as key:
        try:
            winreg.DeleteValue(key, VALUE_NAME)
            return True
        except FileNotFoundError:
            return False


def get_startup_command() -> str | None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_QUERY_VALUE) as key:
            value, _ = winreg.QueryValueEx(key, VALUE_NAME)
            return str(value)
    except FileNotFoundError:
        return None
