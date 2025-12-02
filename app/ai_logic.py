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


def run_ai_coo_logic(task) -> str:
    """
    Try OpenAI; if that fails (e.g. insufficient_quota), fall back to a local plan.
    """
    title = getattr(task, "title", "")
    metadata = getattr(task, "metadata_json", {}) or {}

    prompt = f"""
You are an AI COO. Create a structured execution plan.

Task title: {title}
Metadata: {metadata}
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
        # Fallback: no crash, just a local structured plan
        print(f"[AI-COO] External provider error: {e!r}")
        return build_local_fallback_plan(title, metadata)
