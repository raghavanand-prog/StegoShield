"""Authentication routes: /login, /signup, /logout, plus the
authenticated area (/dashboard, /account, /history). Everything else in
StegoShield (encode/decode/steganalysis/image-analysis/docs) is
unauthenticated by design - see README "Authentication" for why the
public demo intentionally has no login wall in front of it.
"""
from __future__ import annotations

import re

from flask import Blueprint, current_app, redirect, render_template, request, session, url_for

from app import limiter
from app.auth.decorators import (
    clear_session,
    csrf_valid,
    get_csrf_token,
    get_current_user,
    login_required,
    start_session,
)
from app.auth.supabase_client import (
    AuthError,
    fetch_history,
    fetch_history_item,
    get_profile,
    sign_in,
    sign_out,
    sign_up,
    touch_last_login,
)
from app.config import Config
from app.utils.logging_config import get_logger

logger = get_logger(__name__)
auth_bp = Blueprint("auth", __name__)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _valid_email(email: str) -> bool:
    return bool(email) and bool(_EMAIL_RE.match(email))


def _password_issues(password: str) -> str | None:
    if len(password) < 8:
        return "Password must be at least 8 characters."
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        return "Password must include at least one letter and one number."
    return None


def _auth_disabled_response(template: str):
    return render_template(
        template,
        auth_disabled=True,
        error="Authentication isn't configured on this deployment.",
        csrf_token="",
    )


@auth_bp.get("/login")
def login():
    if not current_app.config["AUTH_ENABLED"]:
        return _auth_disabled_response("auth/login.html")
    if get_current_user():
        return redirect(url_for("auth.dashboard"))
    return render_template("auth/login.html", csrf_token=get_csrf_token(), next=request.args.get("next", ""))


@auth_bp.post("/login")
@limiter.limit(Config.RATE_LIMIT_AUTH)
def login_submit():
    if not current_app.config["AUTH_ENABLED"]:
        return _auth_disabled_response("auth/login.html")

    if not csrf_valid(request.form.get("csrf_token")):
        return render_template("auth/login.html", csrf_token=get_csrf_token(), error="Your session expired, please try again."), 400

    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    next_url = request.form.get("next") or url_for("auth.dashboard")

    try:
        token_data = sign_in(email, password)
    except AuthError as exc:
        logger.info("login_failed", extra={"reason": exc.detail})
        return render_template("auth/login.html", csrf_token=get_csrf_token(), error=exc.safe_message, next=next_url), 401

    start_session(token_data)
    user = token_data.get("user") or {}
    if user.get("id"):
        touch_last_login(user["id"], token_data["access_token"])
    return redirect(next_url if next_url.startswith("/") else url_for("auth.dashboard"))


@auth_bp.get("/signup")
def signup():
    if not current_app.config["AUTH_ENABLED"]:
        return _auth_disabled_response("auth/signup.html")
    if get_current_user():
        return redirect(url_for("auth.dashboard"))
    return render_template("auth/signup.html", csrf_token=get_csrf_token())


@auth_bp.post("/signup")
@limiter.limit(Config.RATE_LIMIT_AUTH)
def signup_submit():
    if not current_app.config["AUTH_ENABLED"]:
        return _auth_disabled_response("auth/signup.html")

    if not csrf_valid(request.form.get("csrf_token")):
        return render_template("auth/signup.html", csrf_token=get_csrf_token(), error="Your session expired, please try again."), 400

    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    confirm = request.form.get("confirm_password", "")

    if not _valid_email(email):
        return render_template("auth/signup.html", csrf_token=get_csrf_token(), error="Enter a valid email address."), 400
    if password != confirm:
        return render_template("auth/signup.html", csrf_token=get_csrf_token(), error="Passwords do not match."), 400
    issue = _password_issues(password)
    if issue:
        return render_template("auth/signup.html", csrf_token=get_csrf_token(), error=issue), 400

    try:
        result = sign_up(email, password)
    except AuthError as exc:
        logger.info("signup_failed", extra={"reason": exc.detail})
        return render_template("auth/signup.html", csrf_token=get_csrf_token(), error=exc.safe_message), 400

    if result.get("email_confirmation_required"):
        return render_template(
            "auth/signup.html",
            csrf_token=get_csrf_token(),
            success="Account created. Check your email to confirm your address before signing in.",
        )

    # Confirmation disabled on this Supabase project - sign in immediately.
    start_session(result)
    return redirect(url_for("auth.dashboard"))


@auth_bp.post("/logout")
def logout():
    # CSRF check even though logout has no data-leak impact by itself -
    # an attacker forcing a surprise logout is a real (if low-severity)
    # nuisance, and every other state-changing form in this app checks
    # csrf_token, so this stays consistent rather than being a silent
    # exception to that rule.
    if csrf_valid(request.form.get("csrf_token")):
        auth = session.get("auth")
        if auth:
            sign_out(auth["access_token"])
        clear_session()
    return redirect(url_for("pages.dashboard"))


@auth_bp.get("/dashboard")
@login_required
def dashboard(user: dict):
    profile = get_profile(user["user_id"], user["access_token"])
    recent = fetch_history(user["access_token"], limit=5)
    return render_template("auth/dashboard.html", user=user, profile=profile, recent=recent)


@auth_bp.get("/account")
@login_required
def account(user: dict):
    profile = get_profile(user["user_id"], user["access_token"])
    return render_template("auth/account.html", user=user, profile=profile)


@auth_bp.get("/history")
@login_required
def history(user: dict):
    records = fetch_history(user["access_token"], limit=100)
    return render_template("auth/history.html", user=user, records=records)


@auth_bp.get("/history/<record_id>")
@login_required
def history_detail(user: dict, record_id: str):
    # fetch_history_item runs the query as this user (their access
    # token) - Postgres RLS returns zero rows for a record that belongs
    # to someone else, so this 404s exactly the same way for "doesn't
    # exist" and "isn't yours". That's deliberate: it doesn't confirm to
    # an attacker that a given ID even exists.
    record = fetch_history_item(user["access_token"], record_id)
    if record is None:
        return render_template("errors/404.html"), 404
    return render_template("auth/history_detail.html", user=user, record=record)
