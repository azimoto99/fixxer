from __future__ import annotations

from fixer.models import AppConfig, Suspicion
from fixer.utils import normalize_process_name


class ProcessClassifier:
    def __init__(self, config: AppConfig) -> None:
        self._config = config

    def classify(self, name: str, cmdline: str) -> list[Suspicion]:
        normalized_name = normalize_process_name(name)
        normalized_cmdline = cmdline.strip().lower()

        findings: list[Suspicion] = []

        if self._is_unauthorized_recorder(normalized_name):
            findings.append(
                Suspicion(
                    kind="unauthorized_recorder",
                    reason="Recorder pattern matched and process is not authorized",
                )
            )

        if self._matches_any(self._config.suspicious.keylogger_indicators, normalized_name, normalized_cmdline):
            findings.append(
                Suspicion(
                    kind="possible_keylogger",
                    reason="Keylogger indicator matched process name or command line",
                )
            )

        if self._matches_any(self._config.suspicious.miner_indicators, normalized_name, normalized_cmdline):
            findings.append(
                Suspicion(
                    kind="possible_miner",
                    reason="Cryptominer indicator matched process name or command line",
                )
            )

        return findings

    def _is_unauthorized_recorder(self, name: str) -> bool:
        if name in self._config.suspicious.authorized_recorders:
            return False

        # Recorder detection is intentionally name-focused to reduce
        # false positives from generic terms in long command lines.
        for indicator in self._config.suspicious.recorder_indicators:
            if indicator and indicator in name:
                return True

        return False

    @staticmethod
    def _matches_any(indicators: list[str], name: str, cmdline: str) -> bool:
        for indicator in indicators:
            if indicator and (indicator in name or indicator in cmdline):
                return True
        return False
