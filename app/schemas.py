from datetime import datetime
from typing import List, Optional

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

    model_config = ConfigDict(from_attributes=True)


class SprintWithIssues(Sprint):
    issues: List["Issue"] = []


class SprintRiskReport(BaseModel):
    sprint_id: int
    risk_level: str
    risk_score: float
    summary: str
    details: str

    model_config = ConfigDict(from_attributes=True)


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
