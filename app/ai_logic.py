import os
from typing import Dict, Any

from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def build_local_fallback_plan(title: str, metadata: Dict[str, Any]) -> str:
    return f"""Summary: Execution plan for '{title}' (local fallback, external AI unavailable).

All financial metrics below are in Rupees (₹).

Steps:
- Confirm scope and success criteria with stakeholders in the relevant team.
- Log this task into your tracking tool with priority 'normal'.
- Identify 5–10 key KPIs such as weekly revenue (₹), CAC (₹), retention, and churn.
- Pull recent KPI data (last 4–12 weeks) and check for trends, anomalies, and spending in Rupees.
- Draft a concise report or slide deck summarizing performance with Rupee-based numbers.
- Review the report with the relevant team and finalize.

Risks:
- Data might be incomplete, inconsistent, or delayed.
- Stakeholders may not align on which Rupee-based KPIs matter most.
- Tight timelines may limit depth of analysis.

DataNeeded:
- Recent KPI dashboards or exports (₹).
- Targets/OKRs from leadership.
- Any existing KPI definitions or documentation.

Note:
- External AI provider is currently unavailable.
- Used the built-in local playbook instead."""


def _extract_title_and_metadata(task_or_title, metadata):
    """Support both Task objects and explicit title/metadata arguments."""

    if isinstance(task_or_title, str):
        return task_or_title, metadata or {}

    # Fallback for callers passing a Task-like object
    return getattr(task_or_title, "title", ""), getattr(task_or_title, "metadata_json", {}) or {}


def run_ai_coo_logic(task_or_title, metadata=None, currency: str = "INR") -> str:
    """Generate an execution plan, enforcing an INR-first theme.

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

        return response.choices[0].message.content.strip()

    except Exception as e:
        print("[AI-COO] External provider error:", e)

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
