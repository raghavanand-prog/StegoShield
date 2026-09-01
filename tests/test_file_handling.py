"""Tests for secure temporary-file infrastructure and request-level size limits.

Note: the live encode/decode/steganalysis/image-analysis pipelines never
write uploaded bytes to disk at all (they operate on in-memory BytesIO /
NumPy arrays end-to-end), which is a stronger guarantee than "temp files
get cleaned up." app.security.file_handler is provided as reusable,
tested infrastructure for any future feature that does need scratch
files on disk (e.g. streaming a very large batch job) - see
docs/security-review.md for the full rationale.
"""
from __future__ import annotations

import io

from app.security.file_handler import generate_secure_filename, temporary_file


class TestTemporaryFileHandling:
    def test_temporary_file_is_created_and_removed(self):
        path_ref = {}
        with temporary_file("png") as path:
            path.write_bytes(b"scratch data")
            path_ref["path"] = path
            assert path.exists()
        assert not path_ref["path"].exists(), "Temp file must be removed after the context exits"

    def test_temporary_file_removed_even_on_exception(self):
        path_ref = {}
        try:
            with temporary_file("png") as path:
                path_ref["path"] = path
                raise RuntimeError("simulated processing failure")
        except RuntimeError:
            pass
        assert not path_ref["path"].exists(), "Temp file must be cleaned up even after an error"

    def test_filenames_are_not_predictable(self):
        names = {generate_secure_filename("png") for _ in range(20)}
        assert len(names) == 20  # no collisions across 20 generations


class TestRequestSizeLimit:
    def test_oversized_upload_rejected_with_413(self, flask_app):
        flask_app.config["MAX_CONTENT_LENGTH"] = 1024  # 1 KB, for this test only
        client = flask_app.test_client()
        oversized = b"x" * 5000
        resp = client.post(
            "/api/capacity",
            data={"image": (io.BytesIO(oversized), "big.png")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 413
        assert resp.get_json()["error"]["code"] == "file_too_large"
        # Restore for any subsequent tests in the same session.
        from app.config import Config

        flask_app.config["MAX_CONTENT_LENGTH"] = Config.MAX_CONTENT_LENGTH
