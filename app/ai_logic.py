import logging
import os
from typing import Any, Dict

from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
logger = logging.getLogger(__name__)


def build_local_fallback_plan(
    title: str, metadata: Dict[str, Any], currency: str = "INR"
) -> str:
    return f"""Summary: Execution plan for '{title}' (local fallback, external AI unavailable).

Currency: {currency} (₹)

Steps:
- Confirm scope and success criteria with stakeholders in the relevant team.
- Log this task into your tracking tool with priority 'normal'.
- Identify 5–10 key KPIs and where their data lives (BI tool, data warehouse, etc.).
- Pull recent KPI data (₹ amounts) for the last 4–12 weeks, and check for trends and anomalies.
- Draft a concise report or slide deck summarizing current status and key insights.
- Review the report with the relevant team and finalize next steps.

Risks:
- Data might be incomplete, inconsistent, or delayed.
- Stakeholders may not align on which KPIs matter most.
- Tight timelines may limit the depth of analysis.

DataNeeded:
- Recent KPI dashboards or exports (₹ values).
- Targets/OKRs from leadership.
- Any existing KPI definitions or documentation.

Note:
- External AI provider is currently unavailable (quota, network, or configuration issue).
- Used the built-in local INR-based playbook instead."""


def run_ai_coo_logic(title: str, metadata: dict) -> tuple[str, str]:
    """
    Returns: (result_text, external_provider_status)
    external_provider_status:
      - "ok"                        -> external AI used successfully
      - "fallback_insufficient_quota" -> quota/429 error, INR fallback used
      - "fallback_error"           -> some other error, INR fallback used
    """

    try:
        prompt = f"""
You are an AI COO. Create a structured execution plan.

Task title: {title}
Metadata: {metadata}

Use INR (₹) for all currency references.
        """.strip()

        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You are an AI COO, expert in operations and execution.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=400,
        )

        result_text = response.choices[0].message.content.strip()
        return result_text, "ok"

    except Exception as e:
        msg = str(e)
        logger.error(f"[AI-COO] External provider error: {msg}")

        if "insufficient_quota" in msg or "429" in msg:
            provider_status = "fallback_insufficient_quota"
        else:
            provider_status = "fallback_error"

        result_text = build_local_fallback_plan(title, metadata or {}, currency="INR")
        return result_text, provider_status
