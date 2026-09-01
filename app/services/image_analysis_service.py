"""Orchestration for the /api/image-analysis endpoint (standalone compare)."""
from __future__ import annotations

import time

from app.security.validators import validate_and_decode_image
from app.services import activity_log
from app.services.image_quality import compute_quality_metrics
from app.services.visual_analysis import build_visual_analysis
from app.utils.errors import APIError
from app.utils.logging_config import get_logger

logger = get_logger(__name__)


def run_image_analysis(original_bytes: bytes, original_name: str, modified_bytes: bytes, modified_name: str) -> dict:
    t0 = time.time()
    original_validated = validate_and_decode_image(original_bytes, original_name)
    modified_validated = validate_and_decode_image(modified_bytes, modified_name)

    original_array = original_validated.rgb_array
    modified_array = modified_validated.rgb_array

    if original_array.shape != modified_array.shape:
        raise APIError(
            "The two images must have identical dimensions to be compared "
            f"(got {original_array.shape[1]}x{original_array.shape[0]} vs "
            f"{modified_array.shape[1]}x{modified_array.shape[0]}).",
            422,
            "dimension_mismatch",
        )

    quality = compute_quality_metrics(original_array, modified_array)
    visual = build_visual_analysis(original_array, modified_array)

    activity_log.record("IMAGE_ANALYSIS", {"status": "success"})

    return {
        "quality": quality.as_dict(),
        "visual_analysis": visual,
        "processing_time_ms": round((time.time() - t0) * 1000, 2),
    }
