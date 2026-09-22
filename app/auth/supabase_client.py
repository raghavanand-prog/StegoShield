"""Thin wrapper over Supabase's Auth (GoTrue) and PostgREST HTTP APIs.

Every call here uses the anon key plus, for anything user-scoped, the
signed-in user's own access token as the `Authorization: Bearer ...`
header - never a service-role key (this app doesn't have one, and
doesn't need one: Postgres Row Level Security in supabase/schema.sql
enforces that a user's token can only read/write that user's own
rows). This is what makes the IDOR protection real rather than
application-code-only: even a bug in our route logic can't leak
another user's data, because the database itself refuses the query.

All functions raise AuthError with a `safe_message` meant for display
to the end user (never a raw provider error string, which could leak
internal details or be used to enumerate accounts) and log the full
detail server-side.
"""
from __future__ import annotations

import requests
from flask import current_app

from app.utils.logging_config import get_logger

logger = get_logger(__name__)

_TIMEOUT = 8


class AuthError(Exception):
    def __init__(self, safe_message: str, detail: str = ""):
        super().__init__(safe_message)
        self.safe_message = safe_message
        self.detail = detail or safe_message


def _base_url() -> str:
    return current_app.config["SUPABASE_URL"].rstrip("/")


def _anon_headers(extra: dict | None = None) -> dict:
    headers = {
        "apikey": current_app.config["SUPABASE_ANON_KEY"],
        "Content-Type": "application/json",
    }
    if extra:
        headers.update(extra)
    return headers


def _request(method: str, url: str, *, headers: dict, json: dict | None = None, params: dict | None = None):
    try:
        resp = requests.request(method, url, headers=headers, json=json, params=params, timeout=_TIMEOUT)
    except requests.RequestException as exc:
        logger.warning("supabase_request_failed", extra={"url": url, "error": str(exc)})
        raise AuthError("Authentication service is temporarily unavailable. Please try again.") from exc
    return resp


def sign_up(email: str, password: str) -> dict:
    """Create a Supabase Auth user. Returns {"email_confirmation_required": bool}."""
    url = f"{_base_url()}/auth/v1/signup"
    resp = _request("POST", url, headers=_anon_headers(), json={"email": email, "password": password})
    if resp.status_code == 200:
        data = resp.json()
        # Supabase returns a user with no session when email confirmation
        # is required (project setting, not something this app controls).
        session_data = data.get("session")
        result = {"email_confirmation_required": session_data is None, "user": data.get("user")}
        if session_data:
            result.update(session_data)
            result["user"] = data.get("user")
        return result
    _raise_for_auth_error(resp, context="signup")


def sign_in(email: str, password: str) -> dict:
    """Password sign-in. Returns {access_token, refresh_token, expires_at, user}."""
    url = f"{_base_url()}/auth/v1/token"
    resp = _request(
        "POST", url, headers=_anon_headers(), params={"grant_type": "password"},
        json={"email": email, "password": password},
    )
    if resp.status_code == 200:
        return resp.json()
    _raise_for_auth_error(resp, context="signin")


def refresh_session(refresh_token: str) -> dict:
    url = f"{_base_url()}/auth/v1/token"
    resp = _request(
        "POST", url, headers=_anon_headers(), params={"grant_type": "refresh_token"},
        json={"refresh_token": refresh_token},
    )
    if resp.status_code == 200:
        return resp.json()
    raise AuthError("Your session has expired. Please sign in again.")


def sign_out(access_token: str) -> None:
    """Best-effort - revokes the refresh token server-side. Failure here
    never blocks logout; the Flask session is cleared regardless."""
    url = f"{_base_url()}/auth/v1/logout"
    try:
        requests.post(url, headers=_anon_headers({"Authorization": f"Bearer {access_token}"}), timeout=_TIMEOUT)
    except requests.RequestException:
        pass


def _raise_for_auth_error(resp: requests.Response, *, context: str) -> None:
    try:
        detail = resp.json().get("msg") or resp.json().get("error_description") or resp.text
    except ValueError:
        detail = resp.text
    logger.info("auth_rejected", extra={"context": context, "status": resp.status_code})

    if resp.status_code == 400 and context == "signin":
        raise AuthError("Incorrect email or password.", detail)
    if resp.status_code == 422 and context == "signup" and "already registered" in detail.lower():
        raise AuthError("An account with that email already exists.", detail)
    if resp.status_code == 422 and context == "signup":
        raise AuthError("Please use a valid email and a stronger password.", detail)
    if resp.status_code == 429:
        raise AuthError("Too many attempts. Please wait a moment and try again.", detail)
    raise AuthError("We couldn't complete that request. Please try again.", detail)


# --- PostgREST (analysis_history / profiles), always user-scoped ------------

def _user_headers(access_token: str) -> dict:
    return _anon_headers({"Authorization": f"Bearer {access_token}"})


def touch_last_login(user_id: str, access_token: str) -> None:
    """Best-effort - never blocks login on failure."""
    url = f"{_base_url()}/rest/v1/profiles"
    try:
        requests.patch(
            url,
            headers={**_user_headers(access_token), "Prefer": "return=minimal"},
            params={"id": f"eq.{user_id}"},
            json={"last_login": "now()"},
            timeout=_TIMEOUT,
        )
    except requests.RequestException as exc:
        logger.warning("profile_touch_failed", extra={"error": str(exc)})


def get_profile(user_id: str, access_token: str) -> dict | None:
    url = f"{_base_url()}/rest/v1/profiles"
    resp = _request(
        "GET", url, headers=_user_headers(access_token),
        params={"id": f"eq.{user_id}", "select": "*"},
    )
    if resp.status_code == 200:
        rows = resp.json()
        return rows[0] if rows else None
    return None


def record_analysis(
    *, user_id: str, access_token: str, analysis_type: str, filename: str | None,
    result: str | None, confidence: float | None, model_version: str | None,
) -> None:
    """Best-effort: a failure here (e.g. Supabase misconfigured or down)
    never breaks the underlying encode/decode/steganalysis workflow -
    it's called after the real work has already succeeded."""
    url = f"{_base_url()}/rest/v1/analysis_history"
    payload = {
        "user_id": user_id,
        "analysis_type": analysis_type,
        "filename": filename,
        "result": result,
        "confidence": confidence,
        "model_version": model_version,
    }
    try:
        requests.post(
            url,
            headers={**_user_headers(access_token), "Prefer": "return=minimal"},
            json=payload,
            timeout=_TIMEOUT,
        )
    except requests.RequestException as exc:
        logger.warning("analysis_history_write_failed", extra={"error": str(exc)})


def fetch_history(access_token: str, *, limit: int = 50) -> list[dict]:
    url = f"{_base_url()}/rest/v1/analysis_history"
    resp = _request(
        "GET", url, headers=_user_headers(access_token),
        params={"select": "*", "order": "created_at.desc", "limit": str(limit)},
    )
    if resp.status_code == 200:
        return resp.json()
    return []


def fetch_history_item(access_token: str, record_id: str) -> dict | None:
    """Fetches a single history record. No manual ownership check is
    needed here beyond RLS: the query runs as the signed-in user (their
    access token), so Postgres itself returns zero rows for a record
    that belongs to someone else - the caller can't distinguish
    "not found" from "not yours", which is the correct behavior for
    preventing ID enumeration."""
    url = f"{_base_url()}/rest/v1/analysis_history"
    resp = _request(
        "GET", url, headers=_user_headers(access_token),
        params={"id": f"eq.{record_id}", "select": "*"},
    )
    if resp.status_code == 200:
        rows = resp.json()
        return rows[0] if rows else None
    return None
