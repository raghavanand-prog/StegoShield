"""Low-level bit <-> byte conversion helpers used by the LSB engine.

Kept isolated from PIL/NumPy so it can be unit-tested in complete
isolation from image I/O.
"""
from __future__ import annotations

import numpy as np


def bytes_to_bits(data: bytes) -> np.ndarray:
    """Convert a bytes object into a 1-D numpy array of 0/1 uint8 bits.

    Bits are produced most-significant-bit first for every byte, which
    is the conventional big-endian bit ordering and keeps encode/decode
    symmetric and easy to reason about.
    """
    if not data:
        return np.array([], dtype=np.uint8)
    arr = np.frombuffer(data, dtype=np.uint8)
    bits = np.unpackbits(arr)  # MSB-first per byte
    return bits


def bits_to_bytes(bits: np.ndarray) -> bytes:
    """Inverse of bytes_to_bits. `bits` length must be a multiple of 8."""
    if len(bits) % 8 != 0:
        raise ValueError("Bit array length must be a multiple of 8.")
    if len(bits) == 0:
        return b""
    packed = np.packbits(bits.astype(np.uint8))
    return packed.tobytes()


def int_to_bytes(value: int, length: int) -> bytes:
    """Big-endian fixed-width integer encoding."""
    return value.to_bytes(length, byteorder="big", signed=False)


def bytes_to_int(data: bytes) -> int:
    return int.from_bytes(data, byteorder="big", signed=False)
