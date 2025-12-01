from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from .database import Base, engine
from .routers import companies, integrations, sprints, auth
from . import models  # register models

Base.metadata.create_all(bind=engine)

app = FastAPI(title="WorkYodha AI COO for SaaS")

# Routers
app.include_router(integrations.router, prefix="/integrations", tags=["integrations"])
app.include_router(sprints.router, prefix="/sprints", tags=["sprints"])
app.include_router(companies.router)
app.include_router(auth.router, tags=["auth"])

templates = Jinja2Templates(directory="app/templates")


# Landing page redirects to login for now
@app.get("/")
async def root_redirect():
    return RedirectResponse(url="/login")


# Dashboard
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})


# Optional: simple health endpoint
@app.get("/api/health")
def health():
    return {"status": "ok", "app": "WorkYodha AI COO backend running"}
