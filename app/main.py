import os
from typing import Optional

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from .database import get_db, SessionLocal
from .ai_logic import run_ai_coo_logic
from .database import Base, engine
from .routers import auth, companies, integrations, sprints
from . import models  # register models
from .models import AiTaskLog, Task
from .schemas import TaskCreate, TaskUpdate
from .supabase_client import SUPABASE_AVAILABLE, supabase

Base.metadata.create_all(bind=engine)

app = FastAPI(title="WorkYodha AI COO for SaaS")
templates = Jinja2Templates(directory="app/templates")


@app.get("/")
async def health_check():
    return {
        "status": "ok",
        "app": "WorkYodha AI COO backend running",
    }

def log_task_event(
    db: Session,
    task: Task,
    event: str,
    old_status: str | None,
    new_status: str | None,
):

    log = AiTaskLog(
        task_id=task.id,
        event=event,
        old_status=old_status,
        new_status=new_status,
        result_text=task.result_text,
    )
    db.add(log)
    db.commit()

def process_task_in_background(task_id: int):


    """
    Background worker:
    - Loads the task
    - Marks it in_progress
    - Runs AI logic
    - Marks it completed or failed
    """
    db = SessionLocal()
    try:
        print(f"[BG] Starting background processing for task_id={task_id}")
        task = db.get(Task, task_id)
        if not task:
            print(f"[BG] Task {task_id} not found, aborting")
            return

        # 1) -> in_progress
        old_status = task.status
        task.status = "in_progress"
        db.commit()

        log_task_event(
            db=db,
            task=task,
            event="status_change",
            old_status=old_status,
            new_status=task.status,
        )
        # log_task_event now commits internally

        try:
            # 2) Run AI logic
            print(f"[BG] Running AI COO logic for task_id={task_id}")
            result_text = run_ai_coo_logic(task)

            # 3) -> completed
            old_status = task.status
            task.status = "completed"
            task.result_text = result_text
            db.commit()
            db.refresh(task)

            log_task_event(
                db=db,
                task=task,
                event="status_change",
                old_status=old_status,
                new_status=task.status,
            )
            print(f"[BG] Task {task_id} completed successfully")

        except Exception as e:
            # If AI logic crashes, mark task as failed so you see it
            print(f"[BG] Error while processing task {task_id}: {e!r}")

            old_status = task.status
            task.status = "failed"
            # keep message short; you can expand later
            task.result_text = f"Background error: {e}"
            db.commit()
            db.refresh(task)

            log_task_event(
                db=db,
                task=task,
                event="error",
                old_status=old_status,
                new_status=task.status,
            )
    finally:
        db.close()
        print(f"[BG] Closed DB session for task_id={task_id}")

def serialize_task(task: Task) -> dict:
    """Return a JSON-safe dictionary for a Task ORM object."""

    return {
        "id": task.id,
        "title": task.title,
        "status": task.status,
        "company_id": task.company_id,
        "squad": task.squad,
        "metadata_json": task.metadata_json or {},
        "result_text": task.result_text,
        "created_at": task.created_at.isoformat() if task.created_at else None,
    }

# Routers
app.include_router(integrations.router, prefix="/integrations", tags=["integrations"])
app.include_router(sprints.router, prefix="/sprints", tags=["sprints"])
app.include_router(companies.router)
app.include_router(auth.router, tags=["auth"])


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    db: Session = Depends(get_db),
):
    tasks = db.query(Task).order_by(Task.created_at.desc()).limit(100).all()
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

# ---------- Task endpoints (database-backed) ---------


@app.post("/tasks")
async def create_task(task: TaskCreate, db: Session = Depends(get_db)):
    """
    Create a new task in the local database.
    """
    try:
        db_task = Task(
            title=task.title,
            status="pending",
            metadata_json=task.metadata or {},
            company_id=task.company_id,
            squad=task.squad,
        )
        db.add(db_task)
        db.commit()
        db.refresh(db_task)
        return {"ok": True, "task": serialize_task(db_task)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/tasks")
def list_tasks(
    db: Session = Depends(get_db),
    company_id: int | None = None,
    squad: str | None = None,
    status: Optional[str] = Query(
        None,
        description="Filter by status: pending, in_progress, completed, failed",
    ),
    limit: int = 50,
):
    query = db.query(Task).order_by(Task.created_at.desc())
    if company_id is not None:
        query = query.filter(Task.company_id == company_id)
    if squad is not None:
        query = query.filter(Task.squad == squad)
    if status is not None:
        query = query.filter(Task.status == status)
    tasks = query.limit(limit).all()
    return {"ok": True, "tasks": [serialize_task(t) for t in tasks]}


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
        }
        for t in tasks
    ]


@app.patch("/tasks/{task_id}")
async def update_task(task_id: int, update: TaskUpdate, db: Session = Depends(get_db)):
    """
    Update a task's status.
    """
    try:
        db_task = db.get(Task, task_id)
        if not db_task:
            raise HTTPException(status_code=404, detail="Task not found")

        if update.status is not None:
            db_task.status = update.status
            
        if update.result_text is not None:
            db_task.result_text = update.result_text

        if update.metadata is not None:
            db_task.metadata_json = update.metadata

        db.commit()
        db.refresh(db_task)
        return {"ok": True, "task": serialize_task(db_task)}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ---------------------------
# AI COO RUN TASK ENDPOINTS
# ---------------------------


