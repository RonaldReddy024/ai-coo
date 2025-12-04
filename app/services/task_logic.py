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
    Derive human-readable dependency guidance for a task.

    The logic:
    - Find same-project tasks via keyword overlap.
    - If this task is a later phase, it depends on the earlier one.
    - If this task is an earlier phase, it blocks the later one.
    - Return a multiline string for the ``next_steps`` field.
    """

    all_tasks: List[models.Task] = (
        db.query(models.Task)
        .filter(models.Task.id != new_task.id)
        .order_by(models.Task.created_at.asc())
        .all()
    )

    this_text = f"{new_task.title or ''} {getattr(new_task, 'result_text', '')}".lower()
    this_phase = detect_phase(this_text)
    this_phase_order = PHASE_ORDER.get(this_phase, 0)

    depends_on_ids: List[int] = []
    blocks_ids: List[int] = []

    for task in all_tasks:
        other_text = f"{task.title or ''} {getattr(task, 'result_text', '')}".lower()
        other_phase = detect_phase(other_text)
        other_phase_order = PHASE_ORDER.get(other_phase, 0)

        same_project = False
        for kw in ["bigbasket", "browserstack", "finance", "inventory", "stock"]:
            if kw in this_text and kw in other_text:
                same_project = True
                break

        if not same_project:
            continue

        if this_phase_order > other_phase_order and other_phase_order > 0:
            depends_on_ids.append(task.id)

        if this_phase_order < other_phase_order and this_phase_order > 0:
            blocks_ids.append(task.id)

    lines: List[str] = []

    if depends_on_ids:
        ids_str = ", ".join(f"#{i}" for i in sorted(set(depends_on_ids)))
        lines.append(
            f"This task cannot be completed until the following tasks are finished: {ids_str}."
        )

    if blocks_ids:
        ids_str = ", ".join(f"#{i}" for i in sorted(set(blocks_ids)))
        lines.append(
            f"This task must be finished before the following tasks can be completed: {ids_str}."
        )

    if not depends_on_ids and not blocks_ids:
        lines.append(
            "This task has no obvious prerequisite or blocking tasks based on current data."
        )

    if this_phase == "design":
        lines.append(
            "Operational next steps: finalize requirements, get stakeholder sign-off, then hand over to engineering."
        )
    elif this_phase == "build":
        lines.append(
            "Operational next steps: confirm design/PRD is approved, break work into subtasks, and start implementation."
        )
    elif this_phase == "test":
        lines.append(
            "Operational next steps: coordinate with engineering, run test cases, capture bugs, and verify fixes."
        )
    elif this_phase == "launch":
        lines.append(
            "Operational next steps: verify testing is complete, align on rollout plan, and monitor after deployment."
        )
    else:
        lines.append(
            "Operational next steps: clarify owner, deadline, and success criteria for this task."
        )

    return "\n".join(lines)
