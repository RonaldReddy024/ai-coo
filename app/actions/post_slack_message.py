from __future__ import annotations

import logging
from typing import Dict

import httpx

from app.config import settings
from . import ActionPlugin, register_plugin

logger = logging.getLogger(__name__)


class PostSlackMessagePlugin(ActionPlugin):
    """Send a message to Slack if credentials are available."""

    name = "post_slack_message"

    def execute(self, task_context: Dict) -> Dict:
        channel = task_context.get("channel") or "#general"
        text = task_context.get("text") or "(empty message)"

        if not settings.SLACK_BOT_TOKEN:
            logger.warning("Slack bot token missing; returning dry-run response")
            return {
                "sent": False,
                "channel": channel,
                "text": text,
                "reason": "SLACK_BOT_TOKEN not configured",
            }

        url = "https://slack.com/api/chat.postMessage"
        headers = {"Authorization": f"Bearer {settings.SLACK_BOT_TOKEN}"}
        payload = {"channel": channel, "text": text}

        with httpx.Client() as client:
            response = client.post(url, json=payload, headers=headers, timeout=10)
        data = response.json()

        if not data.get("ok"):
            raise RuntimeError(f"Slack API error: {data}")

        return {"sent": True, "channel": channel, "ts": data.get("ts")}


register_plugin(PostSlackMessagePlugin())

__all__ = ["PostSlackMessagePlugin"]
