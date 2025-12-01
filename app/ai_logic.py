from typing import Any, Optional, TYPE_CHECKING, Union

if TYPE_CHECKING:
    from .models import Task
    

def run_ai_coo_logic(
    task_or_title: Union[str, "Task"], metadata: Optional[dict[str, Any]] = None
) -> str:
    """
    Placeholder for your real AI COO workflow.

    For now, it returns a simple string.
    """
    if not isinstance(task_or_title, str):
        title = getattr(task_or_title, "title", "Unknown task")
        metadata = getattr(task_or_title, "metadata", metadata)
    else:
        title = task_or_title

    base = f"AI-COO processed task: {title}"
    if metadata:
        base += f" | metadata keys: {', '.join(metadata.keys())}"
    return base
