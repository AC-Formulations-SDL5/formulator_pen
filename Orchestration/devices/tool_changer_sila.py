"""SiLA client wrapper for the tool changer (Pololu Tic T500, USB).

Wraps the ToolChanger feature of the tool changer's SiLA 2 server on the
cell-side Raspberry Pi 5. The device-side Close SiLA command is not called
from the node lifecycle; the server owns the USB connection.
"""

import logging
from typing import Optional

from sila2.client import SilaClient


class ToolChangerSila:
    """Client for the tool changer (port 50054)."""

    def __init__(
        self,
        host: str,
        sila_port: int = 50054,
        insecure: bool = True,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self._logger = logger or logging.getLogger(__name__)
        self._client = SilaClient(host, sila_port, insecure=insecure)
        self.is_locked: bool = False
        self.status: str = "connected"
        self.reachable: bool = False
        self._logger.info(f"ToolChangerSila connected to {host}:{sila_port}")

    def lock(self) -> bool:
        """Rotate to the LOCK side until the limit switch engages.

        Returns True on success, raises on timeout (so failures can't be
        silently ignored mid-sequence).
        """
        success = bool(self._client.ToolChanger.Lock().Success)
        if not success:
            raise Exception("ToolChanger lock timed out before the limit switch engaged")
        self.is_locked = True
        return success

    def unlock(self) -> bool:
        """Rotate to the UNLOCK side until the limit switch engages, then deenergize.

        Returns True on success, raises on timeout.
        """
        success = bool(self._client.ToolChanger.Unlock().Success)
        if not success:
            raise Exception("ToolChanger unlock timed out before the limit switch engaged")
        self.is_locked = False
        return success

    def check_status(self) -> None:
        """Refresh the device status and whether its SiLA server is reachable."""
        try:
            self.status = str(self._client.ToolChanger.Status.get())
        except Exception:
            self.reachable = False
            self.status = "disconnected"
            return
        self.reachable = True
        try:
            self.is_locked = bool(self._client.ToolChanger.IsLocked.get())
        except Exception:
            pass

    def close(self) -> None:
        """Drop the gRPC client. Does not close the device-side USB connection."""
        try:
            self._client.close()
        except Exception:
            pass
        self.status = "disconnected"
        self.reachable = False
        self._logger.info("ToolChangerSila client closed")
