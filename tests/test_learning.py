from __future__ import annotations

import json

from fixer.learning import LearningEngine
from fixer.models import AppConfig, ContextState, LearningConfig, ProfileConfig, SuspiciousConfig


class _FakeProcess:
    def __init__(self, name: str) -> None:
        self.info = {"name": name}


def _make_config(output_path: str, min_occurrences: int = 2) -> AppConfig:
    profiles = {
        "default": ProfileConfig(boost=[], throttle=[], close=[]),
        "gaming": ProfileConfig(boost=[], throttle=[], close=[]),
        "streaming": ProfileConfig(boost=[], throttle=[], close=[]),
    }

    return AppConfig(
        mode="safe",
        loop_interval_seconds=1.0,
        hog_cpu_percent=60.0,
        hog_observation_windows=2,
        game_processes=["game.exe"],
        streaming_processes=["obs64.exe"],
        profiles=profiles,
        suspicious=SuspiciousConfig(
            authorized_recorders=["obs64.exe"],
            recorder_indicators=["obs", "bandicam"],
            keylogger_indicators=["keylog"],
            miner_indicators=["xmrig"],
            always_terminate_names=["xmrig.exe"],
        ),
        protected_processes=["system"],
        resource_allowlist=["obs64.exe"],
        learning=LearningConfig(
            enabled=True,
            output_path=output_path,
            min_occurrences=min_occurrences,
            autosave_seconds=5.0,
        ),
        log_level="INFO",
    )


def test_learning_engine_suggests_allowlist_updates(tmp_path) -> None:
    output_path = tmp_path / "learning_suggestions.json"
    config = _make_config(str(output_path), min_occurrences=2)
    engine = LearningEngine(config)

    context_streaming = ContextState(
        profile_name="streaming",
        active_game="game.exe",
        streaming_active=True,
        foreground_process="discord.exe",
    )

    for _ in range(2):
        engine.observe_cycle([_FakeProcess("discord.exe")], context_streaming)
        engine.observe_hog("discord.exe")
        engine.observe_suspicion("discord.exe", "unauthorized_recorder")

    output = engine.save_now(config)
    payload = json.loads(output.read_text(encoding="utf-8"))

    targets = {(item["target"], item["value"]) for item in payload["suggestions"]}

    assert ("resource_allowlist", "discord.exe") in targets
    assert ("suspicious.authorized_recorders", "discord.exe") in targets


def test_learning_engine_suggests_game_process_from_foreground(tmp_path) -> None:
    output_path = tmp_path / "learning_suggestions.json"
    config = _make_config(str(output_path), min_occurrences=2)
    engine = LearningEngine(config)

    context_gaming = ContextState(
        profile_name="gaming",
        active_game=None,
        streaming_active=False,
        foreground_process="newgame.exe",
    )

    for _ in range(2):
        engine.observe_cycle([_FakeProcess("newgame.exe")], context_gaming)

    payload = json.loads(engine.save_now(config).read_text(encoding="utf-8"))
    targets = {(item["target"], item["value"]) for item in payload["suggestions"]}

    assert ("game_processes", "newgame.exe") in targets
