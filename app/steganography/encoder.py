"""High-level encode operation: message + cover image -> stego image."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.steganography import bitstream, capacity, lsb_core, payload
from app.steganography.exceptions import CapacityExceededError, EmptyMessageError


@dataclass
class EncodeResult:
    stego_array: np.ndarray
    capacity_report: capacity.CapacityReport
    message_bytes: int
    utilization_percent: float


def encode_message(image_array: np.ndarray, message: str) -> EncodeResult:
    """Embed `message` (UTF-8 text) into `image_array` using LSB steganography.

    Returns an EncodeResult containing the modified pixel array (the
    original array is not mutated) plus capacity/utilization metadata
    for display in the UI.
    """
    if message is None or len(message) == 0:
        raise EmptyMessageError("Secret message must not be empty.")

    message_bytes = message.encode("utf-8")
    report = capacity.compute_capacity(image_array)

    if len(message_bytes) > report.max_message_bytes:
        raise CapacityExceededError(len(message_bytes), report.max_message_bytes)

    framed = payload.build_payload(message_bytes)
    bits = bitstream.bytes_to_bits(framed)
    stego_array = lsb_core.embed_bits(image_array, bits)

    util = capacity.utilization_percent(len(message_bytes), report)

    return EncodeResult(
        stego_array=stego_array,
        capacity_report=report,
        message_bytes=len(message_bytes),
        utilization_percent=util,
    )
