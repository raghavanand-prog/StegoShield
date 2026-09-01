"""Reproducible dataset generation: base photos -> labeled cover/stego crops.

Pipeline
--------
1. Load the base RGB photograph corpus (ml/dataset/base_images.py).
2. Tile each base photo into non-overlapping/lightly-overlapping crops
   so we get many distinct cover images from a small photo corpus.
3. For every crop, produce one CLEAN sample (label 0, unmodified) and
   one STEGO sample (label 1) at each target payload-capacity
   utilization level, using StegoShield's own LSB engine
   (app.steganography.encoder) to embed a random text payload sized to
   hit that utilization.
4. Extract the full statistical feature vector for every sample.
5. Record a `source_image` group id (the base photo name) on every row
   so training can split train/val/test by group and guarantee that no
   crop - and no stego derivative of a crop - crosses a split boundary.

This keeps the dataset fully reproducible from a fixed random seed and
avoids any external network dependency or licensing ambiguity.
"""
from __future__ import annotations

import random
import string
from dataclasses import dataclass

import numpy as np
import pandas as pd

from app.steganalysis.features import extract_features
from app.steganography import capacity as capacity_mod
from app.steganography.encoder import encode_message
from ml.dataset.base_images import load_base_images

DEFAULT_PAYLOAD_LEVELS = (0.05, 0.10, 0.20, 0.30, 0.50)
DEFAULT_TILE_SIZE = 256
DEFAULT_STRIDE = 256  # == tile size => non-overlapping crops (independent samples)
MAX_CROPS_PER_IMAGE = 16  # caps any single source photo's share of the dataset


def _augment_crop(crop: np.ndarray) -> list[tuple[str, np.ndarray]]:
    """Return (tag, array) pairs: the crop plus geometric augmentations.

    Flips/rotations create genuinely different pixel arrangements (and
    therefore different local-correlation/noise statistics) from a
    small base photo corpus, without introducing any leakage risk: an
    augmented view of a crop still belongs to the SAME source_image
    group, so it can never cross the train/val/test boundary alone.
    This only multiplies within-group sample count/diversity.
    """
    return [
        ("orig", crop),
        ("hflip", np.ascontiguousarray(crop[:, ::-1])),
        ("vflip", np.ascontiguousarray(crop[::-1, :])),
        ("rot180", np.ascontiguousarray(crop[::-1, ::-1])),
    ]


@dataclass
class DatasetSample:
    sample_id: str
    source_image: str
    crop_index: int
    label: int  # 0 = clean, 1 = stego
    payload_level: float  # 0.0 for clean
    payload_bytes: int
    utilization_percent: float
    width: int
    height: int
    features: dict


def tile_image(
    array: np.ndarray,
    tile_size: int = DEFAULT_TILE_SIZE,
    stride: int = DEFAULT_STRIDE,
    max_crops: int = MAX_CROPS_PER_IMAGE,
):
    """Yield (crop_index, crop_array) for sliding-window crops of `array`.

    If the image is smaller than one tile in either dimension, the
    whole image is returned as a single crop (index 0) instead of being
    skipped, so small base photos still contribute a sample. Crops are
    capped at `max_crops`, evenly subsampled, so a single large photo
    (e.g. a 1411x1411 sample) cannot dominate the dataset and skew the
    group-wise train/val/test split.
    """
    h, w = array.shape[0], array.shape[1]
    if h < tile_size or w < tile_size:
        yield 0, array
        return

    positions = [
        (y, x)
        for y in range(0, h - tile_size + 1, stride)
        for x in range(0, w - tile_size + 1, stride)
    ]
    if len(positions) > max_crops:
        step = len(positions) / max_crops
        positions = [positions[int(i * step)] for i in range(max_crops)]

    for idx, (y, x) in enumerate(positions):
        yield idx, array[y : y + tile_size, x : x + tile_size]


def _random_payload_for_utilization(image_array: np.ndarray, target_util: float, rng: random.Random) -> str:
    """Build a random text payload sized to hit approximately `target_util`
    fraction of the image's usable capacity (including header overhead).
    """
    report = capacity_mod.compute_capacity(image_array)
    target_total_bytes = int(round(report.total_capacity_bytes * target_util))
    message_bytes_target = max(1, target_total_bytes - report.header_overhead_bytes)
    message_bytes_target = min(message_bytes_target, report.max_message_bytes)
    alphabet = string.ascii_letters + string.digits + string.punctuation + " "
    return "".join(rng.choice(alphabet) for _ in range(message_bytes_target))


def generate_dataset(
    tile_size: int = DEFAULT_TILE_SIZE,
    stride: int = DEFAULT_STRIDE,
    payload_levels: tuple = DEFAULT_PAYLOAD_LEVELS,
    seed: int = 42,
) -> pd.DataFrame:
    """Generate the full labeled feature dataset as a pandas DataFrame."""
    rng = random.Random(seed)
    base_images = load_base_images()

    rows: list[dict] = []
    sample_counter = 0

    for image_name, image_array in sorted(base_images.items()):
        for crop_index, base_crop in tile_image(image_array, tile_size, stride):
            for aug_tag, crop in _augment_crop(base_crop):
                sample_key = f"{image_name}_{crop_index}_{aug_tag}"

                # --- CLEAN sample ---------------------------------------------
                clean_features = extract_features(crop)
                sample_counter += 1
                rows.append(
                    {
                        "sample_id": f"{sample_key}_clean",
                        "source_image": image_name,
                        "crop_index": crop_index,
                        "label": 0,
                        "payload_level": 0.0,
                        "payload_bytes": 0,
                        "utilization_percent": 0.0,
                        "width": crop.shape[1],
                        "height": crop.shape[0],
                        **clean_features,
                    }
                )

                # --- STEGO samples at each target payload level ----------------
                for level in payload_levels:
                    message = _random_payload_for_utilization(crop, level, rng)
                    if not message:
                        continue
                    result = encode_message(crop, message)
                    stego_features = extract_features(result.stego_array)
                    rows.append(
                        {
                            "sample_id": f"{sample_key}_stego_{int(level*100)}",
                            "source_image": image_name,
                            "crop_index": crop_index,
                            "label": 1,
                            "payload_level": level,
                            "payload_bytes": result.message_bytes,
                            "utilization_percent": result.utilization_percent,
                            "width": crop.shape[1],
                            "height": crop.shape[0],
                            **stego_features,
                        }
                    )

    df = pd.DataFrame(rows)
    return df


def feature_columns(df: pd.DataFrame) -> list[str]:
    non_feature = {
        "sample_id",
        "source_image",
        "crop_index",
        "label",
        "payload_level",
        "payload_bytes",
        "utilization_percent",
        "width",
        "height",
    }
    return sorted(c for c in df.columns if c not in non_feature)
