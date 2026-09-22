"""Validation for untrusted user uploads.

Every uploaded file is treated as hostile until proven otherwise:

1. Extension allow-list (never a deny-list).
2. Real content-type sniffing via libmagic - a renamed .exe with a
   ".png" extension will not pass this check, because we inspect the
   file's actual byte signature rather than trusting the client-supplied
   extension or MIME type header.
3. Size ceiling, enforced both at the Flask/WSGI layer
   (MAX_CONTENT_LENGTH) and again here for defense in depth.
4. Pillow re-decodes the image (Image.verify() + a second full load)
   rather than passing the raw bytes through, which prevents malformed
   image files from reaching downstream libraries.
5. Dimension ceiling to bound memory/CPU usage (resource-exhaustion
   protection against "decompression bomb" style uploads).

Nothing here executes the uploaded file, shells out, or trusts a
client-supplied filename for filesystem paths - see file_handler.py for
secure temp-file naming.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field

import numpy as np

# pylibmagic bundles libmagic's shared library + signature database and
# patches ctypes.CDLL to resolve to them - required on platforms (e.g.
# Vercel's serverless Python runtime) that don't have the system
# libmagic package installed. Must be imported before `magic`. It is a
# no-op wherever a system libmagic is already present.
import pylibmagic  # noqa: F401,E402
import magic
from PIL import Image

from app.config import Config
from app.steganography.exceptions import InvalidImageError

# Real, sniffed MIME types we accept - independent of file extension.
ALLOWED_MIME_TYPES = {
    "image/png": "png",
    "image/bmp": "bmp",
    "image/x-ms-bmp": "bmp",
    "image/jpeg": "jpg",
}

# Pillow "decompression bomb" guard (also enforced separately by our own
# MAX_IMAGE_DIMENSION check, which is more restrictive and app-specific).
Image.MAX_IMAGE_PIXELS = 64_000_000  # ~64 MP ceiling


@dataclass
class ValidatedUpload:
    file_bytes: bytes
    detected_mime: str
    detected_extension: str
    width: int
    height: int
    mode: str
    # RGB pixel array decoded once during validation and reused by every
    # caller (encode/decode/steganalysis/image-analysis services), so a
    # single upload is only ever fully decoded by Pillow once instead of
    # being independently re-opened later via app.utils.image_io.
    rgb_array: np.ndarray = field(repr=False)


_PLAUSIBLE_EXTENSION_RE = re.compile(r"^[a-z0-9]{1,10}$")


def validate_extension(filename: str) -> str:
    if not filename or "." not in filename:
        raise InvalidImageError("Uploaded file has no extension.")
    ext = filename.rsplit(".", 1)[-1].lower()
    if ext not in Config.ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(Config.ALLOWED_EXTENSIONS))
        # The client-supplied filename (and therefore `ext`) is untrusted
        # input. Only echo it back in the error message when it's a
        # short, plausible-looking extension (letters/digits only) -
        # otherwise a crafted filename like `evil.<img src=x onerror=...>`
        # could get its payload reflected into an API error message that
        # the frontend renders. (The frontend also renders all error
        # messages as plain text, never HTML, as a second independent
        # layer of defense - see frontend/static/js/app.js::showAlert.)
        if _PLAUSIBLE_EXTENSION_RE.match(ext):
            raise InvalidImageError(f"Unsupported file extension '.{ext}'. Allowed: {allowed}.")
        raise InvalidImageError(f"Unsupported or invalid file extension. Allowed: {allowed}.")
    return ext


def validate_file_size(file_bytes: bytes) -> None:
    if len(file_bytes) == 0:
        raise InvalidImageError("Uploaded file is empty.")
    if len(file_bytes) > Config.MAX_CONTENT_LENGTH:
        max_mb = Config.MAX_CONTENT_LENGTH_MB
        raise InvalidImageError(f"File exceeds the maximum allowed size of {max_mb} MB.")


def sniff_mime_type(file_bytes: bytes) -> str:
    try:
        mime = magic.from_buffer(file_bytes, mime=True)
    except Exception as exc:  # pragma: no cover - environment-dependent
        raise InvalidImageError("Unable to determine file type.") from exc
    if mime not in ALLOWED_MIME_TYPES:
        raise InvalidImageError(
            f"File content does not match an allowed image type (detected: {mime})."
        )
    return mime


def validate_and_decode_image(file_bytes: bytes, filename: str) -> ValidatedUpload:
    """Run the full validation pipeline and return decoded image metadata.

    Raises InvalidImageError with a user-safe message on any failure.

    Ordering matters here for resource-exhaustion safety: a malicious
    PNG can have a tiny compressed file size (well under
    MAX_CONTENT_LENGTH) but declare an enormous pixel width/height, so
    that decoding it burns disproportionate CPU/memory relative to its
    upload size ("decompression bomb"). `Image.open()` alone only reads
    the file header to learn `.size` - it does not decompress pixel
    data. Dimensions are therefore checked from that header-only probe
    BEFORE any full decode (`.verify()` and `.load()` both decompress
    the pixel stream), so an oversized image is rejected cheaply.
    """
    validate_extension(filename)
    validate_file_size(file_bytes)
    mime = sniff_mime_type(file_bytes)

    # Header-only probe: reads image metadata (dimensions, mode) without
    # decompressing pixel data. Reject absurd dimensions before doing
    # any expensive decode work.
    try:
        header_probe = Image.open(io.BytesIO(file_bytes))
        width, height = header_probe.size
    except Exception as exc:
        raise InvalidImageError("File is not a valid, readable image.") from exc

    if width < Config.MIN_IMAGE_DIMENSION or height < Config.MIN_IMAGE_DIMENSION:
        raise InvalidImageError(
            f"Image is too small (minimum {Config.MIN_IMAGE_DIMENSION}x"
            f"{Config.MIN_IMAGE_DIMENSION} pixels)."
        )
    if width > Config.MAX_IMAGE_DIMENSION or height > Config.MAX_IMAGE_DIMENSION:
        raise InvalidImageError(
            f"Image exceeds the maximum supported dimension of "
            f"{Config.MAX_IMAGE_DIMENSION}px per side."
        )

    # Only now (dimensions already bounded) do the full, expensive
    # decode: verify() checks structural integrity (e.g. PNG chunk
    # CRCs, which requires decompressing the pixel stream for this
    # format), then a fresh re-open + load() performs the real decode
    # verify() invalidates the file handle it was given.
    try:
        probe = Image.open(io.BytesIO(file_bytes))
        probe.verify()
    except Exception as exc:
        raise InvalidImageError("File is not a valid, readable image.") from exc

    try:
        img = Image.open(io.BytesIO(file_bytes))
        img.load()
    except Exception as exc:
        raise InvalidImageError("Failed to decode image data.") from exc

    rgb_array = np.array(img.convert("RGB"), dtype=np.uint8)

    return ValidatedUpload(
        file_bytes=file_bytes,
        detected_mime=mime,
        detected_extension=ALLOWED_MIME_TYPES[mime],
        width=width,
        height=height,
        mode=img.mode,
        rgb_array=rgb_array,
    )


def validate_lossless_for_encoding(detected_extension: str) -> None:
    """Reject JPEG uploads for *encoding* operations only.

    JPEG's lossy DCT-domain compression destroys pixel-exact LSB data,
    so encoding into a JPEG (or an image that will be re-saved as one)
    would silently corrupt the payload. Steganalysis/decoding still
    accept JPEGs since we must be able to *analyze* whatever a user
    uploads, even if we can't losslessly embed into it.
    """
    if detected_extension not in Config.LOSSLESS_EXTENSIONS:
        raise InvalidImageError(
            "Encoding requires a lossless image format (PNG or BMP). "
            "JPEG compression would destroy the hidden payload."
        )
