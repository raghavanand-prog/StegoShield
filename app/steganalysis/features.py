"""Statistical feature extraction for steganalysis.

This is the single source of truth for turning a raw RGB image array
into a fixed-length numeric feature vector. It is used identically at
training time (ml/training/train_model.py, via ml/features/extractor.py)
and at inference time (app/steganalysis/predictor.py), which matters:
if training and inference computed features differently, the model
would be evaluated on a distribution it never saw.

Every feature below has a concrete steganalysis rationale - LSB
embedding statistically perturbs a real photograph in specific,
measurable ways even though it is visually imperceptible:

* It flattens/whitens the LSB plane of a natural image (which is
  normally *not* uniformly random - real photo LSBs are weakly
  correlated with the image content) towards a ~50/50 bit
  distribution with elevated entropy.
* It weakens the correlation between spatially adjacent pixels,
  because roughly half of the LSBs are being overwritten with
  effectively-random payload bits rather than following the smooth
  gradients typical of natural images.
* It adds a small amount of high-frequency noise, detectable in
  pixel-difference and local-noise statistics.
* It can subtly perturb the low-order histogram structure (a
  classic artifact is the flattening of "pairs of values" in LSB
  planes, related to the RS/chi-square steganalysis literature).

None of these signals is individually reliable (payload sizes below
~5-10% capacity are notoriously hard to detect from statistics alone,
and this is documented as a limitation), but a Random Forest trained
across many such weak signals can learn a useful decision boundary,
which is the entire premise of statistical steganalysis.
"""
from __future__ import annotations

import numpy as np
from scipy import stats as scipy_stats

FEATURE_NAMES: list[str] = []  # populated at import time, see bottom of file


def _shannon_entropy(channel: np.ndarray) -> float:
    """Shannon entropy (bits) of an 8-bit channel's value distribution.

    High entropy = pixel values are spread evenly across [0, 255]
    (closer to random noise). Natural photographic channels usually
    have entropy well below the theoretical maximum of 8.0 bits.
    """
    hist, _ = np.histogram(channel, bins=256, range=(0, 256))
    probs = hist / max(hist.sum(), 1)
    probs = probs[probs > 0]
    return float(-np.sum(probs * np.log2(probs)))


def _lsb_plane_entropy(channel: np.ndarray) -> float:
    """Entropy of just the least-significant-bit plane (0/1 values).

    This is the single most direct steganalysis signal for LSB
    steganography: a clean channel's LSB plane is usually *not*
    perfectly 50/50 (it correlates weakly with texture/edges), while
    a fully-utilized LSB-embedded region drives the LSB plane toward
    maximum entropy (1.0 bit, i.e. uniform 50/50).
    """
    lsb = (channel & 1).astype(np.uint8)
    p1 = np.mean(lsb)
    p0 = 1 - p1
    if p0 <= 0 or p1 <= 0:
        return 0.0
    return float(-(p0 * np.log2(p0) + p1 * np.log2(p1)))


def _lsb_plane_mean(channel: np.ndarray) -> float:
    """Mean value of the LSB plane; a clean image is typically below 0.5."""
    return float(np.mean((channel & 1).astype(np.float64)))


def _adjacent_pixel_correlation(channel: np.ndarray) -> tuple[float, float]:
    """Pearson correlation between horizontally/vertically adjacent pixels.

    Natural images are smooth locally, so adjacent pixels correlate
    strongly (typically > 0.9). LSB embedding slightly weakens this
    correlation because embedded bits are independent of neighboring
    pixel values.
    """
    h_pairs_a = channel[:, :-1].astype(np.float64).ravel()
    h_pairs_b = channel[:, 1:].astype(np.float64).ravel()
    v_pairs_a = channel[:-1, :].astype(np.float64).ravel()
    v_pairs_b = channel[1:, :].astype(np.float64).ravel()

    def _safe_corr(a, b):
        if np.std(a) < 1e-9 or np.std(b) < 1e-9:
            return 1.0
        return float(np.corrcoef(a, b)[0, 1])

    return _safe_corr(h_pairs_a, h_pairs_b), _safe_corr(v_pairs_a, v_pairs_b)


def _pixel_difference_stats(channel: np.ndarray) -> tuple[float, float]:
    """Mean absolute difference and its std-dev between horizontally adjacent pixels.

    LSB embedding injects small +/-1 perturbations, which slightly
    raises the average local pixel difference (a simple, fast proxy
    for the "noise residual" features used in classical steganalysis
    such as SPAM/WAM feature sets).
    """
    diffs = np.abs(channel[:, 1:].astype(np.int16) - channel[:, :-1].astype(np.int16))
    return float(np.mean(diffs)), float(np.std(diffs))


def _local_noise_estimate(channel: np.ndarray) -> float:
    """High-pass residual energy: channel minus a 3x3 mean-filtered version.

    Approximates the noise-residual features common in steganalysis
    (e.g. SRM-style filters), computed cheaply with NumPy instead of a
    full convolution library dependency.
    """
    c = channel.astype(np.float64)
    kernel_sum = (
        np.pad(c, 1, mode="edge")[0:-2, 0:-2]
        + np.pad(c, 1, mode="edge")[0:-2, 1:-1]
        + np.pad(c, 1, mode="edge")[0:-2, 2:]
        + np.pad(c, 1, mode="edge")[1:-1, 0:-2]
        + np.pad(c, 1, mode="edge")[1:-1, 1:-1]
        + np.pad(c, 1, mode="edge")[1:-1, 2:]
        + np.pad(c, 1, mode="edge")[2:, 0:-2]
        + np.pad(c, 1, mode="edge")[2:, 1:-1]
        + np.pad(c, 1, mode="edge")[2:, 2:]
    )
    local_mean = kernel_sum / 9.0
    residual = c - local_mean
    return float(np.std(residual))


