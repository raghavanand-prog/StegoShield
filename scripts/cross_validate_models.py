#!/usr/bin/env python3
"""Leave-one-source-photo-out cross-validation.

This is the "improved validation methodology" referenced in
docs/research-notes.md's Future Work: the single train/val/test split
used elsewhere in this project (5 photos train / 2 val / 2 test) is
reproducible and leak-safe, but resting a headline number on exactly
2 held-out photos (`chelsea`, `retina`) is statistically fragile - a
different pair could tell a different story. Leave-One-Group-Out (LOGO)
cross-validation fixes that: every one of the 9 source photographs
takes a turn as the *sole* held-out test set, with the other 8 used for
training. This still preserves full source-image-disjoint splitting
(sklearn's LeaveOneGroupOut guarantees a photo's crops - and every
payload-level derivative of them - never appear in both the training
fold and its own test fold) while using every sample as out-of-fold
test data exactly once, giving a far more robust estimate than one
split.

This script answers two concrete questions with real, computed evidence
rather than a single split's numbers:

1. Does removing `class_weight='balanced'` from the Random Forest
   (Experiment C in docs/research-notes.md, based on only the
   chelsea/retina split) actually generalize, or was it an artifact of
   that one test pair?
2. Which of the three model families should be the *primary* model,
   using an explicit, stated criterion appropriate for a detection
   system - not just whichever has the highest ROC-AUC?

Two aggregations are reported for each configuration:

- POOLED: every sample's single out-of-fold prediction is concatenated
  across all 9 folds and scored once, as if this were one big
  leak-safe held-out set of all 960 samples. This is the headline
  number - it isn't distorted by small folds carrying equal weight to
  large ones.
- PER-FOLD (mean +/- std across the 9 photos): shows how much
  performance varies from one held-out photo to another, which the
  pooled number alone hides.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import LeaveOneGroupOut
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from ml.evaluation.metrics import compute_metrics  # noqa: E402
from ml.training.train_model import get_feature_columns  # noqa: E402

SEED = 42
N_ESTIMATORS = 300

CONFIGS = {
    "random_forest_balanced": lambda: RandomForestClassifier(
        n_estimators=N_ESTIMATORS, random_state=SEED, n_jobs=-1, class_weight="balanced"
    ),
    "random_forest_unweighted": lambda: RandomForestClassifier(
        n_estimators=N_ESTIMATORS, random_state=SEED, n_jobs=-1, class_weight=None
    ),
    "logistic_regression_balanced": lambda: LogisticRegression(
        max_iter=2000, random_state=SEED, class_weight="balanced"
    ),
    "gradient_boosting": lambda: GradientBoostingClassifier(random_state=SEED),
}


def run_logo_cv(df: pd.DataFrame, feature_cols: list[str], model_factory) -> dict:
    logo = LeaveOneGroupOut()
    groups = df["source_image"].values
    X = df[feature_cols].values
    y = df["label"].values

    oof_true = np.zeros(len(y), dtype=int)
    oof_pred = np.zeros(len(y), dtype=int)
    oof_proba = np.zeros(len(y), dtype=float)
    per_fold = []

    for train_idx, test_idx in logo.split(X, y, groups=groups):
        held_out_photo = groups[test_idx][0]
        pipe = Pipeline([("scaler", StandardScaler()), ("model", model_factory())])
        pipe.fit(X[train_idx], y[train_idx])
        y_pred = pipe.predict(X[test_idx])
        y_proba = pipe.predict_proba(X[test_idx])[:, 1]

        oof_true[test_idx] = y[test_idx]
        oof_pred[test_idx] = y_pred
        oof_proba[test_idx] = y_proba

        fold_metrics = compute_metrics(y[test_idx], y_pred, y_proba)
        per_fold.append({"held_out_photo": str(held_out_photo), "n": int(len(test_idx)), **fold_metrics})

    pooled_metrics = compute_metrics(oof_true, oof_pred, oof_proba)

    # Per-fold mean/std for the scalar metrics that are always defined
    # (ROC-AUC/PR-AUC can be undefined for a fold if, in principle, a
    # held-out photo had only one class present - doesn't happen here
    # since every photo contributes both clean and stego samples, but
    # guarded defensively anyway).
    scalar_keys = ["accuracy", "balanced_accuracy", "precision", "recall",
                   "specificity", "false_positive_rate", "f1_score", "roc_auc", "pr_auc"]
    per_fold_summary = {}
    for key in scalar_keys:
        values = [f[key] for f in per_fold if f[key] is not None]
        if values:
            per_fold_summary[key] = {"mean": float(np.mean(values)), "std": float(np.std(values))}

    return {
        "pooled": pooled_metrics,
        "per_fold_summary": per_fold_summary,
        "per_fold": per_fold,
    }


def main() -> None:
    csv_path = BASE_DIR / "data" / "dataset" / "features.csv"
    df = pd.read_csv(csv_path)
    feature_cols = get_feature_columns(df)
    n_groups = df["source_image"].nunique()

    print("StegoShield — leave-one-source-photo-out cross-validation")
    print("=" * 70)
    print(f"{len(df)} samples across {n_groups} source photos "
          f"({int((df['label']==0).sum())} clean / {int((df['label']==1).sum())} stego)")
    print()

    all_results = {}
    t0 = time.time()
    for name, factory in CONFIGS.items():
        print(f"Running LOGO-CV for '{name}' ({n_groups} folds)...")
        result = run_logo_cv(df, feature_cols, factory)
        all_results[name] = result
        p = result["pooled"]
        print(f"  pooled: acc={p['accuracy']:.4f} bal_acc={p['balanced_accuracy']:.4f} "
              f"specificity={p['specificity']:.4f} fpr={p['false_positive_rate']:.4f} "
              f"recall={p['recall']:.4f} roc_auc={p['roc_auc']:.4f} pr_auc={p['pr_auc']:.4f} "
              f"tpr@fpr20={p['tpr_at_fpr']['at_fpr_20']:.4f}")
    elapsed = time.time() - t0
    print(f"\nDone in {elapsed:.1f}s")

    out_path = BASE_DIR / "data" / "dataset" / "cross_validation_results.json"
    out_path.write_text(json.dumps({
        "seed": SEED,
        "n_estimators": N_ESTIMATORS,
        "method": "LeaveOneGroupOut (leave-one-source-photo-out), 9 folds",
        "n_samples": int(len(df)),
        "n_groups": int(n_groups),
        "results": all_results,
    }, indent=2))
    print(f"Full results written to {out_path.relative_to(BASE_DIR)}")

    print("\n" + "=" * 70)
    print("Summary table (pooled, all 960 out-of-fold predictions):")
    print(f"{'Config':<28} {'Acc':>7} {'BalAcc':>7} {'Spec':>7} {'FPR':>7} {'Recall':>7} {'ROC-AUC':>8} {'PR-AUC':>7} {'TPR@FPR20':>10}")
    print("-" * 100)
    for name, result in all_results.items():
        p = result["pooled"]
        print(f"{name:<28} {p['accuracy']:>7.4f} {p['balanced_accuracy']:>7.4f} "
              f"{p['specificity']:>7.4f} {p['false_positive_rate']:>7.4f} {p['recall']:>7.4f} "
              f"{p['roc_auc']:>8.4f} {p['pr_auc']:>7.4f} {p['tpr_at_fpr']['at_fpr_20']:>10.4f}")


if __name__ == "__main__":
    main()
