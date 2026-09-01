"""Transparent, model-driven risk scoring.

IMPORTANT: this is a project-defined triage score for demonstration
purposes, not an industry-standard or scientifically validated metric
(no such universal standard exists for steganalysis risk). It is
derived directly from the trained model's predicted probability for
the STEGO class - never hardcoded - on a simple linear 0-100 scale:

    risk_score = round(P(stego) * 100)

    0-30   -> LOW       "Statistically consistent with a clean image."
    31-60  -> MEDIUM     "Some steganalysis indicators present; inconclusive."
    61-80  -> HIGH       "Strong statistical indicators of hidden data."
    81-100 -> CRITICAL   "Very strong statistical indicators of hidden data."

The score is intentionally just a monotonic rescaling of the model's
own probability output (not a separate hand-tuned formula) so that it
stays honest about what the model actually predicted; the bands exist
only to make the number easier to triage at a glance.
"""
from __future__ import annotations

from dataclasses import dataclass

RISK_BANDS = [
    (0, 30, "LOW", "Statistically consistent with a clean image."),
    (31, 60, "MEDIUM", "Some steganalysis indicators present; result is inconclusive."),
    (61, 80, "HIGH", "Strong statistical indicators of hidden data."),
    (81, 100, "CRITICAL", "Very strong statistical indicators of hidden data."),
]


@dataclass
class RiskAssessment:
    risk_score: int
    risk_level: str
    risk_description: str

    def as_dict(self) -> dict:
        return {
            "risk_score": self.risk_score,
            "risk_level": self.risk_level,
            "risk_description": self.risk_description,
            "disclaimer": (
                "Project-defined risk score for demonstration and triage "
                "purposes only - not a scientifically validated cybersecurity "
                "standard."
            ),
        }


def score_from_probability(stego_probability: float) -> RiskAssessment:
    score = int(round(max(0.0, min(1.0, stego_probability)) * 100))
    for low, high, level, desc in RISK_BANDS:
        if low <= score <= high:
            return RiskAssessment(risk_score=score, risk_level=level, risk_description=desc)
    return RiskAssessment(risk_score=score, risk_level="CRITICAL", risk_description=RISK_BANDS[-1][3])
