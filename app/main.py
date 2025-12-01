from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse

from .database import Base, engine
from .routers import companies, integrations, sprints, auth
from . import models  # register models
from .supabase_client import supabase

Base.metadata.create_all(bind=engine)

app = FastAPI(title="WorkYodha AI COO for SaaS")

# Routers
app.include_router(integrations.router, prefix="/integrations", tags=["integrations"])
app.include_router(sprints.router, prefix="/sprints", tags=["sprints"])
app.include_router(companies.router)
app.include_router(auth.router, tags=["auth"])


# Landing page redirects to login for now
@app.get("/")
async def root_redirect():
    return RedirectResponse(url="/login")


# Dashboard placeholder
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    return """
    <html>
      <head><title>AI COO Dashboard</title></head>
      <body style=\"font-family: system-ui; background:#020617; color:#e5e7eb;\">
        <h1>WorkYodha AI COO</h1>
        <p>You are logged in via Supabase magic link ✅</p>
        <p>We’ll replace this with the real sprint dashboard later.</p>
        <a href=\"/sprints-dashboard\" style=\"color:#a855f7;\">Go to Sprint Risks</a>
      </body>
    </html>
    """


# Optional: simple health endpoint
@app.get("/api/health")
def health():
    return {"status": "ok", "app": "WorkYodha AI COO backend running"}


@app.get("/supabase-test")
async def supabase_test():
    try:
        response = supabase.table("ai_tasks").select("*").limit(5).execute()
        return {
            "ok": True,
            "count": len(response.data or []),
            "data": response.data,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
