import os
from typing import Dict, Any

from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def build_local_fallback_plan(title: str, metadata: Dict[str, Any], error: str) -> str:
    team = metadata.get("team", "the relevant team")
    priority = metadata.get("priority", "normal")
    due_date = metadata.get("due_date", "unspecified")

    lines = [
        f"Summary: Execution plan for '{title}' (local fallback, no external AI).",
        "",
        "Steps:",
        f"- Confirm scope and success criteria with stakeholders in {team}.",
        f"- Log this task into your tracking tool with priority '{priority}'.",
        "- Identify 5–10 key KPIs and where their data lives (BI tool, data warehouse, etc.).",
        "- Pull recent KPI data (last 4–12 weeks) and check for trends and anomalies.",
        "- Draft a concise report or slide deck summarizing current status and key insights.",
        f"- Review the report with {team} and finalize before {due_date}.",
        "",
        "Risks:",
        "- Data might be incomplete, inconsistent, or delayed.",
        "- Stakeholders may not align on what KPIs matter most.",
        "- Tight timelines may limit depth of analysis.",
        "",
        "DataNeeded:",
        "- Recent KPI dashboards or exports.",
        "- Targets/OKRs from leadership.",
        "- Any existing KPI definitions or documentation.",
        "",
        "Note:",
        f"- Real AI COO call failed with error: {error}",
    ]

    return "\n".join(lines)


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
        error_text = str(e)
        return build_local_fallback_plan(title, metadata, error_text)
