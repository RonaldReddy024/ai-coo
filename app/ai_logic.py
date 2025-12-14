import logging
import os
import re
import textwrap
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


def _infer_context_flags(text: str) -> Dict[str, bool]:
    text = text.lower()
    return {
        "is_finance": any(k in text for k in ["revenue", "cost", "pricing", "budget", "pnl"]),
        "is_growth": any(k in text for k in ["campaign", "seo", "marketing", "growth", "acquisition"]),
        "is_data": any(k in text for k in ["data", "dashboard", "report", "analysis", "analytics"]),
        "is_engineering": any(k in text for k in ["build", "develop", "integration", "api", "deploy", "ship"]),
        "is_customer": any(k in text for k in ["customer", "support", "cx", "success", "churn"]),
    }


def _infer_currency(metadata: Dict[str, Any], fallback: str = "INR") -> str:
    currency = metadata.get("currency") or metadata.get("currency_code")
    if isinstance(currency, str) and currency.strip():
        return currency.strip().upper()
    return fallback


def build_local_fallback_plan(
    title: str, metadata: Dict[str, Any], currency: str = "INR"
) -> str:
    """
    Build a task-specific execution plan when the external AI provider is unavailable.

    The content adapts to the title/metadata so every task gets tailored steps,
    risks, and data needs instead of a static boilerplate.
    """

    squad = metadata.get("squad") or metadata.get("team")
    priority = metadata.get("priority", "normal")
    company = metadata.get("company") or metadata.get("company_id")
    inferred_currency = _infer_currency(metadata, currency)

    text_blob = f"{title} {metadata}"
    flags = _infer_context_flags(text_blob)

    summary_context = []
    if squad:
        summary_context.append(f"squad {squad}")
    if company:
        summary_context.append(f"company {company}")
    context_str = ", ".join(summary_context) if summary_context else "this task"

    steps: list[str] = [
        f"Clarify owner, deadline, and success criteria with {context_str}.",
        f"Log this task into your tracking tool with priority '{priority}'.",
    ]

    if flags["is_finance"]:
        steps.append(
            "Pull recent financial KPIs and compare week-over-week to flag >10% movements (₹ conversions included)."
        )
    if flags["is_growth"]:
        steps.append(
            "Audit active campaigns and attribution to understand short-term lifts or drops."
        )
    if flags["is_data"]:
        steps.append(
            "Validate data freshness and definitions with BI/analytics before publishing any summary."
        )
    if flags["is_engineering"]:
        steps.append(
            "Break down implementation work into smaller tickets with testable acceptance criteria."
        )
    if flags["is_customer"]:
        steps.append("Review recent customer feedback/tickets to capture qualitative signals.")

    dependencies = metadata.get("dependencies") or metadata.get("depends_on") or []
    if isinstance(dependencies, (list, tuple)) and dependencies:
        steps.append("Confirm prerequisites are done: " + ", ".join(map(str, dependencies)) + ".")
    elif metadata.get("requires"):
        steps.append(f"Confirm prerequisites are done: {metadata['requires']}.")

    risks: list[str] = []
    if flags["is_finance"]:
        risks.append("Delayed or inconsistent revenue data may hide anomalies.")
    if flags["is_growth"]:
        risks.append("Channel mix changes could distort short-term performance.")
    if flags["is_engineering"]:
        risks.append("Integration or API limits may block delivery timelines.")
    if flags["is_customer"]:
        risks.append("Customer-impacting changes may increase churn if not communicated.")
    if flags["is_data"]:
        risks.append("Metric definitions may not be aligned across stakeholders.")
    if not risks:
        risks.append("Key inputs might be incomplete or delayed, affecting decision quality.")

    data_needed: list[str] = []
    if flags["is_finance"]:
        data_needed.append(
            f"Recent revenue/cost exports with {inferred_currency} amounts and volumes."
        )
    if flags["is_growth"]:
        data_needed.append("Campaign performance by channel with spend vs. conversions.")
    if flags["is_data"]:
        data_needed.append("Source-of-truth dashboards or warehouse tables with metric definitions.")
    if flags["is_engineering"]:
        data_needed.append("API docs, architectural constraints, and staging credentials.")
    if flags["is_customer"]:
        data_needed.append("Latest NPS/CSAT or churn/ticket data broken down by segment.")
    if not data_needed:
        data_needed.append("Baseline metrics, owners, and success criteria from stakeholders.")

    dependencies_text = ""
    if isinstance(dependencies, (list, tuple)) and dependencies:
        dependencies_text = "\n".join(f"- {dep}" for dep in dependencies)
    elif metadata.get("requires"):
        dependencies_text = f"- {metadata['requires']}"
    else:
        dependencies_text = "- No explicit dependencies captured in metadata."

    steps_block = "\n".join(f"- {item}" for item in steps)
    risks_block = "\n".join(f"- {item}" for item in risks)
    data_needed_block = "\n".join(f"- {item}" for item in data_needed)

    return textwrap.dedent(
        f"""
        Summary: Execution plan for '{title}' (local fallback, external AI unavailable).

        Context:
        - Currency: {inferred_currency}
        - Scope: {context_str}

        Steps:
        {steps_block}

        Risks:
        {risks_block}

        DataNeeded:
        {data_needed_block}

        Dependencies:
        {dependencies_text}

        Note:
        - External AI provider is currently unavailable (quota, network, or configuration issue).
        - Used the built-in local fallback playbook tuned to this task.
        """
    ).strip()


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
