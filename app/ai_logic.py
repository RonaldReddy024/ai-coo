import logging
import os
from typing import Any, Dict, Tuple

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


def _extract_title_and_metadata(task_or_title, metadata):
    """Support both Task objects and explicit title/metadata arguments."""

    if isinstance(task_or_title, str):
        return task_or_title, metadata or {}

    # Fallback for callers passing a Task-like object
    return getattr(task_or_title, "title", ""), getattr(task_or_title, "metadata_json", {}) or {}


def run_ai_coo_logic(
    task_or_title, metadata=None, currency: str = "INR"
) -> Tuple[str, str]:
    """Generate an execution plan, enforcing an INR-first theme.


    Returns a tuple of (result_text, external_provider_status) where the status
    is "ok" if the external provider succeeded or a fallback_* value otherwise.

    Accepts either a Task ORM object or a raw title/metadata pair so the
    background worker can call it without loading extra relationships.
    """

    title, metadata_dict = _extract_title_and_metadata(task_or_title, metadata)

    prompt = f"""
You are an AI COO. Create a structured execution plan.

Task title: {title}
Metadata: {metadata_dict}

Use {currency} for all currency references.
    """.strip()

    provider_status = "ok"

    try:
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
        return result_text, provider_status

    except Exception as e:
        message = str(e)
        logger.error("[AI-COO] External provider error: %s", message)

        if "insufficient_quota" in message or "429" in message:
            provider_status = "fallback_insufficient_quota"
        else:
            provider_status = "fallback_error"

        result_text = build_local_fallback_plan(title, metadata_dict, currency)
        return result_text, provider_status
