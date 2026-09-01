#!/usr/bin/env python3
"""CLI: train the steganalysis models on the generated dataset.

Usage:
    python scripts/generate_dataset.py      # run first, if not already done
    python scripts/train_model.py [--seed 42] [--n-estimators 300]

Writes:
    ml/models/steganalysis_model.joblib   - the primary (Random Forest) pipeline
    ml/models/model_metadata.json         - metrics for all 3 models + feature importance
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from ml.training.train_model import save_artifacts, train_and_evaluate  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Train the StegoShield steganalysis models.")
    parser.add_argument("--dataset-csv", type=Path, default=BASE_DIR / "data" / "dataset" / "features.csv")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--n-estimators", type=int, default=300)
    parser.add_argument("--max-depth", type=int, default=None)
    parser.add_argument("--model-path", type=Path, default=BASE_DIR / "ml" / "models" / "steganalysis_model.joblib")
    parser.add_argument("--metadata-path", type=Path, default=BASE_DIR / "ml" / "models" / "model_metadata.json")
    args = parser.parse_args()

    if not args.dataset_csv.exists():
        print(f"ERROR: dataset not found at {args.dataset_csv}")
        print("Run `python scripts/generate_dataset.py` first.")
        sys.exit(1)

    print("StegoShield model training")
    print("=" * 60)

    result = train_and_evaluate(
        args.dataset_csv, seed=args.seed, n_estimators=args.n_estimators, max_depth=args.max_depth
    )
    save_artifacts(result, args.model_path, args.metadata_path)

    meta = result["metadata"]
    print(f"Trained on {meta['n_features']} features in {meta['training_time_seconds']}s")
    print("\nDataset split (by source image, group-safe):")
    for split_name, stats in meta["dataset_split"].items():
        print(f"  {split_name:5s}: {stats['samples']:4d} samples "
              f"({stats['clean']} clean / {stats['stego']} stego) "
              f"from {stats['source_images']}")

    print("\nTest-set metrics (all models):")
    for model_name, res in meta["models"].items():
        m = res["test"]
        auc = f"{m['roc_auc']:.4f}" if m["roc_auc"] is not None else "n/a"
        print(f"  {model_name:20s} acc={m['accuracy']:.4f} prec={m['precision']:.4f} "
              f"rec={m['recall']:.4f} f1={m['f1_score']:.4f} roc_auc={auc}")

    print(f"\nTop 5 features by importance ({meta['primary_model']}):")
    for item in meta["feature_importance"][:5]:
        print(f"  {item['feature']:30s} {item['importance']:.4f}")

    print(f"\nModel saved to   : {args.model_path.relative_to(BASE_DIR)}")
    print(f"Metadata saved to: {args.metadata_path.relative_to(BASE_DIR)}")
    print("Done.")


if __name__ == "__main__":
    main()
