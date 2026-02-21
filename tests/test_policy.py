from __future__ import annotations

from fixer.models import AppConfig, LearningConfig, ProfileConfig, SuspiciousConfig
from fixer.policy import ProcessClassifier


def _make_classifier() -> ProcessClassifier:
    profiles = {
        "default": ProfileConfig(boost=[], throttle=[], close=[]),
        "gaming": ProfileConfig(boost=[], throttle=[], close=[]),
        "streaming": ProfileConfig(boost=[], throttle=[], close=[]),
    }
    config = AppConfig(
        mode="safe",
        loop_interval_seconds=1.0,
        hog_cpu_percent=50.0,
        hog_observation_windows=2,
        game_processes=[],
        streaming_processes=[],
        profiles=profiles,
        suspicious=SuspiciousConfig(
            authorized_recorders=["obs64.exe"],
            recorder_indicators=["obs", "screenrec", "bandicam"],
            keylogger_indicators=["keylog", "keystroke"],
            miner_indicators=["xmrig", "ethminer", "nicehash", "miner", "cryptonight"],
            always_terminate_names=["xmrig.exe"],
        ),
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
    return ProcessClassifier(config)


def test_authorized_recorder_is_not_flagged() -> None:
    classifier = _make_classifier()
    findings = classifier.classify("obs64.exe", "obs64.exe --profile main")

    assert not any(item.kind == "unauthorized_recorder" for item in findings)


def test_unauthorized_recorder_is_flagged() -> None:
    classifier = _make_classifier()
    findings = classifier.classify("bandicam.exe", "bandicam.exe")

    assert any(item.kind == "unauthorized_recorder" for item in findings)


def test_miner_indicator_in_cmdline_is_flagged() -> None:
    classifier = _make_classifier()
    findings = classifier.classify("python.exe", "python miner.py --algo cryptonight")

    assert any(item.kind == "possible_miner" for item in findings)


def test_keylogger_indicator_is_flagged() -> None:
    classifier = _make_classifier()
    findings = classifier.classify("keyloghelper.exe", "keyloghelper.exe")

    assert any(item.kind == "possible_keylogger" for item in findings)
