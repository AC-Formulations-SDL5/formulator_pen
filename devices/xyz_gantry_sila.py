"""SiLA client wrapper for the XYZ gantry (GRBL).

Wraps the XyzGantry feature of the gantry's SiLA 2 server on the cell-side
Raspberry Pi 5. The device-side Close SiLA command is not called from the node
lifecycle; the server owns the serial connection.
"""

import logging
from typing import Optional

from sila2.client import SilaClient


class XyzGantrySila:
    """Client for the XYZ gantry (port 50053)."""

    def __init__(
        self,
        host: str,
        sila_port: int = 50053,
        insecure: bool = True,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self._logger = logger or logging.getLogger(__name__)
        self._client = SilaClient(host, sila_port, insecure=insecure)
        self.current_position: dict[str, float] = {"x": 0.0, "y": 0.0, "z": 0.0}
        self.status: str = "connected"
        self.reachable: bool = False
        self._logger.info(f"XyzGantrySila connected to {host}:{sila_port}")

    def move_to(self, x: float, y: float, z: float, speed: float) -> None:
        """Move the gantry to the given XYZ coordinates (mm) at `speed` (mm/min).

        The caller (the node) owns the feed rate -- normal vs slow comes from
        gantry_params, not from the device."""
        self._client.XyzGantry.MoveTo(X=x, Y=y, Z=z, Speed=speed)
        self.current_position = {"x": x, "y": y, "z": z}

    def return_home(self) -> None:
        """Return to origin (0,0,0) with the safe staged sequence (Z, X, Y)."""
        self._client.XyzGantry.ReturnHome()
        self.current_position = {"x": 0.0, "y": 0.0, "z": 0.0}

    def homing(self) -> None:
        """Establish the machine origin using hardware limit switches."""
        self._client.XyzGantry.Homing()
        self.current_position = {"x": 0.0, "y": 0.0, "z": 0.0}

    def check_status(self) -> None:
        """Refresh the device status and whether its SiLA server is reachable."""
        try:
            self.status = str(self._client.XyzGantry.Status.get())
        except Exception:
            self.reachable = False
            self.status = "disconnected"
            return
        self.reachable = True
        try:
            pos = self._client.XyzGantry.CurrentPosition.get()
            self.current_position = {
                "x": float(pos.X),
                "y": float(pos.Y),
                "z": float(pos.Z),
            }
        except Exception:
            pass

    def close(self) -> None:
        """Drop the gRPC client. Does not close the device-side serial port."""
        try:
            self._client.close()
        except Exception:
            pass
        self.status = "disconnected"
        self.reachable = False
        self._logger.info("XyzGantrySila client closed")
