from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict


# ---------- Company & Project Schemas ----------

class CompanyBase(BaseModel):
    name: str


class CompanyCreate(CompanyBase):
    pass


class Company(CompanyBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


class ProjectBase(BaseModel):
    name: str
    company_id: int


class ProjectCreate(ProjectBase):
    pass


class Project(ProjectBase):
    id: int
    jira_key: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


# ---------- Sprint Schemas ----------

class SprintBase(BaseModel):
    name: str
    project_id: int
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    baseline_date: Optional[datetime] = None

class SprintCreate(SprintBase):
    pass


class Sprint(BaseModel):
    id: int
    project_id: int
    name: str
    start_date: datetime
    end_date: datetime
    risk_score: float
    risk_level: str
    last_evaluated_at: datetime

    baseline_date: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)


class SprintWithIssues(Sprint):
    issues: List["Issue"] = []


class SprintCollaboratorBase(BaseModel):
    email: str


class SprintCollaboratorCreate(SprintCollaboratorBase):
    pass


class SprintCollaborator(SprintCollaboratorBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


class SprintRiskReport(BaseModel):
    sprint_id: int
    risk_level: str
    risk_score: float
    summary: str
    details: str

    model_config = ConfigDict(from_attributes=True)


class SprintAlert(BaseModel):
    type: str        # e.g. "risk", "blocker", "deadline", "assignee"
    level: str       # "info", "warning", "critical"
    message: str

    model_config = ConfigDict(from_attributes=True)


class SprintSnapshot(BaseModel):
    tasks_total: int
    tasks_completed: int
    risks_open: int
    days_active: int


class SprintInsights(BaseModel):
    next_steps: List[str]
    triggered_risks: List[str]
    data_needed: List[str]
    snapshot: SprintSnapshot
    label: str


# ---------- Issue Schemas ----------

class IssueBase(BaseModel):
    title: str
    status: str
    assignee: Optional[str] = None
    is_blocker: bool = False


class IssueCreate(IssueBase):
    # sprint_id is not strictly required in body, we’ll pass it via path,
    # but it doesn't hurt to keep it here if you want.
    sprint_id: Optional[int] = None


class Issue(IssueBase):
    id: int
    key: str
    sprint_id: int
    updated_at: datetime
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------- Task Schemas ----------


class TaskBase(BaseModel):
    title: str
    metadata: Optional[Dict[str, Any]] = None


class TaskCreate(TaskBase):
    # NEW: multi-tenant fields
    company_id: Optional[int] = None
    squad: Optional[str] = None


class TaskUpdate(BaseModel):
    status: Optional[str] = None
    result_text: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    external_provider_status: Optional[str] = None

class Task(TaskBase):
    id: int
    status: str
    result_text: Optional[str] = None
    created_at: datetime
    company_id: Optional[int] = None
    squad: Optional[str] = None
    external_provider_status: Optional[str] = None
    next_steps: Optional[str] = None
    metadata_json: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(from_attributes=True)


class TaskSummary(BaseModel):
    task: Task
    next_steps: str
    depends_on: List[Task]
    blocks: List[Task]
    
    model_config = ConfigDict(from_attributes=True)
