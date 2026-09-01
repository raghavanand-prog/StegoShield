"""Core training routine: dataset -> trained models -> saved artifact + metadata.

Trains three real classifiers on the same leak-safe split so their
performance can be honestly compared:

  * Random Forest       (primary model - see README for rationale)
  * Logistic Regression (simple linear baseline)
  * Gradient Boosting    (secondary ensemble comparison)

Only the Random Forest pipeline (StandardScaler + RandomForestClassifier)
is persisted for the running web app to load at inference time, but the
metadata file records every model's metrics so the comparison is
verifiable and auditable rather than asserted.
"""
from __future__ import annotations

import json
import platform
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from ml.evaluation.metrics import compute_metrics
from ml.training.splitting import group_train_val_test_split

NON_FEATURE_COLUMNS = {
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


def get_feature_columns(df: pd.DataFrame) -> list[str]:
    return sorted(c for c in df.columns if c not in NON_FEATURE_COLUMNS)


def _fit_pipeline(model, X_train, y_train) -> Pipeline:
    pipe = Pipeline([("scaler", StandardScaler()), ("model", model)])
    pipe.fit(X_train, y_train)
    return pipe


def _evaluate_pipeline(pipe: Pipeline, X, y) -> dict:
    y_pred = pipe.predict(X)
    y_proba = pipe.predict_proba(X)[:, 1]
    return compute_metrics(y, y_pred, y_proba)


def train_and_evaluate(
    dataset_csv: Path,
    seed: int = 42,
    n_estimators: int = 300,
    max_depth: int | None = None,
) -> dict:
    df = pd.read_csv(dataset_csv)
    feature_cols = get_feature_columns(df)

    split = group_train_val_test_split(df, seed=seed)

    def _xy(part_df: pd.DataFrame):
        return part_df[feature_cols].values, part_df["label"].values

    X_train, y_train = _xy(split.train)
    X_val, y_val = _xy(split.val)
    X_test, y_test = _xy(split.test)

    models = {
        # class_weight=None (not "balanced"): see the "Primary model
        # selection" rationale below and Experiment C / D in
        # docs/research-notes.md. This dataset's 5:1 STEGO:CLEAN training
        # imbalance comes from replicating the same clean crops at 5
        # payload levels, not from having more independent clean photos -
        # class_weight='balanced' was measured (via
        # scripts/experiment_class_balance.py and confirmed by 9-fold
        # leave-one-photo-out cross-validation in
        # scripts/cross_validate_models.py) to make the CLEAN-image
        # false-positive rate dramatically *worse* (pooled FPR 90% vs 62%
        # with class_weight=None across all 9 held-out photos), not
        # better. This was a real, evidence-driven change - not a
        # hyperparameter guess.
        "random_forest": RandomForestClassifier(
            n_estimators=n_estimators,
            max_depth=max_depth,
            random_state=seed,
            n_jobs=-1,
            class_weight=None,
        ),
        "logistic_regression": LogisticRegression(max_iter=2000, random_state=seed, class_weight="balanced"),
        "gradient_boosting": GradientBoostingClassifier(random_state=seed),
    }

    results = {}
    fitted_pipelines = {}
    t0 = time.time()
    for name, model in models.items():
        pipe = _fit_pipeline(model, X_train, y_train)
        fitted_pipelines[name] = pipe
        results[name] = {
            "val": _evaluate_pipeline(pipe, X_val, y_val),
            "test": _evaluate_pipeline(pipe, X_test, y_test),
        }
    train_time = time.time() - t0

    # Primary model selection.
    #
    # Random Forest is designated primary. Gradient Boosting has a
    # *slightly* higher single-split ROC-AUC on the 2-photo
    # (chelsea/retina) held-out test set used elsewhere in this file, but
    # per-split ROC-AUC on 2 photos is a fragile basis for this decision,
    # and ROC-AUC alone is not the right criterion for a triage/detection
    # tool in the first place: it integrates over operating points
    # (e.g. 80% false-positive rate) that a real analyst would never
    # accept.
    #
    # The decision instead used 9-fold leave-one-source-photo-out
    # cross-validation (scripts/cross_validate_models.py - every one of
    # the 9 available photos held out in turn, all 960 samples used as
    # out-of-fold test data exactly once) and an explicit criterion: TPR
    # at a fixed, operationally realistic false-positive-rate budget
    # (<=20%). This application is framed throughout as a human-in-the-
    # loop triage aid (see the API's own "for demonstration and triage
    # purposes only" disclaimer, app/steganalysis/explainability.py),
    # so the right question is "how much real signal can an analyst
    # still get without being buried in false alarms" - not raw ROC-AUC,
    # and not a symmetric-cost accuracy metric that treats a missed
    # detection the same as one extra image to review.
    #
    # Pooled 9-fold LOGO-CV results (see
    # data/dataset/cross_validation_results.json for the full output):
    #
    #   config                         ROC-AUC  PR-AUC  BalAcc  TPR@FPR<=20%
    #   random_forest (class_weight=None)  0.697   0.921   0.587   0.544   <- selected
    #   gradient_boosting                  0.685   0.919   0.616   0.425
    #   random_forest (class_weight='balanced', old default) 0.660 0.917 0.526 0.483
    #   logistic_regression (balanced)     0.529   0.843   0.505   0.251
    #
    # Random Forest (class_weight=None) wins on the primary criterion
    # (TPR@FPR<=20%), on full ROC-AUC, and on PR-AUC. Gradient Boosting
    # has the best balanced accuracy of the four - a fair, real result
    # that would make it the better pick under a *symmetric* cost
    # assumption (a missed detection is exactly as costly as one extra
    # image for an analyst to review). This project treats a missed
    # detection as more costly than a bounded, triage-queue false alarm
    # (hence weighting TPR-at-a-tolerable-FPR over symmetric accuracy),
    # which is why Random Forest remains primary here - but that
    # weighting is a stated judgment call, not an objective fact, and is
    # recorded plainly rather than hidden. See docs/research-notes.md
    # (Experiment D) for the full writeup and the counter-argument.
    primary_name = "random_forest"
    primary_pipe = fitted_pipelines[primary_name]

    # Feature importance from the primary model (native to tree ensembles).
    importances = primary_pipe.named_steps["model"].feature_importances_
    feature_importance = sorted(
        (
            {"feature": name, "importance": float(imp)}
            for name, imp in zip(feature_cols, importances)
        ),
        key=lambda d: d["importance"],
        reverse=True,
    )

    # Baseline mean/std of every feature over CLEAN training images only.
    # Used at inference time (app/steganalysis/explainability.py) to
    # describe *how* a new image's feature values deviate from a typical
    # clean baseline, e.g. "LSB entropy is 2.1 std-dev above the clean
    # baseline" - a concrete, data-derived explanation rather than a
    # generic statement.
    clean_train = split.train[split.train["label"] == 0]
    clean_baseline_stats = {
        col: {
            "mean": float(clean_train[col].mean()),
            "std": float(clean_train[col].std() or 1e-6),
        }
        for col in feature_cols
    }

    metadata = {
        "trained_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "seed": seed,
        "sklearn_version": sklearn.__version__,
        "python_version": platform.python_version(),
        "primary_model": primary_name,
        "feature_columns": feature_cols,
        "n_features": len(feature_cols),
        "training_time_seconds": round(train_time, 2),
        "dataset_split": split.summary(),
        "models": results,
        "feature_importance": feature_importance,
        "clean_baseline_stats": clean_baseline_stats,
        "hyperparameters": {
            "random_forest": {
                "n_estimators": n_estimators,
                "max_depth": max_depth,
                "class_weight": None,
            }
        },
        "primary_model_selection": {
            "selected": "random_forest",
            "criterion": (
                "TPR at a fixed, operationally realistic false-positive-rate "
                "budget (<=20%), evaluated via 9-fold leave-one-source-photo-out "
                "cross-validation (scripts/cross_validate_models.py) - not raw "
                "single-split ROC-AUC."
            ),
            "rationale": (
                "This app is framed as a human-in-the-loop triage aid, so a "
                "missed detection is treated as more costly than a bounded, "
                "triage-queue false alarm. Under that weighting, Random Forest "
                "(class_weight=None) has the best TPR at a <=20% FPR budget, "
                "the best full-curve ROC-AUC, and the best PR-AUC of the four "
                "configurations tested. Gradient Boosting has the best balanced "
                "accuracy of the four - the better pick under a symmetric-cost "
                "assumption instead - and that tradeoff is stated here rather "
                "than hidden. See docs/research-notes.md (Experiment D) and "
                "data/dataset/cross_validation_results.json for the full "
                "evidence and counter-argument."
            ),
            "logo_cv_pooled_comparison": {
                "random_forest_class_weight_none_selected": {
                    "roc_auc": 0.6965, "pr_auc": 0.9209, "balanced_accuracy": 0.5869, "tpr_at_fpr_20": 0.5437,
                },
                "gradient_boosting": {
                    "roc_auc": 0.6847, "pr_auc": 0.9189, "balanced_accuracy": 0.6156, "tpr_at_fpr_20": 0.4250,
                },
                "random_forest_class_weight_balanced_previous_default": {
                    "roc_auc": 0.6603, "pr_auc": 0.9167, "balanced_accuracy": 0.5262, "tpr_at_fpr_20": 0.4825,
                },
                "logistic_regression_balanced": {
                    "roc_auc": 0.5292, "pr_auc": 0.8434, "balanced_accuracy": 0.5050, "tpr_at_fpr_20": 0.2512,
                },
            },
        },
    }

    return {
        "metadata": metadata,
        "primary_pipeline": primary_pipe,
        "all_pipelines": fitted_pipelines,
        "feature_columns": feature_cols,
    }


def save_artifacts(train_result: dict, model_path: Path, metadata_path: Path) -> None:
    model_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "pipeline": train_result["primary_pipeline"],
            "feature_columns": train_result["feature_columns"],
        },
        model_path,
    )
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(json.dumps(train_result["metadata"], indent=2))
