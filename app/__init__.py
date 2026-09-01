"""Flask application factory for StegoShield."""
from __future__ import annotations

from flask import Flask, jsonify, render_template, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.exceptions import HTTPException

from app.config import get_config
from app.steganography.exceptions import SteganographyError
from app.utils.errors import APIError, map_exception_to_api_error
from app.utils.logging_config import configure_logging, get_logger

logger = get_logger(__name__)

limiter = Limiter(key_func=get_remote_address)


def create_app() -> Flask:
    configure_logging()

    config_cls = get_config()
    app = Flask(
        __name__,
        template_folder="../frontend/templates",
        static_folder="../frontend/static",
    )
    app.config.from_object(config_cls)
    app.config["MAX_CONTENT_LENGTH"] = config_cls.MAX_CONTENT_LENGTH

    limiter.init_app(app)
    if not config_cls.RATE_LIMIT_ENABLED:
        limiter.enabled = False
    else:
        limiter.default_limits = [config_cls.RATE_LIMIT_DEFAULT]

    _register_blueprints(app)
    _register_error_handlers(app)
    _register_security_headers(app)

    logger.info("app_started", extra={"debug": app.config.get("DEBUG", False)})
    return app


def _register_blueprints(app: Flask) -> None:
    from app.routes.api import api_bp
    from app.routes.pages import pages_bp

    app.register_blueprint(pages_bp)
    app.register_blueprint(api_bp, url_prefix="/api")


def _register_security_headers(app: Flask) -> None:
    @app.after_request
    def set_security_headers(response):
        # Defense-in-depth headers appropriate for a self-contained,
        # same-origin server-rendered app with a JSON API.
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-XSS-Protection"] = "0"  # superseded by CSP; disable legacy filter
        # Chart.js is vendored locally (frontend/static/js/vendor/) rather
        # than loaded from a CDN, so the policy needs no third-party
        # script-src exception and the app works fully offline.
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            # 'blob:' is required for the local file-preview thumbnails on
            # the Encode/Decode/Steganalysis/Image-Analysis pages, which
            # use URL.createObjectURL(file) to show a preview before any
            # upload happens (see frontend/static/js/{encode,decode,
            # steganalysis,image_analysis}.js). Found missing via live
            # browser testing during the production audit - previously
            # every preview thumbnail was silently broken by this policy.
            "img-src 'self' data: blob:; "
            "style-src 'self' 'unsafe-inline'; "
            "script-src 'self'; "
            "connect-src 'self'"
        )
        return response


def _register_error_handlers(app: Flask) -> None:
    @app.errorhandler(APIError)
    def handle_api_error(err: APIError):
        return jsonify(err.to_dict()), err.status_code

    @app.errorhandler(SteganographyError)
    def handle_steganography_error(err: SteganographyError):
        # These are ordinary, expected validation outcomes (bad upload,
        # message too big, no payload found, corrupted checksum, ...) -
        # not application bugs. Registering a dedicated handler (rather
        # than letting them fall through to the catch-all Exception
        # handler below) keeps them out of the ERROR-level
        # "unhandled_exception" log stream with a full stack trace, so
        # real errors don't get lost in routine-validation noise.
        api_error = map_exception_to_api_error(err)
        logger.info(
            "request_rejected",
            extra={"path": request.path, "code": api_error.code, "status": api_error.status_code},
        )
        if request.path.startswith("/api/"):
            return jsonify(api_error.to_dict()), api_error.status_code
        return render_template("errors/500.html"), api_error.status_code

    @app.errorhandler(413)
    def handle_too_large(err):
        max_mb = app.config.get("MAX_CONTENT_LENGTH_MB", 10)
        return (
            jsonify(
                {
                    "error": {
                        "code": "file_too_large",
                        "message": f"Upload exceeds the maximum allowed size of {max_mb} MB.",
                    }
                }
            ),
            413,
        )

    @app.errorhandler(429)
    def handle_rate_limited(err):
        return (
            jsonify(
                {
                    "error": {
                        "code": "rate_limited",
                        "message": "Too many requests. Please slow down and try again shortly.",
                    }
                }
            ),
            429,
        )

    @app.errorhandler(HTTPException)
    def handle_http_exception(err: HTTPException):
        if request.path.startswith("/api/"):
            return (
                jsonify({"error": {"code": "http_error", "message": err.description}}),
                err.code,
            )
        return err

    @app.errorhandler(Exception)
    def handle_unexpected(err: Exception):
        # Never leak a stack trace or internal exception message to the
        # client; log full details server-side only.
        logger.exception("unhandled_exception", extra={"path": request.path})
        api_error = map_exception_to_api_error(err)
        if request.path.startswith("/api/"):
            return jsonify(api_error.to_dict()), api_error.status_code
        return render_template("errors/500.html"), 500
