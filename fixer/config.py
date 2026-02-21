from __future__ import annotations

import json
from pathlib import Path

from fixer.models import AppConfig, LearningConfig, ProfileConfig, SuspiciousConfig
from fixer.utils import normalize_process_name

_ALLOWED_MODES = {"safe", "balanced", "aggressive"}
_REQUIRED_PROFILES = {"default", "gaming", "streaming"}


def _normalize_unique(names: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for raw in names:
        name = normalize_process_name(raw)
        if not name or name in seen:
            continue
        seen.add(name)
        output.append(name)
    return output


def _build_profile(raw: dict) -> ProfileConfig:
    return ProfileConfig(
        boost=_normalize_unique(raw.get("boost", [])),
        throttle=_normalize_unique(raw.get("throttle", [])),
        close=_normalize_unique(raw.get("close", [])),
    )


def load_config(path: str | Path) -> AppConfig:
    config_path = Path(path)
    payload = json.loads(config_path.read_text(encoding="utf-8"))

    mode = str(payload.get("mode", "safe")).strip().lower()
    if mode not in _ALLOWED_MODES:
        raise ValueError(f"Invalid mode: {mode}. Expected one of {_ALLOWED_MODES}")

    raw_profiles = payload.get("profiles", {})
    profiles: dict[str, ProfileConfig] = {
        normalize_process_name(name): _build_profile(raw)
        for name, raw in raw_profiles.items()
        if isinstance(raw, dict)
    }

    missing = _REQUIRED_PROFILES - set(profiles)
    if missing:
        raise ValueError(f"Missing required profiles: {sorted(missing)}")

    raw_suspicious = payload.get("suspicious", {})
    suspicious = SuspiciousConfig(
        authorized_recorders=_normalize_unique(raw_suspicious.get("authorized_recorders", [])),
        recorder_indicators=_normalize_unique(raw_suspicious.get("recorder_indicators", [])),
        keylogger_indicators=_normalize_unique(raw_suspicious.get("keylogger_indicators", [])),
        miner_indicators=_normalize_unique(raw_suspicious.get("miner_indicators", [])),
        always_terminate_names=_normalize_unique(raw_suspicious.get("always_terminate_names", [])),
    )

    raw_learning = payload.get("learning", {})
    learning_output = str(raw_learning.get("output_path", "data/learning_suggestions.json")).strip()
    if not learning_output:
        learning_output = "data/learning_suggestions.json"

    learning = LearningConfig(
        enabled=bool(raw_learning.get("enabled", False)),
        output_path=learning_output,
        min_occurrences=max(int(raw_learning.get("min_occurrences", 5)), 1),
        autosave_seconds=max(float(raw_learning.get("autosave_seconds", 30.0)), 5.0),
    )

    return AppConfig(
        mode=mode,
        loop_interval_seconds=float(payload.get("loop_interval_seconds", 2.0)),
        hog_cpu_percent=float(payload.get("hog_cpu_percent", 55.0)),
        hog_observation_windows=max(int(payload.get("hog_observation_windows", 3)), 1),
        game_processes=_normalize_unique(payload.get("game_processes", [])),
        streaming_processes=_normalize_unique(payload.get("streaming_processes", [])),
        profiles=profiles,
        suspicious=suspicious,
        protected_processes=_normalize_unique(payload.get("protected_processes", [])),
        resource_allowlist=_normalize_unique(payload.get("resource_allowlist", [])),
        learning=learning,
        log_level=str(payload.get("log_level", "INFO")).upper(),
    )
