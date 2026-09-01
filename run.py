#!/usr/bin/env python3
"""Development entry point: `python run.py`.

For production, use a WSGI server instead, e.g.:
    gunicorn "app:create_app()" --bind 0.0.0.0:5000 --workers 2
"""
from app import create_app
from app.config import get_config

app = create_app()

if __name__ == "__main__":
    config_cls = get_config()
    app.run(host=config_cls.HOST, port=config_cls.PORT, debug=config_cls.DEBUG)
