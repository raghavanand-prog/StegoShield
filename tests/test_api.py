"""End-to-end API tests using Flask's test client (no live server needed)."""
from __future__ import annotations

import io

from app.steganography.encoder import encode_message
from tests.conftest import array_to_png_bytes


def _upload(client, path, field, data_bytes, filename, extra_fields=None):
    payload = {field: (io.BytesIO(data_bytes), filename)}
    if extra_fields:
        payload.update(extra_fields)
    return client.post(path, data=payload, content_type="multipart/form-data")


class TestEncodeDecodeAPI:
    def test_full_encode_decode_cycle(self, client, random_image_png_bytes):
        resp = _upload(
            client, "/api/encode", "image", random_image_png_bytes, "cover.png",
            extra_fields={"message": "classified payload for the API test"},
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["message_bytes"] == len("classified payload for the API test".encode())
        assert "quality" in body and "psnr" in body["quality"]
        assert "stego_image_png_base64" in body

        import base64

        stego_bytes = base64.b64decode(body["stego_image_png_base64"])
        resp2 = _upload(client, "/api/decode", "image", stego_bytes, "stego.png")
        assert resp2.status_code == 200
        assert resp2.get_json()["message"] == "classified payload for the API test"

    def test_decode_clean_image_returns_404(self, client, random_image_png_bytes):
        resp = _upload(client, "/api/decode", "image", random_image_png_bytes, "clean.png")
        assert resp.status_code == 404
        assert resp.get_json()["error"]["code"] == "no_hidden_data"

    def test_capacity_endpoint(self, client, random_image_png_bytes):
        resp = _upload(client, "/api/capacity", "image", random_image_png_bytes, "cover.png")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["width"] == 128
        assert body["height"] == 128


class TestSteganalysisAPI:
    def test_steganalysis_endpoint_shape(self, client, random_image_png_bytes):
        resp = _upload(client, "/api/steganalysis", "image", random_image_png_bytes, "image.png")
        # 200 if model trained, 503 (model_not_trained) if not - either is
        # a valid, well-formed response, never a 500.
        assert resp.status_code in (200, 503)
        body = resp.get_json()
        if resp.status_code == 200:
            assert body["prediction"] in ("CLEAN", "POSSIBLE STEGO")
            assert "risk_score" in body


class TestImageAnalysisAPI:
    def test_dimension_mismatch_rejected(self, client, random_image_array):
        import numpy as np

        original_bytes = array_to_png_bytes(random_image_array)
        different_size = np.zeros((64, 64, 3), dtype=np.uint8)
        modified_bytes = array_to_png_bytes(different_size)

        payload = {
            "original": (io.BytesIO(original_bytes), "a.png"),
            "modified": (io.BytesIO(modified_bytes), "b.png"),
        }
        resp = client.post("/api/image-analysis", data=payload, content_type="multipart/form-data")
        assert resp.status_code == 422
        assert resp.get_json()["error"]["code"] == "dimension_mismatch"

    def test_matching_dimensions_succeeds(self, client, random_image_array):
        original_bytes = array_to_png_bytes(random_image_array)
        result = encode_message(random_image_array, "analysis test")
        modified_bytes = array_to_png_bytes(result.stego_array)

        payload = {
            "original": (io.BytesIO(original_bytes), "a.png"),
            "modified": (io.BytesIO(modified_bytes), "b.png"),
        }
        resp = client.post("/api/image-analysis", data=payload, content_type="multipart/form-data")
        assert resp.status_code == 200
        body = resp.get_json()
        assert "quality" in body
        assert "visual_analysis" in body


class TestPageRoutes:
    def test_all_pages_render_200(self, client):
        for path in ["/", "/encode", "/decode", "/steganalysis", "/image-analysis", "/model-performance", "/about"]:
            resp = client.get(path)
            assert resp.status_code == 200, f"{path} returned {resp.status_code}"
