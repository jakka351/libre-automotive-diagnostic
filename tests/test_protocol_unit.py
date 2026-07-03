"""Protocol-layer unit tests — no hardware, run on any platform (incl. Windows CI).

These drive the OBD-II helpers through :class:`FakeTransport`, so they verify the
parsing/decoding logic without needing SocketCAN. The end-to-end SocketCAN path is
covered separately in ``test_socketcan_vin.py`` (Linux only).
"""
from __future__ import annotations

import pytest

from protocol.dtc import decode_dtc, encode_dtc
from protocol.obd2 import (
    read_coolant_temp,
    read_dtcs,
    read_engine_rpm,
    read_vehicle_speed,
    read_vin,
)
from transport.fake import FakeTransport


# --------------------------------------------------------------------------- #
#  DTC codec
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "code, wire",
    [
        ("P0301", b"\x03\x01"),
        ("P0420", b"\x04\x20"),
        ("P1234", b"\x12\x34"),
        ("C1234", b"\x52\x34"),
        ("B0001", b"\x80\x01"),
        ("U0100", b"\xc1\x00"),
    ],
)
def test_dtc_encode_matches_wire(code, wire):
    assert encode_dtc(code) == wire


@pytest.mark.parametrize(
    "code", ["P0301", "P0420", "P1234", "C1234", "B0001", "U0100", "P0000"]
)
def test_dtc_roundtrip(code):
    hi, lo = encode_dtc(code)
    assert decode_dtc(hi, lo) == code


# --------------------------------------------------------------------------- #
#  Mode 09 VIN
# --------------------------------------------------------------------------- #
def test_read_vin():
    vin = "1HGCM82633A004352"
    responder = {bytes([0x09, 0x02]): bytes([0x49, 0x02, 0x01]) + vin.encode()}
    with FakeTransport(responder) as t:
        assert read_vin(t) == vin


def test_read_vin_no_response():
    with FakeTransport({}) as t:
        assert read_vin(t) is None


# --------------------------------------------------------------------------- #
#  Mode 03 DTCs
# --------------------------------------------------------------------------- #
def test_read_dtcs():
    body = bytes([0x43, 0x02]) + encode_dtc("P0301") + encode_dtc("P0420")
    with FakeTransport({bytes([0x03]): body}) as t:
        assert read_dtcs(t) == ["P0301", "P0420"]


def test_read_dtcs_none_stored():
    with FakeTransport({bytes([0x03]): bytes([0x43, 0x00])}) as t:
        assert read_dtcs(t) == []


# --------------------------------------------------------------------------- #
#  Mode 01 live PIDs
# --------------------------------------------------------------------------- #
def test_read_engine_rpm():
    with FakeTransport({bytes([0x01, 0x0C]): bytes([0x41, 0x0C, 0x1A, 0xF8])}) as t:
        assert read_engine_rpm(t) == 1726.0


def test_read_vehicle_speed():
    with FakeTransport({bytes([0x01, 0x0D]): bytes([0x41, 0x0D, 0x50])}) as t:
        assert read_vehicle_speed(t) == 80


def test_read_coolant_temp():
    with FakeTransport({bytes([0x01, 0x05]): bytes([0x41, 0x05, 0x5A])}) as t:
        assert read_coolant_temp(t) == 50
