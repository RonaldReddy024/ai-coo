from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..deps import get_current_user_email, get_db
from .. import models
from ..schemas import (
    CompanyCreate,
    Company as CompanySchema,
    ProjectCreate,
    Project as ProjectSchema,
)

router = APIRouter(prefix="/companies", tags=["companies"])


# -------- Companies --------

@router.post("/", response_model=CompanySchema)
def create_company(
    payload: CompanyCreate,
    db: Session = Depends(get_db),
    user_email: str = Depends(get_current_user_email),
):
    company = models.Company(name=payload.name, owner_email=user_email)
    db.add(company)
    db.commit()
    db.refresh(company)
    return company


@router.get("/", response_model=list[CompanySchema])
def list_companies(
    db: Session = Depends(get_db),
    user_email: str = Depends(get_current_user_email),
):
    return db.query(models.Company).filter_by(owner_email=user_email).all()

# -------- Projects (under a company) --------

@router.post("/{company_id}/projects", response_model=ProjectSchema)
def create_project_for_company(
    company_id: int,
    payload: ProjectCreate,
    db: Session = Depends(get_db),
    user_email: str = Depends(get_current_user_email),
):
    company = (
        db.query(models.Company)
        .filter_by(id=company_id, owner_email=user_email)
        .first()
    )
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    project = models.Project(
        name=payload.name,
        company_id=company_id,
        jira_key=None,
        owner_email=user_email,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.get("/{company_id}/projects", response_model=list[ProjectSchema])
def list_projects_for_company(
    company_id: int,
    db: Session = Depends(get_db),
    user_email: str = Depends(get_current_user_email),
):
    company = (
        db.query(models.Company)
        .filter_by(id=company_id, owner_email=user_email)
        .first()
    )
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    return (
        db.query(models.Project)
        .filter_by(company_id=company_id, owner_email=user_email)
        .all()
    )
