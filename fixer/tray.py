from __future__ import annotations

import logging
import os
import queue
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


def _open_in_notepad(path: Path) -> OSError | None:
    try:
        subprocess.Popen(["notepad.exe", str(path)], close_fds=True)
        return None
    except OSError as exc:
        return exc


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


class ControlPanelWindow:
    def __init__(self, controller: AgentController, log_path: Path) -> None:
        self._controller = controller
        self._log_path = log_path
        self._commands: queue.Queue[str] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def show(self) -> None:
        with self._lock:
            if not self._thread or not self._thread.is_alive():
                self._thread = threading.Thread(
                    target=self._run_loop,
                    name="fixer-control-panel",
                    daemon=True,
                )
                self._thread.start()

        self._commands.put("show")

    def shutdown(self) -> None:
        with self._lock:
            thread = self._thread

        if not thread or not thread.is_alive():
            return

        self._commands.put("quit")
        thread.join(timeout=3)

        with self._lock:
            if self._thread is thread and not thread.is_alive():
                self._thread = None

    def _run_loop(self) -> None:
        try:
            import tkinter as tk
            from tkinter import ttk
        except ImportError:
            LOGGER.exception("Control panel unavailable because tkinter could not be imported")
            return

        root = tk.Tk()
        root.title("Fixer Control Panel")
        root.geometry("520x390")
        root.minsize(460, 330)
        root.withdraw()

        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)

        container = ttk.Frame(root, padding=12)
        container.grid(row=0, column=0, sticky="nsew")
        container.columnconfigure(0, weight=1)
        container.rowconfigure(2, weight=1)

        status_value = tk.StringVar(value=self._controller.status_text())
        mode_value = tk.StringVar(value=self._controller.mode_override() or "auto")
        profile_value = tk.StringVar(value=self._controller.profile_override() or "auto")
        action_value = tk.StringVar(value="Ready")

        ttk.Label(container, text="Status", font=("", 10, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(
            container,
            textvariable=status_value,
            wraplength=470,
            justify="left",
        ).grid(row=1, column=0, sticky="ew", pady=(4, 10))

        runtime_bar = ttk.Frame(container)
        runtime_bar.grid(row=2, column=0, sticky="ew")
        runtime_bar.columnconfigure(0, weight=1)
        runtime_bar.columnconfigure(1, weight=1)
        runtime_bar.columnconfigure(2, weight=1)

        overrides = ttk.Frame(container)
        overrides.grid(row=3, column=0, sticky="nsew", pady=(10, 0))
        overrides.columnconfigure(0, weight=1)
        overrides.columnconfigure(1, weight=1)

        mode_frame = ttk.LabelFrame(overrides, text="Mode Override", padding=10)
        mode_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        profile_frame = ttk.LabelFrame(overrides, text="Profile Override", padding=10)
        profile_frame.grid(row=0, column=1, sticky="nsew", padx=(6, 0))

        utility_bar = ttk.Frame(container)
        utility_bar.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        utility_bar.columnconfigure(0, weight=1)
        utility_bar.columnconfigure(1, weight=1)
        utility_bar.columnconfigure(2, weight=1)

        ttk.Label(container, textvariable=action_value, wraplength=470, justify="left").grid(
            row=5,
            column=0,
            sticky="ew",
            pady=(10, 0),
        )

        def _refresh_bindings() -> None:
            mode_selected = self._controller.mode_override() or "auto"
            if mode_value.get() != mode_selected:
                mode_value.set(mode_selected)

            profile_selected = self._controller.profile_override() or "auto"
            if profile_value.get() != profile_selected:
                profile_value.set(profile_selected)

        def _apply_mode() -> None:
            selected = mode_value.get()
            if selected == "auto":
                self._controller.set_mode_override(None)
                action_value.set("Mode override set to auto")
                return

            if selected in {"safe", "balanced", "aggressive"}:
                self._controller.set_mode_override(selected)
                action_value.set(f"Mode override set to {selected}")

        def _apply_profile() -> None:
            selected = profile_value.get()
            if selected == "auto":
                self._controller.set_profile_override(None)
                action_value.set("Profile override set to auto")
                return

            try:
                self._controller.set_profile_override(selected)
                action_value.set(f"Profile override set to {selected}")
            except ValueError as exc:
                LOGGER.warning("Profile override rejected: %s", exc)
                action_value.set(str(exc))
                _refresh_bindings()

        def _start_runtime() -> None:
            self._controller.start()
            action_value.set("Runtime started")

        def _stop_runtime() -> None:
            self._controller.stop()
            action_value.set("Runtime stopped")

        def _open_logs() -> None:
            error = _open_in_notepad(self._log_path)
            if error:
                LOGGER.warning("Failed to open log file: %s", error)
                action_value.set("Could not open logs")
            else:
                action_value.set(f"Opened logs: {self._log_path}")

        def _save_learning() -> None:
            output = self._controller.save_learning_snapshot()
            action_value.set(f"Learning snapshot: {output}")

        def _hide_window() -> None:
            root.withdraw()

        def _refresh_status() -> None:
            status_value.set(self._controller.status_text())
            _refresh_bindings()
            root.after(1000, _refresh_status)

        def _process_commands() -> None:
            while True:
                try:
                    command = self._commands.get_nowait()
                except queue.Empty:
                    break

                if command == "show":
                    root.deiconify()
                    root.lift()
                    try:
                        root.focus_force()
                    except tk.TclError:
                        pass
                    continue

                if command == "quit":
                    root.destroy()
                    return

            root.after(200, _process_commands)

        ttk.Button(runtime_bar, text="Start", command=_start_runtime).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ttk.Button(runtime_bar, text="Stop", command=_stop_runtime).grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(runtime_bar, text="Hide", command=_hide_window).grid(row=0, column=2, sticky="ew", padx=(6, 0))

        ttk.Radiobutton(mode_frame, text="Auto", value="auto", variable=mode_value, command=_apply_mode).grid(
            row=0,
            column=0,
            sticky="w",
        )
        ttk.Radiobutton(mode_frame, text="Safe", value="safe", variable=mode_value, command=_apply_mode).grid(
            row=1,
            column=0,
            sticky="w",
        )
        ttk.Radiobutton(
            mode_frame,
            text="Balanced",
            value="balanced",
            variable=mode_value,
            command=_apply_mode,
        ).grid(row=2, column=0, sticky="w")
        ttk.Radiobutton(
            mode_frame,
            text="Aggressive",
            value="aggressive",
            variable=mode_value,
            command=_apply_mode,
        ).grid(row=3, column=0, sticky="w")

        ttk.Radiobutton(
            profile_frame,
            text="Auto",
            value="auto",
            variable=profile_value,
            command=_apply_profile,
        ).grid(row=0, column=0, sticky="w")
        ttk.Radiobutton(
            profile_frame,
            text="Default",
            value="default",
            variable=profile_value,
            command=_apply_profile,
        ).grid(row=1, column=0, sticky="w")
        ttk.Radiobutton(
            profile_frame,
            text="Gaming",
            value="gaming",
            variable=profile_value,
            command=_apply_profile,
        ).grid(row=2, column=0, sticky="w")
        ttk.Radiobutton(
            profile_frame,
            text="Streaming",
            value="streaming",
            variable=profile_value,
            command=_apply_profile,
        ).grid(row=3, column=0, sticky="w")

        ttk.Button(utility_bar, text="Open Logs", command=_open_logs).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ttk.Button(utility_bar, text="Save Learning Snapshot", command=_save_learning).grid(
            row=0,
            column=1,
            sticky="ew",
            padx=6,
        )
        ttk.Button(utility_bar, text="Refresh Status", command=lambda: status_value.set(self._controller.status_text())).grid(
            row=0,
            column=2,
            sticky="ew",
            padx=(6, 0),
        )

        root.protocol("WM_DELETE_WINDOW", _hide_window)

        _refresh_bindings()
        _refresh_status()
        _process_commands()

        try:
            root.mainloop()
        finally:
            current = threading.current_thread()
            with self._lock:
                if self._thread is current:
                    self._thread = None


class TrayApplication:
    def __init__(self, config: AppConfig, dry_run: bool, learning_mode: bool) -> None:
        self._controller = AgentController(config, dry_run=dry_run, learning_mode=learning_mode)
        self._log_path = _tray_log_path()
        self._configure_file_logging(config.log_level)
        self._control_panel = ControlPanelWindow(controller=self._controller, log_path=self._log_path)

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
            MenuItem("Open Control Panel", self._on_open_control_panel),
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

    def _on_open_control_panel(self, _icon: pystray.Icon, _item: MenuItem) -> None:
        self._control_panel.show()

    def _on_open_logs(self, icon: pystray.Icon, _item: MenuItem) -> None:
        error = _open_in_notepad(self._log_path)
        if error:
            LOGGER.warning("Failed to open log file: %s", error)
            icon.notify("Could not open logs", "Fixer")

    def _on_save_learning(self, icon: pystray.Icon, _item: MenuItem) -> None:
        output = self._controller.save_learning_snapshot()
        icon.notify(f"Learning snapshot: {output}", "Fixer")

    def _on_exit(self, icon: pystray.Icon, _item: MenuItem) -> None:
        LOGGER.info("Exiting tray UI")
        self._control_panel.shutdown()
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
