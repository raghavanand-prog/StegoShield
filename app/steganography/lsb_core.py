"""Pixel-level LSB (Least Significant Bit) embedding primitives.

This module operates purely on NumPy arrays representing image pixel
data - it has no knowledge of payload framing, files, or Flask. That
separation keeps the bit-embedding math easy to test and easy to reason
about independently of everything built on top of it.

Algorithm
---------
For an 8-bit channel value `p` and a secret bit `b` (0 or 1), LSB
embedding replaces the least significant bit of `p`:

    p' = (p & 0xFE) | b       # clear bit 0, then set it to b

This changes `p` by at most 1 (in either direction), which is why LSB
steganography is visually imperceptible: for a byte with LSB 0, setting
b=1 adds 1; for a byte with LSB 1, setting b=0 subtracts 1; if the bit
already matches, the pixel is unchanged.

Extraction simply reads bit 0 of each channel value back out:

    b = p' & 1

We embed sequentially across the flattened R, G, B channel bytes of the
image in row-major order (alpha, if present, is left untouched so
transparency is preserved unmodified).
"""
from __future__ import annotations

import numpy as np


def usable_channels(image_array: np.ndarray) -> int:
    """Return the number of colour channels usable for embedding (RGB only).

    Alpha channels are excluded: modifying them can alter visible
    transparency in some viewers and is unnecessary since RGB already
    provides ample capacity.
    """
    if image_array.ndim == 2:
        return 1  # grayscale
    return min(3, image_array.shape[2])


def capacity_bits(image_array: np.ndarray) -> int:
    """Total number of bits that can be embedded in this image."""
    h, w = image_array.shape[0], image_array.shape[1]
    return h * w * usable_channels(image_array)


def embed_bits(image_array: np.ndarray, bits: np.ndarray) -> np.ndarray:
    """Return a copy of image_array with `bits` embedded in the LSBs.

    Raises ValueError if there is insufficient capacity - callers should
    validate capacity beforehand via capacity_bits() for a friendlier
    error message; this is a defensive last-resort check.
    """
    channels = usable_channels(image_array)
    total_capacity = capacity_bits(image_array)
    if len(bits) > total_capacity:
        raise ValueError(
            f"Insufficient capacity: need {len(bits)} bits, have {total_capacity}."
        )

    out = image_array.copy()
    flat = out[..., :channels].reshape(-1) if out.ndim == 3 else out.reshape(-1)

    n = len(bits)
    # Clear LSBs of the target region then OR in the new bits.
    target = flat[:n]
    target &= np.uint8(0xFE)
    target |= bits.astype(np.uint8)
    flat[:n] = target

    if out.ndim == 3:
        out[..., :channels] = flat.reshape(out.shape[0], out.shape[1], channels)
    else:
        out = flat.reshape(out.shape)
    return out


def extract_bits(image_array: np.ndarray, num_bits: int) -> np.ndarray:
    """Extract the first `num_bits` LSBs from the image in embedding order."""
    channels = usable_channels(image_array)
    total_capacity = capacity_bits(image_array)
    if num_bits > total_capacity:
        raise ValueError(
            f"Requested {num_bits} bits but image only holds {total_capacity}."
        )

    flat = (
        image_array[..., :channels].reshape(-1)
        if image_array.ndim == 3
        else image_array.reshape(-1)
    )
    return (flat[:num_bits] & np.uint8(1)).astype(np.uint8)
