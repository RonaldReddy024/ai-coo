from fastapi import APIRouter, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
import logging
import os
from typing import Optional

from pydantic import BaseModel

from ..supabase_client import SUPABASE_AVAILABLE, supabase

SITE_URL = os.getenv("SITE_URL", "http://127.0.0.1:8000")

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
logger = logging.getLogger(__name__)


def _extract_email_from_user(user_obj) -> Optional[str]:
    if not user_obj:
        return None

    if hasattr(user_obj, "email"):
        return getattr(user_obj, "email")

    if isinstance(user_obj, dict):
        return user_obj.get("email")

    return None


def _normalize_session_data(result):
    """Pull the session payload out of a Supabase auth response."""

    if result is None:
        return None

    if isinstance(result, dict) and "session" in result:
        return result.get("session")

    session = getattr(result, "session", None)
    return session or result


def _build_auth_response(session) -> JSONResponse:
    session_dict = session if isinstance(session, dict) else {}
    access_token = getattr(session, "access_token", None) or session_dict.get(
        "access_token"
    )
    refresh_token = getattr(session, "refresh_token", None) or session_dict.get(
        "refresh_token"
    )
    user_obj = getattr(session, "user", None) or session_dict.get("user")
    user_email = _extract_email_from_user(user_obj)

    if SUPABASE_AVAILABLE and not user_email and access_token:
        try:
            user_result = supabase.auth.get_user(access_token)
            user_email = _extract_email_from_user(
                getattr(user_result, "user", None)
                or (user_result.get("user") if isinstance(user_result, dict) else None)
            )
        except Exception:
            logger.exception("Failed to fetch user for access token")

    if not access_token:
        raise HTTPException(
            status_code=500, detail="Auth session missing access token"
        )

    response = JSONResponse({"ok": True, "email": user_email})
    response.set_cookie(
        key="sb-access-token",
        value=access_token,
        httponly=True,
        samesite="lax",
    )

    if refresh_token:
        response.set_cookie(
            key="sb-refresh-token",
            value=refresh_token,
            httponly=True,
            samesite="lax",
        )

    if user_email:
        response.set_cookie(
            key="wy_email",
            value=user_email,
            httponly=True,
            samesite="lax",
        )

    return response


class CodeIn(BaseModel):
    code: str


class TokensIn(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None

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
def auth_callback_page():
    return """
<!doctype html>
<html>
  <head><meta charset="utf-8"><title>Logging in…</title></head>
  <body>
    <h3>Logging you in…</h3>
    <pre id="debug" style="white-space:pre-wrap;"></pre>
    <script>
      const debug = document.getElementById("debug");

      // Supabase may send either ?code=... or #access_token=...
      const url = new URL(window.location.href);
      const code = url.searchParams.get("code");

      const hash = window.location.hash.startsWith("#") ? window.location.hash.slice(1) : "";
      const hashParams = new URLSearchParams(hash);
      const access_token = hashParams.get("access_token");
      const refresh_token = hashParams.get("refresh_token");

      debug.textContent =
        "code=" + code + "\n" +
        "access_token=" + (access_token ? access_token.slice(0,20)+"..." : null) + "\n" +
        "refresh_token=" + (refresh_token ? refresh_token.slice(0,20)+"..." : null);

      // If we got a PKCE code, send it to backend to exchange for a session
      if (code) {
        fetch("/auth/exchange", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({ code })
        }).then(r => r.json()).then(data => {
          if (data.ok) window.location.href = "/dashboard";
          else debug.textContent += "\n\nExchange failed: " + JSON.stringify(data);
        });
      } else if (access_token) {
        // If tokens came in fragment, you can store a cookie/session server-side by POSTing them
        fetch("/auth/store", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({ access_token, refresh_token })
        }).then(r => r.json()).then(data => {
          if (data.ok) window.location.href = "/dashboard";
          else debug.textContent += "\n\nStore failed: " + JSON.stringify(data);
        });
      } else {
        debug.textContent += "\n\nNo token/code found in URL. Try opening the link in Chrome (not inside Gmail).";
      }
    </script>
  </body>
</html>
"""


@router.post("/auth/exchange")
def auth_exchange(payload: CodeIn):

    if not SUPABASE_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="Supabase authentication is not configured on this server.",
        )
    try:
        exchange_result = supabase.auth.exchange_code_for_session(payload.code)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    session = _normalize_session_data(exchange_result)

    if not session:
        raise HTTPException(status_code=500, detail="No session returned from Supabase")

    return _build_auth_response(session)


@router.post("/auth/store")
def auth_store(payload: TokensIn):
    if not SUPABASE_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="Supabase authentication is not configured on this server.",
        )

    session = {
        "access_token": payload.access_token,
        "refresh_token": payload.refresh_token,
    }

    if payload.access_token:
        try:
            user_result = supabase.auth.get_user(payload.access_token)
            session["user"] = getattr(user_result, "user", None) or (
                user_result.get("user") if isinstance(user_result, dict) else None
            )
        except Exception:
            logger.exception("Failed to fetch user during token store")

    return _build_auth_response(session)


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
