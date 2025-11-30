from fastapi import FastAPI
from .database import Base, engine
from .routers import integrations, sprints

# Import models so they are registered with SQLAlchemy
from . import models

# Create all tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title="AI COO for SaaS")

app.include_router(integrations.router, prefix="/integrations", tags=["integrations"])
app.include_router(sprints.router, prefix="/sprints", tags=["sprints"])

@app.get("/")
def read_root():
    return {"message": "AI COO backend running"}
