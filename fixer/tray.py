from __future__ import annotations

import logging
import os
import subprocess
import threading
from pathlib import Path

import pystray
from PIL import Image, ImageDraw
from pystray import Menu, MenuItem

from fixer.agent import OptimizerAgent
from fixer.learning import LearningEngine
from fixer.models import AppConfig, Mode

LOGGER = logging.getLogger("fixer.tray")


def _tray_log_path() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        path = Path(local_app_data) / "Fixer" / "tray.log"
    else:
        path = Path("logs") / "tray.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


class AgentController:
    def __init__(self, config: AppConfig, dry_run: bool, learning_mode: bool) -> None:
        self._config = config
        self._dry_run = dry_run
        self._learning_mode = learning_mode

        self._agent: OptimizerAgent | None = None
        self._thread: threading.Thread | None = None
        self._mode_override: Mode | None = None
        self._profile_override: str | None = None
        self._lock = threading.Lock()

    def start(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return

            learning_engine = LearningEngine(self._config) if self._learning_mode else None
            self._agent = OptimizerAgent(
                config=self._config,
                dry_run=self._dry_run,
                once=False,
                learning_engine=learning_engine,
            )
            self._agent.set_mode_override(self._mode_override)
            self._agent.set_profile_override(self._profile_override)

            self._thread = threading.Thread(target=self._agent.run, name="fixer-agent", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        with self._lock:
            agent = self._agent
            thread = self._thread

        if not agent or not thread:
            return

        agent.stop()
        thread.join(timeout=5)

        with self._lock:
            self._thread = None
            self._agent = None

    def mode_override(self) -> Mode | None:
        with self._lock:
            return self._mode_override

    def profile_override(self) -> str | None:
        with self._lock:
            return self._profile_override

    def set_mode_override(self, mode: Mode | None) -> None:
        with self._lock:
            self._mode_override = mode
            agent = self._agent
        if agent:
            agent.set_mode_override(mode)

    def set_profile_override(self, profile: str | None) -> None:
        with self._lock:
            self._profile_override = profile
            agent = self._agent
        if agent:
            agent.set_profile_override(profile)

    def status_text(self) -> str:
        with self._lock:
            agent = self._agent
        if not agent:
            return "Stopped"

        status = agent.status()
        if not status.running:
            return "Stopped"

        profile = status.current_profile or "unknown"
        mode = status.effective_mode
        active = status.active_game or "none"
        return f"Running | profile={profile} mode={mode} game={active}"

    def save_learning_snapshot(self) -> str:
        with self._lock:
            agent = self._agent

        if not agent:
            return "Agent not running"

        path = agent.save_learning_snapshot()
        if path is None:
            return "Learning is disabled"

        return str(path)


class TrayApplication:
    def __init__(self, config: AppConfig, dry_run: bool, learning_mode: bool) -> None:
        self._controller = AgentController(config, dry_run=dry_run, learning_mode=learning_mode)
        self._log_path = _tray_log_path()
        self._configure_file_logging(config.log_level)

        self._icon = pystray.Icon(
            name="Fixer",
            icon=self._build_icon(),
            title="Fixer Optimizer",
            menu=self._build_menu(),
        )

    def _configure_file_logging(self, level: str) -> None:
        root = logging.getLogger()
        root.setLevel(getattr(logging, level.upper(), logging.INFO))

        has_file_handler = False
        for handler in root.handlers:
            if isinstance(handler, logging.FileHandler) and Path(handler.baseFilename) == self._log_path:
                has_file_handler = True
                break

        if not has_file_handler:
            file_handler = logging.FileHandler(self._log_path, encoding="utf-8")
            file_handler.setLevel(getattr(logging, level.upper(), logging.INFO))
            file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s - %(message)s"))
            root.addHandler(file_handler)

        LOGGER.info("Tray logging initialized at %s", self._log_path)

    def run(self) -> None:
        LOGGER.info("Starting tray UI")
        self._controller.start()
        self._icon.run()

    def _build_menu(self) -> Menu:
        return Menu(
            MenuItem(lambda _: self._controller.status_text(), None, enabled=False),
            MenuItem(
                "Runtime",
                Menu(
                    MenuItem("Start", self._on_start),
                    MenuItem("Stop", self._on_stop),
                    MenuItem("Open Logs", self._on_open_logs),
                    MenuItem("Save Learning Snapshot", self._on_save_learning),
                ),
            ),
            MenuItem(
                "Mode Override",
                Menu(
                    MenuItem("Auto (Config)", self._set_mode_auto, checked=self._is_mode_auto),
                    MenuItem("Safe", self._set_mode_safe, checked=self._is_mode_safe),
                    MenuItem("Balanced", self._set_mode_balanced, checked=self._is_mode_balanced),
                    MenuItem("Aggressive", self._set_mode_aggressive, checked=self._is_mode_aggressive),
                ),
            ),
            MenuItem(
                "Profile Override",
                Menu(
                    MenuItem("Auto", self._set_profile_auto, checked=self._is_profile_auto),
                    MenuItem("Default", self._set_profile_default, checked=self._is_profile_default),
                    MenuItem("Gaming", self._set_profile_gaming, checked=self._is_profile_gaming),
                    MenuItem("Streaming", self._set_profile_streaming, checked=self._is_profile_streaming),
                ),
            ),
            MenuItem("Exit", self._on_exit),
        )

    def _on_start(self, _icon: pystray.Icon, _item: MenuItem) -> None:
        self._controller.start()

    def _on_stop(self, _icon: pystray.Icon, _item: MenuItem) -> None:
        self._controller.stop()

    def _on_open_logs(self, icon: pystray.Icon, _item: MenuItem) -> None:
        try:
            subprocess.Popen(["notepad.exe", str(self._log_path)], close_fds=True)
        except OSError as exc:
            LOGGER.warning("Failed to open log file: %s", exc)
            icon.notify("Could not open logs", "Fixer")

    def _on_save_learning(self, icon: pystray.Icon, _item: MenuItem) -> None:
        output = self._controller.save_learning_snapshot()
        icon.notify(f"Learning snapshot: {output}", "Fixer")

    def _on_exit(self, icon: pystray.Icon, _item: MenuItem) -> None:
        LOGGER.info("Exiting tray UI")
        self._controller.stop()
        icon.stop()

    def _set_mode_auto(self, _icon: pystray.Icon, _item: MenuItem) -> None:
        self._controller.set_mode_override(None)

    def _set_mode_safe(self, _icon: pystray.Icon, _item: MenuItem) -> None:
        self._controller.set_mode_override("safe")

    def _set_mode_balanced(self, _icon: pystray.Icon, _item: MenuItem) -> None:
        self._controller.set_mode_override("balanced")

    def _set_mode_aggressive(self, _icon: pystray.Icon, _item: MenuItem) -> None:
        self._controller.set_mode_override("aggressive")

    def _set_profile_auto(self, _icon: pystray.Icon, _item: MenuItem) -> None:
        self._controller.set_profile_override(None)

    def _set_profile_default(self, _icon: pystray.Icon, _item: MenuItem) -> None:
        self._controller.set_profile_override("default")

    def _set_profile_gaming(self, _icon: pystray.Icon, _item: MenuItem) -> None:
        self._controller.set_profile_override("gaming")

    def _set_profile_streaming(self, _icon: pystray.Icon, _item: MenuItem) -> None:
        self._controller.set_profile_override("streaming")

    def _is_mode_auto(self, _item: MenuItem) -> bool:
        return self._controller.mode_override() is None

    def _is_mode_safe(self, _item: MenuItem) -> bool:
        return self._controller.mode_override() == "safe"

    def _is_mode_balanced(self, _item: MenuItem) -> bool:
        return self._controller.mode_override() == "balanced"

    def _is_mode_aggressive(self, _item: MenuItem) -> bool:
        return self._controller.mode_override() == "aggressive"

    def _is_profile_auto(self, _item: MenuItem) -> bool:
        return self._controller.profile_override() is None

    def _is_profile_default(self, _item: MenuItem) -> bool:
        return self._controller.profile_override() == "default"

    def _is_profile_gaming(self, _item: MenuItem) -> bool:
        return self._controller.profile_override() == "gaming"

    def _is_profile_streaming(self, _item: MenuItem) -> bool:
        return self._controller.profile_override() == "streaming"

    @staticmethod
    def _build_icon() -> Image.Image:
        image = Image.new("RGB", (64, 64), color=(28, 39, 58))
        draw = ImageDraw.Draw(image)
        draw.rectangle((8, 8, 56, 56), outline=(135, 214, 255), width=3)
        draw.line((18, 42, 30, 24), fill=(135, 214, 255), width=4)
        draw.line((30, 24, 46, 40), fill=(135, 214, 255), width=4)
        return image


def run_tray_app(config: AppConfig, dry_run: bool, learning_mode: bool) -> None:
    app = TrayApplication(config=config, dry_run=dry_run, learning_mode=learning_mode)
    app.run()
