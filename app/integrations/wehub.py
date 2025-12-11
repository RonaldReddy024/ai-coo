import os
from typing import List, Dict, Any, Optional
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

# ---------------------------------------------------------
# FastAPI router for WE HUB
# ---------------------------------------------------------
router = APIRouter(prefix="/wehub", tags=["wehub"])

# ---------------------------------------------------------
# Environment-based config
# ---------------------------------------------------------
# Path to your service account JSON (put it in project root or safe folder)
WEHUB_SERVICE_ACCOUNT_FILE = os.getenv(
    "WEHUB_SERVICE_ACCOUNT_FILE",
    "wehub_service_account.json",  # default
)

# The spreadsheet ID (string in the URL of their Google Sheet)
WEHUB_SPREADSHEET_ID = os.getenv("WEHUB_SPREADSHEET_ID", "")

# Default range – change if WE HUB uses a different sheet/tab/range
WEHUB_SHEET_RANGE = os.getenv(
    "WEHUB_SHEET_RANGE",
    "Cohort!A1:Z1000",  # example: sheet/tab named "Cohort"
)


# ---------------------------------------------------------
# Helper: Google Sheets service
# ---------------------------------------------------------
def get_sheets_service():
    if not WEHUB_SPREADSHEET_ID:
        raise HTTPException(
            status_code=500,
            detail="WEHUB_SPREADSHEET_ID is not set in environment variables.",
        )

    if not os.path.exists(WEHUB_SERVICE_ACCOUNT_FILE):
        raise HTTPException(
            status_code=500,
            detail=f"Service account file not found: {WEHUB_SERVICE_ACCOUNT_FILE}",
        )

    creds = Credentials.from_service_account_file(
        WEHUB_SERVICE_ACCOUNT_FILE,
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
    )

    try:
        service = build("sheets", "v4", credentials=creds)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to build Google Sheets service: {e}",
        )

    return service


# ---------------------------------------------------------
# Pydantic model for a WE HUB cohort row (you can tune fields)
# ---------------------------------------------------------
class WeHubCohortRow(BaseModel):
    # These are generic; map them to your actual sheet columns
    startup_name: str
    founder_name: Optional[str] = None
    email: Optional[str] = None
    stage: Optional[str] = None
    status: Optional[str] = None
    last_update: Optional[str] = None
    notes: Optional[str] = None

    @classmethod
    def from_row(cls, header: List[str], row: List[str]) -> "WeHubCohortRow":
        """
        Convert a raw row (list of values) + header into a WeHubCohortRow.
        Any unknown columns go into notes.
        """
        # Create a dict mapping header->value
        data: Dict[str, Any] = {}
        for i, col_name in enumerate(header):
            value = row[i] if i < len(row) else ""
            key = col_name.strip().lower().replace(" ", "_")
            data[key] = value

        # Try to map flexible column names to our model fields
        # Adjust these mappings to match WE HUB's actual sheet columns
        mapped = {
            "startup_name": data.get("startup_name") or data.get("company") or "",
            "founder_name": data.get("founder_name")
            or data.get("founder")
            or data.get("primary_contact"),
            "email": data.get("email") or data.get("contact_email"),
            "stage": data.get("stage") or data.get("program_stage"),
            "status": data.get("status") or data.get("current_status"),
            "last_update": data.get("last_update")
            or data.get("last_check_in")
            or data.get("last_touch"),
            "notes": data.get("notes") or data.get("comments"),
        }

        return cls(**mapped)


