"""Fake interface for XyzGantrySila. Same API, no network access."""

import logging
import random
import time
from typing import Optional


class XyzGantrySilaFake:
    """Fake gantry: instant moves scaled by latency, no SiLA connection."""

    def __init__(
        self,
        host: str,
        sila_port: int = 50053,
        insecure: bool = True,
        latency: float = 0.1,
        failure_rate: float = 0.0,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self._logger = logger or logging.getLogger(__name__)
        self._latency = latency
        self._failure_rate = failure_rate
        self.current_position: dict[str, float] = {"x": 0.0, "y": 0.0, "z": 0.0}
        self.status: str = "connected"
        self._logger.info(f"XyzGantrySilaFake initialized (would be {host}:{sila_port})")

    def _maybe_fail(self) -> None:
        if random.random() < self._failure_rate:
            raise Exception("XyzGantrySilaFake: simulated failure")

    def move_to(self, x: float, y: float, z: float, speed: float) -> None:
        """Move the gantry to the given XYZ coordinates (mm) at `speed` (mm/min).

        The fake ignores `speed`; the real interface passes it to MoveTo."""
        self._maybe_fail()
        time.sleep(2.0 * self._latency)
        self.current_position = {"x": x, "y": y, "z": z}

    def return_home(self) -> None:
        """Return to origin (0,0,0) with the safe staged sequence (Z, X, Y)."""
        self._maybe_fail()
        time.sleep(3.0 * self._latency)
        self.current_position = {"x": 0.0, "y": 0.0, "z": 0.0}

    def homing(self) -> None:
        """Establish the machine origin using hardware limit switches."""
        self._maybe_fail()
        time.sleep(5.0 * self._latency)
        self.current_position = {"x": 0.0, "y": 0.0, "z": 0.0}

    def check_status(self) -> None:
        """No-op for fake interface; status is always connected."""

    def close(self) -> None:
        """Drop the (simulated) client."""
        self.status = "disconnected"
