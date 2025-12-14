from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..deps import get_current_user_email, get_db
from .. import models
from ..schemas import Sprint, SprintCollaborator, SprintCollaboratorCreate, SprintWithIssues
from ..schemas import Issue as IssueSchema
from ..schemas import (
    IssueCreate,
    SprintAlert,
    SprintCreate,
    SprintInsights,
    SprintRiskReport,
    SprintSnapshot,
)

router = APIRouter()


def _get_owned_sprint(
    sprint_id: int, user_email: str, db: Session
) -> models.Sprint:
    sprint = (
        db.query(models.Sprint)
        .filter_by(id=sprint_id, owner_email=user_email)
        .first()
    )
    if not sprint:
        raise HTTPException(status_code=404, detail="Sprint not found")
    return sprint

def _get_accessible_sprint(
    sprint_id: int, user_email: str, db: Session
) -> models.Sprint:
    sprint = db.query(models.Sprint).filter_by(id=sprint_id).first()
    if not sprint:
        raise HTTPException(status_code=404, detail="Sprint not found")

    if sprint.owner_email == user_email:
        return sprint

    collaborator = (
        db.query(models.SprintCollaborator)
        .filter_by(sprint_id=sprint_id, email=user_email)
        .first()
    )
    if not collaborator:
        raise HTTPException(status_code=404, detail="Sprint not found")

    return sprint



def compute_risk_for_sprint(sprint: models.Sprint) -> None:
    """
    Simple heuristic:
    - % incomplete issues vs days remaining
    - blockers increase risk
    """
    now = datetime.utcnow()
    total_issues = len(sprint.issues)
    
    if total_issues == 0:
        sprint.risk_score = 0.0
        sprint.risk_level = "low"
        sprint.last_evaluated_at = now
        return

    incomplete = [
        i
        for i in sprint.issues
        if i.status.lower() not in ("done", "resolved", "closed")
    ] 
    incomplete_ratio = len(incomplete) / total_issues

    # Time factor
    total_days = (sprint.end_date - sprint.start_date).days or 1
    days_left = (sprint.end_date - now).days
    days_progress = max(0, min(1, (total_days - days_left) / total_days))

    # Blocker penalty
    blockers = [i for i in sprint.issues if i.is_blocker]
    blocker_factor = 0.1 * len(blockers)

    # Simple risk formula
    risk_score = incomplete_ratio * 0.6 + days_progress * 0.3 + blocker_factor
    risk_score = max(0.0, min(1.0, risk_score))  # clamp 0–1

    if risk_score > 0.7:
        level = "high"
    elif risk_score > 0.4:
        level = "medium"
    else:
        level = "low"

    sprint.risk_score = risk_score
    sprint.risk_level = level
    sprint.last_evaluated_at = now


