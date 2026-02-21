from __future__ import annotations

import json

from fixer.config import load_config


def test_load_config_includes_learning_defaults(tmp_path) -> None:
    payload = {
        "mode": "safe",
        "profiles": {
            "default": {"boost": [], "throttle": [], "close": []},
            "gaming": {"boost": [], "throttle": [], "close": []},
            "streaming": {"boost": [], "throttle": [], "close": []},
        },
        "suspicious": {
            "authorized_recorders": [],
            "recorder_indicators": [],
            "keylogger_indicators": [],
            "miner_indicators": [],
            "always_terminate_names": [],
        },
    }
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(payload), encoding="utf-8")

    config = load_config(config_path)

    assert config.learning.enabled is False
    assert config.learning.output_path == "data/learning_suggestions.json"
    assert config.learning.min_occurrences == 5
    assert config.learning.autosave_seconds == 30.0


def test_load_config_reads_learning_section(tmp_path) -> None:
    payload = {
        "mode": "safe",
        "profiles": {
            "default": {"boost": [], "throttle": [], "close": []},
            "gaming": {"boost": [], "throttle": [], "close": []},
            "streaming": {"boost": [], "throttle": [], "close": []},
        },
        "suspicious": {
            "authorized_recorders": [],
            "recorder_indicators": [],
            "keylogger_indicators": [],
            "miner_indicators": [],
            "always_terminate_names": [],
        },
        "learning": {
            "enabled": True,
            "output_path": "tmp/learn.json",
            "min_occurrences": 7,
            "autosave_seconds": 12.5,
        },
    }
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(payload), encoding="utf-8")

    config = load_config(config_path)

    assert config.learning.enabled is True
    assert config.learning.output_path == "tmp/learn.json"
    assert config.learning.min_occurrences == 7
    assert config.learning.autosave_seconds == 12.5
