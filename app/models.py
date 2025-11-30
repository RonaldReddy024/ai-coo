from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Float, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from .database import Base

class Company(Base):
    __tablename__ = "companies"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    size = Column(Integer, nullable=True)

    users = relationship("User", back_populates="company")
    projects = relationship("Project", back_populates="company")

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    name = Column(String)
    hashed_password = Column(String)
    role = Column(String, default="user")
    company_id = Column(Integer, ForeignKey("companies.id"))

    company = relationship("Company", back_populates="users")

class Integration(Base):
    __tablename__ = "integrations"
    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"))
    type = Column(String)  # "slack" or "jira"
    access_token = Column(String)
    metadata = Column(String, nullable=True)

class Project(Base):
    __tablename__ = "projects"
    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"))
    name = Column(String)
    jira_key = Column(String, index=True)

    company = relationship("Company", back_populates="projects")
    sprints = relationship("Sprint", back_populates="project")

class Sprint(Base):
    __tablename__ = "sprints"
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"))
    name = Column(String)
    start_date = Column(DateTime)
    end_date = Column(DateTime)
    risk_score = Column(Float, default=0.0)
    risk_level = Column(String, default="low")  # low / medium / high
    last_evaluated_at = Column(DateTime, default=datetime.utcnow)

    project = relationship("Project", back_populates="sprints")
    issues = relationship("Issue", back_populates="sprint")

class Issue(Base):
    __tablename__ = "issues"
    id = Column(Integer, primary_key=True, index=True)
    sprint_id = Column(Integer, ForeignKey("sprints.id"))
    key = Column(String, index=True)
    title = Column(String)
    status = Column(String)
    assignee = Column(String, nullable=True)
    updated_at = Column(DateTime)
    created_at = Column(DateTime)
    is_blocker = Column(Boolean, default=False)

    sprint = relationship("Sprint", back_populates="issues")

class Alert(Base):
    __tablename__ = "alerts"
    id = Column(Integer, primary_key=True, index=True)
    sprint_id = Column(Integer, ForeignKey("sprints.id"))
    message = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    recipient = Column(String)  # email or slack user id
