from datetime import datetime

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..deps import get_current_user_email, get_db
from ..config import settings
from .. import models
from ..services.whatsapp import whatsapp_service

router = APIRouter()


class WhatsAppMessage(BaseModel):
    sender: str
    message: str
    squad: str | None = None


class WhatsAppAlert(BaseModel):
    to: str
    text: str


@router.post("/jira/import-project")
async def import_jira_project(
    jira_project_key: str,
    company_id: int,
    db: Session = Depends(get_db),
    user_email: str = Depends(get_current_user_email),
):
    """
    Fetch sprints & issues from a Jira project and store them.
    This is a simple importer that you can refine later.
    """
    # JIRA authentication (basic auth with email + API token)
    auth = (settings.JIRA_EMAIL, settings.JIRA_API_TOKEN)
    base_url = settings.JIRA_BASE_URL

    if not base_url or not settings.JIRA_API_TOKEN:
        raise HTTPException(status_code=400, detail="Jira not configured")

    # Ensure the company belongs to the current user, then create or get project
    company = (
        db.query(models.Company)
        .filter_by(id=company_id, owner_email=user_email)
        .first()
    )
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    project = (
        db.query(models.Project)
        .filter_by(jira_key=jira_project_key, company_id=company_id, owner_email=user_email)
        .first()
    )
    if not project:
        project = models.Project(
            company_id=company_id,
            name=f"Jira {jira_project_key}",
            jira_key=jira_project_key,
            owner_email=user_email,
        )
        db.add(project)
        db.commit()
        db.refresh(project)

    # Fetch issues (simplified: you might want pagination here)
    jql = f"project={jira_project_key}"
    issues_url = f"{base_url}/rest/api/3/search"
    params = {"jql": jql, "maxResults": 100}
    async with httpx.AsyncClient() as client:
        resp = await client.get(issues_url, params=params, auth=auth)
    if resp.status_code != 200:
        raise HTTPException(status_code=400, detail=f"Jira error: {resp.text}")

    data = resp.json()
    issues = data.get("issues", [])

    # For now, treat everything as one sprint "Imported Sprint"
    sprint = models.Sprint(
        project_id=project.id,
        name="Imported Sprint",
        start_date=datetime.utcnow(),
        end_date=datetime.utcnow(),  # you'll override with real dates when you use boards/sprints API
        risk_score=0.0,
        risk_level="low",
        owner_email=user_email,
    )
    db.add(sprint)
    db.commit()
    db.refresh(sprint)

    for issue in issues:
        fields = issue.get("fields", {})
        db_issue = models.Issue(
            sprint_id=sprint.id,
            key=issue.get("key"),
            title=fields.get("summary", ""),
            status=fields.get("status", {}).get("name", ""),
            assignee=(fields.get("assignee") or {}).get("displayName"),
            created_at=datetime.fromisoformat(fields.get("created")[:-5]) if fields.get("created") else datetime.utcnow(),
            updated_at=datetime.fromisoformat(fields.get("updated")[:-5]) if fields.get("updated") else datetime.utcnow(),
            is_blocker=False
        )
        db.add(db_issue)

    db.commit()
    return {"message": f"Imported {len(issues)} issues into sprint {sprint.id}"}

@router.post("/slack/test-message")
async def slack_test_message(channel: str = "#general"):
    """
    Send a test message to a Slack channel to verify integration.
    """
    if not settings.SLACK_BOT_TOKEN:
        raise HTTPException(status_code=400, detail="Slack bot token not configured")

    url = "https://slack.com/api/chat.postMessage"
    headers = {"Authorization": f"Bearer {settings.SLACK_BOT_TOKEN}"}
    payload = {
        "channel": channel,
        "text": "👋 WorkYodha AI COO test message – integration is working!"
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json=payload, headers=headers)

    if not resp.json().get("ok"):
        raise HTTPException(status_code=400, detail=f"Slack error: {resp.text}")

    return {"message": "Test message sent to Slack"}


@router.post("/whatsapp/ingest")
def whatsapp_ingest(payload: WhatsAppMessage):
    """Accept an inbound WhatsApp message and generate a structured breakdown."""

    parsed = whatsapp_service.receive_task_message(
        payload.message, metadata={"squad": payload.squad}
    )
    return {
        "ok": True,
        "from": payload.sender,
        "language": parsed["language"],
        "normalized": parsed["normalized"],
        "breakdown": parsed["breakdown"],
    }


@router.post("/whatsapp/alert")
def whatsapp_alert(payload: WhatsAppAlert):
    """Send a WhatsApp alert or approval request to a recipient."""

    result = whatsapp_service.send_alert(payload.to, payload.text)
    return {"ok": result.get("sent", False), "result": result}
