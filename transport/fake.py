"""In-memory transport for tests and hardware-free GUI development.

Runs on any platform (no CAN, no serial, no kernel modules). Feed it either a
mapping of request-bytes -> response-bytes, or a callable that returns a list of
:class:`EcuResponse`. Useful for unit-testing the protocol layer and for driving
the GUI on a laptop with no vehicle attached.
"""
from __future__ import annotations

from typing import Callable, Mapping, Union

from .base import EcuResponse, Transport, TransportError

# Either a lookup table {request_bytes: response_bytes} or a responder function.
Responder = Union[
    Mapping[bytes, bytes],
    Callable[[bytes], "list[EcuResponse]"],
]


class FakeTransport(Transport):
    """A Transport backed by a dict or a function instead of hardware.

    Args:
        responder: a ``{request: response_data}`` mapping (each reply is treated
            as coming from ECU ``0x7E8``), or a callable ``req -> [EcuResponse]``.
    """

    def __init__(self, responder: Responder):
        self._responder = responder
        self._open = False

    def open(self) -> None:
        self._open = True

    def close(self) -> None:
        self._open = False

    def request(
        self,
        payload: bytes,
        *,
        functional: bool = True,
        timeout: float = 1.0,
    ) -> list[EcuResponse]:
        if not self._open:
            raise TransportError("transport not open — call open() first")

        payload = bytes(payload)
        if callable(self._responder):
            return list(self._responder(payload))

        data = self._responder.get(payload)
        return [EcuResponse(0x7E8, data)] if data is not None else []
