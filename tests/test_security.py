"""Tests for untrusted-input validation and the API's security posture."""
from __future__ import annotations

import io

import pytest

from app.config import Config
from app.security import validators
from app.security.file_handler import generate_secure_filename
from app.steganography.exceptions import InvalidImageError


class TestExtensionValidation:
    def test_valid_extension_accepted(self):
        assert validators.validate_extension("photo.png") == "png"

    def test_disallowed_extension_rejected(self):
        with pytest.raises(InvalidImageError):
            validators.validate_extension("payload.exe")

    def test_missing_extension_rejected(self):
        with pytest.raises(InvalidImageError):
            validators.validate_extension("noextension")

    def test_double_extension_uses_final_segment(self):
        # "image.png.exe" must be judged by its real (final) extension,
        # not whatever precedes it - this prevents a classic extension-
        # spoofing bypass.
        with pytest.raises(InvalidImageError):
            validators.validate_extension("image.png.exe")


class TestFileSizeValidation:
    def test_empty_file_rejected(self):
        with pytest.raises(InvalidImageError):
            validators.validate_file_size(b"")

    def test_oversized_file_rejected(self, monkeypatch):
        monkeypatch.setattr(Config, "MAX_CONTENT_LENGTH", 100)
        with pytest.raises(InvalidImageError):
            validators.validate_file_size(b"x" * 200)

    def test_file_within_limit_accepted(self, monkeypatch):
        monkeypatch.setattr(Config, "MAX_CONTENT_LENGTH", 1000)
        validators.validate_file_size(b"x" * 500)  # should not raise


