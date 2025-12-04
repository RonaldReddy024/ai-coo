from __future__ import annotations

import logging
from typing import Dict

from app.config import settings
from . import ActionPlugin, register_plugin

logger = logging.getLogger(__name__)


class UpdateJiraPlugin(ActionPlugin):
    """Stub Jira updater that can be swapped with a real client later."""

    name = "update_jira"

    def execute(self, task_context: Dict) -> Dict:
        issue_key = task_context.get("issue_key")
        fields = task_context.get("fields") or {}

        if not issue_key:
            raise ValueError("update_jira requires 'issue_key'")

        jira_url = settings.__dict__.get("JIRA_BASE_URL", "")
        logger.info("[Action] Updating Jira issue %s (base=%s)", issue_key, jira_url)

        # No outbound network calls here; just echo the intent.
        return {
            "updated": True,
            "issue_key": issue_key,
            "fields": fields,
            "jira_base_url": jira_url,
        }


register_plugin(UpdateJiraPlugin())

__all__ = ["UpdateJiraPlugin"]
