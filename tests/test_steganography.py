"""Tests for the LSB steganography engine: encode/decode round-trips,
edge cases, and the payload-integrity API endpoints."""
from __future__ import annotations

import numpy as np
import pytest

from app.steganography.decoder import decode_message
from app.steganography.encoder import encode_message
from app.steganography.exceptions import (
    CapacityExceededError,
    EmptyMessageError,
    IntegrityVerificationError,
    NoHiddenDataError,
)


class TestEncodeDecodeRoundTrip:
    def test_normal_message_round_trip(self, random_image_array):
        message = "The quick brown fox jumps over the lazy dog."
        result = encode_message(random_image_array, message)
        decoded = decode_message(result.stego_array)
        assert decoded.message == message
        assert decoded.payload_length == len(message.encode("utf-8"))

    def test_unicode_message_round_trip(self, random_image_array):
        message = "Confidential 機密 café naïve emoji: 🔐🛡️日本語"
        result = encode_message(random_image_array, message)
        decoded = decode_message(result.stego_array)
        assert decoded.message == message

    def test_single_character_message(self, random_image_array):
        result = encode_message(random_image_array, "x")
        decoded = decode_message(result.stego_array)
        assert decoded.message == "x"

    def test_large_message_near_capacity(self, random_image_array):
        from app.steganography.capacity import compute_capacity

        report = compute_capacity(random_image_array)
        message = "A" * (report.max_message_bytes - 1)
        result = encode_message(random_image_array, message)
        decoded = decode_message(result.stego_array)
        assert decoded.message == message

    def test_original_array_not_mutated(self, random_image_array):
        original_copy = random_image_array.copy()
        encode_message(random_image_array, "does this mutate the input?")
        assert np.array_equal(random_image_array, original_copy)


class TestEdgeCases:
    def test_empty_message_rejected(self, random_image_array):
        with pytest.raises(EmptyMessageError):
            encode_message(random_image_array, "")

    def test_message_exceeding_capacity_rejected(self):
        tiny_image = np.zeros((8, 8, 3), dtype=np.uint8)
        with pytest.raises(CapacityExceededError):
            encode_message(tiny_image, "x" * 1000)

    def test_capacity_error_reports_correct_limits(self):
        tiny_image = np.zeros((8, 8, 3), dtype=np.uint8)
        with pytest.raises(CapacityExceededError) as exc_info:
            encode_message(tiny_image, "x" * 1000)
        assert exc_info.value.message_bytes == 1000

    def test_decode_random_image_has_no_payload(self, random_image_array):
        with pytest.raises(NoHiddenDataError):
            decode_message(random_image_array)

    def test_decode_tiny_image_has_no_payload(self):
        tiny_image = np.zeros((2, 2, 3), dtype=np.uint8)
        with pytest.raises(NoHiddenDataError):
            decode_message(tiny_image)


class TestPayloadIntegrity:
    def test_corrupted_payload_detected(self, random_image_array):
        result = encode_message(random_image_array, "integrity check message payload")
        corrupted = result.stego_array.copy()
        # Flip several LSBs within the payload region to force a checksum mismatch.
        flat = corrupted.reshape(-1)
        for offset in range(400, 460):
            flat[offset] ^= 1
        corrupted = flat.reshape(result.stego_array.shape)

        with pytest.raises(IntegrityVerificationError):
            decode_message(corrupted)

    def test_uncorrupted_payload_passes_integrity_check(self, random_image_array):
        result = encode_message(random_image_array, "no corruption here")
        decoded = decode_message(result.stego_array)  # should not raise
        assert decoded.message == "no corruption here"


class TestCapacityReporting:
    def test_capacity_report_fields(self, random_image_array):
        from app.steganography.capacity import compute_capacity

        report = compute_capacity(random_image_array)
        assert report.width == 128
        assert report.height == 128
        assert report.channels == 3
        assert report.total_capacity_bytes == (128 * 128 * 3) // 8
        assert report.max_message_bytes == report.total_capacity_bytes - report.header_overhead_bytes

    def test_utilization_percent_increases_with_message_size(self, random_image_array):
        from app.steganography.capacity import compute_capacity, utilization_percent

        report = compute_capacity(random_image_array)
        small = utilization_percent(10, report)
        large = utilization_percent(1000, report)
        assert large > small
