"""Shared pytest fixtures."""
from __future__ import annotations

import io
import os

import numpy as np
import pytest
from PIL import Image

os.environ.setdefault("FLASK_ENV", "testing")

from app import create_app  # noqa: E402


@pytest.fixture(scope="session")
def flask_app():
    app = create_app()
    app.config.update(TESTING=True)
    return app


@pytest.fixture()
def client(flask_app):
    return flask_app.test_client()


@pytest.fixture()
def rng():
    return np.random.default_rng(1234)


@pytest.fixture()
def random_image_array(rng):
    """A 128x128 RGB array with natural-ish smooth gradients (not pure
    noise), which better matches feature-extraction assumptions."""
    base = rng.integers(0, 256, size=(128, 128, 3), dtype=np.uint8)
    # light smoothing to mimic natural image correlation
    from scipy.ndimage import uniform_filter

    smoothed = uniform_filter(base.astype(np.float32), size=(3, 3, 1))
    return smoothed.astype(np.uint8)


def array_to_png_bytes(array: np.ndarray) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(array.astype(np.uint8), mode="RGB").save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture()
def random_image_png_bytes(random_image_array):
    return array_to_png_bytes(random_image_array)
