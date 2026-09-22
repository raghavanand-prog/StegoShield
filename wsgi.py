"""WSGI entrypoint for platforms that expect a module-level `app`
object (e.g. Vercel's Python runtime, referenced from pyproject.toml's
`[tool.vercel] entrypoint`).

Local development still uses `python run.py`; this file changes
nothing about how the app is built, it only exposes the same factory
output at import time.
"""
from app import create_app

app = create_app()
