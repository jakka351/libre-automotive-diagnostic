"""OBD-II (SAE J1979) and UDS (ISO 14229) protocol layer.

Sits on top of a transport backend and speaks in vehicle terms
(``read_vin``, ``read_dtcs``, ...) rather than CAN frames.
"""
