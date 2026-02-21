from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from fixer.__main__ import _resolve_config_path, _resolve_runtime


def test_resolve_runtime_handles_namespace_without_mode() -> None:
    args = Namespace(config="config/default.json", learning_mode=False)

    config, learning_enabled = _resolve_runtime(args)

    assert config.mode == "safe"
    assert learning_enabled is False


def test_resolve_config_path_uses_existing_relative_path(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "custom.json"
    config_path.write_text("{}", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    resolved = _resolve_config_path("custom.json")

    assert Path(resolved) == config_path.resolve()


def test_resolve_config_path_falls_back_to_base_dir(tmp_path, monkeypatch) -> None:
    base_dir = tmp_path / "base"
    cfg_dir = base_dir / "config"
    cfg_dir.mkdir(parents=True)
    expected = cfg_dir / "default.json"
    expected.write_text("{}", encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("fixer.__main__._default_base_dir", lambda: base_dir)

    resolved = _resolve_config_path("config/default.json")

    assert Path(resolved) == expected.resolve()
