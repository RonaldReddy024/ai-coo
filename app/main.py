from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from .ai_logic import run_ai_coo_logic
from .database import Base, SessionLocal, engine
from .deps import get_db
from .routers import auth, companies, integrations, sprints
from . import models  # register models
from .models import Task
from .schemas import TaskCreate, TaskUpdate
from .supabase_client import supabase

Base.metadata.create_all(bind=engine)

app = FastAPI(title="WorkYodha AI COO for SaaS")

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
    """Runs the AI-COO logic in the background and updates the DB."""
    db = SessionLocal()
    try:
        task = db.get(Task, task_id)
        if not task:
            return

        # Mark as in progress
        task.status = "in_progress"
        db.commit()

        # Run your AI COO logic (this can be slow)
        result_text = run_ai_coo_logic(task)

        # Save result
        task.status = "completed"
        task.result_text = result_text
        db.commit()
    except Exception as e:
        # Basic failure handling
        task = db.get(Task, task_id)
        if task:
            task.status = "failed"
            task.result_text = f"Error while processing task: {e}"
            db.commit()
    finally:
        db.close()


@app.post("/tasks/run")
def run_task(
    payload: TaskCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Create a task, run AI COO logic, store result, and return updated task.
    """
    try:
        # 1. Create the task as "pending"
        task = Task(
            title=payload.title,
            status="pending",
            result_text=None,
            metadata_json=payload.metadata or {},
        )
        db.add(task)
        db.commit()
        db.refresh(task)
       
        # 2. Enqueue background processing
        background_tasks.add_task(process_task_in_background, task.id)
       
        # 3. Return immediately
        return {"ok": True, "task": task}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



@app.get("/tasks/{task_id}")
def get_task(task_id: int, db: Session = Depends(get_db)):
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task
