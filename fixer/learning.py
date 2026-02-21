from __future__ import annotations

import json
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import psutil

from fixer.models import AppConfig, ContextState
from fixer.utils import normalize_process_name


@dataclass(frozen=True)
class LearningSuggestion:
    target: str
    value: str
    reason: str
    confidence: str
    evidence_count: int


class LearningEngine:
    def __init__(
        self,
        config: AppConfig,
        output_path: str | Path | None = None,
        min_occurrences: int | None = None,
        autosave_seconds: float | None = None,
    ) -> None:
        self._output_path = Path(output_path or config.learning.output_path)
        self._min_occurrences = max(int(min_occurrences or config.learning.min_occurrences), 1)
        self._autosave_seconds = max(float(autosave_seconds or config.learning.autosave_seconds), 5.0)

        self._process_seen: dict[str, int] = defaultdict(int)
        self._profile_seen: dict[tuple[str, str], int] = defaultdict(int)
        self._hog_events: dict[str, int] = defaultdict(int)
        self._suspicion_events: dict[tuple[str, str], int] = defaultdict(int)
        self._foreground_profile_seen: dict[tuple[str, str], int] = defaultdict(int)
        self._last_save_monotonic = time.monotonic()

    def observe_cycle(self, processes: list[psutil.Process], context: ContextState) -> None:
        for proc in processes:
            name = normalize_process_name(proc.info.get("name"))
            if not name:
                continue

            self._process_seen[name] += 1
            self._profile_seen[(context.profile_name, name)] += 1

        if context.foreground_process:
            self._foreground_profile_seen[(context.profile_name, context.foreground_process)] += 1

    def observe_hog(self, name: str) -> None:
        normalized = normalize_process_name(name)
        if normalized:
            self._hog_events[normalized] += 1

    def observe_suspicion(self, name: str, kind: str) -> None:
        normalized = normalize_process_name(name)
        if normalized:
            self._suspicion_events[(normalized, kind)] += 1

    def save_if_due(self, config: AppConfig) -> Path | None:
        if time.monotonic() - self._last_save_monotonic < self._autosave_seconds:
            return None
        return self.save_now(config)

    def save_now(self, config: AppConfig) -> Path:
        suggestions = self._build_suggestions(config)

        payload = {
            "generated_at": datetime.now(UTC).isoformat(),
            "min_occurrences": self._min_occurrences,
            "suggestions": [
                {
                    "target": item.target,
                    "value": item.value,
                    "reason": item.reason,
                    "confidence": item.confidence,
                    "evidence_count": item.evidence_count,
                }
                for item in suggestions
            ],
            "evidence": {
                "hog_events": dict(sorted(self._hog_events.items())),
                "unauthorized_recorder_events": {
                    name: count
                    for (name, kind), count in sorted(self._suspicion_events.items())
                    if kind == "unauthorized_recorder"
                },
            },
        }

        self._output_path.parent.mkdir(parents=True, exist_ok=True)
        self._output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        self._last_save_monotonic = time.monotonic()
        return self._output_path

    def _build_suggestions(self, config: AppConfig) -> list[LearningSuggestion]:
        suggestions: list[LearningSuggestion] = []

        protected = set(config.protected_processes)
        resource_allowlist = set(config.resource_allowlist)
        authorized_recorders = set(config.suspicious.authorized_recorders)
        game_processes = set(config.game_processes)
        streaming_processes = set(config.streaming_processes)

        for name, hog_count in self._hog_events.items():
            if name in protected or name in resource_allowlist:
                continue
            session_count = self._profile_seen[("gaming", name)] + self._profile_seen[("streaming", name)]
            if hog_count < self._min_occurrences or session_count < self._min_occurrences:
                continue

            confidence = "high" if hog_count >= self._min_occurrences * 2 else "medium"
            suggestions.append(
                LearningSuggestion(
                    target="resource_allowlist",
                    value=name,
                    reason="Frequently detected as a CPU hog during gaming/streaming sessions",
                    confidence=confidence,
                    evidence_count=hog_count,
                )
            )

        for (name, kind), count in self._suspicion_events.items():
            if kind != "unauthorized_recorder":
                continue
            if name in authorized_recorders or name in protected:
                continue
            if count < self._min_occurrences:
                continue

            streaming_presence = self._profile_seen[("streaming", name)]
            if streaming_presence < self._min_occurrences:
                continue

            confidence = "high" if count >= self._min_occurrences * 2 else "medium"
            suggestions.append(
                LearningSuggestion(
                    target="suspicious.authorized_recorders",
                    value=name,
                    reason="Frequently flagged as recorder while streaming profile is active",
                    confidence=confidence,
                    evidence_count=count,
                )
            )

        for (profile, name), count in self._foreground_profile_seen.items():
            if count < self._min_occurrences or name in protected:
                continue

            if profile == "gaming" and name not in game_processes:
                confidence = "high" if count >= self._min_occurrences * 2 else "low"
                suggestions.append(
                    LearningSuggestion(
                        target="game_processes",
                        value=name,
                        reason="Frequently foreground while gaming profile is active",
                        confidence=confidence,
                        evidence_count=count,
                    )
                )

            if profile == "streaming" and name not in streaming_processes and name not in game_processes:
                confidence = "high" if count >= self._min_occurrences * 2 else "low"
                suggestions.append(
                    LearningSuggestion(
                        target="streaming_processes",
                        value=name,
                        reason="Frequently foreground while streaming profile is active",
                        confidence=confidence,
                        evidence_count=count,
                    )
                )

        deduped: dict[tuple[str, str], LearningSuggestion] = {}
        for suggestion in suggestions:
            key = (suggestion.target, suggestion.value)
            existing = deduped.get(key)
            if not existing or suggestion.evidence_count > existing.evidence_count:
                deduped[key] = suggestion

        return sorted(
            deduped.values(),
            key=lambda item: (item.target, -item.evidence_count, item.value),
        )
