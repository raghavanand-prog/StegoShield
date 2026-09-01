"""Payload framing: MAGIC + VERSION + LENGTH + CHECKSUM + DATA.

Wire format (all integers big-endian / network byte order)::

    +----------+-----------+----------------+------------------+-------------------+
    | MAGIC    | VERSION   | PAYLOAD_LENGTH | SHA-256 CHECKSUM | PAYLOAD (message) |
    | 4 bytes  | 1 byte    | 4 bytes        | 32 bytes         | N bytes            |
    | b"STG1"  | 0x01      | uint32         | of PAYLOAD only  |                    |
    +----------+-----------+----------------+------------------+-------------------+

The MAGIC value lets the decoder cheaply distinguish "this image was
produced by StegoShield" from an arbitrary image (whose LSBs are
effectively random noise and would only match the magic by a 1-in-2^32
chance). VERSION allows the wire format to evolve without breaking
older stego-images. The checksum lets us detect corruption or
tampering (e.g. re-saving the PNG through an editor, or lossy
recompression) independently of whatever length field is present,
which is important because a corrupted length field could otherwise
cause the decoder to read garbage.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

from app.config import Config
from app.steganography.bitstream import bytes_to_int, int_to_bytes
from app.steganography.exceptions import IntegrityVerificationError, NoHiddenDataError


@dataclass
class ParsedPayload:
    version: int
    length: int
    checksum: bytes
    data: bytes


def build_payload(message: bytes) -> bytes:
    """Wrap a raw message in the MAGIC/VERSION/LENGTH/CHECKSUM header."""
    checksum = hashlib.sha256(message).digest()
    header = (
        Config.MAGIC
        + int_to_bytes(Config.VERSION, Config.HEADER_VERSION_LEN)
        + int_to_bytes(len(message), Config.HEADER_LENGTH_LEN)
        + checksum
    )
    return header + message


def header_size() -> int:
    return Config.HEADER_TOTAL_LEN


def parse_header(header_bytes: bytes) -> tuple[int, int, bytes]:
    """Parse the fixed-size header. Returns (version, length, checksum).

    Raises NoHiddenDataError if the magic bytes don't match - this is
    the expected outcome for any image that was never encoded with
    StegoShield, and must NOT be treated as an integrity failure.
    """
    if len(header_bytes) < Config.HEADER_TOTAL_LEN:
        raise NoHiddenDataError("Image is too small to contain a valid payload header.")

    offset = 0
    magic = header_bytes[offset : offset + Config.HEADER_MAGIC_LEN]
    offset += Config.HEADER_MAGIC_LEN
    if magic != Config.MAGIC:
        raise NoHiddenDataError(
            "No StegoShield payload detected in this image (magic header mismatch)."
        )

    version = header_bytes[offset]
    offset += Config.HEADER_VERSION_LEN

    length_bytes = header_bytes[offset : offset + Config.HEADER_LENGTH_LEN]
    offset += Config.HEADER_LENGTH_LEN
    length = bytes_to_int(length_bytes)

    checksum = header_bytes[offset : offset + Config.HEADER_CHECKSUM_LEN]

    if length < 0 or length > Config.MAX_MESSAGE_BYTES:
        raise NoHiddenDataError(
            "Payload length field is out of a plausible range; this image likely "
            "does not contain a StegoShield payload."
        )

    return version, length, checksum


def verify_and_extract(version: int, length: int, checksum: bytes, data: bytes) -> bytes:
    """Verify the SHA-256 checksum of `data` against the header's checksum.

    Raises IntegrityVerificationError on mismatch. Returns `data` unchanged
    on success.
    """
    if len(data) != length:
        raise IntegrityVerificationError(
            "Payload detected but its declared length does not match the "
            "recovered data. The image may be corrupted or modified."
        )
    actual_checksum = hashlib.sha256(data).digest()
    if actual_checksum != checksum:
        raise IntegrityVerificationError(
            "Payload detected but integrity verification failed (checksum "
            "mismatch). The image may be corrupted or modified."
        )
    return data
