from __future__ import annotations

import logging
from typing import Dict, Optional

from app.config import settings
from app.models import Task
from .intelligence import generate_project_breakdown, normalize_multilingual_task

logger = logging.getLogger(__name__)


class WhatsAppService:
    def __init__(self, api_key: Optional[str], sender: Optional[str]):
        self.api_key = api_key
        self.sender = sender or "WorkYodha"

    def _can_send(self) -> bool:
        return bool(self.api_key)

    def format_task_summary(self, task: Task) -> str:
        return (
            f"Task #{task.id}: {task.title}\n"
            f"Status: {task.status}\n"
            f"Next steps: {task.next_steps or 'Not generated'}"
        )

    def receive_task_message(self, message: str, metadata: Optional[Dict] = None) -> Dict:
        normalized = normalize_multilingual_task(message)
        breakdown = generate_project_breakdown(message, squad=(metadata or {}).get("squad"))
        return {
            "language": normalized["language"],
            "normalized": normalized["normalized"],
            "breakdown": breakdown,
        }

    def send_alert(self, to: str, text: str) -> Dict:
        if not self._can_send():
            logger.warning("WhatsApp API key missing; returning dry-run response")
            return {"sent": False, "to": to, "sender": self.sender, "text": text}

        # Real implementation would call a WhatsApp provider API
        logger.info("[WhatsApp] Sending alert to %s", to)
        return {"sent": True, "to": to, "sender": self.sender, "text": text}


whatsapp_service = WhatsAppService(settings.WHATSAPP_API_KEY, settings.WHATSAPP_SENDER)

__all__ = ["WhatsAppService", "whatsapp_service"]
