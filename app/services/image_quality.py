"""Objective image-quality metrics comparing a cover image to its stego version.

All three metrics are computed directly from the actual pixel arrays -
nothing here is estimated or hardcoded.

MSE (Mean Squared Error)
    Average squared per-pixel difference. Lower is more similar.
    MSE = (1/N) * sum((original - stego)^2)

PSNR (Peak Signal-to-Noise Ratio, dB)
    PSNR = 10 * log10(MAX^2 / MSE), MAX = 255 for 8-bit images.
    Higher is more similar; LSB embedding typically yields PSNR well
    above 50 dB because each modified pixel changes by at most 1/255.
    PSNR is undefined (infinite) when MSE == 0, i.e. identical images.

SSIM (Structural Similarity Index)
    Perceptual similarity metric in [-1, 1] (practically [0, 1] for
    natural images) that accounts for luminance, contrast, and
    structure rather than raw pixel differences. Computed via
    scikit-image's windowed implementation.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from skimage.metrics import structural_similarity as sk_ssim


@dataclass
class QualityMetrics:
    mse: float
    psnr: float  # dB; float('inf') if images are identical
    ssim: float
    processing_time_ms: float = 0.0

    def as_dict(self) -> dict:
        return {
            "mse": round(self.mse, 6),
            "psnr": (None if np.isinf(self.psnr) else round(self.psnr, 2)),
            "psnr_display": ("∞ (identical images)" if np.isinf(self.psnr) else f"{self.psnr:.2f} dB"),
            "ssim": round(self.ssim, 6),
        }


def compute_mse(original: np.ndarray, modified: np.ndarray) -> float:
    a = original.astype(np.float64)
    b = modified.astype(np.float64)
    return float(np.mean((a - b) ** 2))


def compute_psnr(original: np.ndarray, modified: np.ndarray, mse: float | None = None) -> float:
    if mse is None:
        mse = compute_mse(original, modified)
    if mse == 0:
        return float("inf")
    max_pixel = 255.0
    return 10.0 * np.log10((max_pixel**2) / mse)


def compute_ssim(original: np.ndarray, modified: np.ndarray) -> float:
    a = original.astype(np.uint8)
    b = modified.astype(np.uint8)
    channel_axis = 2 if a.ndim == 3 else None
    return float(sk_ssim(a, b, channel_axis=channel_axis, data_range=255))


def compute_quality_metrics(original: np.ndarray, modified: np.ndarray) -> QualityMetrics:
    if original.shape != modified.shape:
        raise ValueError("Original and modified images must have identical shape.")
    mse = compute_mse(original, modified)
    psnr = compute_psnr(original, modified, mse)
    ssim = compute_ssim(original, modified)
    return QualityMetrics(mse=mse, psnr=psnr, ssim=ssim)


METRIC_EXPLANATIONS = {
    "mse": (
        "Mean Squared Error: the average squared difference between corresponding "
        "pixels. Values near 0 mean the two images are nearly pixel-identical, "
        "which is expected for LSB steganography since each modified channel "
        "value changes by at most 1."
    ),
    "psnr": (
        "Peak Signal-to-Noise Ratio (dB): measures how much the stego image "
        "deviates from the original relative to the maximum possible pixel "
        "value. LSB embedding typically produces PSNR above 50 dB (higher is "
        "better); values above ~40 dB are generally considered visually "
        "indistinguishable from the original."
    ),
    "ssim": (
        "Structural Similarity Index: a perceptual metric (0-1) that compares "
        "luminance, contrast, and structural patterns rather than raw pixel "
        "differences. Values close to 1.0 indicate the images are structurally "
        "identical to the human eye."
    ),
}
