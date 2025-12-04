from typing import Optional

from fastapi import Cookie, HTTPException, status

from .database import get_db


def get_current_user_email(wy_email: Optional[str] = Cookie(None)) -> str:
    """Retrieve the current user's email from the auth cookie."""

    if not wy_email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not logged in",
        )

    return wy_email
