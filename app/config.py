"""
Central application configuration.

Values are read from environment variables (see .env.example) with sane
defaults so the project runs out-of-the-box in a development setting.
Nothing here should contain secrets - copy .env.example to .env and
override values locally instead of editing this file.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


class Config:
    """Base configuration shared by all environments."""

    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-me")
    DEBUG = _bool("DEBUG", False)

    HOST = os.getenv("HOST", "127.0.0.1")
    PORT = int(os.getenv("PORT", "5000"))

    # --- Upload / processing limits -------------------------------------
    MAX_CONTENT_LENGTH_MB = int(os.getenv("MAX_CONTENT_LENGTH_MB", "10"))
    MAX_CONTENT_LENGTH = MAX_CONTENT_LENGTH_MB * 1024 * 1024

    MAX_IMAGE_DIMENSION = int(os.getenv("MAX_IMAGE_DIMENSION", "6000"))
    MIN_IMAGE_DIMENSION = 16

    ALLOWED_EXTENSIONS = set(
        e.strip().lower()
        for e in os.getenv("ALLOWED_EXTENSIONS", "png,bmp,jpg,jpeg").split(",")
        if e.strip()
    )
    # LSB steganography only survives lossless formats. JPEG uploads are
    # accepted for *analysis/steganalysis* but rejected for *encoding*
    # because re-compression would destroy the hidden payload.
    LOSSLESS_EXTENSIONS = {"png", "bmp"}

    # --- Rate limiting ----------------------------------------------------
    RATE_LIMIT_DEFAULT = os.getenv("RATE_LIMIT_DEFAULT", "60 per minute")
    RATE_LIMIT_UPLOAD = os.getenv("RATE_LIMIT_UPLOAD", "10 per minute")
    RATE_LIMIT_ENABLED = _bool("RATE_LIMIT_ENABLED", True)

    # --- Paths --------------------------------------------------------------
    UPLOAD_TEMP_DIR = BASE_DIR / os.getenv("UPLOAD_TEMP_DIR", "data/tmp")
    MODEL_PATH = BASE_DIR / os.getenv("MODEL_PATH", "ml/models/steganalysis_model.joblib")
    MODEL_METADATA_PATH = BASE_DIR / os.getenv(
        "MODEL_METADATA_PATH", "ml/models/model_metadata.json"
    )

    # --- Logging --------------------------------------------------------------
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE = BASE_DIR / os.getenv("LOG_FILE", "logs/app.log")

    # --- Steganography payload framing ---------------------------------------
    MAGIC = b"STG1"
    VERSION = 1
    HEADER_MAGIC_LEN = 4
    HEADER_VERSION_LEN = 1
    HEADER_LENGTH_LEN = 4  # uint32 big-endian payload length in bytes
    HEADER_CHECKSUM_LEN = 32  # SHA-256 digest
    HEADER_TOTAL_LEN = (
        HEADER_MAGIC_LEN + HEADER_VERSION_LEN + HEADER_LENGTH_LEN + HEADER_CHECKSUM_LEN
    )
    MAX_MESSAGE_BYTES = 5 * 1024 * 1024  # hard ceiling regardless of image capacity


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False


class TestingConfig(Config):
    TESTING = True
    RATE_LIMIT_ENABLED = False
    UPLOAD_TEMP_DIR = BASE_DIR / "data" / "tmp_test"


CONFIG_MAP = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
}


def get_config():
    env = os.getenv("FLASK_ENV", "production").lower()
    return CONFIG_MAP.get(env, ProductionConfig)
