from __future__ import annotations

from fixer.models import AppConfig, ContextState


class ContextEngine:
    def __init__(self, config: AppConfig) -> None:
        self._config = config

    def detect(self, running_names: set[str], foreground_process: str | None) -> ContextState:
        active_game = self._find_active_game(running_names, foreground_process)
        streaming_active = any(name in running_names for name in self._config.streaming_processes)

        if streaming_active and active_game:
            profile_name = "streaming"
        elif active_game:
            profile_name = "gaming"
        else:
            profile_name = "default"

        return ContextState(
            profile_name=profile_name,
            active_game=active_game,
            streaming_active=streaming_active,
            foreground_process=foreground_process,
        )

    def _find_active_game(self, running_names: set[str], foreground_process: str | None) -> str | None:
        if foreground_process and foreground_process in self._config.game_processes:
            return foreground_process

        for game in self._config.game_processes:
            if game in running_names:
                return game

        return None
