from __future__ import annotations

import logging
import os
import threading
import time
from collections import defaultdict
from typing import TYPE_CHECKING

import psutil

from fixer.context_engine import ContextEngine
from fixer.models import AgentStatus, AppConfig, ContextState, Mode, Suspicion
from fixer.policy import ProcessClassifier
from fixer.utils import normalize_process_name
from fixer.windows_focus import get_foreground_process_name

if TYPE_CHECKING:
    from pathlib import Path

    from fixer.learning import LearningEngine

LOGGER = logging.getLogger("fixer.agent")

_WINDOWS_PRIORITY = {
    "idle": getattr(psutil, "IDLE_PRIORITY_CLASS", 64),
    "below_normal": getattr(psutil, "BELOW_NORMAL_PRIORITY_CLASS", 16384),
    "normal": getattr(psutil, "NORMAL_PRIORITY_CLASS", 32),
    "above_normal": getattr(psutil, "ABOVE_NORMAL_PRIORITY_CLASS", 32768),
    "high": getattr(psutil, "HIGH_PRIORITY_CLASS", 128),
}

_POSIX_PRIORITY = {
    "idle": 19,
    "below_normal": 10,
    "normal": 0,
    "above_normal": -5,
    "high": -10,
}


class OptimizerAgent:
    def __init__(
        self,
        config: AppConfig,
        dry_run: bool = True,
        once: bool = False,
        learning_engine: LearningEngine | None = None,
    ) -> None:
        self._config = config
        self._dry_run = dry_run
        self._once = once
        self._learning_engine = learning_engine

        self._classifier = ProcessClassifier(config)
        self._context_engine = ContextEngine(config)

        self._hog_windows: dict[int, int] = defaultdict(int)
        self._priority_cache: dict[int, int] = {}
        self._seen_suspicion: set[tuple[int, str]] = set()
        self._last_context_signature: tuple[str, str | None, bool, str | None] | None = None

        self._stop_event = threading.Event()
        self._state_lock = threading.Lock()
        self._is_running = False
        self._mode_override: Mode | None = None
        self._profile_override: str | None = None
        self._latest_context: ContextState | None = None

    def run(self) -> None:
        with self._state_lock:
            if self._is_running:
                LOGGER.warning("Optimizer is already running")
                return
            self._is_running = True
            self._stop_event.clear()

        LOGGER.info(
            "Starting Fixer mode=%s dry_run=%s learning=%s",
            self._effective_mode(),
            self._dry_run,
            self._learning_engine is not None,
        )

        self._prime_cpu_counters()

        try:
            while not self._stop_event.is_set():
                self._run_cycle()

                if self._once:
                    break

                if self._stop_event.wait(self._config.loop_interval_seconds):
                    break
        except KeyboardInterrupt:
            LOGGER.info("Received interrupt, stopping optimizer")
        finally:
            if self._learning_engine:
                output = self.save_learning_snapshot()
                if output:
                    LOGGER.info("Learning suggestions written to %s", output)

            with self._state_lock:
                self._is_running = False

    def stop(self) -> None:
        self._stop_event.set()

    def set_mode_override(self, mode: Mode | None) -> None:
        with self._state_lock:
            self._mode_override = mode

        if mode is None:
            LOGGER.info("Cleared mode override, using config mode=%s", self._config.mode)
        else:
            LOGGER.info("Set mode override=%s", mode)

    def set_profile_override(self, profile: str | None) -> None:
        normalized = normalize_process_name(profile)
        if normalized and normalized not in self._config.profiles:
            raise ValueError(f"Unknown profile override: {profile}")

        with self._state_lock:
            self._profile_override = normalized or None

        if normalized:
            LOGGER.info("Set profile override=%s", normalized)
        else:
            LOGGER.info("Cleared profile override, using automatic context detection")

    def status(self) -> AgentStatus:
        with self._state_lock:
            context = self._latest_context
            return AgentStatus(
                running=self._is_running and not self._stop_event.is_set(),
                effective_mode=self._effective_mode_unlocked(),
                profile_override=self._profile_override,
                current_profile=context.profile_name if context else None,
                active_game=context.active_game if context else None,
                streaming_active=context.streaming_active if context else False,
                foreground_process=context.foreground_process if context else None,
            )

    def save_learning_snapshot(self) -> Path | None:
        if not self._learning_engine:
            return None

        try:
            return self._learning_engine.save_now(self._config)
        except OSError as exc:
            LOGGER.warning("Failed to persist learning suggestions: %s", exc)
            return None

    def _run_cycle(self) -> None:
        try:
            processes = self._iter_processes()
            running_names = {
                normalize_process_name(proc.info.get("name"))
                for proc in processes
                if proc.info.get("name")
            }
            foreground = get_foreground_process_name()
            context = self._context_engine.detect(running_names, foreground)
            context = self._apply_profile_override(context)

            with self._state_lock:
                self._latest_context = context

            self._log_context(context)

            if self._learning_engine:
                self._learning_engine.observe_cycle(processes, context)

            self._apply_profile_actions(processes, context)
            self._handle_resource_hogs(processes, context)
            self._handle_suspicious(processes)
            self._cleanup_state(processes)

            if self._learning_engine:
                output = self._learning_engine.save_if_due(self._config)
                if output:
                    LOGGER.info("Learning suggestions updated at %s", output)

        except Exception:
            LOGGER.exception("Unhandled error during optimizer cycle")

    def _apply_profile_override(self, context: ContextState) -> ContextState:
        with self._state_lock:
            override = self._profile_override

        if not override:
            return context

        return ContextState(
            profile_name=override,
            active_game=context.active_game,
            streaming_active=context.streaming_active,
            foreground_process=context.foreground_process,
        )

    def _effective_mode(self) -> Mode:
        with self._state_lock:
            return self._effective_mode_unlocked()

    def _effective_mode_unlocked(self) -> Mode:
        return self._mode_override or self._config.mode

    def _log_context(self, context: ContextState) -> None:
        signature = (
            context.profile_name,
            context.active_game,
            context.streaming_active,
            context.foreground_process,
        )
        if signature == self._last_context_signature:
            return

        self._last_context_signature = signature
        LOGGER.info(
            "Context profile=%s active_game=%s streaming=%s foreground=%s",
            context.profile_name,
            context.active_game,
            context.streaming_active,
            context.foreground_process,
        )

    def _iter_processes(self) -> list[psutil.Process]:
        return list(psutil.process_iter(["pid", "name", "cpu_percent", "cmdline"]))

    def _prime_cpu_counters(self) -> None:
        for proc in psutil.process_iter(["pid"]):
            try:
                proc.cpu_percent(None)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue

    def _apply_profile_actions(self, processes: list[psutil.Process], context: ContextState) -> None:
        profile = self._config.profiles[context.profile_name]

        boost_targets = self._resolve_targets(profile.boost, context)
        throttle_targets = self._resolve_targets(profile.throttle, context)
        close_targets = self._resolve_targets(profile.close, context)

        by_name = self._index_by_name(processes)
        boost_priority = "high" if context.profile_name in {"gaming", "streaming"} else "above_normal"

        mode = self._effective_mode()

        for target in boost_targets:
            for proc in by_name.get(target, []):
                self._set_priority(proc, boost_priority, reason=f"{context.profile_name} boost")

        for target in throttle_targets:
            for proc in by_name.get(target, []):
                self._set_priority(proc, "below_normal", reason=f"{context.profile_name} throttle")

        for target in close_targets:
            for proc in by_name.get(target, []):
                if mode == "safe":
                    LOGGER.info(
                        "[dry-policy] would close process pid=%s name=%s (profile close target)",
                        proc.pid,
                        normalize_process_name(proc.info.get("name")),
                    )
                else:
                    self._terminate_process(proc, reason=f"{context.profile_name} close target")

    def _handle_resource_hogs(self, processes: list[psutil.Process], context: ContextState) -> None:
        exempt = set(self._config.resource_allowlist)
        exempt.update(self._config.streaming_processes)
        if context.active_game:
            exempt.add(context.active_game)

        live_pids = {proc.pid for proc in processes}
        mode = self._effective_mode()

        for proc in processes:
            name = normalize_process_name(proc.info.get("name"))
            if not name:
                continue
            if name in exempt or self._is_protected(name):
                continue

            cpu = self._read_cpu_percent(proc)
            if cpu < self._config.hog_cpu_percent:
                self._hog_windows.pop(proc.pid, None)
                continue

            self._hog_windows[proc.pid] += 1
            if self._hog_windows[proc.pid] < self._config.hog_observation_windows:
                continue

            LOGGER.warning(
                "Resource hog detected pid=%s name=%s cpu=%.2f",
                proc.pid,
                name,
                cpu,
            )

            if self._learning_engine:
                self._learning_engine.observe_hog(name)

            if mode == "safe":
                LOGGER.info("[dry-policy] keeping process pid=%s name=%s (safe mode)", proc.pid, name)
            elif mode == "balanced":
                self._set_priority(proc, "idle", reason="resource hog")
            else:
                self._terminate_process(proc, reason="resource hog")

            self._hog_windows[proc.pid] = 0

        stale = set(self._hog_windows) - live_pids
        for pid in stale:
            self._hog_windows.pop(pid, None)

    def _handle_suspicious(self, processes: list[psutil.Process]) -> None:
        for proc in processes:
            name = normalize_process_name(proc.info.get("name"))
            if not name or self._is_protected(name):
                continue

            cmdline = self._format_cmdline(proc.info.get("cmdline"))
            findings = self._classifier.classify(name, cmdline)
            if not findings:
                continue

            for finding in findings:
                event_key = (proc.pid, finding.kind)
                if event_key not in self._seen_suspicion:
                    LOGGER.warning(
                        "Suspicious process pid=%s name=%s kind=%s reason=%s",
                        proc.pid,
                        name,
                        finding.kind,
                        finding.reason,
                    )
                    self._seen_suspicion.add(event_key)

                if self._learning_engine:
                    self._learning_engine.observe_suspicion(name, finding.kind)

                self._take_suspicion_action(proc, name, finding)

    def _take_suspicion_action(self, proc: psutil.Process, name: str, finding: Suspicion) -> None:
        mode = self._effective_mode()

        if mode == "safe":
            LOGGER.info("[dry-policy] no enforcement for pid=%s name=%s kind=%s", proc.pid, name, finding.kind)
            return

        if finding.kind == "possible_miner":
            if mode == "aggressive" or name in self._config.suspicious.always_terminate_names:
                self._terminate_process(proc, reason=finding.kind)
            else:
                self._set_priority(proc, "idle", reason=finding.kind)
            return

        if finding.kind == "unauthorized_recorder":
            if mode == "aggressive":
                self._terminate_process(proc, reason=finding.kind)
            else:
                self._set_priority(proc, "below_normal", reason=finding.kind)
            return

        if finding.kind == "possible_keylogger":
            if mode == "aggressive":
                self._terminate_process(proc, reason=finding.kind)
            else:
                self._set_priority(proc, "idle", reason=finding.kind)

    def _index_by_name(self, processes: list[psutil.Process]) -> dict[str, list[psutil.Process]]:
        indexed: dict[str, list[psutil.Process]] = {}
        for proc in processes:
            name = normalize_process_name(proc.info.get("name"))
            if not name:
                continue
            indexed.setdefault(name, []).append(proc)
        return indexed

    def _resolve_targets(self, targets: list[str], context: ContextState) -> list[str]:
        resolved: list[str] = []
        for target in targets:
            if target == "{active_game}":
                if context.active_game:
                    resolved.append(context.active_game)
                continue
            resolved.append(target)
        return resolved

    def _set_priority(self, proc: psutil.Process, level: str, reason: str) -> None:
        name = normalize_process_name(proc.info.get("name"))
        if not name or self._is_protected(name) or proc.pid == os.getpid():
            return

        priority = self._priority_for_level(level)
        if self._priority_cache.get(proc.pid) == priority:
            return

        if self._dry_run:
            LOGGER.info(
                "[dry-run] set priority pid=%s name=%s level=%s reason=%s",
                proc.pid,
                name,
                level,
                reason,
            )
            self._priority_cache[proc.pid] = priority
            return

        try:
            current = proc.nice()
            if current != priority:
                proc.nice(priority)
                LOGGER.info(
                    "Set priority pid=%s name=%s level=%s reason=%s",
                    proc.pid,
                    name,
                    level,
                    reason,
                )
            self._priority_cache[proc.pid] = priority
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess) as exc:
            LOGGER.debug("Priority update failed pid=%s name=%s error=%s", proc.pid, name, exc)

    def _terminate_process(self, proc: psutil.Process, reason: str) -> None:
        name = normalize_process_name(proc.info.get("name"))
        if not name or self._is_protected(name) or proc.pid == os.getpid():
            return

        if self._dry_run:
            LOGGER.info("[dry-run] terminate pid=%s name=%s reason=%s", proc.pid, name, reason)
            return

        try:
            proc.terminate()
            proc.wait(timeout=3)
            LOGGER.warning("Terminated pid=%s name=%s reason=%s", proc.pid, name, reason)
            self._priority_cache.pop(proc.pid, None)
        except psutil.TimeoutExpired:
            try:
                proc.kill()
                LOGGER.warning("Killed pid=%s name=%s reason=%s", proc.pid, name, reason)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess) as exc:
                LOGGER.debug("Kill failed pid=%s name=%s error=%s", proc.pid, name, exc)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess) as exc:
            LOGGER.debug("Terminate failed pid=%s name=%s error=%s", proc.pid, name, exc)

    def _cleanup_state(self, processes: list[psutil.Process]) -> None:
        active_pids = {proc.pid for proc in processes}

        for pid in list(self._priority_cache):
            if pid not in active_pids:
                self._priority_cache.pop(pid, None)

        self._seen_suspicion = {
            (pid, kind)
            for pid, kind in self._seen_suspicion
            if pid in active_pids
        }

    def _priority_for_level(self, level: str) -> int:
        if os.name == "nt":
            return _WINDOWS_PRIORITY[level]
        return _POSIX_PRIORITY[level]

    def _is_protected(self, name: str) -> bool:
        return name in self._config.protected_processes

    @staticmethod
    def _format_cmdline(value: object) -> str:
        if isinstance(value, list):
            return " ".join(str(item) for item in value)
        if value is None:
            return ""
        return str(value)

    @staticmethod
    def _read_cpu_percent(proc: psutil.Process) -> float:
        raw = proc.info.get("cpu_percent")
        if isinstance(raw, (int, float)):
            return float(raw)

        try:
            return float(proc.cpu_percent(None))
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            return 0.0
