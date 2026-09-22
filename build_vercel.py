"""Vercel build-time step.

`ml/models/*.joblib` is intentionally gitignored (see .gitignore) to
keep the repository free of binary model artifacts - the project's own
convention is "regenerate via scripts/train_model.py". Vercel deploys
straight from this git checkout, so the deployed function needs the
model file to exist on disk *before* Vercel packages the function,
which this script does by running the same two CLI steps documented in
the README for local setup.

Fully offline and deterministic: the dataset generator draws its cover
images from scikit-image's bundled sample data (no network access, no
external dataset download), and both steps are seeded (default 42).
Total runtime is well under a minute.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def run(cmd: list[str]) -> None:
    print(f"$ {' '.join(cmd)}", flush=True)
    subprocess.run(cmd, check=True, cwd=BASE_DIR)


def main() -> None:
    # Explicit and self-contained rather than relying on Vercel's
    # implicit "install requirements.txt" step still running alongside
    # a custom top-level `buildCommand` (vercel.json) - this way the
    # build works the same regardless of that platform behavior.
    run([sys.executable, "-m", "pip", "install", "--no-cache-dir", "-r", "requirements.txt"])
    run([sys.executable, "scripts/generate_dataset.py"])
    run([sys.executable, "scripts/train_model.py"])


if __name__ == "__main__":
    main()
