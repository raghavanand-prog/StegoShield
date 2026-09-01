#!/usr/bin/env python3
"""CLI: generate the reproducible labeled steganalysis dataset.

Usage:
    python scripts/generate_dataset.py [--seed 42] [--tile-size 256]

Writes:
    data/dataset/features.csv   - one row per (crop, payload level) sample
    data/dataset/manifest.json  - generation parameters + summary stats
    data/sample_images/*.png    - a handful of clean demo images for the
                                   web UI's "try it" flow and for tests
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from ml.dataset.base_images import load_base_images  # noqa: E402
from ml.dataset.generator import (  # noqa: E402
    DEFAULT_PAYLOAD_LEVELS,
    DEFAULT_STRIDE,
    DEFAULT_TILE_SIZE,
    feature_columns,
    generate_dataset,
)
from app.utils.image_io import rgb_array_to_png_bytes  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the StegoShield steganalysis dataset.")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--tile-size", type=int, default=DEFAULT_TILE_SIZE)
    parser.add_argument("--stride", type=int, default=DEFAULT_STRIDE)
    parser.add_argument(
        "--payload-levels",
        type=float,
        nargs="+",
        default=list(DEFAULT_PAYLOAD_LEVELS),
        help="Target capacity-utilization levels for stego samples, e.g. 0.05 0.1 0.2",
    )
    parser.add_argument("--output-dir", type=Path, default=BASE_DIR / "data" / "dataset")
    parser.add_argument("--samples-dir", type=Path, default=BASE_DIR / "data" / "sample_images")
    args = parser.parse_args()

    print("StegoShield dataset generation")
    print("=" * 60)
    print(f"tile_size={args.tile_size} stride={args.stride} seed={args.seed}")
    print(f"payload_levels={args.payload_levels}")

    t0 = time.time()
    df = generate_dataset(
        tile_size=args.tile_size,
        stride=args.stride,
        payload_levels=tuple(args.payload_levels),
        seed=args.seed,
    )
    elapsed = time.time() - t0

    args.output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = args.output_dir / "features.csv"
    df.to_csv(csv_path, index=False)

    manifest = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "seed": args.seed,
        "tile_size": args.tile_size,
        "stride": args.stride,
        "payload_levels": args.payload_levels,
        "total_samples": len(df),
        "clean_samples": int((df["label"] == 0).sum()),
        "stego_samples": int((df["label"] == 1).sum()),
        "source_images": sorted(df["source_image"].unique().tolist()),
        "samples_per_source_image": df.groupby("source_image").size().to_dict(),
        "feature_count": len(feature_columns(df)),
        "feature_names": feature_columns(df),
        "generation_time_seconds": round(elapsed, 2),
        "note": (
            "Cover images are public-domain sample photographs bundled with "
            "scikit-image (skimage.data), tiled into fixed-size crops. This is "
            "a small, fully-reproducible demonstration corpus - see "
            "docs/research-notes.md for how this compares to research-scale "
            "corpora (BOSSbase, ALASKA2)."
        ),
    }
    manifest_path = args.output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, default=int))

    # Export a handful of small clean demo images (one crop per source image)
    args.samples_dir.mkdir(parents=True, exist_ok=True)
    base_images = load_base_images()
    for name, arr in base_images.items():
        crop = arr[:200, :200] if arr.shape[0] >= 200 and arr.shape[1] >= 200 else arr
        out_path = args.samples_dir / f"{name}_sample.png"
        out_path.write_bytes(rgb_array_to_png_bytes(crop))

    print("-" * 60)
    print(f"Generated {len(df)} samples ({manifest['clean_samples']} clean / "
          f"{manifest['stego_samples']} stego) in {elapsed:.1f}s")
    print(f"Features CSV : {csv_path.relative_to(BASE_DIR)}")
    print(f"Manifest     : {manifest_path.relative_to(BASE_DIR)}")
    print(f"Sample images: {args.samples_dir.relative_to(BASE_DIR)} ({len(base_images)} files)")
    print("Done.")


if __name__ == "__main__":
    main()
