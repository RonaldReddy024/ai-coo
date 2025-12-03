import os
from typing import Optional

from fastapi import FastAPI, Depends, Request
from fastapi import HTTPException
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
