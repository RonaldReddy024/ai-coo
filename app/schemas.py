from pydantic import BaseModel
from datetime import datetime
from typing import List, Optional

class SprintBase(BaseModel):
    id: int
    name: str
    start_date: datetime
    end_date: datetime
    risk_score: float
    risk_level: str

    class Config:
        orm_mode = True

class IssueBase(BaseModel):
    id: int
    key: str
    title: str
    status: str
    assignee: Optional[str]
    updated_at: datetime
    created_at: datetime
    is_blocker: bool

    class Config:
        orm_mode = True

class SprintWithIssues(SprintBase):
    issues: List[IssueBase] = []
