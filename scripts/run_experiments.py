#!/usr/bin/env python3
"""CLI: run the two research experiments referenced in docs/research-notes.md.

Experiment A - Payload size vs. image quality
    For each base cover image and each target capacity-utilization
    level, encode a payload and measure MSE / PSNR / SSIM against the
    original. Demonstrates the (very slight) quality cost of larger
    payloads.

Experiment B - Payload size vs. detection accuracy
    Using the ALREADY-GENERATED, leak-safe TEST split (see
    ml/training/splitting.py) from data/dataset/features.csv, and the
    trained model, compute steganalysis accuracy separately for each
    payload level. Demonstrates that larger payloads are easier to
    detect than smaller ones - the expected and well-documented
    behaviour of statistical steganalysis.

Both experiments use only real, already-computed data - nothing here
is invented. Results are written to data/dataset/experiment_results.json
so docs/research-notes.md can cite exact figures.

Usage:
    python scripts/run_experiments.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import joblib  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from app.services.image_quality import compute_quality_metrics  # noqa: E402
from app.steganography.encoder import encode_message  # noqa: E402
from ml.dataset.base_images import load_base_images  # noqa: E402
from ml.dataset.generator import DEFAULT_PAYLOAD_LEVELS, _random_payload_for_utilization  # noqa: E402
from ml.training.splitting import group_train_val_test_split  # noqa: E402
import random  # noqa: E402


def experiment_payload_vs_quality() -> list[dict]:
    print("Experiment A: payload size vs. image quality")
    base_images = load_base_images()
    rng = random.Random(7)
    results = []
    for name, arr in sorted(base_images.items()):
        crop = arr[:256, :256] if arr.shape[0] >= 256 and arr.shape[1] >= 256 else arr
        for level in DEFAULT_PAYLOAD_LEVELS:
            message = _random_payload_for_utilization(crop, level, rng)
            if not message:
                continue
            enc = encode_message(crop, message)
            q = compute_quality_metrics(crop, enc.stego_array)
            results.append(
                {
                    "source_image": name,
                    "payload_level": level,
                    "utilization_percent": enc.utilization_percent,
                    "mse": q.mse,
                    "psnr_db": None if np.isinf(q.psnr) else round(q.psnr, 2),
                    "ssim": round(q.ssim, 6),
                }
            )
    df = pd.DataFrame(results)
    summary = df.groupby("payload_level")[["mse", "psnr_db", "ssim"]].mean().reset_index()
    print(summary.to_string(index=False))
    return results


def experiment_payload_vs_detection() -> list[dict]:
    print("\nExperiment B: payload size vs. detection accuracy (test split)")
    model_path = BASE_DIR / "ml" / "models" / "steganalysis_model.joblib"
    dataset_path = BASE_DIR / "data" / "dataset" / "features.csv"
    if not model_path.exists() or not dataset_path.exists():
        print("  Skipped: model or dataset not found. Run generate_dataset.py and train_model.py first.")
        return []

    bundle = joblib.load(model_path)
    pipeline = bundle["pipeline"]
    feature_columns = bundle["feature_columns"]

    df = pd.read_csv(dataset_path)
    metadata = json.loads((BASE_DIR / "ml" / "models" / "model_metadata.json").read_text())
    split = group_train_val_test_split(df, seed=metadata["seed"])
    test_df = split.test

    results = []
    # Clean images (payload_level == 0.0) as their own baseline row.
    for level in [0.0] + list(DEFAULT_PAYLOAD_LEVELS):
        subset = test_df[test_df["payload_level"] == level]
        if len(subset) == 0:
            continue
        X = subset[feature_columns].values
        y_true = subset["label"].values
        y_pred = pipeline.predict(X)
        accuracy = float(np.mean(y_pred == y_true))
        results.append(
            {
                "payload_level": level,
                "n_samples": int(len(subset)),
                "accuracy": round(accuracy, 4),
                "label": "CLEAN" if level == 0.0 else f"STEGO @ {int(level*100)}%",
            }
        )
        print(f"  level={level:>4} ({results[-1]['label']:14s}) n={len(subset):4d} accuracy={accuracy:.4f}")
    return results


def main() -> None:
    quality_results = experiment_payload_vs_quality()
    detection_results = experiment_payload_vs_detection()

    output = {
        "payload_vs_quality": quality_results,
        "payload_vs_detection_accuracy": detection_results,
    }
    out_path = BASE_DIR / "data" / "dataset" / "experiment_results.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, indent=2))
    print(f"\nResults written to {out_path.relative_to(BASE_DIR)}")


if __name__ == "__main__":
    main()
