from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from .database import Base, engine
from .routers import integrations, sprints

# Import models so they are registered with SQLAlchemy
from . import models

# Create all tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title="AI COO for SaaS")

# Routers
app.include_router(integrations.router, prefix="/integrations", tags=["integrations"])
app.include_router(sprints.router, prefix="/sprints", tags=["sprints"])

# Templates
templates = Jinja2Templates(directory="app/templates")


@app.get("/", response_model=dict)
def read_root():
    return {"message": "AI COO backend running"}


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    # We don't fetch data here; the JS on the page will call /sprints and /sprints/{id}/risk
    return templates.TemplateResponse("dashboard.html", {"request": request})
