from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import models
from ..deps import get_db
from ..schemas import Issue, IssueCreate, Sprint, SprintCreate, SprintWithIssues

router = APIRouter()


def compute_risk_for_sprint(sprint: models.Sprint) -> None:
    """
    Simple heuristic:
    - % incomplete issues vs days remaining
    - if many incomplete and little time => high risk
    """
    now = datetime.utcnow()
    total_issues = len(sprint.issues)
    
    if total_issues == 0:
        sprint.risk_score = 0.0
        sprint.risk_level = "low"
        sprint.last_evaluated_at = now
        return

    incomplete = [
        i for i in sprint.issues if i.status.lower() not in ("done", "resolved", "closed")
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

    # clamp between 0 and 1
    risk_score = max(0.0, min(1.0, risk_score))

    if risk_score > 0.7:
        level = "high"
    elif risk_score > 0.4:
        level = "medium"
    else:
        level = "low"

    sprint.risk_score = risk_score
    sprint.risk_level = level
    sprint.last_evaluated_at = now


@router.post("/", response_model=Sprint)
def create_sprint(payload: SprintCreate, db: Session = Depends(get_db)):
    # ensure project exists
    project = db.query(models.Project).filter_by(id=payload.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    sprint = models.Sprint(
        project_id=payload.project_id,
        name=payload.name,
        start_date=payload.start_date or datetime.utcnow(),
        end_date=payload.end_date or datetime.utcnow(),
    )
    db.add(sprint)
    db.commit()
    db.refresh(sprint)
    return sprint


@router.get("/", response_model=list[Sprint])
def list_sprints(
    db: Session = Depends(get_db),
    project_id: int | None = Query(None, description="Filter by project_id"),
):
    query = db.query(models.Sprint)
    if project_id is not None:
        query = query.filter(models.Sprint.project_id == project_id)
    sprints = query.all()
    return sprints


@router.post("/{sprint_id}/issues", response_model=Issue)
def create_issue_for_sprint(
    sprint_id: int, payload: IssueCreate, db: Session = Depends(get_db)
):
    sprint = db.query(models.Sprint).filter_by(id=sprint_id).first()
    if not sprint:
        raise HTTPException(status_code=404, detail="Sprint not found")

    issue = models.Issue(
        sprint_id=sprint_id,
        key=payload.key,
        title=payload.title,
        status=payload.status,
        assignee=payload.assignee,
        is_blocker=payload.is_blocker,
    )
    db.add(issue)
    db.commit()
    db.refresh(issue)

    return issue


@router.get("/{sprint_id}", response_model=SprintWithIssues)
def get_sprint(sprint_id: int, db: Session = Depends(get_db)):
    sprint = db.query(models.Sprint).filter_by(id=sprint_id).first()
    if not sprint:
        raise HTTPException(status_code=404, detail="Sprint not found")

    # Ensure issues are loaded
    _ = sprint.issues

    # Recompute risk when fetched (you can move this to a background job)
    compute_risk_for_sprint(sprint)
    db.commit()
    db.refresh(sprint)

    return sprint


@router.get("/{sprint_id}/risk", response_model=dict)
def get_sprint_risk_summary(sprint_id: int, db: Session = Depends(get_db)):
    sprint = db.query(models.Sprint).filter_by(id=sprint_id).first()
    if not sprint:
        raise HTTPException(status_code=404, detail="Sprint not found")

    # ensure issues loaded
    _ = sprint.issues
    compute_risk_for_sprint(sprint)
    db.commit()
    db.refresh(sprint)

    total = len(sprint.issues)
    incomplete = [
        i for i in sprint.issues if i.status.lower() not in ("done", "resolved", "closed")
    ]
    blockers = [i for i in sprint.issues if i.is_blocker]

    explanation = (
        f"Sprint '{sprint.name}' is currently rated as {sprint.risk_level.upper()} risk "
        f"with a score of {sprint.risk_score:.2f}. "
        f"{len(incomplete)} out of {total} issues are still open, "
        f"and {len(blockers)} are marked as blockers. "
        f"End date: {sprint.end_date.date()}."
    )

    return {
        "id": sprint.id,
        "name": sprint.name,
        "risk_level": sprint.risk_level,
        "risk_score": sprint.risk_score,
        "open_issues": len(incomplete),
        "total_issues": total,
        "blockers": len(blockers),
        "last_evaluated_at": sprint.last_evaluated_at,
        "explanation": explanation,
    }
