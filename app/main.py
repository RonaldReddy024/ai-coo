from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel

from .database import Base, engine
from .routers import companies, integrations, sprints, auth
from . import models  # register models
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



# ---------- Pydantic models ----------


class TaskCreate(BaseModel):
    title: str


class TaskUpdate(BaseModel):
    status: str | None = None


# ---------- Routes using Supabase ----------


@app.post("/tasks")
async def create_task(task: TaskCreate):
    """
    Create a new task in ai_tasks table.
    """
    try:
        payload = {
            "title": task.title,
            # status will default to 'pending' in DB
        }
        response = supabase.table("ai_tasks").insert(payload).execute()
        return {
            "ok": True,
            "data": response.data,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/tasks")
async def list_tasks(limit: int = 20):
    """
    List tasks from ai_tasks.
    """
    try:
        response = (
            supabase.table("ai_tasks")
            .select("*")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return {
            "ok": True,
            "count": len(response.data or []),
            "data": response.data,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.patch("/tasks/{task_id}")
async def update_task(task_id: int, update: TaskUpdate):
    """
    Update a task's status.
    """
    try:
        update_data = {}
        if update.status is not None:
            update_data["status"] = update.status

        if not update_data:
            raise HTTPException(status_code=400, detail="No fields to update")

        response = (
            supabase.table("ai_tasks")
            .update(update_data)
            .eq("id", task_id)
            .execute()
        )
        return {
            "ok": True,
            "data": response.data,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ---------------------------
# AI COO RUN TASK ENDPOINT
# ---------------------------

from typing import Any, Optional

def run_ai_coo_logic(title: str, metadata: Optional[dict[str, Any]] = None) -> str:
    """
    Placeholder for your real AI COO workflow.

    For now, it returns a simple string.
    """
    base = f"AI-COO processed task: {title}"
    if metadata:
        base += f" | metadata keys: {', '.join(metadata.keys())}"
    return base


@app.post("/tasks/run")
async def run_task(task: TaskCreate):
    """
    Create a task, run AI COO logic, store result, and return updated task.
    """
    try:
        # Create the task first
        insert_payload: dict[str, Any] = {
            "title": task.title,
            "status": "pending",
        }
        if task.metadata is not None:
            insert_payload["metadata"] = task.metadata

        insert_resp = supabase.table("ai_tasks").insert(insert_payload).execute()

        created_task = insert_resp.data[0]
        task_id = created_task["id"]

        # Run the AI logic
        result = run_ai_coo_logic(task.title, task.metadata)

        # Update the task with result
        update_payload = {
            "status": "completed",
            "result_text": result,
        }

        update_resp = (
            supabase.table("ai_tasks")
            .update(update_payload)
            .eq("id", task_id)
            .execute()
        )

        updated_task = update_resp.data[0]

        return {
            "ok": True,
            "task": updated_task,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
