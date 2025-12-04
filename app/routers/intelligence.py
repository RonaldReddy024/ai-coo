from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user_email
from ..models import Task
from ..services.intelligence import (
    build_execution_plan,
    classify_priority,
    evaluate_task_risk,
    generate_project_breakdown,
    suggest_load_balance,
    summarize_sprint_health,
)


router = APIRouter(prefix="/intelligence", tags=["intelligence"])


class BreakdownRequest(BaseModel):
    title: str
    squad: Optional[str] = None


@router.get("/analysis")
def get_intelligence_view(
    db: Session = Depends(get_db),
    user_email: str = Depends(get_current_user_email),
):
    tasks = db.query(Task).filter(Task.owner_email == user_email).all()

    risk_cards = []
    for task in tasks:
        score, level, reasons = evaluate_task_risk(task, tasks)
        risk_cards.append(
            {
                "id": task.id,
                "title": task.title,
                "risk_score": score,
                "risk_level": level,
                "reasons": reasons,
                "priority": classify_priority(task),
                "status": task.status,
            }
        )

    return {
        "ok": True,
        "tasks_analyzed": len(tasks),
        "risk": sorted(risk_cards, key=lambda t: t["risk_score"], reverse=True),
        "load_balance": suggest_load_balance(tasks),
        "execution_plan": build_execution_plan(tasks),
        "sprint_summary": summarize_sprint_health(tasks),
    }


@router.post("/breakdown")
def create_breakdown(payload: BreakdownRequest):
    return generate_project_breakdown(title=payload.title, squad=payload.squad)
