from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from .database import Base


class Company(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)

    integrations = relationship("Integration", back_populates="company", cascade="all, delete-orphan")
    projects = relationship("Project", back_populates="company", cascade="all, delete-orphan")


class Integration(Base):
    __tablename__ = "integrations"
    
    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"))
    type = Column(String)  # "slack" or "jira"
    access_token = Column(String)
    extra = Column(String, nullable=True)  # renamed from metadata -> extra

    company = relationship("Company", back_populates="integrations")


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    name = Column(String, nullable=False)
    jira_key = Column(String, nullable=True, unique=True)
    
    company = relationship("Company", back_populates="projects")

    sprints = relationship("Sprint", back_populates="project", cascade="all, delete-orphan")


class Sprint(Base):
    __tablename__ = "sprints"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    name = Column(String, nullable=False)
    start_date = Column(DateTime, default=datetime.utcnow)
    end_date = Column(DateTime, default=datetime.utcnow)
    risk_score = Column(Float, default=0.0)
    risk_level = Column(String, default="low")
    last_evaluated_at = Column(DateTime, default=datetime.utcnow)

    project = relationship("Project", back_populates="sprints")
    issues = relationship("Issue", back_populates="sprint", cascade="all, delete-orphan")


class Issue(Base):
    __tablename__ = "issues"

    id = Column(Integer, primary_key=True, index=True)
    sprint_id = Column(Integer, ForeignKey("sprints.id"), nullable=False)
    key = Column(String, nullable=False)
    title = Column(Text, nullable=False)
    status = Column(String, nullable=False)
    assignee = Column(String, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_blocker = Column(Boolean, default=False)

    sprint = relationship("Sprint", back_populates="issues")
