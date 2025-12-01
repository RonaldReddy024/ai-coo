import os
from typing import Dict, Any

from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def build_ai_coo_prompt(title: str, metadata: Dict[str, Any]) -> str:
    """
    Turn a task title + metadata into a rich prompt for the AI COO.
    (Used only if the real API call succeeds.)
    """
    meta_lines = []
    for k, v in (metadata or {}).items():
        meta_lines.append(f"- {k}: {v}")
    meta_block = "\n".join(meta_lines) if meta_lines else "None"

    prompt = f"""
You are an AI COO helping an operations team execute tasks.

Task:
- Title: {title}

Context / metadata:
{meta_block}

Your job:
1. Interpret what this task actually means in a business/ops context.
2. Break it down into 3–7 clear, actionable steps.
3. Flag any assumptions you had to make.
4. Suggest what data or tools you would want to query or use.

Return your answer in this bullet format:

Summary: <one sentence summary>
Steps:
- <step 1>
- <step 2>
Risks:
- <risk 1>
DataNeeded:
- <data or systems you'd query>
    """.strip()

    return prompt


def build_local_fallback_plan(title: str, metadata: Dict[str, Any], error: str) -> str:
    """
    Local 'fake AI COO' that still gives a structured, useful answer
    when the real LLM call fails (e.g. insufficient_quota).
    """
    team = metadata.get("team", "the relevant team")
    priority = metadata.get("priority", "normal")
    due_date = metadata.get("due_date", "unspecified")

    lines = [
        f"Summary: High-level execution plan for '{title}' (generated via local fallback, no external AI).",
        "",
        "Steps:",
        f"- Clarify the exact scope of the task with stakeholders in " + team + ".",
        "- Identify the 5–10 most important KPIs and how they are currently tracked.",
        "- Pull recent data (last 4–12 weeks) for these KPIs from your analytics / BI tools.",
        "- Analyze trends, anomalies, and risks; highlight 3–5 key insights for leadership.",
        "- Draft a concise slide or 1-pager summarizing KPIs, trends, and recommended actions.",
        f"- Review the draft with the team and finalize before the due date ({due_date}).",
        "",
        "Risks:",
        "- Incomplete or low-quality data may weaken the KPI story.",
        "- Misalignment with what leadership actually cares about can reduce impact.",
        "- Tight timelines may not allow deep analysis.",
        "",
        "DataNeeded:",
        "- Historical KPI data (traffic, conversion, revenue, churn, etc.).",
        "- Any existing KPI dashboards or reports.",
        "- Current goals/targets from leadership or OKR documents.",
        "",
        "Note:",
        f"- Real AI COO call failed with error: {error}",
        "- Once you have API credits, the system will automatically switch to richer LLM-generated plans.",
    ]

    return "\n".join(lines)


def run_ai_coo_logic(task) -> str:
    """
    Real AI COO brain with graceful fallback:
    - Try OpenAI API (if quota + billing are OK).
    - On any error (e.g. insufficient_quota), return a local structured plan.
    """
    title = getattr(task, "title", "")
    metadata = getattr(task, "metadata_json", {}) or {}

    prompt = build_ai_coo_prompt(title, metadata)

    try:
        # Try real OpenAI call
        response = client.chat.completions.create(
            model="gpt-4.1-mini",  # adjust to any model you have access to
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an AI COO, an expert in operations, process design, "
                        "and executive decision support. Be concise but concrete."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=400,
        )

        content = response.choices[0].message.content.strip()
        return content

    except Exception as e:
        # On any error (429, bad key, network, etc.), generate a local plan instead
        error_text = str(e)
        return build_local_fallback_plan(title, metadata, error_text)
