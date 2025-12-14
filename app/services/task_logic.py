from typing import List

from sqlalchemy.orm import Session

from app import models

PHASE_ORDER = {
    "design": 1,  # PRD, spec, requirements
    "build": 2,  # implement, develop, code
    "test": 3,  # QA, bug testing
    "launch": 4,  # deploy, release
}


def detect_phase(text: str) -> str:
    text = text.lower()
    if any(k in text for k in ["prd", "spec", "design", "requirements", "architecture"]):
        return "design"
    if any(k in text for k in ["implement", "develop", "build", "code", "integration"]):
        return "build"
    if any(k in text for k in ["test", "qa", "validate", "bug", "regression"]):
        return "test"
    if any(k in text for k in ["deploy", "release", "launch", "rollout", "go live"]):
        return "launch"
    return "unknown"


def analyze_task_relationships(db: Session, new_task: models.Task) -> str:
    """
    Derive dependency guidance for a task based on explicit prerequisite data.

    The output intentionally avoids guessing relationships from text so the
    "Dependencies & Next Steps" block only reflects persisted facts.
    """

    lines: List[str] = []

    prerequisite = None
    if getattr(new_task, "prerequisite_task_id", None):
        prerequisite = db.get(models.Task, new_task.prerequisite_task_id)

    if prerequisite:
        prereq_status = (prerequisite.status or "").lower()
        if prereq_status not in {"done", "completed"}:
            lines.append(
                f"This task is blocked by prerequisite task \"{prerequisite.title}\", which is not yet complete."
            )
        else:
            lines.append("No blocking prerequisites detected.")
    elif getattr(new_task, "prerequisite_task_id", None):
        lines.append("Prerequisite task reference is configured but could not be loaded.")
    else:
        lines.append("No blocking prerequisites detected.")

    this_text = f"{new_task.title or ''} {getattr(new_task, 'result_text', '')}".lower()
    this_phase = detect_phase(this_text)

    operational_line = None
    if prerequisite and (prerequisite.status or "").lower() not in {"done", "completed"}:
        operational_line = (
            "Operational next steps: assign an owner and complete the prerequisite task."
        )

    if operational_line is None:
        if "kpi" in this_text and "analysis" in this_text:
            operational_line = "Operational next steps: attach KPI data and begin analysis."
        elif this_phase == "design":
            operational_line = (
                "Operational next steps: finalize requirements, get stakeholder sign-off, then hand over to engineering."
            )
        elif this_phase == "build":
            operational_line = (
                "Operational next steps: confirm design/PRD is approved, break work into subtasks, and start implementation."
            )
        elif this_phase == "test":
            operational_line = (
                "Operational next steps: coordinate with engineering, run test cases, capture bugs, and verify fixes."
            )
        elif this_phase == "launch":
            operational_line = (
                "Operational next steps: verify testing is complete, align on rollout plan, and monitor after deployment."
            )
        else:
            operational_line = (
                "Operational next steps: clarify owner, deadline, and success criteria for this task."
            )

    lines.append(operational_line)

    return "\n".join(lines)
