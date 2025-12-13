from fastapi import APIRouter, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
import logging
import os
from typing import Optional
from urllib.parse import quote

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


def _set_auth_cookies(response, session) -> None:
    """Set auth cookies on a response object."""

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



def _build_auth_response(session) -> JSONResponse:
    response = JSONResponse({"ok": True})
    _set_auth_cookies(response, session)
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
        {
            "request": request,
            "message": None,
            "next_path": request.query_params.get("next"),
        },
    )


@router.post("/auth/magic-link", response_class=HTMLResponse)
def send_magic_link(
    request: Request, email: str = Form(...), next_path: Optional[str] = Form(None)
):
    if not SUPABASE_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="Supabase authentication is not configured on this server.",
        )

    try:
        raw_next = next_path or request.query_params.get("next")
        next_path = raw_next if isinstance(raw_next, str) and raw_next.startswith("/") else None
        next_path = next_path or "/dashboard"

        site = SITE_URL.rstrip("/")
        email_redirect = f"{site}/auth/callback?next={quote(next_path)}"

        supabase.auth.sign_in_with_otp(
            {
                "email": email,
                "options": {
                    "email_redirect_to": email_redirect,
                    "emailRedirectTo": email_redirect,
                },
            }
        )
        return templates.TemplateResponse(
            "magic_link_sent.html",
            {"request": request, "email": email},
        )
    except Exception as e:
        logger.exception("Magic link send failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/auth/callback", response_class=HTMLResponse)
def auth_callback_page():
    return """
<!doctype html>
<html>
<head><meta charset="utf-8"><title>Logging in…</title></head>
<body style="font-family: system-ui; padding: 24px;">
  <h3>Logging you in…</h3>
  <p id="status">Finalizing your session.</p>
  <pre id="err" style="color:#b00020; white-space:pre-wrap;"></pre>

  <script>
    const statusEl = document.getElementById("status");
    const errEl = document.getElementById("err");

    const url = new URL(window.location.href);
    const code = url.searchParams.get("code");
    const next = url.searchParams.get("next") || "/dashboard";
    
    const hash = window.location.hash.startsWith("#") ? window.location.hash.slice(1) : "";
    const hashParams = new URLSearchParams(hash);
    const access_token = hashParams.get("access_token");
    const refresh_token = hashParams.get("refresh_token");

    async function finalize(payload) {
      const res = await fetch("/auth/finalize", {
        method: "POST",
        headers: {"Content-Type":"application/json"},
        body: JSON.stringify(payload)
      });

      const text = await res.text();
      let data = {};
      try { data = JSON.parse(text); } catch(e) {}

      if (!res.ok) {
        throw new Error((data && (data.detail || data.message)) || text || ("HTTP " + res.status));
      }
      return data;
    }

    (async () => {
      try {
        let payload = null;

        if (code) payload = { code, next };
        else if (access_token) payload = { access_token, refresh_token, next };
        else {
          statusEl.textContent = "This login link is missing token data.";
          errEl.textContent = "Tip: Open the link in Chrome (not Gmail in-app browser).";
          return;
        }

        statusEl.textContent = "Creating your session…";
        const out = await finalize(payload);

        const target = out.redirect_to || next || "/dashboard";
        statusEl.textContent = "Redirecting…";
        window.location.replace(target);
      } catch (e) {
        statusEl.textContent = "Login failed.";
        errEl.textContent = e.message;
        console.error(e);
      }
    })();
  </script>
</body>
</html>
"""


@router.post("/auth/finalize")
def auth_finalize(payload: dict):
    if not SUPABASE_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="Supabase authentication is not configured on this server.",
        )

    try:
        access_token = None
        refresh_token = None

        if payload.get("code"):
            session = supabase.auth.exchange_code_for_session(payload["code"])
            sess = getattr(session, "session", None) or session.get("session")
            access_token = getattr(sess, "access_token", None) or (
                sess.get("access_token") if isinstance(sess, dict) else None
            )
            refresh_token = getattr(sess, "refresh_token", None) or (
                sess.get("refresh_token") if isinstance(sess, dict) else None
            )

        elif payload.get("access_token"):
            access_token = payload["access_token"]
            refresh_token = payload.get("refresh_token")

        else:
            raise HTTPException(status_code=400, detail="Missing code/access_token")

        if not access_token:
            raise HTTPException(
                status_code=500,
                detail="Could not obtain access token from Supabase session.",
            )

        raw_next = payload.get("next")
        redirect_to = raw_next if isinstance(raw_next, str) and raw_next.startswith("/") else None
        
        if not redirect_to:
            user_resp = supabase.auth.get_user(access_token)
            u = getattr(user_resp, "user", None) or user_resp.get("user")
            meta = getattr(u, "user_metadata", None) or (
                u.get("user_metadata") if isinstance(u, dict) else {}
            ) or {}

            company_slug = meta.get("company_slug") or meta.get("company")
            redirect_to = (
                f"/company/{company_slug}/dashboard" if company_slug else "/dashboard"
            )

        redirect_to = redirect_to if redirect_to.startswith("/") else "/dashboard"

        resp = JSONResponse({"ok": True, "redirect_to": redirect_to})

        resp.set_cookie("wy_access", access_token, httponly=True, samesite="lax")
        if refresh_token:
            resp.set_cookie("wy_refresh", refresh_token, httponly=True, samesite="lax")

        return resp

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
