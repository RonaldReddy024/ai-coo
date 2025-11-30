from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from .database import Base, engine
from .routers import integrations, sprints
from . import models  # register models

Base.metadata.create_all(bind=engine)

app = FastAPI(title="AI COO for SaaS")

# Routers
app.include_router(integrations.router, prefix="/integrations", tags=["integrations"])
app.include_router(sprints.router, prefix="/sprints", tags=["sprints"])

templates = Jinja2Templates(directory="app/templates")


# Landing page
@app.get("/", response_class=HTMLResponse)
async def landing(request: Request):
    return templates.TemplateResponse("landing.html", {"request": request})


# Fake login page (no real auth yet)
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


# Dashboard
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})


# Optional: simple health endpoint
@app.get("/api/health")
def health():
    return {"status": "ok", "app": "AI COO backend running"}
