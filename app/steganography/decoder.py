"""High-level decode operation: stego image -> verified secret message."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.steganography import bitstream, lsb_core, payload
from app.steganography.exceptions import NoHiddenDataError


@dataclass
class DecodeResult:
    message: str
    version: int
    payload_length: int


def decode_message(image_array: np.ndarray) -> DecodeResult:
    """Extract and verify a StegoShield payload from `image_array`.

    Raises NoHiddenDataError if no valid magic header is found, or
    IntegrityVerificationError (from payload.verify_and_extract) if the
    checksum does not match.
    """
    header_bits_needed = payload.header_size() * 8
    total_capacity = lsb_core.capacity_bits(image_array)

    if header_bits_needed > total_capacity:
        raise NoHiddenDataError("Image is too small to contain a valid payload header.")

    header_bits = lsb_core.extract_bits(image_array, header_bits_needed)
    header_bytes = bitstream.bits_to_bytes(header_bits)

    version, length, checksum = payload.parse_header(header_bytes)

    total_bits_needed = (payload.header_size() + length) * 8
    if total_bits_needed > total_capacity:
        raise NoHiddenDataError(
            "Payload header found but declared length exceeds image capacity; "
            "this is not a valid StegoShield payload."
        )

    all_bits = lsb_core.extract_bits(image_array, total_bits_needed)
    data_bits = all_bits[header_bits_needed:]
    data_bytes = bitstream.bits_to_bytes(data_bits)

    message_bytes = payload.verify_and_extract(version, length, checksum, data_bytes)

    return DecodeResult(
        message=message_bytes.decode("utf-8", errors="strict"),
        version=version,
        payload_length=length,
    )
