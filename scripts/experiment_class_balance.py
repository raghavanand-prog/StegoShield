#!/usr/bin/env python3
"""Diagnostic experiment: does the RandomForest's false-positive bias on
CLEAN images come from training-label class imbalance (5 STEGO samples
generated per 1 CLEAN crop, since each crop is embedded at 5 payload
levels)?

This is a controlled ablation, not a new model search: everything is
held fixed (same features.csv, same leak-safe group split, same
n_estimators/max_depth/random_state) except the ONE variable under
test - how the 5:1 label imbalance is handled during training. Three
conditions:

  A. "balanced"    - current production setting: class_weight='balanced'
                      on the full (imbalanced) training set.
  B. "none"         - same imbalanced training set, but class_weight=None
                      (isolates whether the *balanced* option itself is
                      responsible for the false-positive bias).
  C. "undersampled" - class_weight=None, but the STEGO class is randomly
                      undersampled to match the CLEAN count 1:1 before
                      fitting (a second, independent way to correct
                      label imbalance, for comparison against A).

All three are evaluated on the identical, untouched held-out test set
(2 source photos never seen during training or validation) so results
are directly comparable. Every number below is computed by this run,
not asserted.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from ml.evaluation.metrics import compute_metrics  # noqa: E402
from ml.training.splitting import group_train_val_test_split  # noqa: E402
from ml.training.train_model import get_feature_columns  # noqa: E402

SEED = 42
N_ESTIMATORS = 300


def undersample_majority(X: np.ndarray, y: np.ndarray, seed: int) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    idx_clean = np.where(y == 0)[0]
    idx_stego = np.where(y == 1)[0]
    n = len(idx_clean)  # minority class count
    idx_stego_sampled = rng.choice(idx_stego, size=n, replace=False)
    keep = np.concatenate([idx_clean, idx_stego_sampled])
    rng.shuffle(keep)
    return X[keep], y[keep]


def fit_and_eval(X_train, y_train, X_test, y_test, class_weight) -> dict:
    model = RandomForestClassifier(
        n_estimators=N_ESTIMATORS,
        max_depth=None,
        random_state=SEED,
        n_jobs=-1,
        class_weight=class_weight,
    )
    pipe = Pipeline([("scaler", StandardScaler()), ("model", model)])
    pipe.fit(X_train, y_train)
    y_pred = pipe.predict(X_test)
    y_proba = pipe.predict_proba(X_test)[:, 1]
    return compute_metrics(y_test, y_pred, y_proba)


def main() -> None:
    csv_path = BASE_DIR / "data" / "dataset" / "features.csv"
    df = pd.read_csv(csv_path)
    feature_cols = get_feature_columns(df)
    split = group_train_val_test_split(df, seed=SEED)

    def _xy(part_df: pd.DataFrame):
        return part_df[feature_cols].values, part_df["label"].values

    X_train, y_train = _xy(split.train)
    X_test, y_test = _xy(split.test)

    print("StegoShield — class-imbalance diagnostic experiment")
    print("=" * 70)
    print(f"Train: {len(y_train)} samples ({int((y_train==0).sum())} clean / "
          f"{int((y_train==1).sum())} stego)")
    print(f"Test : {len(y_test)} samples ({int((y_test==0).sum())} clean / "
          f"{int((y_test==1).sum())} stego)")
    print()

    results = {}
    t0 = time.time()

    print("[A] class_weight='balanced' (current production setting)...")
    results["A_balanced"] = fit_and_eval(X_train, y_train, X_test, y_test, class_weight="balanced")

    print("[B] class_weight=None, full imbalanced training set...")
    results["B_none_imbalanced"] = fit_and_eval(X_train, y_train, X_test, y_test, class_weight=None)

    print("[C] class_weight=None, STEGO undersampled to 1:1 with CLEAN...")
    X_train_us, y_train_us = undersample_majority(X_train, y_train, seed=SEED)
    print(f"    undersampled train: {len(y_train_us)} samples "
          f"({int((y_train_us==0).sum())} clean / {int((y_train_us==1).sum())} stego)")
    results["C_undersampled"] = fit_and_eval(X_train_us, y_train_us, X_test, y_test, class_weight=None)

    elapsed = time.time() - t0
    print(f"\nDone in {elapsed:.1f}s\n")

    print(f"{'Condition':<20} {'Accuracy':>9} {'CleanAcc':>9} {'StegoRec':>9} {'ROC-AUC':>8} {'TN':>4} {'FP':>4} {'FN':>4} {'TP':>4}")
    print("-" * 80)
    for name, m in results.items():
        cm = m["confusion_matrix"]
        tn, fp, fn, tp = cm["true_negative"], cm["false_positive"], cm["false_negative"], cm["true_positive"]
        clean_acc = tn / (tn + fp) if (tn + fp) else float("nan")
        stego_rec = tp / (tp + fn) if (tp + fn) else float("nan")
        print(f"{name:<20} {m['accuracy']:>9.4f} {clean_acc:>9.4f} {stego_rec:>9.4f} "
              f"{m['roc_auc']:>8.4f} {tn:>4} {fp:>4} {fn:>4} {tp:>4}")

    out_path = BASE_DIR / "data" / "dataset" / "class_balance_experiment_results.json"
    out_path.write_text(json.dumps({
        "seed": SEED,
        "n_estimators": N_ESTIMATORS,
        "train_size": int(len(y_train)),
        "test_size": int(len(y_test)),
        "results": results,
    }, indent=2))
    print(f"\nFull results written to {out_path.relative_to(BASE_DIR)}")


if __name__ == "__main__":
    main()
