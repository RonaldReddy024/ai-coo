import logging
import os
import re
from typing import Any, Dict, List, Tuple

from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
logger = logging.getLogger(__name__)


def analyze_task_relationships(
    new_task, existing_tasks: List[Any]
) -> Tuple[str, List[int], List[int]]:
    """
    Infer next steps and dependency relationships for a task.

    Returns
    -------
    next_steps_text: str
        Human-readable next steps for the task.
    depends_on_ids: list[int]
        Task IDs that should be completed before this task.
    blocks_ids: list[int]
        Task IDs that are blocked by this task.
    """

    title = (getattr(new_task, "title", "") or "").lower()
    desc = (getattr(new_task, "description", "") or "").lower()
    text = f"{title} {desc}"

    is_design = bool(re.search(r"\b(spec|design|discovery|requirements|prd)\b", text))
    is_build = bool(re.search(r"\b(implement|build|develop|code|integration)\b", text))
    is_test = bool(re.search(r"\b(test|qa|validation|bug|issue)\b", text))
    is_launch = bool(re.search(r"\b(release|deploy|launch|rollout|go live)\b", text))

    next_steps_lines: list[str] = []

    if is_design:
        next_steps_lines.append(
            "- Schedule a design/requirements review with the relevant squad (e.g., product + engineering)."
        )
        next_steps_lines.append("- Confirm acceptance criteria before implementation tasks are started.")
    if is_build:
        next_steps_lines.append(
            "- Ensure any design/PRD tasks are completed and approved before starting implementation."
        )
        next_steps_lines.append("- Break this into smaller implementation subtasks if it’s too broad.")
    if is_test:
        next_steps_lines.append(
            "- Confirm that implementation tasks related to this feature are completed and merged."
        )
        next_steps_lines.append(
            "- Coordinate with QA/owners to define test cases and success criteria."
        )
    if is_launch:
        next_steps_lines.append("- Verify that testing tasks are completed and results are signed off.")
        next_steps_lines.append(
            "- Align with stakeholders on rollout plan, communication, and monitoring."
        )

    if not next_steps_lines:
        next_steps_lines.append("- Clarify owner, deadline, and success criteria for this task.")

    depends_on_ids: list[int] = []
    blocks_ids: list[int] = []

    for task in existing_tasks:
        if getattr(task, "id", None) == getattr(new_task, "id", None):
            continue

        t_text = f"{(getattr(task, 'title', '') or '').lower()} {(getattr(task, 'description', '') or '').lower()}"

        same_squad = False
        same_company = False

        if "frontend" in text and "frontend" in t_text:
            same_squad = True
        if "finance" in text and "finance" in t_text:
            same_squad = True
        if "bigbasket" in text and "bigbasket" in t_text:
            same_company = True
        if "browserstack" in text and "browserstack" in t_text:
            same_company = True

        if not (same_squad or same_company):
            continue

        t_is_design = any(k in t_text for k in ["spec", "design", "prd"])
        t_is_build = any(k in t_text for k in ["implement", "build", "develop"])
        t_is_test = any(k in t_text for k in ["test", "qa", "bug", "issue"])
        t_is_launch = any(k in t_text for k in ["release", "deploy", "launch"])

        if is_build and t_is_design:
            depends_on_ids.append(task.id)

        if is_test and t_is_build:
            depends_on_ids.append(task.id)

        if is_launch and t_is_test:
            depends_on_ids.append(task.id)

        if is_design and t_is_build:
            blocks_ids.append(task.id)

        if is_build and t_is_test:
            blocks_ids.append(task.id)

        if is_test and t_is_launch:
            blocks_ids.append(task.id)

    unique_depends = sorted(set(depends_on_ids))
    unique_blocks = sorted(set(blocks_ids))

    dependency_text = ""

    if unique_depends:
        dependency_text += (
            "This task cannot be completed until the following tasks are finished:\n"
        )
        for dep_id in unique_depends:
            dependency_text += f"- Task #{dep_id}\n"

    if unique_blocks:
        dependency_text += "\nThis task must be completed before the following tasks can proceed:\n"
        for blk_id in unique_blocks:
            dependency_text += f"- Task #{blk_id}\n"

    if dependency_text == "":
        dependency_text = "This task has no blocking or prerequisite tasks."

    next_steps_text = dependency_text + "\n\n" + "\n".join(next_steps_lines)
    return next_steps_text, unique_depends, unique_blocks


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
