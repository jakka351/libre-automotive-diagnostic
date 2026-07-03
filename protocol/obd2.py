"""SAE J1979 OBD-II service helpers, transport-neutral.

These functions work over *any* :class:`~transport.base.Transport` — SocketCAN,
ELM327, or the in-memory fake — because the transport already delivers a fully
reassembled service payload. No AT commands, no ASCII scraping, no assumption of
a single ECU: responses are aggregated across everything that answered.

Only the handful of services needed to prove the stack end-to-end live here for
now (VIN, stored DTCs, a couple of live PIDs). The full Mode 01 PID table and the
J1979 formula set (ported from the correct math in the old ``obd_formulas.c``)
land in Ticket 5.
"""
from __future__ import annotations

from transport.base import Transport

from .dtc import decode_dtc

# --------------------------------------------------------------------------- #
#  Mode 09 — Vehicle Information (VIN)
# --------------------------------------------------------------------------- #
def read_vin(transport: Transport, *, timeout: float = 2.0) -> str | None:
    """Read the VIN (Mode 09 PID 02). Returns the 17-char VIN or ``None``.

    The response spans multiple CAN frames; ISO-TP reassembly is the transport's
    job, so here we just parse the ``49 02 <count> <ascii...>`` payload.
    """
    for r in transport.request(bytes([0x09, 0x02]), timeout=timeout):
        vin = _parse_vin(r.data)
        if vin:
            return vin
    return None


def _parse_vin(data: bytes) -> str | None:
    if len(data) < 3 or data[0] != 0x49 or data[1] != 0x02:
        return None
    raw = data[3:]  # drop SID (0x49), PID (0x02), and the message-count byte
    text = bytes(b for b in raw if 0x20 <= b <= 0x7E).decode("ascii", "ignore").strip()
    return text or None


# --------------------------------------------------------------------------- #
#  Mode 03 — Stored DTCs
# --------------------------------------------------------------------------- #
def read_dtcs(transport: Transport, *, timeout: float = 1.0) -> list[str]:
    """Read stored DTCs (Mode 03), aggregated across all responding ECUs."""
    codes: list[str] = []
    for r in transport.request(bytes([0x03]), timeout=timeout):
        codes.extend(_parse_dtcs(r.data))
    return codes


def _parse_dtcs(data: bytes) -> list[str]:
    # Wire format (CAN): 43 <count> <hi lo> <hi lo> ...
    if len(data) < 2 or data[0] != 0x43:
        return []
    count = data[1]
    body = data[2:]
    usable = min(count * 2, len(body) - (len(body) % 2))
    out: list[str] = []
    for i in range(0, usable, 2):
        code = decode_dtc(body[i], body[i + 1])
        if code != "P0000":  # 0x0000 = "no DTC in this slot" padding
            out.append(code)
    return out


# --------------------------------------------------------------------------- #
#  Mode 01 — Live data (minimal set for the keystone; full table in Ticket 5)
# --------------------------------------------------------------------------- #
def read_engine_rpm(transport: Transport, *, timeout: float = 1.0) -> float | None:
    """PID 0x0C — engine RPM = ((256*A)+B)/4."""
    for r in transport.request(bytes([0x01, 0x0C]), timeout=timeout):
        d = r.data
        if len(d) >= 4 and d[0] == 0x41 and d[1] == 0x0C:
            return ((256 * d[2]) + d[3]) / 4.0
    return None


def read_vehicle_speed(transport: Transport, *, timeout: float = 1.0) -> int | None:
    """PID 0x0D — vehicle speed in km/h = A."""
    for r in transport.request(bytes([0x01, 0x0D]), timeout=timeout):
        d = r.data
        if len(d) >= 3 and d[0] == 0x41 and d[1] == 0x0D:
            return d[2]
    return None


def read_coolant_temp(transport: Transport, *, timeout: float = 1.0) -> int | None:
    """PID 0x05 — engine coolant temperature in degC = A - 40."""
    for r in transport.request(bytes([0x01, 0x05]), timeout=timeout):
        d = r.data
        if len(d) >= 3 and d[0] == 0x41 and d[1] == 0x05:
            return d[2] - 40
    return None