def generate_risk_explanation(sprint: models.Sprint) -> tuple[str, str]:
    """
    Returns (summary, details) text for the sprint's risk.
    """
    total_issues = len(sprint.issues)
    blockers = [i for i in sprint.issues if i.is_blocker]
    done_like_statuses = ("done", "resolved", "closed")
    done_issues = [i for i in sprint.issues if i.status.lower() in done_like_statuses]
    open_issues = [i for i in sprint.issues if i not in done_issues]

    now = datetime.utcnow()
    days_left = (sprint.end_date - now).days
    total_days = (sprint.end_date - sprint.start_date).days or 1
    elapsed_days = max(0, min(total_days, (now - sprint.start_date).days))

    # --- Summary sentence ---
    if sprint.risk_level == "high":
        summary = f"Sprint '{sprint.name}' is at HIGH risk and may not hit its end date on time."
    elif sprint.risk_level == "medium":
        summary = f"Sprint '{sprint.name}' is at MEDIUM risk and will need close monitoring."
    else:
        summary = f"Sprint '{sprint.name}' is currently at LOW risk based on the latest signals."

    # --- Details paragraph ---
    parts = []

    # Issue counts
    if total_issues == 0:
        parts.append("There are no issues linked to this sprint yet, so the risk assessment is based only on dates.")
    else:
        parts.append(
            f"The sprint has {total_issues} issues in total: "
            f"{len(done_issues)} done and {len(open_issues)} still open."
        )

    # Blockers
    if blockers:
        blocker_titles = ", ".join(b.title for b in blockers[:3])
        extra = "" if len(blockers) <= 3 else f" and {len(blockers) - 3} more"
        parts.append(
            f"{len(blockers)} issue(s) are flagged as blockers ({blocker_titles}{extra}). "
            "These should be cleared first to unblock progress."
        )

    # Time progress
    if days_left < 0:
        parts.append("The sprint has already passed its planned end date.")
    else:
        parts.append(
            f"The sprint runs from {sprint.start_date.date()} to {sprint.end_date.date()}, "
            f"with about {max(days_left, 0)} day(s) remaining."
        )

    if total_days > 0:
        time_progress = elapsed_days / total_days
        if total_issues > 0:
            completion_ratio = len(done_issues) / total_issues
        else:
            completion_ratio = 0.0

        parts.append(
            f"Roughly {int(time_progress * 100)}% of the time has elapsed, while about "
            f"{int(completion_ratio * 100)}% of the work is marked done."
        )

        if completion_ratio + 0.15 < time_progress:
            parts.append(
                "Work completion is lagging behind time elapsed, which increases the risk of spillover."
            )
        elif completion_ratio > time_progress + 0.15:
            parts.append(
                "Work completion is ahead of schedule relative to time elapsed, which reduces risk."
            )

    # Risk score hint
    parts.append(f"Current risk score is {sprint.risk_score:.2f} on a 0–1 scale.")

    details = " ".join(parts)
    return summary, details


def generate_alerts_for_sprint(sprint: models.Sprint) -> list[SprintAlert]:
    alerts: list[SprintAlert] = []

    now = datetime.utcnow()
    issues = sprint.issues or []
    open_issues = [i for i in issues if i.status.lower() not in ("done", "resolved", "closed")]
    blockers = [i for i in open_issues if i.is_blocker]

    # 1) High risk sprint
    if sprint.risk_level == "high":
        alerts.append(SprintAlert(
            type="risk",
            level="critical",
            message=f"Sprint '{sprint.name}' is at HIGH risk based on current progress vs. time."
        ))
    elif sprint.risk_level == "medium":
        alerts.append(SprintAlert(
            type="risk",
            level="warning",
            message=f"Sprint '{sprint.name}' is at MEDIUM risk and should be monitored closely."
        ))

    # 2) Blockers open > 1 day
    for blk in blockers:
        if blk.updated_at:
            age = now - blk.updated_at
        elif blk.created_at:
            age = now - blk.created_at
        else:
            age = timedelta(days=0)

        if age >= timedelta(days=1):
            alerts.append(SprintAlert(
                type="blocker",
                level="critical",
                message=(
                    f"Blocker '{blk.key}: {blk.title}' has been open for about "
                    f"{age.days} day(s). It may be blocking other work."
                ),
            ))
        else:
            alerts.append(SprintAlert(
                type="blocker",
                level="warning",
                message=f"Blocker '{blk.key}: {blk.title}' is still open and should be prioritised."
            ))

    # 3) Sprint ending soon with open issues
    days_left = (sprint.end_date - now).days
    if days_left <= 2 and days_left >= 0 and open_issues:
        alerts.append(SprintAlert(
            type="deadline",
            level="warning",
            message=(
                f"Sprint ends in {days_left} day(s) and there are still "
                f"{len(open_issues)} open issue(s)."
            ),
        ))
    elif days_left < 0 and open_issues:
        alerts.append(SprintAlert(
            type="deadline",
            level="critical",
            message=(
                f"Sprint has passed its end date and there are still "
                f"{len(open_issues)} open issue(s)."
            ),
        ))

    # 4) Overloaded assignees (4+ open issues)
    assignee_counts: dict[str, int] = {}
    for i in open_issues:
        if not i.assignee:
            continue
        assignee_counts[i.assignee] = assignee_counts.get(i.assignee, 0) + 1

    overloaded = [a for a, cnt in assignee_counts.items() if cnt >= 4]
    for a in overloaded:
        alerts.append(SprintAlert(
            type="assignee",
            level="info",
            message=(
                f"{a} currently has {assignee_counts[a]} open issues in this sprint; "
                "consider redistributing workload."
            ),
        ))

    return alerts


