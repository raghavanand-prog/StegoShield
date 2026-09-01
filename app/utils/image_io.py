"""Conversions between raw bytes, PIL Images, and RGB numpy arrays."""
from __future__ import annotations

import io

import numpy as np
from PIL import Image


def bytes_to_rgb_array(file_bytes: bytes) -> np.ndarray:
    """Decode image bytes to an (H, W, 3) uint8 RGB array.

    Images are normalized to RGB (dropping alpha, expanding grayscale)
    so every downstream component (steganography, feature extraction,
    quality metrics) can assume a consistent 3-channel layout.
    """
    img = Image.open(io.BytesIO(file_bytes))
    img = img.convert("RGB")
    return np.array(img, dtype=np.uint8)


def rgb_array_to_png_bytes(array: np.ndarray) -> bytes:
    img = Image.fromarray(array.astype(np.uint8), mode="RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
