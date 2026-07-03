"""OBD-II (SAE J1979) and UDS (ISO 14229) protocol layer.

Sits on top of a transport backend and speaks in vehicle terms:

    from protocol.obd2 import J1979          # all 10 OBD-II modes
    from protocol.uds import UDSClient        # full ISO 14229 service set
    from protocol.dtc_library import describe  # DTC definitions
"""
from . import dtc, dtc_library, obd2, pids, uds  # noqa: F401

__all__ = ["dtc", "dtc_library", "obd2", "pids", "uds"]
