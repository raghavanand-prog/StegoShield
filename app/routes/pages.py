"""Server-rendered HTML pages (the dashboard UI)."""
from __future__ import annotations

import json
from pathlib import Path

from flask import Blueprint, render_template

from app.services.model_service import get_model_status

pages_bp = Blueprint("pages", __name__)

DATASET_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "dataset"


def _load_json(filename: str):
    """Read a research artifact from data/dataset/, or None if missing/invalid.

    Read-only, best-effort: the Experiments page is additive UI over existing
    on-disk artifacts and must never 500 the app if a file is absent.
    """
    path = DATASET_DIR / filename
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None


@pages_bp.get("/")
def dashboard():
    status = get_model_status()
    dataset_stats = None
    if status.get("trained") and status.get("dataset_split"):
        split = status["dataset_split"]
        source_images = set()
        n_samples = 0
        for part in split.values():
            n_samples += part.get("samples", 0)
            source_images.update(part.get("source_images", []))
        dataset_stats = {"n_samples": n_samples, "n_source_images": len(source_images)}
    return render_template(
        "dashboard.html",
        model_status=status,
        dataset_stats=dataset_stats,
        active_page="dashboard",
    )


@pages_bp.get("/encode")
def encode_page():
    return render_template("encode.html", active_page="encode")


@pages_bp.get("/decode")
def decode_page():
    return render_template("decode.html", active_page="decode")


@pages_bp.get("/steganalysis")
def steganalysis_page():
    status = get_model_status()
    return render_template("steganalysis.html", model_status=status, active_page="steganalysis")


@pages_bp.get("/image-analysis")
def image_analysis_page():
    return render_template("image_analysis.html", active_page="image_analysis")


@pages_bp.get("/model-performance")
def model_performance_page():
    status = get_model_status()
    return render_template("model_performance.html", model_status=status, active_page="model_performance")


def _payload_vs_quality_summary(experiment_results):
    """Average MSE/PSNR/SSIM across all source images at each payload level.

    Derived directly from the real per-image rows in experiment_results.json
    (the same aggregation docs/research-notes.md reports) — no new numbers.
    """
    rows = (experiment_results or {}).get("payload_vs_quality") or []
    by_level: dict[float, list[dict]] = {}
    for row in rows:
        by_level.setdefault(row["payload_level"], []).append(row)

    summary = []
    for level in sorted(by_level.keys()):
        group = by_level[level]
        n = len(group)
        summary.append(
            {
                "payload_level": level,
                "utilization_percent": group[0].get("utilization_percent"),
                "n_images": n,
                "mean_mse": sum(r["mse"] for r in group) / n,
                "mean_psnr_db": sum(r["psnr_db"] for r in group) / n,
                "mean_ssim": sum(r["ssim"] for r in group) / n,
            }
        )
    return summary


@pages_bp.get("/experiments")
def experiments_page():
    experiment_results = _load_json("experiment_results.json")
    cross_validation = _load_json("cross_validation_results.json")
    class_balance = _load_json("class_balance_experiment_results.json")
    quality_summary = _payload_vs_quality_summary(experiment_results)
    return render_template(
        "experiments.html",
        active_page="experiments",
        experiment_results=experiment_results,
        quality_summary=quality_summary,
        cross_validation=cross_validation,
        class_balance=class_balance,
    )


@pages_bp.get("/docs")
def docs_page():
    status = get_model_status()
    return render_template("docs.html", active_page="docs", model_status=status)


@pages_bp.get("/about")
def about_page():
    return render_template("about.html", active_page="about")
