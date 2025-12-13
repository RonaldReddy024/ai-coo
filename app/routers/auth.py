from fastapi import APIRouter, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
import logging
import os
from typing import Optional

from ..supabase_client import SUPABASE_AVAILABLE, supabase

SITE_URL = os.getenv("SITE_URL", "http://127.0.0.1:8000")

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
logger = logging.getLogger(__name__)

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "message": None},
    )


@router.post("/auth/magic-link")
def send_magic_link(email: str = Form(...)):
    if not SUPABASE_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="Supabase authentication is not configured on this server.",
        )

    try:
        print("SUPABASE_URL:", os.getenv("SUPABASE_URL"))
        print("ANON starts eyJ:", (os.getenv("SUPABASE_ANON_KEY") or "").startswith("eyJ"))
        print("ANON len:", len(os.getenv("SUPABASE_ANON_KEY") or ""))
        supabase.auth.sign_in_with_otp(
            {
                "email": email,
                "options": {
                    "email_redirect_to": SITE_URL + "/auth/callback",
                },
            }
        )
        return {"ok": True, "message": "Magic link sent"}
    except Exception as e:
        logger.exception("Magic link send failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/auth/callback", response_class=HTMLResponse)
async def auth_callback(
    request: Request,
    email: Optional[str] = Query(None),
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

    if not email:
        return templates.TemplateResponse(
            "magic_error.html",
            {
                "request": request,
                "error_message": (
                    "This login link is missing the user email. Please request a new one."
                ),
            },
        )

    try:
        verify_res = supabase.auth.verify_otp(
            {
                "email": email,
                "token_hash": raw_token,
                "type": type,
            }
        )
    except Exception:
        logger.exception("Magic link verification failed for token %s", raw_token)
        return templates.TemplateResponse(
            "magic_error.html",
            {
                "request": request,
                "error_message": (
                    "This login link is invalid or has expired."
                ),
            },
        )

    verify_error = getattr(verify_res, "error", None)
    if verify_error:
        logger.warning(
            "Magic link verification returned error for token %s: %s",
            raw_token,
            getattr(verify_error, "message", verify_error),
        )
        return templates.TemplateResponse(
            "magic_error.html",
            {
                "request": request,
                "error_message": (
                    "This login link is invalid or has expired."
                ),
            },
        )

    session = getattr(verify_res, "session", None)
    access_token = getattr(session, "access_token", None) if session else None
    if not session or not access_token:
        logger.warning(
            "Magic link verification returned no session or missing access token",
        )
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
        value=access_token,
        httponly=True,
        samesite="lax",
    )
    response.set_cookie(
        key="wy_email",
        value=email,
        httponly=True,
        samesite="lax",
    )
    return response


@router.get("/magic-login")
async def magic_login(
    request: Request,
    email: Optional[str] = Query(None),
):
    """
    DEV MODE:
    - Takes ?email= from the magic link redirect
    - Sets a cookie so we know who is "logged in"
    - Sends them to the dashboard
    """

    if not email:
        return templates.TemplateResponse(
            "magic_error.html",
            {
                "request": request,
                "error_message": "This login link is missing an email parameter.",
            },
        )

    response = RedirectResponse(url="/dashboard", status_code=302)
    response.set_cookie(
        "wy_email",
        email,
        httponly=True,
        samesite="lax",
    )
    return response
