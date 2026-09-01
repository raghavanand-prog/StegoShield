"""Capacity calculation and reporting for a cover image."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.steganography import lsb_core, payload


@dataclass
class CapacityReport:
    width: int
    height: int
    channels: int
    total_capacity_bits: int
    total_capacity_bytes: int
    header_overhead_bytes: int
    max_message_bytes: int

    def as_dict(self) -> dict:
        return {
            "width": self.width,
            "height": self.height,
            "channels": self.channels,
            "total_capacity_bytes": self.total_capacity_bytes,
            "header_overhead_bytes": self.header_overhead_bytes,
            "max_message_bytes": self.max_message_bytes,
        }


def compute_capacity(image_array: np.ndarray) -> CapacityReport:
    channels = lsb_core.usable_channels(image_array)
    h, w = image_array.shape[0], image_array.shape[1]
    total_bits = lsb_core.capacity_bits(image_array)
    total_bytes = total_bits // 8
    overhead = payload.header_size()
    max_message = max(0, total_bytes - overhead)
    return CapacityReport(
        width=w,
        height=h,
        channels=channels,
        total_capacity_bits=total_bits,
        total_capacity_bytes=total_bytes,
        header_overhead_bytes=overhead,
        max_message_bytes=max_message,
    )


def utilization_percent(message_bytes: int, report: CapacityReport) -> float:
    if report.max_message_bytes == 0:
        return 0.0
    used = message_bytes + report.header_overhead_bytes
    return round(100.0 * used / report.total_capacity_bytes, 2)
