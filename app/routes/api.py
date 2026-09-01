"""JSON API endpoints. All upload-accepting endpoints treat their input
as untrusted (see app.security.validators) and never echo back raw
exception text - see app.utils.errors for the safe-message mapping
wired up in the global error handler.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from app import limiter
from app.services import activity_log
from app.services.decode_service import run_decode
from app.services.encode_service import compute_capacity_for_upload, run_encode
from app.services.image_analysis_service import run_image_analysis
from app.services.model_service import get_model_metadata, get_model_status
from app.services.steganalysis_service import run_steganalysis
from app.steganography.exceptions import EmptyMessageError
from app.utils.errors import APIError
from app.config import Config

api_bp = Blueprint("api", __name__)


def _get_uploaded_file(field_name: str):
    if field_name not in request.files or request.files[field_name].filename == "":
        raise APIError(f"No file provided for '{field_name}'.", 400, "missing_file")
    f = request.files[field_name]
    data = f.read()
    return data, f.filename


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
    return jsonify(run_encode(file_bytes, filename, message))


@api_bp.post("/decode")
@limiter.limit(Config.RATE_LIMIT_UPLOAD)
def decode():
    file_bytes, filename = _get_uploaded_file("image")
    return jsonify(run_decode(file_bytes, filename))


@api_bp.post("/steganalysis")
@limiter.limit(Config.RATE_LIMIT_UPLOAD)
def steganalysis():
    file_bytes, filename = _get_uploaded_file("image")
    return jsonify(run_steganalysis(file_bytes, filename))


@api_bp.post("/image-analysis")
@limiter.limit(Config.RATE_LIMIT_UPLOAD)
def image_analysis():
    original_bytes, original_name = _get_uploaded_file("original")
    modified_bytes, modified_name = _get_uploaded_file("modified")
    return jsonify(run_image_analysis(original_bytes, original_name, modified_bytes, modified_name))


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
