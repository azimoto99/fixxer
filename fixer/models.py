from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Mode = Literal["safe", "balanced", "aggressive"]
ProfileName = Literal["default", "gaming", "streaming"]


@dataclass(frozen=True)
class ProfileConfig:
    boost: list[str]
    throttle: list[str]
    close: list[str]


@dataclass(frozen=True)
class SuspiciousConfig:
    authorized_recorders: list[str]
    recorder_indicators: list[str]
    keylogger_indicators: list[str]
    miner_indicators: list[str]
    always_terminate_names: list[str]


@dataclass(frozen=True)
class LearningConfig:
    enabled: bool
    output_path: str
    min_occurrences: int
    autosave_seconds: float


@dataclass(frozen=True)
class AppConfig:
    mode: Mode
    loop_interval_seconds: float
    hog_cpu_percent: float
    hog_observation_windows: int
    game_processes: list[str]
    streaming_processes: list[str]
    profiles: dict[str, ProfileConfig]
    suspicious: SuspiciousConfig
    protected_processes: list[str]
    resource_allowlist: list[str]
    learning: LearningConfig
    log_level: str


@dataclass(frozen=True)
class ContextState:
    profile_name: str
    active_game: str | None
    streaming_active: bool
    foreground_process: str | None


@dataclass(frozen=True)
class Suspicion:
    kind: str
    reason: str


@dataclass(frozen=True)
class AgentStatus:
    running: bool
    effective_mode: Mode
    profile_override: str | None
    current_profile: str | None
    active_game: str | None
    streaming_active: bool
    foreground_process: str | None
