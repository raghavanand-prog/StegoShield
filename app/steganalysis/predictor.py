"""Inference-time steganalysis: image -> features -> model -> risk + explanation.

The trained pipeline (StandardScaler + RandomForestClassifier) and its
metadata are loaded once and cached in-process (ModelRegistry), not
reloaded from disk on every request.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

import joblib
import numpy as np

from app.config import Config
from app.steganalysis.explainability import build_explanation, explanation_to_indicator_strings
from app.steganalysis.features import extract_features, features_to_vector
from app.steganalysis.risk_scoring import RiskAssessment, score_from_probability
from app.utils.logging_config import get_logger

logger = get_logger(__name__)


class ModelNotTrainedError(RuntimeError):
    pass


@dataclass
class PredictionResult:
    prediction: str  # "CLEAN" or "POSSIBLE STEGO"
    stego_probability: float
    clean_probability: float
    risk: RiskAssessment
    indicators: list[str]
    explanation: list[dict]
    processing_time_ms: float
    model_name: str = "random_forest"

    def as_dict(self) -> dict:
        return {
            "prediction": self.prediction,
            "stego_probability": round(self.stego_probability, 4),
            "clean_probability": round(self.clean_probability, 4),
            **self.risk.as_dict(),
            "indicators": self.indicators,
            "explanation": self.explanation,
            "processing_time_ms": round(self.processing_time_ms, 2),
            "model_name": self.model_name,
        }


@dataclass
class _LoadedModel:
    pipeline: object
    feature_columns: list[str]
    metadata: dict = field(default_factory=dict)


class ModelRegistry:
    _instance: "_LoadedModel | None" = None

    @classmethod
    def load(cls, force: bool = False) -> _LoadedModel:
        if cls._instance is not None and not force:
            return cls._instance

        model_path: Path = Config.MODEL_PATH
        metadata_path: Path = Config.MODEL_METADATA_PATH

        if not model_path.exists():
            raise ModelNotTrainedError(
                "No trained steganalysis model found. Run "
                "`python scripts/generate_dataset.py` then "
                "`python scripts/train_model.py` to train one."
            )

        bundle = joblib.load(model_path)
        metadata = {}
        if metadata_path.exists():
            metadata = json.loads(metadata_path.read_text())

        cls._instance = _LoadedModel(
            pipeline=bundle["pipeline"],
            feature_columns=bundle["feature_columns"],
            metadata=metadata,
        )
        logger.info(
            "model_loaded",
            extra={"n_features": len(bundle["feature_columns"]), "model_path": str(model_path)},
        )
        return cls._instance


def predict(image_array: np.ndarray) -> PredictionResult:
    t0 = time.time()
    loaded = ModelRegistry.load()

    feature_values = extract_features(image_array)
    vector = features_to_vector(feature_values, loaded.feature_columns).reshape(1, -1)

    proba = loaded.pipeline.predict_proba(vector)[0]
    classes = list(loaded.pipeline.named_steps["model"].classes_)
    stego_idx = classes.index(1) if 1 in classes else 1
    clean_idx = classes.index(0) if 0 in classes else 0
    stego_prob = float(proba[stego_idx])
    clean_prob = float(proba[clean_idx])

    prediction_label = "POSSIBLE STEGO" if stego_prob >= 0.5 else "CLEAN"
    risk = score_from_probability(stego_prob)

    feature_importance = loaded.metadata.get("feature_importance", [])
    clean_baseline = loaded.metadata.get("clean_baseline_stats", {})
    explanation = build_explanation(feature_values, feature_importance, clean_baseline)
    indicators = explanation_to_indicator_strings(explanation)

    elapsed_ms = (time.time() - t0) * 1000

    logger.info(
        "steganalysis_prediction",
        extra={
            "prediction": prediction_label,
            "stego_probability": round(stego_prob, 4),
            "risk_level": risk.risk_level,
            "processing_time_ms": round(elapsed_ms, 2),
        },
    )

    return PredictionResult(
        prediction=prediction_label,
        stego_probability=stego_prob,
        clean_probability=clean_prob,
        risk=risk,
        indicators=indicators,
        explanation=explanation,
        processing_time_ms=elapsed_ms,
    )
