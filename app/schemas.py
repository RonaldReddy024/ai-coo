from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


# ---------- Issue Schemas ----------

class IssueBase(BaseModel):
    key: str
    title: str
    status: str
    assignee: Optional[str] = None
    is_blocker: bool = False


class IssueCreate(IssueBase):
    sprint_id: int


class Issue(IssueBase):
    id: int
    updated_at: datetime
    created_at: datetime

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
    issues: List[Issue]
