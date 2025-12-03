from typing import Optional

from fastapi import APIRouter, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from ..supabase_client import SUPABASE_AVAILABLE, supabase

BASE_URL = "http://127.0.0.1:8000"

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
    if not SUPABASE_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="Supabase authentication is not configured on this server.",
        )

    redirect_url = f"{BASE_URL}/magic-login"

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


@router.get("/auth/callback", response_class=HTMLResponse)
async def auth_callback(
    request: Request,
    token_hash: Optional[str] = Query(None),
    token: Optional[str] = Query(None),
    type: str = Query("email"),
):
    raw_token = token_hash or token

    if not raw_token:
        return templates.TemplateResponse(
            "magic_error.html",
            {
                "request": request,
                "error_message": (
                    "This login link is missing a token or has been opened incorrectly."
                ),
            },
        )

    if not SUPABASE_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="Supabase authentication is not configured on this server.",
        )

    verify_res = supabase.auth.verify_otp(
        {
            "token_hash": raw_token,
            "type": type,
        }
    )

    session = getattr(verify_res, "session", None)
    if not session:
        return templates.TemplateResponse(
            "magic_error.html",
            {
                "request": request,
                "error_message": (
                    "This login link is invalid or has expired."
                ),
            },
        )

    response = RedirectResponse(url="/dashboard")
    response.set_cookie(
        key="sb-access-token",
        value=session.access_token,
        httponly=True,
        samesite="lax",
    )
    return response


@router.get("/magic-login")
async def magic_login(
    request: Request,
    token_hash: Optional[str] = Query(None),
    token: Optional[str] = Query(None),
):
    """
    DEV MODE:
    Any magic link -> treat as logged in and send user to dashboard.
    """
    return RedirectResponse(url="/dashboard", status_code=302)
