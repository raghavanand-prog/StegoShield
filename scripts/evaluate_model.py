#!/usr/bin/env python3
"""CLI: reload the saved model and re-run evaluation, printing a full report.

This script exists to make the reported results independently
reproducible/auditable: it does not reuse train_model.py's in-memory
results, it reloads the persisted model_metadata.json from disk and
re-derives the test-set split with the same seed to confirm the
metrics are consistent.

Usage:
    python scripts/evaluate_model.py
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import joblib  # noqa: E402
import pandas as pd  # noqa: E402

from ml.evaluation.metrics import compute_metrics  # noqa: E402
from ml.training.splitting import group_train_val_test_split  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate the saved StegoShield model.")
    parser.add_argument("--dataset-csv", type=Path, default=BASE_DIR / "data" / "dataset" / "features.csv")
    parser.add_argument("--model-path", type=Path, default=BASE_DIR / "ml" / "models" / "steganalysis_model.joblib")
    parser.add_argument("--metadata-path", type=Path, default=BASE_DIR / "ml" / "models" / "model_metadata.json")
    args = parser.parse_args()

    if not args.model_path.exists():
        print(f"ERROR: trained model not found at {args.model_path}")
        print("Run `python scripts/train_model.py` first.")
        sys.exit(1)

    bundle = joblib.load(args.model_path)
    pipeline = bundle["pipeline"]
    feature_columns = bundle["feature_columns"]
    metadata = json.loads(args.metadata_path.read_text())
    seed = metadata["seed"]

    df = pd.read_csv(args.dataset_csv)
    split = group_train_val_test_split(df, seed=seed)
    X_test = split.test[feature_columns].values
    y_test = split.test["label"].values

    y_pred = pipeline.predict(X_test)
    y_proba = pipeline.predict_proba(X_test)[:, 1]
    metrics = compute_metrics(y_test, y_pred, y_proba)

    print("StegoShield model evaluation (independent re-run)")
    print("=" * 60)
    print(f"Model trained at: {metadata['trained_at']}  (seed={seed})")
    print(f"Test set: {len(y_test)} samples from {sorted(split.test['source_image'].unique())}")
    print("-" * 60)
    print(f"Accuracy : {metrics['accuracy']:.4f}")
    print(f"Precision: {metrics['precision']:.4f}")
    print(f"Recall   : {metrics['recall']:.4f}")
    print(f"F1-score : {metrics['f1_score']:.4f}")
    auc = metrics["roc_auc"]
    print(f"ROC-AUC  : {auc:.4f}" if auc is not None else "ROC-AUC  : n/a")
    cm = metrics["confusion_matrix"]
    print("-" * 60)
    print("Confusion matrix:")
    print(f"                 Predicted CLEAN   Predicted STEGO")
    print(f"  Actual CLEAN   {cm['true_negative']:>15d}   {cm['false_positive']:>15d}")
    print(f"  Actual STEGO   {cm['false_negative']:>15d}   {cm['true_positive']:>15d}")
    print("=" * 60)
    print("This re-computation should match the test metrics recorded in "
          "ml/models/model_metadata.json under models.random_forest.test.")


if __name__ == "__main__":
    main()
