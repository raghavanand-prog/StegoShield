"""Session helpers, login_required, and CSRF token handling for the
authenticated area.

The Flask session cookie stores the signed-in user's Supabase access
token, refresh token, expiry, id and email. It is a signed (not
encrypted) cookie - tamper-proof but not confidential - which is an
acceptable tradeoff here because the only thing in it is a user's OWN
credentials, not a server secret; SESSION_COOKIE_HTTPONLY/SECURE/
SAMESITE (set in app/config.py) stop it being read by JavaScript or
sent cross-site. See README "Authentication" for the full rationale.
"""
from __future__ import annotations

import hmac
import secrets
import time
from functools import wraps

from flask import redirect, request, session, url_for

from app.auth.supabase_client import AuthError, refresh_session
from app.utils.logging_config import get_logger

logger = get_logger(__name__)

_REFRESH_MARGIN_SECONDS = 60


def start_session(token_data: dict) -> None:
    user = token_data.get("user") or {}
    session.permanent = True
    session["auth"] = {
        "access_token": token_data["access_token"],
        "refresh_token": token_data["refresh_token"],
        "expires_at": time.time() + token_data.get("expires_in", 3600),
        "user_id": user.get("id"),
        "email": user.get("email"),
    }


def clear_session() -> None:
    session.pop("auth", None)


def get_current_user() -> dict | None:
    """Returns {"user_id", "email", "access_token"} for the signed-in
    user, refreshing the Supabase access token first if it's about to
    expire. Returns None (and clears the session) if there is no valid
    session - the caller never sees a stale/expired token."""
    auth = session.get("auth")
    if not auth:
        return None

    if auth["expires_at"] - time.time() < _REFRESH_MARGIN_SECONDS:
        try:
            refreshed = refresh_session(auth["refresh_token"])
        except AuthError:
            clear_session()
            return None
        refreshed.setdefault("user", {"id": auth["user_id"], "email": auth["email"]})
        start_session(refreshed)
        auth = session["auth"]

    return {"user_id": auth["user_id"], "email": auth["email"], "access_token": auth["access_token"]}


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = get_current_user()
        if user is None:
            return redirect(url_for("auth.login", next=request.path))
        return view(*args, user=user, **kwargs)

    return wrapped


def get_csrf_token() -> str:
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


def csrf_valid(submitted: str | None) -> bool:
    expected = session.get("csrf_token")
    return bool(expected and submitted and hmac.compare_digest(expected, submitted))
