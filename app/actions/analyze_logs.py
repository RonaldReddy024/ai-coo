from __future__ import annotations

import logging
from collections import Counter
from typing import Dict, Iterable

from . import ActionPlugin, register_plugin

logger = logging.getLogger(__name__)


class AnalyzeLogsPlugin(ActionPlugin):
    """Simple log analyzer that surfaces anomalies and error spikes."""

    name = "analyze_logs"

    def execute(self, task_context: Dict) -> Dict:
        logs: Iterable[str] = task_context.get("logs") or []
        window = int(task_context.get("window", 50))

        sample = list(logs)[:window]
        level_counts = Counter()
        error_lines = []

        for line in sample:
            normalized = line.lower()
            if "error" in normalized or "exception" in normalized:
                level_counts["error"] += 1
                error_lines.append(line)
            elif "warn" in normalized:
                level_counts["warning"] += 1
            else:
                level_counts["info"] += 1

        logger.info("[Action] Analyzed %s log lines", len(sample))
        return {
            "total": len(sample),
            "levels": dict(level_counts),
            "error_preview": error_lines[:5],
        }


register_plugin(AnalyzeLogsPlugin())

__all__ = ["AnalyzeLogsPlugin"]
