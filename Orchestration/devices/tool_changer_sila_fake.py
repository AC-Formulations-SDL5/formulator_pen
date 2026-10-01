"""Fake interface for ToolChangerSila. Same API, no network access."""

import logging
import random
import time
from typing import Optional


class ToolChangerSilaFake:
    """Fake tool changer: lock/unlock always succeed after a short delay."""

    def __init__(
        self,
        host: str,
        sila_port: int = 50054,
        insecure: bool = True,
        latency: float = 0.1,
        failure_rate: float = 0.0,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self._logger = logger or logging.getLogger(__name__)
        self._latency = latency
        self._failure_rate = failure_rate
        self.is_locked: bool = False
        self.status: str = "connected"
        self._logger.info(f"ToolChangerSilaFake initialized (would be {host}:{sila_port})")

    def _maybe_fail(self) -> None:
        if random.random() < self._failure_rate:
            raise Exception("ToolChangerSilaFake: simulated failure")

    def lock(self) -> bool:
        """Rotate to the LOCK side until the limit switch engages."""
        self._maybe_fail()
        time.sleep(5.0 * self._latency)
        self.is_locked = True
        return True

    def unlock(self) -> bool:
        """Rotate to the UNLOCK side until the limit switch engages."""
        self._maybe_fail()
        time.sleep(5.0 * self._latency)
        self.is_locked = False
        return True

    def check_status(self) -> None:
        """No-op for fake interface; status is always connected."""

    def close(self) -> None:
        """Drop the (simulated) client."""
        self.status = "disconnected"
