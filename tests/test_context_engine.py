from __future__ import annotations

from fixer.context_engine import ContextEngine
from fixer.models import AppConfig, LearningConfig, ProfileConfig, SuspiciousConfig


def _make_config() -> AppConfig:
    profiles = {
        "default": ProfileConfig(boost=[], throttle=[], close=[]),
        "gaming": ProfileConfig(boost=["{active_game}"], throttle=[], close=[]),
        "streaming": ProfileConfig(boost=[], throttle=[], close=[]),
    }
    suspicious = SuspiciousConfig(
        authorized_recorders=["obs64.exe"],
        recorder_indicators=["obs", "screenrec"],
        keylogger_indicators=["keylog"],
        miner_indicators=["xmrig"],
        always_terminate_names=["xmrig.exe"],
    )
    return AppConfig(
        mode="safe",
        loop_interval_seconds=1.0,
        hog_cpu_percent=50.0,
        hog_observation_windows=2,
        game_processes=["game.exe"],
        streaming_processes=["obs64.exe"],
        profiles=profiles,
        suspicious=suspicious,
        protected_processes=["system"],
        resource_allowlist=[],
        learning=LearningConfig(
            enabled=False,
            output_path="data/learning_suggestions.json",
            min_occurrences=3,
            autosave_seconds=30.0,
        ),
        log_level="INFO",
    )


def test_streaming_profile_selected_when_game_and_stream_running() -> None:
    engine = ContextEngine(_make_config())
    state = engine.detect({"game.exe", "obs64.exe"}, foreground_process="game.exe")

    assert state.profile_name == "streaming"
    assert state.active_game == "game.exe"
    assert state.streaming_active is True


def test_gaming_profile_selected_when_only_game_running() -> None:
    engine = ContextEngine(_make_config())
    state = engine.detect({"game.exe"}, foreground_process="game.exe")

    assert state.profile_name == "gaming"
    assert state.active_game == "game.exe"
    assert state.streaming_active is False


def test_default_profile_selected_without_game() -> None:
    engine = ContextEngine(_make_config())
    state = engine.detect({"chrome.exe"}, foreground_process="chrome.exe")

    assert state.profile_name == "default"
    assert state.active_game is None
