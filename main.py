"""Vercel Python zero-config entrypoint: a top-level `main.py` exposing
a module-level `app` object is Vercel's default-detected Flask
location, so no pyproject.toml `[tool.vercel] entrypoint` override is
needed. (A pyproject.toml at all switches Vercel's Python builder onto
its newer uv-based path, which - as found via a real production
failure on this project - can defer some dependency installs to
request-time and hit a `/tmp` space limit for a stack this size;
requirements.txt + this file avoids that path entirely.)

Local development still uses `python run.py`; this file changes
nothing about how the app is built, it only exposes the same factory
output at import time.
"""
from app import create_app

app = create_app()
