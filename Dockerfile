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
# This worker configuration is sized for Render's free tier
# specifically (512MB RAM / 0.1 CPU), tuned through two real production
# failures:
#
# 1. --workers 2 (the original setting) meant numpy/scipy/scikit-learn/
#    scikit-image/matplotlib were each fully imported twice (once per
#    worker *process*) - enough alone to exceed 512MB under real
#    request load, so Render OOM-killed and restarted the container.
#    That surfaced as 502s on encode/decode/steganalysis specifically,
#    not on lightweight requests like /api/health.
# 2. Dropping to a single sync worker (--workers 1, no thread support)
#    fixed the memory problem but created a concurrency one: a sync
#    worker handles exactly one request at a time, and a browser
#    loading any page fires several concurrent requests (the HTML,
#    CSS, JS, and a model-status API call) - with only one of those
#    servable at once, the rest queued and Render's proxy timed them
#    out as 503s.
#
# The fix for both at once: one worker *process* (keeps memory low -
# nothing is imported twice) using the `gthread` worker class with
# multiple threads (threads share one process's memory, so this adds
# concurrency without multiplying import cost). This serves several
# concurrent lightweight requests (page assets, health checks) via
# threads while CPU-bound work (an actual encode/decode/steganalysis
# request) still effectively serializes under Python's GIL - which is
# fine for a low-traffic portfolio demo. On a paid Render plan with
# more RAM, --workers can go back up for genuine parallelism.
# --timeout 120 gives headroom for the largest image-analysis/
# steganalysis requests.
EXPOSE 8000
CMD ["sh", "-c", "gunicorn main:app --bind 0.0.0.0:${PORT:-8000} --workers 1 --worker-class gthread --threads 4 --timeout 120"]
