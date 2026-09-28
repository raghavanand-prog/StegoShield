"""Visual-difference analysis: exaggerated diff heatmap + histogram comparison.

Generates actual image artifacts from the real original/stego arrays -
nothing here is a static placeholder.
"""
from __future__ import annotations

import base64
import io
import threading

import matplotlib

# Force the non-interactive Agg backend *before* pyplot is imported.
# This is a server process with no display - relying on matplotlib's
# auto-detected default backend is fragile (it can select an
# interactive, non-thread-safe backend if a GUI toolkit happens to be
# importable on the host) and would fail unpredictably outside this
# sandbox's environment.
matplotlib.use("Agg")

# `pyplot`'s current-figure state (plt.figure(), plt.close()) is a
# module-level global, not thread-local - concurrent calls from
# different threads of the same process race on it regardless of
# backend. The production Gunicorn config uses a threaded worker
# (gthread), so this lock serializes the only function here that
# touches pyplot's global API; everything else in this module
# (numpy array math, PIL encoding) has no shared state and doesn't
# need it.
_PYPLOT_LOCK = threading.Lock()

import numpy as np
from matplotlib import pyplot as plt
from matplotlib.figure import Figure
from PIL import Image


def compute_difference_image(original: np.ndarray, modified: np.ndarray, amplify: int = 40) -> np.ndarray:
    """Return an exaggerated, viewable difference image.

    Raw LSB differences are +/-1 per channel and invisible to the naked
    eye, so we take the absolute difference and multiply by `amplify`
    (clamped to [0, 255]) purely for human visualization. The amplify
    factor is documented so viewers understand this is not the raw
    magnitude of change.
    """
    diff = np.abs(original.astype(np.int16) - modified.astype(np.int16))
    amplified = np.clip(diff * amplify, 0, 255).astype(np.uint8)
    return amplified


def array_to_png_base64(array: np.ndarray) -> str:
    img = Image.fromarray(array)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def compute_histograms(original: np.ndarray, modified: np.ndarray) -> dict:
    """Per-channel (R, G, B) 256-bin histograms for original and modified images."""
    channel_names = ["red", "green", "blue"] if original.ndim == 3 else ["gray"]
    result = {}
    for i, name in enumerate(channel_names):
        orig_channel = original[..., i] if original.ndim == 3 else original
        mod_channel = modified[..., i] if modified.ndim == 3 else modified
        orig_hist, _ = np.histogram(orig_channel, bins=256, range=(0, 256))
        mod_hist, _ = np.histogram(mod_channel, bins=256, range=(0, 256))
        result[name] = {
            "original": orig_hist.tolist(),
            "stego": mod_hist.tolist(),
        }
    return result


def render_histogram_figure(histograms: dict) -> str:
    """Render a matplotlib histogram comparison figure and return base64 PNG."""
    colors = {"red": "#ef4444", "green": "#22c55e", "blue": "#3b82f6", "gray": "#94a3b8"}
    with _PYPLOT_LOCK:
        fig: Figure = plt.figure(figsize=(9, 3.2), dpi=110)
        try:
            channels = list(histograms.keys())
            for idx, name in enumerate(channels, start=1):
                ax = fig.add_subplot(1, len(channels), idx)
                bins = np.arange(256)
                ax.plot(bins, histograms[name]["original"], color="#94a3b8", linewidth=1, label="Original")
                ax.plot(bins, histograms[name]["stego"], color=colors.get(name, "#f97316"), linewidth=1, label="Stego")
                ax.set_title(name.capitalize(), fontsize=9, color="#e2e8f0")
                ax.tick_params(colors="#94a3b8", labelsize=7)
                ax.set_facecolor("#0f172a")
                for spine in ax.spines.values():
                    spine.set_color("#334155")
                if idx == 1:
                    ax.legend(fontsize=6, facecolor="#0f172a", labelcolor="#e2e8f0", edgecolor="#334155")
            fig.patch.set_facecolor("#0f172a")
            fig.tight_layout()
            buf = io.BytesIO()
            fig.savefig(buf, format="png", facecolor=fig.get_facecolor())
        finally:
            plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def build_visual_analysis(original: np.ndarray, modified: np.ndarray) -> dict:
    diff_image = compute_difference_image(original, modified)
    histograms = compute_histograms(original, modified)
    return {
        "original_png_b64": array_to_png_base64(original),
        "stego_png_b64": array_to_png_base64(modified),
        "difference_png_b64": array_to_png_base64(diff_image),
        "difference_amplification_factor": 40,
        "histogram_png_b64": render_histogram_figure(histograms),
        "histograms": histograms,
    }
