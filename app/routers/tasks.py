from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from ..ai_logic import run_ai_coo_logic
from ..database import SessionLocal, get_db
from ..deps import get_current_user_email
from ..models import AiTaskLog, Task
from ..schemas import TaskCreate, TaskUpdate
from ..services.task_logic import analyze_task_relationships

router = APIRouter(prefix="/tasks", tags=["tasks"])


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

        # 2) Run AI logic
        print(f"[BG] Running AI COO logic for task_id={task_id}")
        result_text, provider_status = run_ai_coo_logic(
            title=task.title,
            metadata=getattr(task, "metadata_json", {}) or {},
        )

        # 3) -> completed (even if we fell back locally)
        old_status = task.status
        task.status = "completed"
        task.result_text = result_text
        task.external_provider_status = provider_status
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
        "owner_email": task.owner_email,
        "prerequisite_task_id": getattr(task, "prerequisite_task_id", None),
        "metadata_json": task.metadata_json or {},
        "result_text": task.result_text,
        "external_provider_status": getattr(task, "external_provider_status", None),
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "next_steps": getattr(task, "next_steps", None),
    }


def apply_relationships_and_next_steps(db: Session, task: Task):
    task.next_steps = analyze_task_relationships(db, task)

    if not task.result_text:
        task.result_text = f"AI-COO processed task: {task.title}"

    db.commit()
    db.refresh(task)

    
@router.post("/recompute_next_steps")
def recompute_next_steps(db: Session = Depends(get_db)):
    tasks = db.query(Task).all()
    for task in tasks:
        task.next_steps = analyze_task_relationships(db, task)
        if not task.result_text:
            task.result_text = f"AI-COO processed task: {task.title}"
    db.commit()
    return {"ok": True, "updated": len(tasks)}


@router.get("/", name="list_tasks")
def list_tasks(
    limit: int = 100,
    status: str | None = None,
    squad: str | None = None,
    company_id: int | None = None,
    db: Session = Depends(get_db),
    user_email: str = Depends(get_current_user_email),
):
    """
    List recent tasks for the dashboard.
    Supports optional filters: status, squad, company_id.
    """
    query = (
        db.query(Task)
        .filter(Task.owner_email == user_email)
        .order_by(Task.created_at.desc())
    )

    if status:
        query = query.filter(Task.status == status)

    if squad:
        query = query.filter(Task.squad == squad)

    if company_id is not None:
        query = query.filter(Task.company_id == company_id)

    tasks = query.limit(limit).all()
    return {"ok": True, "tasks": tasks}


@router.post("")
async def create_task(
    task: TaskCreate,
    db: Session = Depends(get_db),
    user_email: str = Depends(get_current_user_email),
):
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
            owner_email=user_email,
            prerequisite_task_id=task.prerequisite_task_id,
        )
        db.add(db_task)
        db.commit()
        db.refresh(db_task)
        apply_relationships_and_next_steps(db, db_task)
        return {"ok": True, "task": serialize_task(db_task)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{task_id}")
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

        if update.external_provider_status is not None:
            db_task.external_provider_status = update.external_provider_status
            
        if update.prerequisite_task_id is not None:
            db_task.prerequisite_task_id = update.prerequisite_task_id

        db.commit()
        db.refresh(db_task)
        return {"ok": True, "task": serialize_task(db_task)}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/run_async")
def run_task_async(
    payload: TaskCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user_email: str = Depends(get_current_user_email),
):

    # 1. Create the task in "pending" state
    task = Task(
        title=payload.title,
        status="pending",
        result_text=None,
        metadata_json=payload.metadata or {},
        company_id=getattr(payload, "company_id", None),
        squad=getattr(payload, "squad", None),
        owner_email=user_email,
        prerequisite_task_id=getattr(payload, "prerequisite_task_id", None),
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    apply_relationships_and_next_steps(db, task)

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
            "owner_email": getattr(task, "owner_email", None),
            "prerequisite_task_id": getattr(task, "prerequisite_task_id", None),
            "external_provider_status": getattr(task, "external_provider_status", None),
        },
    }


@router.post("/run")
def run_task(
    payload: TaskCreate,
    db: Session = Depends(get_db),
    user_email: str = Depends(get_current_user_email),
):
    # 1. Create the task in "pending" state
    task = Task(
        title=payload.title,
        status="pending",
        result_text=None,
        metadata_json=payload.metadata or {},
        company_id=payload.company_id,
        squad=payload.squad,
        owner_email=user_email,
        prerequisite_task_id=payload.prerequisite_task_id,
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    apply_relationships_and_next_steps(db, task)

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
    result_text, provider_status = run_ai_coo_logic(
        title=task.title,
        metadata=task.metadata_json or {},
    )

    # 4. Mark as completed, save result, and log final status
    old_status = task.status
    task.status = "completed"
    task.result_text = result_text
    task.external_provider_status = provider_status
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


@router.get("/{task_id}")
def get_task(task_id: int, db: Session = Depends(get_db)):
    """
    Return full info for a single task.
    """
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # reuse existing serializer
    return {"ok": True, "task": serialize_task(task)}


@router.get("/{task_id}/summary")
def get_task_summary(task_id: int, db: Session = Depends(get_db)):
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    return {
        "task": serialize_task(task),
        "next_steps": task.next_steps or "",
        "depends_on": [serialize_task(t) for t in task.depends_on],
        "blocks": [serialize_task(t) for t in task.blocks],
    }


@router.get("/{task_id}/status")
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
        "external_provider_status": getattr(task, "external_provider_status", None),
    }


@router.post("/run_debug")
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
        prerequisite_task_id=payload.prerequisite_task_id,
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    apply_relationships_and_next_steps(db, task)

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
    result_text, provider_status = run_ai_coo_logic(
        title=task.title,
        metadata=task.metadata_json or {},
    )

    # 4. Mark as completed, save result, and log final status
    old_status = task.status
    task.status = "completed"
    task.result_text = result_text
    task.external_provider_status = provider_status
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
            "prerequisite_task_id": getattr(task, "prerequisite_task_id", None),
            "metadata_json": task.metadata_json,
            "result_text": task.result_text,
            "owner_email": getattr(task, "owner_email", None),
            "external_provider_status": getattr(task, "external_provider_status", None),
            "created_at": task.created_at.isoformat(),
        },
    }


@router.get("/{task_id}/logs")
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


@router.get("/{task_id}/logs_debug")
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