def _histogram_energy_uniformity(channel: np.ndarray) -> tuple[float, float]:
    """Histogram energy (sum of squared normalized bin probabilities) and uniformity.

    Embedding tends to smooth out sharp histogram peaks slightly
    (values get shuffled between adjacent even/odd pairs), which can
    lower energy and raise uniformity marginally.
    """
    hist, _ = np.histogram(channel, bins=256, range=(0, 256))
    probs = hist / max(hist.sum(), 1)
    energy = float(np.sum(probs**2))
    nonzero_bins = float(np.count_nonzero(hist)) / 256.0
    return energy, nonzero_bins


def extract_channel_features(channel: np.ndarray, prefix: str) -> dict:
    flat = channel.astype(np.float64).ravel()
    h_corr, v_corr = _adjacent_pixel_correlation(channel)
    diff_mean, diff_std = _pixel_difference_stats(channel)
    hist_energy, hist_uniformity = _histogram_energy_uniformity(channel)

    return {
        f"{prefix}_mean": float(np.mean(flat)),
        f"{prefix}_std": float(np.std(flat)),
        f"{prefix}_variance": float(np.var(flat)),
        f"{prefix}_skewness": float(scipy_stats.skew(flat)),
        f"{prefix}_kurtosis": float(scipy_stats.kurtosis(flat)),
        f"{prefix}_entropy": _shannon_entropy(channel),
        f"{prefix}_lsb_mean": _lsb_plane_mean(channel),
        f"{prefix}_lsb_entropy": _lsb_plane_entropy(channel),
        f"{prefix}_h_correlation": h_corr,
        f"{prefix}_v_correlation": v_corr,
        f"{prefix}_diff_mean": diff_mean,
        f"{prefix}_diff_std": diff_std,
        f"{prefix}_local_noise": _local_noise_estimate(channel),
        f"{prefix}_hist_energy": hist_energy,
        f"{prefix}_hist_uniformity": hist_uniformity,
    }


def extract_cross_channel_features(image_array: np.ndarray) -> dict:
    """Correlation between colour channels - embedding independently per
    channel can slightly reduce the natural R-G-B correlation present
    in most photographs (colours co-vary smoothly in natural scenes).
    """
    if image_array.ndim != 3 or image_array.shape[2] < 3:
        return {"rg_correlation": 1.0, "gb_correlation": 1.0, "rb_correlation": 1.0}

    r = image_array[..., 0].astype(np.float64).ravel()
    g = image_array[..., 1].astype(np.float64).ravel()
    b = image_array[..., 2].astype(np.float64).ravel()

    def _safe_corr(a, b):
        if np.std(a) < 1e-9 or np.std(b) < 1e-9:
            return 1.0
        return float(np.corrcoef(a, b)[0, 1])

    return {
        "rg_correlation": _safe_corr(r, g),
        "gb_correlation": _safe_corr(g, b),
        "rb_correlation": _safe_corr(r, b),
    }


def extract_features(image_array: np.ndarray) -> dict:
    """Extract the full feature vector (as a name -> value dict) for one image."""
    features: dict = {}

    if image_array.ndim == 2:
        channels = {"gray": image_array}
    else:
        names = ["red", "green", "blue"]
        channels = {names[i]: image_array[..., i] for i in range(min(3, image_array.shape[2]))}

    for name, channel in channels.items():
        features.update(extract_channel_features(channel, name))

    features.update(extract_cross_channel_features(image_array))

    # Aggregate cross-channel summary features (useful for the model and
    # cheap to compute from what we already have).
    means = [v for k, v in features.items() if k.endswith("_lsb_entropy")]
    features["avg_lsb_entropy"] = float(np.mean(means)) if means else 0.0

    return features


def features_to_vector(features: dict, feature_order: list[str]) -> np.ndarray:
    """Convert a feature dict to a numpy vector in a fixed, stable column order."""
    return np.array([features.get(name, 0.0) for name in feature_order], dtype=np.float64)


def get_feature_order(sample_features: dict) -> list[str]:
    return sorted(sample_features.keys())


FEATURE_DESCRIPTIONS = {
    "mean": "Average pixel intensity of the channel.",
    "std": "Standard deviation of pixel intensity (contrast proxy).",
    "variance": "Variance of pixel intensity.",
    "skewness": "Asymmetry of the intensity distribution.",
    "kurtosis": "Tailedness/peakedness of the intensity distribution.",
    "entropy": "Shannon entropy of the intensity histogram (randomness of pixel values).",
    "lsb_mean": "Mean of the least-significant-bit plane; embedding pushes this toward 0.5.",
    "lsb_entropy": "Entropy of the LSB plane; the primary direct LSB-steganalysis signal.",
    "h_correlation": "Horizontal adjacent-pixel correlation; embedding weakens local smoothness.",
    "v_correlation": "Vertical adjacent-pixel correlation; embedding weakens local smoothness.",
    "diff_mean": "Mean absolute difference between adjacent pixels (noise proxy).",
    "diff_std": "Std-dev of adjacent-pixel differences.",
    "local_noise": "High-pass residual energy (3x3 mean-filter residual std-dev).",
    "hist_energy": "Sum of squared normalized histogram bins (peakedness of histogram).",
    "hist_uniformity": "Fraction of histogram bins that are non-empty.",
    "rg_correlation": "Correlation between red and green channels.",
    "gb_correlation": "Correlation between green and blue channels.",
    "rb_correlation": "Correlation between red and blue channels.",
    "avg_lsb_entropy": "Average LSB-plane entropy across all channels.",
}
