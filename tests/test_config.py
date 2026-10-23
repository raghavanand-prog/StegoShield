"""Regression tests for the production SECRET_KEY fail-fast check.

These run `create_app()` in a fresh subprocess (rather than monkeypatching
os.environ + importlib.reload in-process) because app/config.py reads
SECRET_KEY into a class attribute at import time - a subprocess is the
only way to exercise a *different* environment's startup behavior without
mutating the already-imported `app` module that every other test file in
this suite shares via tests/conftest.py.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
_CREATE_APP_SNIPPET = "from app import create_app; create_app()"


def _run_create_app(env_overrides: dict) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env.update(env_overrides)
    return subprocess.run(
        [sys.executable, "-c", _CREATE_APP_SNIPPET],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_production_rejects_missing_secret_key():
    env = {"FLASK_ENV": "production"}
    env.pop("SECRET_KEY", None)
    result = _run_create_app(env)
    assert result.returncode != 0
    assert "SECRET_KEY" in result.stderr


def test_production_rejects_env_example_placeholder():
    result = _run_create_app({
        "FLASK_ENV": "production",
        "SECRET_KEY": "change-this-to-a-long-random-value",
    })
    assert result.returncode != 0
    assert "SECRET_KEY" in result.stderr


def test_production_accepts_a_real_secret_key():
    result = _run_create_app({
        "FLASK_ENV": "production",
        "SECRET_KEY": "a-sufficiently-random-production-value-not-a-placeholder",
    })
    assert result.returncode == 0, result.stderr


def test_development_allows_default_secret_key_for_zero_setup_local_dev():
    env = {"FLASK_ENV": "development"}
    env.pop("SECRET_KEY", None)
    result = _run_create_app(env)
    assert result.returncode == 0, result.stderr
