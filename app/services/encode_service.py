"""Orchestration for the /api/encode endpoint: validate -> encode -> analyze."""
from __future__ import annotations

import time

from app.security.validators import validate_and_decode_image, validate_lossless_for_encoding
from app.services import activity_log
from app.services.image_quality import compute_quality_metrics
from app.services.visual_analysis import build_visual_analysis
from app.steganography import capacity as capacity_mod
from app.steganography.encoder import encode_message
from app.utils.image_io import rgb_array_to_png_bytes
from app.utils.logging_config import get_logger

logger = get_logger(__name__)


def compute_capacity_for_upload(file_bytes: bytes, filename: str) -> dict:
    validated = validate_and_decode_image(file_bytes, filename)
    report = capacity_mod.compute_capacity(validated.rgb_array)
    return {**report.as_dict(), "detected_mime": validated.detected_mime}


def run_encode(file_bytes: bytes, filename: str, message: str, include_visual_analysis: bool = True) -> dict:
    t0 = time.time()
    validated = validate_and_decode_image(file_bytes, filename)
    validate_lossless_for_encoding(validated.detected_extension)

    original_array = validated.rgb_array
    result = encode_message(original_array, message)

    quality = compute_quality_metrics(original_array, result.stego_array)
    stego_png_bytes = rgb_array_to_png_bytes(result.stego_array)

    response = {
        "capacity": result.capacity_report.as_dict(),
        "message_bytes": result.message_bytes,
        "utilization_percent": result.utilization_percent,
        "quality": quality.as_dict(),
        "stego_image_png_base64": _to_base64(stego_png_bytes),
        "processing_time_ms": round((time.time() - t0) * 1000, 2),
    }

    if include_visual_analysis:
        response["visual_analysis"] = build_visual_analysis(original_array, result.stego_array)

    activity_log.record(
        "ENCODE",
        {
            "filename_extension": validated.detected_extension,
            "image_dimensions": f"{validated.width}x{validated.height}",
            "message_bytes": result.message_bytes,
            "utilization_percent": result.utilization_percent,
            "status": "success",
        },
    )
    logger.info(
        "encode_completed",
        extra={
            "width": validated.width,
            "height": validated.height,
            "message_bytes": result.message_bytes,
            "utilization_percent": result.utilization_percent,
            "processing_time_ms": response["processing_time_ms"],
        },
    )
    return response


def _to_base64(data: bytes) -> str:
    import base64

    return base64.b64encode(data).decode("ascii")
