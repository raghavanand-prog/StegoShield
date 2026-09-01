"""Real, computed classification metrics - nothing here is invented.

Every value returned by `compute_metrics` comes directly from
scikit-learn's metric functions applied to actual model predictions on
held-out data.

Beyond the basics (accuracy/precision/recall/F1/ROC-AUC), this also
reports metrics that matter specifically for a detection system where
the positive class (STEGO) is rare in real-world traffic and false
positives have a real operational cost (analyst alert fatigue):

- balanced_accuracy - the average of recall on each class, which
  (unlike raw accuracy) is not dominated by whichever class happens to
  have more test samples.
- specificity (true-negative rate) and false_positive_rate (1 -
  specificity) - reported directly rather than only implied by the
  confusion matrix, since the CLEAN-image false-positive rate is this
  project's most important, most honestly-reported weakness (see
  docs/research-notes.md).
- pr_auc (average precision) - the area under the precision-recall
  curve. Preferred over ROC-AUC as a *summary* statistic under class
  imbalance (Davis & Goadrich, 2006): ROC-AUC can look deceptively
  good when the negative class is large because the false-positive
  *rate* stays low even while the absolute count of false positives
  (and therefore precision) collapses - exactly the failure mode this
  project's CLEAN-image results demonstrate.
- tpr_at_fpr - true-positive rate at fixed, operationally realistic
  false-positive-rate budgets (10% and 20%). A full ROC-AUC integrates
  over the *entire* curve, including high-FPR operating points a real
  analyst would never accept (nobody deploys a detector that flags 80%
  of clean traffic). Reading TPR off the curve at a fixed, defensible
  FPR budget is the standard way detection literature compares models
  at a realistic operating point instead of an average over unrealistic
  ones.
"""
from __future__ import annotations

import numpy as np
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    balanced_accuracy_score,
    confusion_matrix,
    f1_score,
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_auc_score,
    roc_curve,
)


def _tpr_at_fpr_budget(fpr: np.ndarray, tpr: np.ndarray, budget: float) -> float:
    """Highest TPR achieved at or below the given FPR budget on this ROC
    curve. `fpr`/`tpr` from sklearn's `roc_curve` are already sorted by
    ascending threshold (equivalently, ascending FPR), so this is a
    direct lookup, not an approximation beyond the curve's own
    resolution."""
    eligible = tpr[fpr <= budget]
    return float(eligible.max()) if eligible.size else 0.0


def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray, y_proba: np.ndarray) -> dict:
    """`y_proba` is the predicted probability of the positive (STEGO=1) class."""
    cm = confusion_matrix(y_true, y_pred, labels=[0, 1])
    tn, fp, fn, tp = cm.ravel()
    specificity = float(tn / (tn + fp)) if (tn + fp) else 0.0

    metrics = {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "balanced_accuracy": float(balanced_accuracy_score(y_true, y_pred)),
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, zero_division=0)),
        "specificity": specificity,
        "false_positive_rate": float(1.0 - specificity),
        "f1_score": float(f1_score(y_true, y_pred, zero_division=0)),
        "confusion_matrix": {
            "true_negative": int(tn),
            "false_positive": int(fp),
            "false_negative": int(fn),
            "true_positive": int(tp),
            "labels": ["CLEAN (0)", "STEGO (1)"],
            "matrix": cm.tolist(),
        },
        "support": {"clean": int(np.sum(y_true == 0)), "stego": int(np.sum(y_true == 1))},
    }

    # ROC-AUC / PR-AUC require both classes present in y_true.
    if len(np.unique(y_true)) == 2:
        metrics["roc_auc"] = float(roc_auc_score(y_true, y_proba))
        fpr, tpr, _ = roc_curve(y_true, y_proba)
        metrics["tpr_at_fpr"] = {
            "at_fpr_10": _tpr_at_fpr_budget(fpr, tpr, 0.10),
            "at_fpr_20": _tpr_at_fpr_budget(fpr, tpr, 0.20),
        }
        # Subsample the curve to a manageable number of points for the UI.
        step = max(1, len(fpr) // 50)
        metrics["roc_curve"] = {
            "fpr": fpr[::step].tolist(),
            "tpr": tpr[::step].tolist(),
        }

        metrics["pr_auc"] = float(average_precision_score(y_true, y_proba))
        precision_curve, recall_curve, _ = precision_recall_curve(y_true, y_proba)
        step_pr = max(1, len(precision_curve) // 50)
        metrics["pr_curve"] = {
            "precision": precision_curve[::step_pr].tolist(),
            "recall": recall_curve[::step_pr].tolist(),
        }
    else:
        metrics["roc_auc"] = None
        metrics["roc_curve"] = None
        metrics["tpr_at_fpr"] = None
        metrics["pr_auc"] = None
        metrics["pr_curve"] = None

    return metrics