def _issue_status(issue: models.Issue) -> str:
    return (issue.status or "").lower()


def _last_activity_for_sprint(sprint: models.Sprint) -> datetime:
    candidates: list[datetime] = []
    for issue in sprint.issues or []:
        if issue.updated_at:
            candidates.append(issue.updated_at)
        if issue.created_at:
            candidates.append(issue.created_at)
    if sprint.last_evaluated_at:
        candidates.append(sprint.last_evaluated_at)
    if sprint.start_date:
        candidates.append(sprint.start_date)

    return max(candidates) if candidates else datetime.utcnow()


def build_sprint_insights(sprint: models.Sprint) -> SprintInsights:
    issues = sprint.issues or []
    done_like_statuses = {"done", "resolved", "closed", "completed"}
    open_issues = [i for i in issues if _issue_status(i) not in done_like_statuses]
    blockers = [i for i in issues if i.is_blocker]
    unassigned = [i for i in issues if not i.assignee]

    total_issues = len(issues)
    completed_issues = len([i for i in issues if _issue_status(i) in done_like_statuses])
    progress_pct = (completed_issues / total_issues * 100) if total_issues else 0

    last_activity = _last_activity_for_sprint(sprint)
    now = datetime.utcnow()

    next_steps: list[str] = []
    if not sprint.owner_email:
        next_steps.append("Assign an owner to this sprint.")
    if total_issues == 0:
        next_steps.append("Add at least one task to define execution scope.")
    if open_issues:
        next_steps.append("Review and prioritize open tasks.")
    if not blockers:
        next_steps.append("Identify and log potential risks for this sprint.")
    if last_activity < now - timedelta(days=7):
        next_steps.append("Review sprint status — no updates in the last 7 days.")

    triggered_risks: list[str] = []
    if sprint.start_date and sprint.start_date.date() < now.date() - timedelta(days=14):
        if progress_pct < 30:
            triggered_risks.append("Sprint has low progress relative to its age.")
    if unassigned:
        triggered_risks.append("One or more tasks are unassigned.")
    if blockers:
        triggered_risks.append("Blocked tasks may delay sprint delivery.")
    if sprint.risk_level == "high":
        triggered_risks.append("High-severity risks require mitigation review.")
    if last_activity < now - timedelta(days=10):
        triggered_risks.append("No recent activity detected on this sprint.")

    data_needed: list[str] = []
    titles = [(i.title or "").lower() for i in issues]
    has_data_attachment = any("data" in t or "dashboard" in t or "report" in t for t in titles)
    has_analysis_task = any("analysis" in t or "investigation" in t for t in titles)

    if total_issues == 0:
        data_needed.append("Define KPIs for this sprint.")
    if not has_data_attachment:
        data_needed.append("Upload or link relevant data sources.")
    if has_analysis_task and not has_data_attachment:
        data_needed.append("Attach data required for analysis tasks.")
    if sprint.end_date and not sprint.baseline_date:
        data_needed.append("Set a baseline to measure progress against target.")

    snapshot = SprintSnapshot(
        tasks_total=total_issues,
        tasks_completed=completed_issues,
        risks_open=len(triggered_risks),
        days_active=max(0, (now.date() - sprint.start_date.date()).days)
        if sprint.start_date
        else 0,
    )

    return SprintInsights(
        next_steps=next_steps,
        triggered_risks=triggered_risks,
        data_needed=data_needed,
        snapshot=snapshot,
        label="Generated from current sprint state",
    )


# ---------- Sprints CRUD / listing ----------