@app.post("/tasks/run_async")
def run_task_async(
    payload: TaskCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):

    # 1. Create the task in "pending" state
    task = Task(
        title=payload.title,
        status="pending",
        result_text=None,
        metadata_json=payload.metadata or {},
        company_id=getattr(payload, "company_id", None),
        squad=getattr(payload, "squad", None),
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    # TEMPORARILY disable event logging
    # log_task_event(...)

    background_tasks.add_task(process_task_in_background, task.id)

    # Return immediately
    return {
        "ok": True,
        "task": {
            "id": task.id,
            "title": task.title,
            "status": task.status,  # pending
            "metadata_json": task.metadata_json,
            "created_at": task.created_at.isoformat(),
            "company_id": getattr(task, "company_id", None),
            "squad": getattr(task, "squad", None),
        },
    }


@app.post("/tasks/run")
def run_task(
    payload: TaskCreate,
    db: Session = Depends(get_db),
):
    # 1. Create the task in "pending" state
    task = Task(
        title=payload.title,
        status="pending",
        result_text=None,
        metadata_json=payload.metadata or {},
        company_id=payload.company_id,
        squad=payload.squad,
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    # Log creation
    log_task_event(
        db=db,
        task=task,
        event="created",
        old_status=None,
        new_status=task.status,
    )
    db.commit()

    # 2. Mark as in_progress and log that
    old_status = task.status
    task.status = "in_progress"
    db.commit()

    log_task_event(
        db=db,
        task=task,
        event="status_change",
        old_status=old_status,
        new_status=task.status,
    )
    db.commit()

    # 3. Run the AI COO logic synchronously (with fallback)
    result_text = run_ai_coo_logic(task)

    # 4. Mark as completed, save result, and log final status
    old_status = task.status
    task.status = "completed"
    task.result_text = result_text
    db.commit()
    db.refresh(task)

    log_task_event(
        db=db,
        task=task,
        event="status_change",
        old_status=old_status,
        new_status=task.status,
    )
    db.commit()

    # 5. Return a plain dict (no ORM / Pydantic magic)
    return {
        "ok": True,
        "task": serialize_task(task),
    }


@app.get("/tasks/{task_id}")
def get_task(task_id: int, db: Session = Depends(get_db)):
    """
    Return full info for a single task.
    """
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # reuse existing serializer
    return {"ok": True, "task": serialize_task(task)}


@app.get("/tasks/{task_id}/status")
def get_task_status(task_id: int, db: Session = Depends(get_db)):
    """
    Lightweight endpoint to poll status from CLI or frontend.
    """
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    return {
        "ok": True,
        "id": task.id,
        "title": task.title,
        "status": task.status,
        "result_text": task.result_text,
    }


@app.post("/tasks/run_debug")
def run_task_debug(
    payload: TaskCreate,
    db: Session = Depends(get_db),
):
    # 1. Create the task in "pending" state
    task = Task(
        title=payload.title,
        status="pending",
        result_text=None,
        metadata_json=payload.metadata or {},
        company_id=payload.company_id,
        squad=payload.squad,
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    # Log creation
    log_task_event(
        db=db,
        task=task,
        event="created",
        old_status=None,
        new_status=task.status,
    )
    db.commit()

    # 2. Mark as in_progress and log that
    old_status = task.status
    task.status = "in_progress"
    db.commit()

    log_task_event(
        db=db,
        task=task,
        event="status_change",
        old_status=old_status,
        new_status=task.status,
    )
    db.commit()

    # 3. Run the AI COO logic synchronously (with fallback)
    result_text = run_ai_coo_logic(task)

    # 4. Mark as completed, save result, and log final status
    old_status = task.status
    task.status = "completed"
    task.result_text = result_text
    db.commit()
    db.refresh(task)

    log_task_event(
        db=db,
        task=task,
        event="status_change",
        old_status=old_status,
        new_status=task.status,
    )
    db.commit()

    # 5. Return a raw dict (no Pydantic/ORM magic)
    return {
        "ok": True,
        "task": {
            "id": task.id,
            "title": task.title,
            "status": task.status,
            "company_id": task.company_id,
            "squad": task.squad,
            "metadata_json": task.metadata_json,
            "result_text": task.result_text,
            "created_at": task.created_at.isoformat(),
        },
    }


@app.get("/tasks/{task_id}/logs")
def get_task_logs(task_id: int, db: Session = Depends(get_db)):
    try:
        # Do NOT load Task here (table schema mismatch on company_id)
        logs = (
            db.query(AiTaskLog)
            .filter(AiTaskLog.task_id == task_id)
            .order_by(AiTaskLog.created_at.asc())
            .all()
        )

        # If you want a 404 when no logs exist:
        if not logs:
            raise HTTPException(status_code=404, detail="No logs found for this task")

        result = []
        for log in logs:
            if log is None:
                continue

            created_at_value = (
                log.created_at.isoformat() if getattr(log, "created_at", None) else None
            )

            result.append(
                {
                    "id": log.id,
                    "task_id": log.task_id,
                    "event": log.event,
                    "old_status": log.old_status,
                    "new_status": log.new_status,
                    "created_at": created_at_value,
                    "has_result_text": bool(getattr(log, "result_text", None)),
                }
            )

        return result
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - defensive guard against DB errors
        raise HTTPException(status_code=500, detail=f"Failed to fetch task logs: {exc}")


@app.get("/tasks/{task_id}/logs_debug")
def get_task_logs_debug(task_id: int, db: Session = Depends(get_db)):
    logs = db.query(AiTaskLog).filter(AiTaskLog.task_id == task_id).all()

    # Just return ID + event; no dates, no extra serialization
    return [
        {
            "id": log.id,
            "task_id": log.task_id,
            "event": log.event,
        }
        for log in logs
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



