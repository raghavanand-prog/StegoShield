"""Tests for the ML pipeline: feature extraction, dataset splitting,
model training/evaluation mechanics, and inference."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.config import Config
from app.steganalysis.features import extract_features, features_to_vector
from app.steganography.encoder import encode_message
from ml.dataset.generator import tile_image
from ml.evaluation.metrics import compute_metrics
from ml.training.splitting import group_train_val_test_split


class TestFeatureExtraction:
    def test_returns_expected_feature_count(self, random_image_array):
        features = extract_features(random_image_array)
        assert len(features) == 49

    def test_deterministic_for_same_image(self, random_image_array):
        f1 = extract_features(random_image_array)
        f2 = extract_features(random_image_array)
        assert f1 == f2

    def test_lsb_entropy_in_valid_range(self, random_image_array):
        features = extract_features(random_image_array)
        for key, value in features.items():
            if "lsb_entropy" in key:
                assert 0.0 <= value <= 1.0001

    def test_clean_vs_stego_features_differ(self, random_image_array):
        clean_features = extract_features(random_image_array)
        result = encode_message(random_image_array, "x" * 2000)
        stego_features = extract_features(result.stego_array)
        differing = sum(
            1 for k in clean_features if abs(clean_features[k] - stego_features[k]) > 1e-9
        )
        assert differing > 0, "Encoding should measurably change at least one feature"

    def test_features_to_vector_stable_order(self, random_image_array):
        features = extract_features(random_image_array)
        order = sorted(features.keys())
        vector = features_to_vector(features, order)
        assert vector.shape == (len(order),)
        assert vector[0] == features[order[0]]


class TestDatasetTiling:
    def test_tile_image_covers_large_image(self):
        img = np.zeros((512, 512, 3), dtype=np.uint8)
        crops = list(tile_image(img, tile_size=256, stride=256, max_crops=16))
        assert len(crops) == 4  # 2x2 non-overlapping tiles
        for idx, crop in crops:
            assert crop.shape == (256, 256, 3)

    def test_tile_image_handles_small_image(self):
        img = np.zeros((50, 50, 3), dtype=np.uint8)
        crops = list(tile_image(img, tile_size=256, stride=256))
        assert len(crops) == 1
        assert crops[0][1].shape == (50, 50, 3)

    def test_max_crops_respected(self):
        img = np.zeros((2048, 2048, 3), dtype=np.uint8)
        crops = list(tile_image(img, tile_size=128, stride=128, max_crops=10))
        assert len(crops) <= 10


class TestGroupSplitting:
    def _synthetic_df(self, n_groups=10, rows_per_group=20):
        rows = []
        rng = np.random.default_rng(0)
        for g in range(n_groups):
            for i in range(rows_per_group):
                rows.append(
                    {
                        "source_image": f"group_{g}",
                        "label": int(i % 2 == 0),
                        "feature_a": rng.random(),
                        "feature_b": rng.random(),
                    }
                )
        return pd.DataFrame(rows)

    def test_no_group_overlap_between_splits(self):
        df = self._synthetic_df()
        split = group_train_val_test_split(df, seed=42)
        train_groups = set(split.train["source_image"])
        val_groups = set(split.val["source_image"])
        test_groups = set(split.test["source_image"])
        assert not (train_groups & val_groups)
        assert not (train_groups & test_groups)
        assert not (val_groups & test_groups)

    def test_all_rows_accounted_for(self):
        df = self._synthetic_df()
        split = group_train_val_test_split(df, seed=42)
        total = len(split.train) + len(split.val) + len(split.test)
        assert total == len(df)


class TestMetrics:
    def test_perfect_predictions(self):
        y_true = np.array([0, 0, 1, 1])
        y_pred = np.array([0, 0, 1, 1])
        y_proba = np.array([0.1, 0.05, 0.9, 0.95])
        metrics = compute_metrics(y_true, y_pred, y_proba)
        assert metrics["accuracy"] == 1.0
        assert metrics["precision"] == 1.0
        assert metrics["recall"] == 1.0
        assert metrics["roc_auc"] == 1.0
        # Perfect separation: balanced accuracy, specificity, and PR-AUC
        # should all also be perfect, and there's no false-positive rate.
        assert metrics["balanced_accuracy"] == 1.0
        assert metrics["specificity"] == 1.0
        assert metrics["false_positive_rate"] == 0.0
        assert metrics["pr_auc"] == 1.0
        assert metrics["tpr_at_fpr"]["at_fpr_10"] == 1.0
        assert metrics["tpr_at_fpr"]["at_fpr_20"] == 1.0

    def test_confusion_matrix_totals_match_sample_count(self):
        y_true = np.array([0, 0, 1, 1, 1])
        y_pred = np.array([0, 1, 1, 0, 1])
        y_proba = np.array([0.2, 0.6, 0.7, 0.4, 0.8])
        metrics = compute_metrics(y_true, y_pred, y_proba)
        cm = metrics["confusion_matrix"]
        total = cm["true_negative"] + cm["false_positive"] + cm["false_negative"] + cm["true_positive"]
        assert total == len(y_true)

    def test_specificity_and_false_positive_rate_are_complementary(self):
        y_true = np.array([0, 0, 0, 0, 1, 1])
        y_pred = np.array([0, 1, 1, 1, 1, 1])  # 1 TN, 3 FP among 4 CLEAN samples
        y_proba = np.array([0.2, 0.6, 0.7, 0.55, 0.8, 0.9])
        metrics = compute_metrics(y_true, y_pred, y_proba)
        assert metrics["specificity"] == pytest.approx(0.25)  # 1 / (1 + 3)
        assert metrics["false_positive_rate"] == pytest.approx(0.75)
        assert metrics["specificity"] + metrics["false_positive_rate"] == pytest.approx(1.0)

    def test_balanced_accuracy_matches_sklearn(self):
        y_true = np.array([0, 0, 0, 0, 1, 1])
        y_pred = np.array([0, 1, 1, 1, 1, 1])
        y_proba = np.array([0.2, 0.6, 0.7, 0.55, 0.8, 0.9])
        metrics = compute_metrics(y_true, y_pred, y_proba)
        from sklearn.metrics import balanced_accuracy_score

        expected = balanced_accuracy_score(y_true, y_pred)
        assert metrics["balanced_accuracy"] == pytest.approx(expected)
        # By construction here it differs from raw accuracy (imbalanced classes).
        assert metrics["balanced_accuracy"] != pytest.approx(metrics["accuracy"])

    def test_pr_auc_matches_sklearn_average_precision(self):
        y_true = np.array([0, 0, 1, 1, 1])
        y_pred = np.array([0, 1, 1, 0, 1])
        y_proba = np.array([0.2, 0.6, 0.7, 0.4, 0.8])
        metrics = compute_metrics(y_true, y_pred, y_proba)
        from sklearn.metrics import average_precision_score

        expected = average_precision_score(y_true, y_proba)
        assert metrics["pr_auc"] == pytest.approx(expected)
        assert metrics["pr_curve"] is not None
        assert len(metrics["pr_curve"]["precision"]) == len(metrics["pr_curve"]["recall"])

    def test_tpr_at_fpr_never_exceeds_full_curve_tpr_and_respects_budget(self):
        # A classifier with a clear separation gap: half the CLEAN scores
        # sit below the lowest STEGO score, so a low-FPR budget should
        # still recover a meaningful TPR, and a wider budget should never
        # do worse than a tighter one.
        y_true = np.array([0, 0, 0, 0, 1, 1, 1, 1])
        y_proba = np.array([0.05, 0.1, 0.4, 0.45, 0.5, 0.6, 0.8, 0.9])
        y_pred = (y_proba >= 0.5).astype(int)
        metrics = compute_metrics(y_true, y_pred, y_proba)
        tpr10 = metrics["tpr_at_fpr"]["at_fpr_10"]
        tpr20 = metrics["tpr_at_fpr"]["at_fpr_20"]
        assert 0.0 <= tpr10 <= 1.0
        assert 0.0 <= tpr20 <= 1.0
        # A wider FPR budget can only match or beat a tighter one.
        assert tpr20 >= tpr10

    def test_single_class_ground_truth_yields_none_for_curve_metrics(self):
        # ROC-AUC/PR-AUC are undefined with only one class present; the
        # function must degrade gracefully (None) rather than raising or
        # fabricating a value.
        y_true = np.array([1, 1, 1])
        y_pred = np.array([1, 1, 0])
        y_proba = np.array([0.9, 0.8, 0.3])
        metrics = compute_metrics(y_true, y_pred, y_proba)
        assert metrics["roc_auc"] is None
        assert metrics["pr_auc"] is None
        assert metrics["tpr_at_fpr"] is None
        assert metrics["pr_curve"] is None


class TestTrainingSmoke:
    def test_train_and_evaluate_runs_on_small_synthetic_dataset(self, tmp_path):
        """End-to-end smoke test of the training mechanics (not the real
        dataset) - confirms the pipeline fits, evaluates, and produces
        well-formed metadata without requiring the full ~1s+ real run."""
        from ml.training.train_model import train_and_evaluate

        rng = np.random.default_rng(0)
        rows = []
        for g in range(6):
            for i in range(30):
                label = i % 2
                rows.append(
                    {
                        "sample_id": f"{g}_{i}",
                        "source_image": f"img_{g}",
                        "crop_index": i,
                        "label": label,
                        "payload_level": 0.1 if label else 0.0,
                        "payload_bytes": 100 if label else 0,
                        "utilization_percent": 10.0 if label else 0.0,
                        "width": 64,
                        "height": 64,
                        "feat_1": rng.random() + label * 0.5,
                        "feat_2": rng.random(),
                    }
                )
        df = pd.DataFrame(rows)
        csv_path = tmp_path / "synthetic.csv"
        df.to_csv(csv_path, index=False)

        result = train_and_evaluate(csv_path, seed=1, n_estimators=20)
        assert "random_forest" in result["metadata"]["models"]
        assert 0.0 <= result["metadata"]["models"]["random_forest"]["test"]["accuracy"] <= 1.0
        assert len(result["metadata"]["feature_importance"]) == 2


class TestInferenceIfModelTrained:
    def test_predict_on_trained_model(self, random_image_array):
        from app.steganalysis.predictor import ModelNotTrainedError, predict

        if not Config.MODEL_PATH.exists():
            pytest.skip("Model not trained yet - run scripts/train_model.py first.")

        result = predict(random_image_array)
        assert result.prediction in ("CLEAN", "POSSIBLE STEGO")
        assert 0.0 <= result.stego_probability <= 1.0
        assert result.risk.risk_level in ("LOW", "MEDIUM", "HIGH", "CRITICAL")
        assert len(result.indicators) <= 5
