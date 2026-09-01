"""Orchestration for the /api/steganalysis endpoint."""
from __future__ import annotations

from app.security.validators import validate_and_decode_image
from app.services import activity_log
from app.steganalysis.predictor import predict
from app.utils.logging_config import get_logger

logger = get_logger(__name__)


def run_steganalysis(file_bytes: bytes, filename: str) -> dict:
    validated = validate_and_decode_image(file_bytes, filename)

    result = predict(validated.rgb_array)
    response = result.as_dict()
    response["image_dimensions"] = f"{validated.width}x{validated.height}"

    activity_log.record(
        "STEGANALYSIS",
        {
            "filename_extension": validated.detected_extension,
            "image_dimensions": f"{validated.width}x{validated.height}",
            "prediction": result.prediction,
            "risk_level": result.risk.risk_level,
            "status": "success",
        },
    )
    return response
