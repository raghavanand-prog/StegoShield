"""JSON API endpoints. All upload-accepting endpoints treat their input
as untrusted (see app.security.validators) and never echo back raw
exception text - see app.utils.errors for the safe-message mapping
wired up in the global error handler.
"""
from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from app import limiter
from app.auth.decorators import get_current_user
from app.auth.supabase_client import record_analysis
from app.config import Config
from app.services import activity_log
from app.services.decode_service import run_decode
from app.services.encode_service import compute_capacity_for_upload, run_encode
from app.services.image_analysis_service import run_image_analysis
from app.services.model_service import get_model_metadata, get_model_status
from app.services.steganalysis_service import run_steganalysis
from app.steganography.exceptions import EmptyMessageError
from app.utils.errors import APIError

api_bp = Blueprint("api", __name__)


def _get_uploaded_file(field_name: str):
    if field_name not in request.files or request.files[field_name].filename == "":
        raise APIError(f"No file provided for '{field_name}'.", 400, "missing_file")
    f = request.files[field_name]
    data = f.read()
    return data, f.filename


def _safe_filename_for_history(filename: str) -> str:
    """Metadata only, never a path: last path segment, truncated."""
    name = (filename or "").replace("\\", "/").rsplit("/", 1)[-1]
    return name[:200]


def _record_history_if_signed_in(*, analysis_type: str, filename: str, result: str | None,
                                  confidence: float | None = None, model_version: str | None = None) -> None:
    """Best-effort: only runs when Supabase auth is configured and the
    caller has a valid session; any failure is swallowed inside
    record_analysis() itself so it can never affect the actual
    steganography/ML response the user is waiting on."""
    if not current_app.config["AUTH_ENABLED"]:
        return
    user = get_current_user()
    if not user:
        return
    record_analysis(
        user_id=user["user_id"],
        access_token=user["access_token"],
        analysis_type=analysis_type,
        filename=_safe_filename_for_history(filename),
        result=result,
        confidence=confidence,
        model_version=model_version,
    )


@api_bp.post("/capacity")
@limiter.limit(Config.RATE_LIMIT_UPLOAD)
def capacity():
    file_bytes, filename = _get_uploaded_file("image")
    return jsonify(compute_capacity_for_upload(file_bytes, filename))


@api_bp.post("/encode")
@limiter.limit(Config.RATE_LIMIT_UPLOAD)
def encode():
    file_bytes, filename = _get_uploaded_file("image")
    message = request.form.get("message", "")
    if not message:
        raise EmptyMessageError("Secret message must not be empty.")
    result = run_encode(file_bytes, filename, message)
    _record_history_if_signed_in(analysis_type="encode", filename=filename, result="encoded")
    return jsonify(result)


@api_bp.post("/decode")
@limiter.limit(Config.RATE_LIMIT_UPLOAD)
def decode():
    file_bytes, filename = _get_uploaded_file("image")
    result = run_decode(file_bytes, filename)
    _record_history_if_signed_in(analysis_type="decode", filename=filename, result="decoded")
    return jsonify(result)


@api_bp.post("/steganalysis")
@limiter.limit(Config.RATE_LIMIT_UPLOAD)
def steganalysis():
    file_bytes, filename = _get_uploaded_file("image")
    result = run_steganalysis(file_bytes, filename)
    _record_history_if_signed_in(
        analysis_type="steganalysis",
        filename=filename,
        result=result.get("prediction"),
        confidence=result.get("stego_probability"),
        model_version=result.get("model_name"),
    )
    return jsonify(result)


@api_bp.post("/image-analysis")
@limiter.limit(Config.RATE_LIMIT_UPLOAD)
def image_analysis():
    original_bytes, original_name = _get_uploaded_file("original")
    modified_bytes, modified_name = _get_uploaded_file("modified")
    result = run_image_analysis(original_bytes, original_name, modified_bytes, modified_name)
    _record_history_if_signed_in(analysis_type="image_analysis", filename=original_name, result="compared")
    return jsonify(result)


@api_bp.get("/model-performance")
def model_performance():
    return jsonify(get_model_metadata())


@api_bp.get("/model-status")
def model_status():
    return jsonify(get_model_status())


@api_bp.get("/recent-activity")
def recent_activity():
    return jsonify({"activity": activity_log.recent()})


@api_bp.get("/health")
def health():
    return jsonify({"status": "ok"})
