"""Human-readable explanations for a single prediction.

Combines the trained model's global feature importances (from
model_metadata.json) with this specific image's deviation from the
clean-image baseline (also computed at training time from real
training data) to produce concrete, per-prediction explanations such
as:

    "LSB entropy (blue channel) is 2.4 standard deviations above the
     typical clean-image baseline"

instead of a generic, non-committal statement. Nothing here is
templated boilerplate unrelated to the actual feature values.
"""
from __future__ import annotations

from app.steganalysis.features import FEATURE_DESCRIPTIONS

TOP_K_EXPLANATION_FEATURES = 5


def _describe_feature(name: str) -> str:
    for suffix, desc in FEATURE_DESCRIPTIONS.items():
        if name.endswith(suffix):
            return desc
    return "Statistical image feature."


def _friendly_feature_name(name: str) -> str:
    return name.replace("_", " ")


def build_explanation(
    feature_values: dict,
    feature_importance: list[dict],
    clean_baseline_stats: dict,
    top_k: int = TOP_K_EXPLANATION_FEATURES,
) -> list[dict]:
    """Return the top-K globally-important features, annotated with how far
    THIS image's value sits from the clean baseline (z-score), sorted by
    |z-score| * importance so the most suspicious *and* most important
    signals surface first.
    """
    candidates = []
    for item in feature_importance[: max(top_k * 3, top_k)]:
        name = item["feature"]
        importance = item["importance"]
        value = feature_values.get(name)
        baseline = clean_baseline_stats.get(name)
        if value is None or baseline is None:
            continue
        z = (value - baseline["mean"]) / (baseline["std"] or 1e-6)
        candidates.append(
            {
                "feature": name,
                "friendly_name": _friendly_feature_name(name),
                "description": _describe_feature(name),
                "value": round(float(value), 5),
                "clean_baseline_mean": round(baseline["mean"], 5),
                "z_score": round(float(z), 2),
                "direction": "above" if z >= 0 else "below",
                "model_importance": round(importance, 4),
                "signal_strength": round(abs(z) * importance, 5),
            }
        )

    candidates.sort(key=lambda c: c["signal_strength"], reverse=True)
    return candidates[:top_k]


def explanation_to_indicator_strings(explanation: list[dict]) -> list[str]:
    """Render explanation entries as short bullet strings for the UI, e.g.
    'Elevated blue LSB entropy (2.4 sigma above clean baseline)'.
    """
    strings = []
    for item in explanation:
        magnitude = "Elevated" if item["direction"] == "above" else "Reduced"
        strings.append(
            f"{magnitude} {item['friendly_name']} "
            f"({abs(item['z_score']):.1f}σ {item['direction']} clean baseline)"
        )
    return strings