# ---------------------------------------------------------
# Stub: connect a WE HUB row into your internal Task system
# ---------------------------------------------------------
def create_or_update_workyodha_task_from_wehub(row: WeHubCohortRow) -> Dict[str, Any]:
    """
    TODO: Replace this stub with your real DB / service call.

    This function should:
      - Check if this startup already has a task in your system (by email or startup_name).
      - If yes, update it.
      - If no, create a new task.

    For now, we just return a fake "task" dict to show shape.
    """
    # Example metadata to send into your Task model
    metadata = {
        "source": "WEHUB",
        "startup_name": row.startup_name,
        "founder_name": row.founder_name,
        "email": row.email,
        "stage": row.stage,
        "status": row.status,
        "last_update": row.last_update,
        "notes": row.notes,
        "synced_at": datetime.utcnow().isoformat(),
    }

    # 🔥 Integrate here with your existing Task creation logic.
    # For example, if you have a function:
    #     create_task(title: str, status: str, metadata: dict) -> Task
    #
    # You could do:
    #
    # from app.services.tasks import create_task
    # task = create_task(
    #     title=f"[WE HUB] {row.startup_name}",
    #     status="pending",
    #     metadata=metadata,
    # )
    #
    # return {"id": task.id, "title": task.title, "status": task.status}

    # Placeholder demo response:
    return {
        "title": f"[WE HUB] {row.startup_name}",
        "status": "pending",
        "metadata": metadata,
    }


# ---------------------------------------------------------
# Endpoint: health check
# ---------------------------------------------------------
@router.get("/health")
async def wehub_health():
    return {"ok": True, "message": "WE HUB integration is alive"}


# ---------------------------------------------------------
# Endpoint: read the WE HUB sheet and (optionally) create tasks
# ---------------------------------------------------------
@router.post("/sync")
async def sync_wehub_cohort(create_tasks: bool = True):
    """
    Pull rows from WE HUB's Google Sheet and (optionally) create WorkYodha tasks.

    Call this endpoint manually during/after the meeting, or trigger via cron.
    """
    service = get_sheets_service()

    try:
        sheet = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=WEHUB_SPREADSHEET_ID, range=WEHUB_SHEET_RANGE)
        )
        result = sheet.execute()
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to read WE HUB spreadsheet: {e}",
        )

    values: List[List[str]] = result.get("values", [])

    if not values:
        return {"ok": False, "message": "No data found in WE HUB sheet."}

    header = values[0]
    data_rows = values[1:]

    rows_parsed: List[WeHubCohortRow] = []
    created_tasks: List[Dict[str, Any]] = []

    for row in data_rows:
        try:
            cohort_row = WeHubCohortRow.from_row(header, row)
            rows_parsed.append(cohort_row)

            if create_tasks:
                task = create_or_update_workyodha_task_from_wehub(cohort_row)
                created_tasks.append(task)
        except Exception as e:
            # Skip bad rows but continue processing
            print(f"Error parsing row {row}: {e}")

    return {
        "ok": True,
        "source_rows": len(data_rows),
        "parsed_rows": len(rows_parsed),
        "tasks_created_or_updated": len(created_tasks) if create_tasks else 0,
        "sample_task": created_tasks[0] if created_tasks else None,
    }


# ---------------------------------------------------------
# OPTIONAL: Slack event endpoint for WE HUB pilot channel
# (Only use if WE HUB lets you into their Slack workspace)
# ---------------------------------------------------------
@router.post("/slack/events")
async def wehub_slack_events(payload: Dict[str, Any]):
    """
    Basic Slack events handler for a WE HUB pilot channel.

    Connect this to a Slack App's Event Subscription:
      - app_mention
      - message.channels (etc)

    Then you can:
      - Convert messages into tasks
      - Reply with summaries
      - Track action items for WE HUB
    """
    event = payload.get("event", {})
    event_type = event.get("type")
    text = event.get("text")
    user = event.get("user")
    channel = event.get("channel")

    # URL verification challenge
    if payload.get("type") == "url_verification":
        return {"challenge": payload.get("challenge")}

    # Ignore bot messages
    if event.get("subtype") == "bot_message":
        return {"ok": True}

    # Example: whenever someone mentions "task:" create a WorkYodha task
    if event_type == "message" and text:
        if "task:" in text.lower():
            # Extract simple task title
            title = text.split("task:", 1)[1].strip()

            metadata = {
                "source": "WEHUB_SLACK",
                "slack_user": user,
                "slack_channel": channel,
                "raw_text": text,
                "created_at": datetime.utcnow().isoformat(),
            }

            # TODO: call your real task creation logic here
            # from app.services.tasks import create_task
            # task = create_task(title=title, status="pending", metadata=metadata)

            print(f"[WE HUB Slack] New task from Slack: {title}")

    return {"ok": True}
