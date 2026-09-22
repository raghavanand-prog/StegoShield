# StegoShield production image: Flask + the full numpy/scipy/scikit-learn/
# scikit-image/matplotlib ML stack, served by Gunicorn. Unlike Vercel's
# serverless Python runtime (which deferred part of this dependency
# install to request-time and hit a /tmp space limit - see README
# "Production Deployment" for the full story), a normal Docker image
# installs everything once at build time onto a persistent filesystem,
# so that failure mode doesn't exist here.
FROM python:3.11-slim AS base

# libmagic1 gives python-magic (real content-type sniffing for upload
# validation) its system library. python-dotenv/pip/etc need nothing
# else beyond the slim base for this project's pure-Python + manylinux-
# wheel dependencies.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLASK_ENV=production \
    DEBUG=False

WORKDIR /app

# Install dependencies first so this layer is cached across code-only
# changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Train the steganalysis model into the image at build time.
# ml/models/*.joblib is intentionally gitignored (kept out of the repo
# as a binary artifact - see .gitignore); both scripts are seeded (42)
# and use scikit-image's bundled sample images, so this is
# deterministic and needs no network access.
RUN python scripts/generate_dataset.py && python scripts/train_model.py

# Run as a non-root user. The app only ever writes to UPLOAD_TEMP_DIR
# and LOG_FILE (both under /app by default - see app/config.py), which
# this chown covers.
RUN useradd --create-home --uid 1000 stego && chown -R stego:stego /app
USER stego

# Render (and most PaaS platforms) inject PORT at runtime; never
# hardcode 5000 here.
#
# --workers 1: this is not a general recommendation, it's sized for
# Render's free tier specifically (512MB RAM / 0.1 CPU - confirmed via
# a real production failure: 2 workers each fully import numpy/scipy/
# scikit-learn/scikit-image/matplotlib, and that alone was enough to
# exceed 512MB under real request load, causing Render to OOM-kill and
# restart the container - which surfaced as intermittent 502s on
# encode/decode/steganalysis, not on lightweight requests like /api/health).
# One worker halves that baseline import cost. It serializes requests
# (fine for a low-traffic portfolio demo, not fine for real concurrent
# load) - on a paid Render plan with more RAM, raise this back up.
# --timeout 120 gives headroom for the largest image-analysis/
# steganalysis requests now that they queue behind each other instead
# of running in parallel.
EXPOSE 8000
CMD ["sh", "-c", "gunicorn main:app --bind 0.0.0.0:${PORT:-8000} --workers 1 --timeout 120"]