class TestContentSniffing:
    def test_renamed_text_file_rejected(self):
        # A .png-named file whose actual bytes are plain text must be
        # rejected by libmagic content sniffing, not trusted by extension.
        fake_bytes = b"this is not a real image, just text pretending to be one"
        with pytest.raises(InvalidImageError):
            validators.validate_and_decode_image(fake_bytes, "fake.png")

    def test_valid_png_accepted(self, random_image_png_bytes):
        validated = validators.validate_and_decode_image(random_image_png_bytes, "test.png")
        assert validated.detected_mime == "image/png"
        assert validated.width == 128
        assert validated.height == 128

    def test_truncated_image_rejected(self, random_image_png_bytes):
        truncated = random_image_png_bytes[: len(random_image_png_bytes) // 2]
        with pytest.raises(InvalidImageError):
            validators.validate_and_decode_image(truncated, "truncated.png")


class TestDimensionLimits:
    def test_image_too_small_rejected(self, monkeypatch):
        import numpy as np
        from PIL import Image

        tiny = Image.fromarray(np.zeros((4, 4, 3), dtype=np.uint8))
        buf = io.BytesIO()
        tiny.save(buf, format="PNG")
        with pytest.raises(InvalidImageError):
            validators.validate_and_decode_image(buf.getvalue(), "tiny.png")

    def test_oversized_dimensions_rejected_before_full_decode(self, monkeypatch):
        """Regression test from the production audit: an image whose
        declared pixel dimensions exceed MAX_IMAGE_DIMENSION must be
        rejected using only the (cheap, header-only) `Image.open().size`
        probe, WITHOUT first paying for a full pixel decode - otherwise
        a small, highly-compressible file with huge declared dimensions
        ("decompression bomb") can burn disproportionate CPU/memory
        before being rejected. We verify this by asserting Image.load()
        is never called on the oversized path.
        """
        import numpy as np
        from PIL import Image

        # A flat-color image compresses to a tiny file even at dimensions
        # well beyond the configured maximum.
        oversized = Image.fromarray(
            np.full((Config.MAX_IMAGE_DIMENSION + 200, Config.MAX_IMAGE_DIMENSION + 200, 3), 128, dtype=np.uint8)
        )
        buf = io.BytesIO()
        oversized.save(buf, format="PNG")
        data = buf.getvalue()

        original_load = Image.Image.load
        load_called = {"value": False}

        def spy_load(self):
            load_called["value"] = True
            return original_load(self)

        monkeypatch.setattr(Image.Image, "load", spy_load)

        with pytest.raises(InvalidImageError, match="maximum supported dimension"):
            validators.validate_and_decode_image(data, "oversized.png")

        assert not load_called["value"], (
            "Image.load() (a full pixel decode) was called before the oversized "
            "image was rejected - the dimension check must happen first."
        )


class TestLosslessRequirement:
    def test_jpeg_rejected_for_encoding(self):
        with pytest.raises(InvalidImageError):
            validators.validate_lossless_for_encoding("jpg")

    def test_png_accepted_for_encoding(self):
        validators.validate_lossless_for_encoding("png")  # should not raise

    def test_bmp_accepted_for_encoding(self):
        validators.validate_lossless_for_encoding("bmp")  # should not raise


class TestSecureFilenames:
    def test_generated_filenames_are_random_not_user_derived(self):
        name1 = generate_secure_filename("png")
        name2 = generate_secure_filename("png")
        assert name1 != name2
        assert name1.endswith(".png")

    def test_path_traversal_patterns_never_appear_in_generated_name(self):
        # Even if this were (incorrectly) called with attacker input, the
        # function never incorporates any caller-supplied string beyond
        # the extension, so traversal sequences cannot appear.
        name = generate_secure_filename("png")
        assert ".." not in name
        assert "/" not in name


class TestAPISecurity:
    def test_missing_file_returns_clean_error(self, client):
        resp = client.post("/api/encode", data={"message": "hello"})
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["error"]["code"] == "missing_file"

    def test_malicious_extension_rejected_via_api(self, client, random_image_png_bytes):
        data = {"image": (io.BytesIO(random_image_png_bytes), "payload.exe")}
        resp = client.post("/api/capacity", data=data, content_type="multipart/form-data")
        assert resp.status_code == 400
        assert resp.get_json()["error"]["code"] == "invalid_image"

    def test_response_never_leaks_stack_trace(self, client):
        # Force an internal error path (malformed multipart) and confirm
        # no Python traceback / file path ever reaches the client.
        resp = client.post("/api/encode", data={})
        assert resp.status_code < 500 or b"Traceback" not in resp.data
        assert b"/home/" not in resp.data
        assert b"Traceback" not in resp.data

    def test_security_headers_present(self, client):
        resp = client.get("/")
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"
        assert resp.headers.get("X-Frame-Options") == "DENY"
        assert "Content-Security-Policy" in resp.headers

    def test_csp_img_src_allows_blob_for_local_previews(self, client):
        """Regression test from the production audit: the frontend's local
        file-preview thumbnails (Encode/Decode/Steganalysis/Image-Analysis
        pages) use URL.createObjectURL(), which produces a blob: URL. If
        the CSP img-src directive doesn't allow blob:, every preview
        thumbnail silently fails to render (a real bug caught only by live
        browser testing, not the static audit)."""
        resp = client.get("/")
        csp = resp.headers.get("Content-Security-Policy", "")
        img_src_directive = next(
            (part.strip() for part in csp.split(";") if part.strip().startswith("img-src")),
            "",
        )
        assert "blob:" in img_src_directive, f"img-src directive missing blob:: {img_src_directive!r}"

    def test_health_endpoint(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "ok"

    def test_crafted_filename_not_reflected_in_error_message(self, client, random_image_png_bytes):
        """Regression test for a real finding from the production audit:
        a filename whose 'extension' (the substring after the final dot)
        contains HTML/script content was echoed verbatim into the
        invalid_image error message. The server must never reflect an
        implausible (non alphanumeric) extension back to the client -
        see app.security.validators.validate_extension.
        """
        malicious_name = "evil.<img src=x onerror=alert(1)>"
        data = {"image": (io.BytesIO(random_image_png_bytes), malicious_name)}
        resp = client.post("/api/capacity", data=data, content_type="multipart/form-data")
        assert resp.status_code == 400
        message = resp.get_json()["error"]["message"]
        assert "<img" not in message
        assert "onerror" not in message
        assert "<" not in message and ">" not in message

    def test_ordinary_extension_still_echoed_for_usability(self, client, random_image_png_bytes):
        # Plausible (alphanumeric, short) extensions are still named in
        # the error message - only implausible/malicious-looking ones
        # are suppressed. This is a UX regression guard for the fix above.
        data = {"image": (io.BytesIO(random_image_png_bytes), "payload.exe")}
        resp = client.post("/api/capacity", data=data, content_type="multipart/form-data")
        assert ".exe" in resp.get_json()["error"]["message"]

    def test_domain_validation_errors_logged_at_info_not_error(self, client, random_image_png_bytes, caplog):
        """Regression test: ordinary validation failures (bad extension,
        empty message, etc.) must be handled by the dedicated
        SteganographyError handler - not fall through to the generic
        Exception handler, which logs a full ERROR-level stack trace for
        what is just a routine 400 response."""
        import logging

        with caplog.at_level(logging.INFO, logger="stegoshield"):
            data = {"image": (io.BytesIO(random_image_png_bytes), "payload.exe")}
            client.post("/api/capacity", data=data, content_type="multipart/form-data")

        error_records = [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert not error_records, f"Expected no ERROR-level logs for a routine validation failure, got: {error_records}"
