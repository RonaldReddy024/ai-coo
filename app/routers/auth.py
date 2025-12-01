from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from ..config import settings
from ..supabase_client import supabase

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "message": None},
    )


@router.post("/auth/magic-link", response_class=HTMLResponse)
async def send_magic_link(request: Request, email: str = Form(...)):
    redirect_url = f"{settings.SITE_URL}/auth/callback"

    res = supabase.auth.sign_in_with_otp(
        {
            "email": email,
            "options": {
                "email_redirect_to": redirect_url,
                "should_create_user": True,
            },
        }
    )

    if getattr(res, "error", None):
        msg = f"Error sending magic link: {res.error.message}"
    else:
        msg = "Magic link sent! Check your inbox."

    return templates.TemplateResponse(
        "login.html",
        {"request": request, "message": msg},
    )


@router.get("/auth/callback")
async def auth_callback(token_hash: str, type: str = "email"):
    verify_res = supabase.auth.verify_otp(
        {
            "token_hash": token_hash,
            "type": type,
        }
    )

    session = getattr(verify_res, "session", None)
    if not session:
        return RedirectResponse(url="/login")

    response = RedirectResponse(url="/dashboard")
    response.set_cookie(
        key="sb-access-token",
        value=session.access_token,
        httponly=True,
        samesite="lax",
    )
    return response
