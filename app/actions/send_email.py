from __future__ import annotations

import logging
from typing import Dict, List

from . import ActionPlugin, register_plugin

logger = logging.getLogger(__name__)


class SendEmailPlugin(ActionPlugin):
    """Lightweight email sender stub.

    In production this would call an ESP or SMTP relay.
    Here we simply validate inputs and return a preview payload.
    """

    name = "send_email"

    def execute(self, task_context: Dict) -> Dict:
        recipients: List[str] = task_context.get("to", []) or []
        subject: str = task_context.get("subject", "(no subject)")
        body: str = task_context.get("body", "")

        if not recipients:
            raise ValueError("send_email requires at least one recipient")

        logger.info("[Action] Sending email to %s with subject '%s'", recipients, subject)
        return {
            "delivered": True,
            "to": recipients,
            "subject": subject,
            "body_preview": body[:280],
        }


register_plugin(SendEmailPlugin())

__all__ = ["SendEmailPlugin"]