@router.post("/", response_model=Sprint)
def create_sprint(
    payload: SprintCreate,
    db: Session = Depends(get_db),
    user_email: str = Depends(get_current_user_email),
):
    project = (
        db.query(models.Project)
        .filter_by(id=payload.project_id, owner_email=user_email)
        .first()
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    sprint = models.Sprint(
        project_id=payload.project_id,
        name=payload.name,
        start_date=payload.start_date or datetime.utcnow(),
        end_date=payload.end_date or datetime.utcnow(),
        baseline_date=payload.baseline_date,
        owner_email=user_email,
    )
    db.add(sprint)
    db.commit()
    db.refresh(sprint)
    return sprint


@router.get("/", response_model=list[Sprint])
def list_sprints(
    db: Session = Depends(get_db),
    company_id: int | None = Query(None, description="Filter by company_id"),
    project_id: int | None = Query(None, description="Filter by project_id"),
    user_email: str = Depends(get_current_user_email),
):
    query = db.query(models.Sprint).join(models.Project)
    query = query.filter(
        or_(
            models.Sprint.owner_email == user_email,
            models.Sprint.collaborators.any(
                models.SprintCollaborator.email == user_email
            ),
        )
    )
    
    if company_id is not None:
        query = query.join(models.Company).filter(models.Company.id == company_id)

    if project_id is not None:
        query = query.filter(models.Sprint.project_id == project_id)

    sprints = query.all()
    return sprints

@router.get("/with_issues", response_model=List[SprintWithIssues])
def list_sprints_with_issues(
    company_id: Optional[int] = None,
    project_id: Optional[int] = None,
    db: Session = Depends(get_db),
    user_email: str = Depends(get_current_user_email),
):
    query = db.query(models.Sprint).filter(
        or_(
            models.Sprint.owner_email == user_email,
            models.Sprint.collaborators.any(
                models.SprintCollaborator.email == user_email
            ),
        )
    )

    if project_id:
        query = query.filter(models.Sprint.project_id == project_id)
    elif company_id:
        query = query.join(models.Project).filter(models.Project.company_id == company_id)

    sprints = query.all()

    for s in sprints:
        _ = s.issues
        compute_risk_for_sprint(s)
    db.commit()

    return sprints


# ---------- Issues ----------

@router.get("/{sprint_id}/issues", response_model=List[IssueSchema])
def list_issues_for_sprint(
    sprint_id: int,
    db: Session = Depends(get_db),
    user_email: str = Depends(get_current_user_email),
):
    sprint = _get_accessible_sprint(sprint_id, user_email, db)

    return sprint.issues


@router.post("/{sprint_id}/issues", response_model=IssueSchema)
def create_issue_for_sprint(
    sprint_id: int,
    payload: IssueCreate,
    db: Session = Depends(get_db),
    user_email: str = Depends(get_current_user_email),
):
    sprint = _get_owned_sprint(sprint_id, user_email, db)


    # Simple auto key generation: SPR-<sprint_id>-<n>
    count = db.query(models.Issue).filter_by(sprint_id=sprint_id).count()
    key = f"SPR-{sprint_id}-{count + 1}"

    issue = models.Issue(
        sprint_id=sprint_id,
        key=key,
        title=payload.title,
        status=payload.status,
        assignee=payload.assignee,
        is_blocker=payload.is_blocker,
    )
    
    db.add(issue)

    # Recompute risk whenever we add an issue
    compute_risk_for_sprint(sprint)
    db.commit()
    db.refresh(issue)
    db.refresh(sprint)
    
    return issue


# ---------- Sprint collaborators / members ----------


@router.get("/{sprint_id}/members", response_model=List[SprintCollaborator])
def list_sprint_members(
    sprint_id: int,
    db: Session = Depends(get_db),
    user_email: str = Depends(get_current_user_email),
):
    sprint = _get_accessible_sprint(sprint_id, user_email, db)
    return sprint.collaborators


@router.post("/{sprint_id}/members", response_model=SprintCollaborator)
def add_sprint_member(
    sprint_id: int,
    payload: SprintCollaboratorCreate,
    db: Session = Depends(get_db),
    user_email: str = Depends(get_current_user_email),
):
    _ = _get_owned_sprint(sprint_id, user_email, db)

    existing = (
        db.query(models.SprintCollaborator)
        .filter_by(sprint_id=sprint_id, email=payload.email)
        .first()
    )
    if existing:
        return existing

    collaborator = models.SprintCollaborator(
        sprint_id=sprint_id,
        email=payload.email,
    )
    db.add(collaborator)
    db.commit()
    db.refresh(collaborator)

    return collaborator


@router.delete("/{sprint_id}/members", status_code=204)
def remove_sprint_member(
    sprint_id: int,
    email: str = Query(..., description="Email of the member to remove"),
    db: Session = Depends(get_db),
    user_email: str = Depends(get_current_user_email),
):
    _ = _get_owned_sprint(sprint_id, user_email, db)

    collaborator = (
        db.query(models.SprintCollaborator)
        .filter_by(sprint_id=sprint_id, email=email)
        .first()
    )
    if not collaborator:
        raise HTTPException(status_code=404, detail="Member not found")

    db.delete(collaborator)
    db.commit()

    return Response(status_code=204)


# ---------- Sprint details & risk ----------

@router.get("/{sprint_id}", response_model=SprintWithIssues)
def get_sprint(
    sprint_id: int,
    db: Session = Depends(get_db),
    user_email: str = Depends(get_current_user_email),
):
    sprint = _get_accessible_sprint(sprint_id, user_email, db)

    _ = sprint.issues
    compute_risk_for_sprint(sprint)
    db.commit()
    db.refresh(sprint)

    return sprint


@router.get("/{sprint_id}/alerts", response_model=List[SprintAlert])
def get_sprint_alerts(
    sprint_id: int,
    db: Session = Depends(get_db),
    user_email: str = Depends(get_current_user_email),
):
    sprint = _get_accessible_sprint(sprint_id, user_email, db)
    
    # Ensure issues are loaded
    _ = sprint.issues

    # Recompute risk so alerts are up to date
    compute_risk_for_sprint(sprint)
    db.commit()
    db.refresh(sprint)

    alerts = generate_alerts_for_sprint(sprint)
    return alerts


@router.get("/risk/{sprint_id}", response_model=SprintRiskReport)
def get_sprint_risk(
    sprint_id: int,
    db: Session = Depends(get_db),
    user_email: str = Depends(get_current_user_email),
):
    sprint = _get_accessible_sprint(sprint_id, user_email, db)

    # Ensure issues are loaded
    _ = sprint.issues

    # Recompute risk before generating explanation
    compute_risk_for_sprint(sprint)
    db.commit()
    db.refresh(sprint)

    summary, details = generate_risk_explanation(sprint)

    return SprintRiskReport(
        sprint_id=sprint.id,
        risk_level=sprint.risk_level,
        risk_score=sprint.risk_score,
        summary=summary,
        details=details,
    )

@router.get("/{sprint_id}/insights", response_model=SprintInsights)
def get_sprint_insights(
    sprint_id: int,
    db: Session = Depends(get_db),
    user_email: str = Depends(get_current_user_email),
):
    sprint = _get_accessible_sprint(sprint_id, user_email, db)

    # Ensure issues are loaded for deterministic signals
    _ = sprint.issues

    insights = build_sprint_insights(sprint)
    return insights


# ---------- Filters metadata for dashboard ----------

@router.get("/filters", response_model=dict)
def get_filter_metadata(
    db: Session = Depends(get_db),
    user_email: str = Depends(get_current_user_email),
):
    companies = db.query(models.Company).filter_by(owner_email=user_email).all()
    projects = db.query(models.Project).filter_by(owner_email=user_email).all()

    return {
        "companies": [{"id": c.id, "name": c.name} for c in companies],
        "projects": [
            {"id": p.id, "name": p.name, "company_id": p.company_id} for p in projects
        ],
    }
