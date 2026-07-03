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
from .pids import PIDS, Value, decode_pid

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
#  Mode 01 — Live data (data-driven via the J1979 PID table in pids.py)
# --------------------------------------------------------------------------- #
def read_pid(transport: Transport, pid: int, *, timeout: float = 1.0) -> Value | None:
    """Read and decode a single Mode 01 PID, e.g. ``read_pid(t, 0x0C)`` -> RPM.

    Returns the decoded engineering value from the first ECU that answered with a
    well-formed positive response (``41 <pid> ...``), or ``None``.
    """
    for r in transport.request(bytes([0x01, pid]), timeout=timeout):
        d = r.data
        if len(d) >= 2 and d[0] == 0x41 and d[1] == pid:
            value = decode_pid(pid, d[2:])
            if value is not None:
                return value
    return None


def read_supported_pids(transport: Transport, *, timeout: float = 1.0) -> set[int]:
    """Discover supported Mode 01 PIDs by walking the 0x00/0x20/0x40/... bitmasks.

    Each support PID returns a 4-byte bitmask where the MSB of byte A is PID+1;
    the lowest bit signals whether the *next* range is also supported.
    """
    supported: set[int] = set()
    base = 0x00
    while base <= 0xE0:
        bitmap = None
        for r in transport.request(bytes([0x01, base]), timeout=timeout):
            d = r.data
            if len(d) >= 6 and d[0] == 0x41 and d[1] == base:
                bitmap = d[2:6]
                break
        if bitmap is None:
            break
        bits = int.from_bytes(bitmap, "big")
        for i in range(32):
            if bits & (1 << (31 - i)):
                supported.add(base + i + 1)
        # The last bit (PID base+0x20) advertises the next range.
        if not bits & 0x1:
            break
        base += 0x20
    return supported


def scan_live_data(transport: Transport, *, timeout: float = 1.0) -> dict[str, str]:
    """Read every supported, known PID and return ``{name: "value unit"}``."""
    out: dict[str, str] = {}
    for pid in sorted(read_supported_pids(transport, timeout=timeout)):
        spec = PIDS.get(pid)
        if spec is None:
            continue  # supported by the ECU but not in our decode table (yet)
        value = read_pid(transport, pid, timeout=timeout)
        if value is not None:
            shown = f"{value:.2f}".rstrip("0").rstrip(".") if isinstance(value, float) else str(value)
            out[spec.name] = f"{shown} {spec.unit}".strip()
    return out


# Named convenience wrappers (thin shims over the table for common readings).
def read_engine_rpm(transport: Transport, *, timeout: float = 1.0) -> Value | None:
    return read_pid(transport, 0x0C, timeout=timeout)


def read_vehicle_speed(transport: Transport, *, timeout: float = 1.0) -> Value | None:
    return read_pid(transport, 0x0D, timeout=timeout)


def read_coolant_temp(transport: Transport, *, timeout: float = 1.0) -> Value | None:
    return read_pid(transport, 0x05, timeout=timeout)
