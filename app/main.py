import os
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from . import models  # register models
from .database import Base, engine, ensure_sqlite_schema, get_db
from .models import Task
from .routers import auth, companies, integrations, sprints, tasks
from .supabase_client import SUPABASE_AVAILABLE, supabase

Base.metadata.create_all(bind=engine)
ensure_sqlite_schema(engine)

app = FastAPI(title="WorkYodha AI COO for SaaS")
templates = Jinja2Templates(directory="app/templates")


@app.get("/")
async def health_check():
    return {
        "status": "ok",
        "app": "WorkYodha AI COO backend running",
    }


app.include_router(integrations.router, prefix="/integrations", tags=["integrations"])
app.include_router(sprints.router, prefix="/sprints", tags=["sprints"])
app.include_router(companies.router)
app.include_router(auth.router, tags=["auth"])
app.include_router(tasks.router)


def _parse_section_block(text: str, header: str) -> list[str]:
    if not text:
        return []
    marker = header + "\n"
    start = text.find(marker)
    if start == -1:
        return []
    start += len(marker)
    end = text.find("\n\n", start)
    if end == -1:
        end = len(text)
    block = text[start:end].strip()
    lines = []
    for line in block.splitlines():
        line = line.strip()
        if line.startswith("- "):
            line = line[2:]
        if line:
            lines.append(line)
    return lines


@app.get("/tasks")
def list_tasks(
    limit: int = 100,
    status: Optional[str] = None,
    squad: Optional[str] = None,
    company_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """
    List recent tasks for the dashboard.
    Supports optional filters: status, squad, company_id.
    """
    query = db.query(models.Task).order_by(models.Task.created_at.desc())

    if status:
        query = query.filter(models.Task.status == status)

    if squad:
        query = query.filter(models.Task.squad == squad)

    if company_id is not None:
        query = query.filter(models.Task.company_id == company_id)

    tasks = query.limit(limit).all()
    return {"ok": True, "tasks": tasks}


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    db: Session = Depends(get_db),
):
    tasks = (
        db.query(Task)
        .order_by(Task.created_at.desc())
        .limit(100)
        .all()
    )
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "tasks": tasks,
        },
    )


@app.get("/tasks/{task_id}/view", response_class=HTMLResponse)
def task_detail_page(
    task_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    result_text = task.result_text or ""

    steps = _parse_section_block(result_text, "Steps:")
    risks = _parse_section_block(result_text, "Risks:")
    data_needed = _parse_section_block(result_text, "DataNeeded:")

    description = ""
    if result_text:
        description = result_text.split("\n\n", 1)[0]

    provider_status = (task.external_provider_status or "ok").lower()
    if provider_status == "fallback_insufficient_quota":
        provider_status_pretty = "Fallback (quota / insufficient credits)"
    elif provider_status.startswith("fallback"):
        provider_status_pretty = "Fallback (external error)"
    else:
        provider_status_pretty = "External AI OK"

    # ── NEW: related tasks in same company + squad ─────────────────
    upstream_tasks = []
    downstream_tasks = []
    blocking_upstream = []

    if task.company_id is not None and task.squad:
        base_q = (
            db.query(Task)
            .filter(
                Task.company_id == task.company_id,
                Task.squad == task.squad,
                Task.id != task.id,
            )
        )

        upstream_tasks = (
            base_q.filter(Task.created_at < task.created_at)
            .order_by(Task.created_at.desc())
            .limit(5)
            .all()
        )

        downstream_tasks = (
            base_q.filter(Task.created_at > task.created_at)
            .order_by(Task.created_at.asc())
            .limit(5)
            .all()
        )

        blocking_upstream = [t for t in upstream_tasks if t.status != "completed"]

    context = {
        "request": request,
        "task": task,
        "description": description,
        "steps": steps,
        "risks": risks,
        "data_needed": data_needed,
        "provider_status_pretty": provider_status_pretty,
        "provider_status": provider_status,
        "upstream_tasks": upstream_tasks,
        "downstream_tasks": downstream_tasks,
        "blocking_upstream": blocking_upstream,
    }
    return templates.TemplateResponse("task_detail.html", context)


# Optional: simple health endpoint
@app.get("/api/health")
def health():
    return {"status": "ok", "app": "WorkYodha AI COO backend running"}


@app.get("/supabase-test")
async def supabase_test():
    if not SUPABASE_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="Supabase is not configured on this server.",
        )

    try:
        response = supabase.table("ai_tasks").select("*").limit(5).execute()
        return {
            "ok": True,
            "count": len(response.data or []),
            "data": response.data,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/companies/{company_id}/tasks")
def list_company_tasks(
    company_id: int,
    squad: str | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(Task).filter(Task.company_id == company_id)

    if squad:
        query = query.filter(Task.squad == squad)

    tasks = query.order_by(Task.created_at.desc()).all()

    return [
        {
            "id": t.id,
            "title": t.title,
            "status": t.status,
            "squad": t.squad,
            "metadata_json": t.metadata_json or {},
            "created_at": t.created_at.isoformat(),
            "external_provider_status": getattr(t, "external_provider_status", None),
        }
        for t in tasks
    ]


def run():
    """Launch a development server if the module is executed directly."""

    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", 8000)),
        reload=bool(os.getenv("RELOAD", "False").lower() == "true"),
    )


if __name__ == "__main__":
    run()
