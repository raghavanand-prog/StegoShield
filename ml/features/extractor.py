"""Thin re-export so ml/ scripts and app/ share one feature implementation.

The canonical extraction logic lives in app/steganalysis/features.py so
that training-time and inference-time feature computation can never
drift apart. This module exists only so the ml/ package (which mirrors
the architecture requested for the project) has its own importable
entry point, as documented in the README's project structure.
"""
from app.steganalysis.features import (  # noqa: F401
    FEATURE_DESCRIPTIONS,
    extract_channel_features,
    extract_cross_channel_features,
    extract_features,
    features_to_vector,
    get_feature_order,
)
