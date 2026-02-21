from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import dataclass
from pathlib import Path

from fixer.agent import OptimizerAgent
from fixer.config import load_config
from fixer.learning import LearningEngine
from fixer.logging_setup import configure_logging
from fixer.models import Mode

LOGGER = logging.getLogger("fixer.service")

SERVICE_NAME = "FixerOptimizer"
SERVICE_DISPLAY_NAME = "Fixer Optimizer"
SERVICE_DESCRIPTION = "Context-aware process optimizer for gaming and streaming performance"


try:
    import servicemanager
    import win32event
    import win32service
    import win32serviceutil

    PYWIN32_AVAILABLE = True
except ImportError:  # pragma: no cover - platform dependency
    servicemanager = None
    win32event = None
    win32service = None
    win32serviceutil = None
    PYWIN32_AVAILABLE = False


@dataclass(frozen=True)
class ServiceSettings:
    config_path: str
    dry_run: bool
    learning_mode: bool
    mode_override: Mode | None


def _program_data_root() -> Path:
    program_data = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData"))
    return program_data / "Fixer"


def service_settings_path() -> Path:
    return _program_data_root() / "service_settings.json"


def service_log_path() -> Path:
    return _program_data_root() / "service.log"


def _ensure_pywin32() -> None:
    if PYWIN32_AVAILABLE:
        return
    raise RuntimeError("pywin32 is required for service commands. Install it with: pip install pywin32")


def _write_service_settings(settings: ServiceSettings) -> Path:
    output_path = service_settings_path()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "config_path": str(Path(settings.config_path).resolve()),
        "dry_run": settings.dry_run,
        "learning_mode": settings.learning_mode,
        "mode_override": settings.mode_override,
    }
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return output_path


def _read_service_settings() -> ServiceSettings:
    path = service_settings_path()
    if not path.exists():
        raise FileNotFoundError(f"Service settings not found at {path}")

    payload = json.loads(path.read_text(encoding="utf-8"))
    mode_override = payload.get("mode_override")

    return ServiceSettings(
        config_path=str(payload.get("config_path", "config/default.json")),
        dry_run=bool(payload.get("dry_run", False)),
        learning_mode=bool(payload.get("learning_mode", False)),
        mode_override=mode_override if mode_override in {"safe", "balanced", "aggressive"} else None,
    )


def _service_installed() -> bool:
    _ensure_pywin32()
    try:
        win32serviceutil.QueryServiceStatus(SERVICE_NAME)
        return True
    except Exception:
        return False


def install_service(
    config_path: str,
    dry_run: bool,
    learning_mode: bool,
    mode_override: Mode | None,
    auto_start: bool,
) -> str:
    _ensure_pywin32()

    settings = ServiceSettings(
        config_path=config_path,
        dry_run=dry_run,
        learning_mode=learning_mode,
        mode_override=mode_override,
    )
    settings_file = _write_service_settings(settings)

    python_class = "fixer.service.FixerWindowsService"
    start_type = win32service.SERVICE_AUTO_START if auto_start else win32service.SERVICE_DEMAND_START

    if _service_installed():
        win32serviceutil.ChangeServiceConfig(
            pythonClassString=python_class,
            serviceName=SERVICE_NAME,
            startType=start_type,
            displayName=SERVICE_DISPLAY_NAME,
            description=SERVICE_DESCRIPTION,
        )
        return f"updated ({settings_file})"

    win32serviceutil.InstallService(
        pythonClassString=python_class,
        serviceName=SERVICE_NAME,
        displayName=SERVICE_DISPLAY_NAME,
        startType=start_type,
        description=SERVICE_DESCRIPTION,
    )
    return f"installed ({settings_file})"


def remove_service() -> str:
    _ensure_pywin32()
    if not _service_installed():
        return "not_installed"

    try:
        win32serviceutil.StopService(SERVICE_NAME)
    except Exception:
        pass

    win32serviceutil.RemoveService(SERVICE_NAME)
    return "removed"


def start_service() -> str:
    _ensure_pywin32()
    win32serviceutil.StartService(SERVICE_NAME)
    return "started"


def stop_service() -> str:
    _ensure_pywin32()
    win32serviceutil.StopService(SERVICE_NAME)
    return "stopped"


def restart_service() -> str:
    _ensure_pywin32()
    win32serviceutil.RestartService(SERVICE_NAME)
    return "restarted"


def service_status() -> str:
    _ensure_pywin32()
    try:
        status = win32serviceutil.QueryServiceStatus(SERVICE_NAME)[1]
    except Exception:
        return "not_installed"

    mapping = {
        win32service.SERVICE_STOPPED: "stopped",
        win32service.SERVICE_START_PENDING: "start_pending",
        win32service.SERVICE_STOP_PENDING: "stop_pending",
        win32service.SERVICE_RUNNING: "running",
        win32service.SERVICE_CONTINUE_PENDING: "continue_pending",
        win32service.SERVICE_PAUSE_PENDING: "pause_pending",
        win32service.SERVICE_PAUSED: "paused",
    }
    return mapping.get(status, f"unknown({status})")


if PYWIN32_AVAILABLE:  # pragma: no branch

    class FixerWindowsService(win32serviceutil.ServiceFramework):
        _svc_name_ = SERVICE_NAME
        _svc_display_name_ = SERVICE_DISPLAY_NAME
        _svc_description_ = SERVICE_DESCRIPTION

        def __init__(self, args: list[str]) -> None:
            super().__init__(args)
            self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
            self._agent: OptimizerAgent | None = None
            self._thread: threading.Thread | None = None

        def SvcStop(self) -> None:  # noqa: N802 (pywin32 naming)
            self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
            if self._agent:
                self._agent.stop()
            win32event.SetEvent(self.hWaitStop)

        def SvcDoRun(self) -> None:  # noqa: N802 (pywin32 naming)
            settings = _read_service_settings()
            config = load_config(settings.config_path)
            if settings.mode_override:
                from dataclasses import replace

                config = replace(config, mode=settings.mode_override)

            _configure_service_logging(config.log_level)

            learning = LearningEngine(config) if settings.learning_mode else None
            self._agent = OptimizerAgent(
                config=config,
                dry_run=settings.dry_run,
                once=False,
                learning_engine=learning,
            )

            servicemanager.LogInfoMsg("Fixer service starting optimizer loop")
            self._thread = threading.Thread(target=self._agent.run, name="fixer-service-agent", daemon=True)
            self._thread.start()

            while True:
                wait_result = win32event.WaitForSingleObject(self.hWaitStop, 1000)
                if wait_result == win32event.WAIT_OBJECT_0:
                    break
                if self._thread and not self._thread.is_alive():
                    break

            if self._agent:
                self._agent.stop()
            if self._thread:
                self._thread.join(timeout=10)

            servicemanager.LogInfoMsg("Fixer service stopped")


def _configure_service_logging(level: str) -> None:
    configure_logging(level)
    service_log_path().parent.mkdir(parents=True, exist_ok=True)

    file_handler = logging.FileHandler(service_log_path(), encoding="utf-8")
    file_handler.setLevel(getattr(logging, level.upper(), logging.INFO))
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s - %(message)s"))
    logging.getLogger().addHandler(file_handler)
