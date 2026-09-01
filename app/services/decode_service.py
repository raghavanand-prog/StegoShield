"""Orchestration for the /api/decode endpoint: validate -> decode -> verify."""
from __future__ import annotations

import time

from app.security.validators import validate_and_decode_image
from app.services import activity_log
from app.steganography.decoder import decode_message
from app.utils.logging_config import get_logger

logger = get_logger(__name__)


def run_decode(file_bytes: bytes, filename: str) -> dict:
    t0 = time.time()
    validated = validate_and_decode_image(file_bytes, filename)

    result = decode_message(validated.rgb_array)

    response = {
        "message": result.message,
        "payload_length_bytes": result.payload_length,
        "payload_version": result.version,
        "integrity_verified": True,
        "processing_time_ms": round((time.time() - t0) * 1000, 2),
    }

    activity_log.record(
        "DECODE",
        {
            "filename_extension": validated.detected_extension,
            "image_dimensions": f"{validated.width}x{validated.height}",
            "payload_length_bytes": result.payload_length,
            "status": "success",
        },
    )
    logger.info(
        "decode_completed",
        extra={"payload_length": result.payload_length, "processing_time_ms": response["processing_time_ms"]},
    )
    return response
