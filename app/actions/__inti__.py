"""Action plugin registry for WorkYodha.

Provides a lightweight plugin system so automation tasks can
register executable actions (email, Slack, SQL, Jira, etc.)
and invoke them uniformly via ``ActionTask.execute``.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)


class ActionPlugin:
    """Base class for executable action plugins."""

    name: str = ""

    def __init__(self, name: Optional[str] = None):
        if name:
            self.name = name

    def execute(self, task_context: dict) -> dict:  # pragma: no cover - interface
        raise NotImplementedError


# Global registry for plugins keyed by name
ACTION_PLUGINS: Dict[str, ActionPlugin] = {}


def register_plugin(plugin: ActionPlugin):
    """Register a plugin instance by its declared name."""

    if not plugin.name:
        raise ValueError("Plugins must define a name before registration")

    ACTION_PLUGINS[plugin.name] = plugin
    logger.debug("Registered action plugin: %s", plugin.name)


def get_plugin(name: str) -> Optional[ActionPlugin]:
    """Return a plugin by name if registered."""

    return ACTION_PLUGINS.get(name)


@dataclass
class ActionTask:
    """Wrapper that binds an action with execution context."""

    action: str
    payload: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)

    def execute(self) -> dict:
        plugin = get_plugin(self.action)
        if not plugin:
            raise ValueError(f"Action '{self.action}' is not registered")

        logger.info("Executing action '%s' with payload keys=%s", self.action, list(self.payload))
        result = plugin.execute(self.payload)
        return {
            "action": self.action,
            "result": result,
            "metadata": self.metadata,
        }


def load_default_plugins():
    """Import modules to populate the registry with built-ins."""

    from . import analyze_logs, post_slack_message, run_sql_query, send_email, update_jira  # noqa: F401

    logger.debug(
        "Loaded default plugins: %s", ", ".join(sorted(ACTION_PLUGINS.keys()))
    )
    return ACTION_PLUGINS


__all__ = [
    "ActionPlugin",
    "ACTION_PLUGINS",
    "ActionTask",
    "register_plugin",
    "get_plugin",
    "load_default_plugins",
]
