"""Base cover-image corpus used to build the reproducible demo dataset.

We use the public-domain / BSD-licensed sample photographs bundled
with scikit-image (skimage.data) instead of an external download, so
`scripts/generate_dataset.py` works fully offline and is 100%
reproducible without depending on a third-party dataset URL staying
alive. This is explicitly a *small-scale demonstration corpus* - see
docs/research-notes.md and the README Limitations section for how this
compares to a research-grade corpus such as BOSSbase or ALASKA2.

Only genuine RGB photographs are used (grayscale samples are excluded)
so that cross-channel correlation features reflect real photographic
statistics rather than an artificially perfect grayscale-stacked
correlation of 1.0.
"""
from __future__ import annotations

import numpy as np
import skimage.data as skdata

# name -> loader. `cat` is excluded because it is pixel-identical to
# `chelsea` in scikit-image's sample set.
_RGB_LOADERS = {
    "astronaut": skdata.astronaut,
    "coffee": skdata.coffee,
    "chelsea": skdata.chelsea,
    "rocket": skdata.rocket,
    "colorwheel": skdata.colorwheel,
    "immunohistochemistry": skdata.immunohistochemistry,
    "retina": skdata.retina,
    "hubble_deep_field": skdata.hubble_deep_field,
    "logo": skdata.logo,  # RGBA -> RGB (alpha dropped)
}


def load_base_images() -> dict[str, np.ndarray]:
    """Return {name: (H, W, 3) uint8 array} for every base cover image."""
    images = {}
    for name, loader in _RGB_LOADERS.items():
        arr = loader()
        if arr.ndim == 3 and arr.shape[2] == 4:
            arr = arr[..., :3]
        images[name] = np.ascontiguousarray(arr.astype(np.uint8))
    return images
