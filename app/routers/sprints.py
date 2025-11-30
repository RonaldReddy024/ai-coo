from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, timedelta

from ..deps import get_db
from .. import models
from ..schemas import SprintWithIssues

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

    incomplete = [i for i in sprint.issues if i.status.lower() not in ("done", "resolved", "closed")]
    incomplete_ratio = len(incomplete) / total_issues

    # Time factor
    total_days = (sprint.end_date - sprint.start_date).days or 1
    days_left = (sprint.end_date - now).days
    days_progress = max(0, min(1, (total_days - days_left) / total_days))

    # Simple risk formula
    risk_score = incomplete_ratio * 0.7 + days_progress * 0.3

    if risk_score > 0.7:
        level = "high"
    elif risk_score > 0.4:
        level = "medium"
    else:
        level = "low"

    sprint.risk_score = risk_score
    sprint.risk_level = level
    sprint.last_evaluated_at = now


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
