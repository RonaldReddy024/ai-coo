import os

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from .ai_logic import run_ai_coo_logic
from .database import Base, SessionLocal, engine, get_db
from .routers import auth, companies, integrations, sprints
from . import models  # register models
from .models import Task, AiTaskLog
from .schemas import TaskCreate, TaskUpdate
from .supabase_client import SUPABASE_AVAILABLE, supabase

Base.metadata.create_all(bind=engine)

app = FastAPI(title="WorkYodha AI COO for SaaS")


def log_task_event(
    db: Session,
    task: Task,
    event: str,
    old_status: str | None,
    new_status: str | None,
):
    """
    Record a single log entry for a task.
    Does NOT commit by itself; caller decides when to commit.
    """
    log = AiTaskLog(
        task_id=task.id,
        event=event,
        old_status=old_status,
        new_status=new_status,
        result_text=task.result_text,
    )
    db.add(log)

# Routers
app.include_router(integrations.router, prefix="/integrations", tags=["integrations"])
app.include_router(sprints.router, prefix="/sprints", tags=["sprints"])
app.include_router(companies.router)
app.include_router(auth.router, tags=["auth"])


# Landing page redirects to login for now
@app.get("/")
async def root_redirect():
    return RedirectResponse(url="/login")


# Dashboard placeholder
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    return """
    <html>
      <head><title>AI COO Dashboard</title></head>
      <body style=\"font-family: system-ui; background:#020617; color:#e5e7eb;\">
        <h1>WorkYodha AI COO</h1>
        <p>You are logged in via Supabase magic link ✅</p>
        <p>We’ll replace this with the real sprint dashboard later.</p>
        <a href=\"/sprints-dashboard\" style=\"color:#a855f7;\">Go to Sprint Risks</a>
      </body>
    </html>
    """


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
        )
        db.add(db_task)
        db.commit()
        db.refresh(db_task)
        return {"ok": True, "task": db_task}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/tasks")
async def list_tasks(limit: int = 20, db: Session = Depends(get_db)):
    """
    List tasks from the local database.
    """
    try:
        tasks = db.query(Task).order_by(Task.created_at.desc()).limit(limit).all()
        return {"ok": True, "count": len(tasks), "data": tasks}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
        return {"ok": True, "task": db_task}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ---------------------------
# AI COO RUN TASK ENDPOINT
# ---------------------------

def process_task_in_background(task_id: int):
    """
    Runs the AI-COO logic in the background and updates the DB.
    This is triggered by BackgroundTasks in /tasks/run.
    """
    db = SessionLocal()
    try:
        task = db.get(Task, task_id)
        if not task:
            return

        # Mark as in progress
        task.status = "in_progress"
        db.commit()

        # This will either call OpenAI or the local fallback, but it should NOT raise
        result_text = run_ai_coo_logic(task)

        # Mark as completed with result
        task.status = "completed"
        task.result_text = result_text
        db.commit()
        
    except Exception as e:
        # Only truly unexpected errors land here
        task = db.get(Task, task_id)
        if task:
            task.status = "failed"
            task.result_text = f"Unexpected error while processing task: {e}"
            db.commit()
    finally:
        db.close()


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

    return {"ok": True, "task": task}


@app.get("/tasks/{task_id}/logs")
def get_task_logs(task_id: int, db: Session = Depends(get_db)):
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    logs = (
        db.query(AiTaskLog)
        .filter(AiTaskLog.task_id == task_id)
        .order_by(AiTaskLog.created_at.asc())
        .all()
    )

    # Return clean JSON instead of raw ORM objects
    return [
        {
            "id": log.id,
            "task_id": log.task_id,
            "event": log.event,
            "old_status": log.old_status,
            "new_status": log.new_status,
            "created_at": log.created_at.isoformat(),
            "has_result_text": bool(log.result_text),
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



@app.get("/tasks/{task_id}")
def get_task(task_id: int, db: Session = Depends(get_db)):
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task
