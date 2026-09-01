"""Reads the trained model's metadata for the Model Performance and
Dashboard pages. Returns whatever was actually produced by
scripts/train_model.py - nothing here invents metrics."""
from __future__ import annotations

import json

from app.config import Config
from app.utils.errors import APIError


def get_model_metadata() -> dict:
    if not Config.MODEL_METADATA_PATH.exists():
        raise APIError(
            "No trained model metadata found. Run `python scripts/generate_dataset.py` "
            "and `python scripts/train_model.py` to train the steganalysis model.",
            503,
            "model_not_trained",
        )
    return json.loads(Config.MODEL_METADATA_PATH.read_text())


def get_model_status() -> dict:
    if not Config.MODEL_PATH.exists() or not Config.MODEL_METADATA_PATH.exists():
        return {"trained": False}
    meta = get_model_metadata()
    primary = meta["primary_model"]
    test_metrics = meta["models"][primary]["test"]
    return {
        "trained": True,
        "trained_at": meta["trained_at"],
        "primary_model": primary,
        "n_features": meta["n_features"],
        "test_accuracy": test_metrics["accuracy"],
        "test_roc_auc": test_metrics["roc_auc"],
        "dataset_split": meta["dataset_split"],
        "primary_model_selection": meta.get("primary_model_selection"),
    }
