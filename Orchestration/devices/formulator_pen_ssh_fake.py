"""Fake FormulatorPenSsh: runs the run_job logic in-process on fake devices.

The fake Pens and balance live as long as this object, so a fill carries over
to the next dispense exactly as it does on a real Pen. Each fake Pen starts
filled with FAKE_INITIAL_FILL_ML, as the real Pens are filled before a run.

The Pens hold the materials of Programming/formulator_pen/pen_config.yaml once it is filled
in; until then they hold the materials of EXAMPLE_PEN_CONFIG, the two silicone
oils of the reported validation run.
"""

import logging
import tempfile
from pathlib import Path
from typing import Optional

from devices.formulator_pen_fake import FakeBalance, FakeFormulatorDriver
from devices.formulator_pen_ssh import PenJobError, failure_message
from formulator_pen import run_job

FAKE_INITIAL_FILL_ML = 5.0
EXAMPLE_PEN_CONFIG = {
    "pens": {
        "formulator_pen_1": {"formulator_id": "formulator_pen_1", "material": "Bluesilv12", "fluid_profile": "BLUESILV12"},
        "formulator_pen_2": {"formulator_id": "formulator_pen_2", "material": "Siltech60", "fluid_profile": "SILTECH60"},
    },
}


def fake_pen_config() -> dict:
    """Programming/formulator_pen/pen_config.yaml if it is filled in, otherwise EXAMPLE_PEN_CONFIG."""
    try:
        return run_job.load_config(run_job.DEFAULT_CONFIG)
    except ValueError:
        return EXAMPLE_PEN_CONFIG


class FormulatorPenSshFake:
    """Same commands as FormulatorPenSsh, without SSH or hardware."""

    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        port: int = 22,
        remote_dir: str = "formulator_pen/Programming",
        python: str = "python3",
        command_timeout_s: float = 3600.0,
        pen_config: Optional[dict] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self._config = pen_config or fake_pen_config()
        self._results_path = Path(tempfile.mkdtemp(prefix="fake_pen_")) / "dispense_results.xlsx"
        self._balance = FakeBalance(serial_port="fake", balance_id="balance")
        self._pens = {}
        for pen, entry in self._config["pens"].items():
            driver = FakeFormulatorDriver(host=f"fake-{pen}", formulator_id=entry.get("formulator_id", pen))
            driver.balance = self._balance
            driver.preload(FAKE_INITIAL_FILL_ML)
            self._pens[pen] = driver
        self.status = "connected"
        self.reachable = True

    def _job(self, pen: str, **job_args) -> dict:
        if pen not in self._pens:
            raise PenJobError(f"KeyError: {pen!r}", {"error": f"KeyError: {pen!r}"})
        try:
            record = run_job.execute(self._pens[pen], self._balance, pen, self._config["pens"][pen],
                                     self._results_path, **job_args)
        except Exception as error:
            record = {"error": f"{type(error).__name__}: {error}"}
            raise PenJobError(record["error"], record) from error
        if not run_job.job_succeeded(record):
            raise PenJobError(failure_message(record), record)
        return record

    def dispense(self, pen: str, volume_ml: float, location: str = "") -> dict:
        return self._job(pen, volume_ml=volume_ml, location=location or None, action="DISPENSE")

    def draw_and_dispense(self, pen: str, volume_ml: float, location: str = "") -> dict:
        return self._job(pen, volume_ml=volume_ml, location=location or None, action="BOTH")

    def fill(self, pen: str, volume_ml: float) -> dict:
        return self._job(pen, volume_ml=volume_ml, action="FILL")

    def prime(self, pen: str, cycles: int = 1) -> dict:
        return self._job(pen, operation_mode="PRIMING", cycles=cycles)

    def read_weight(self, settle_time_s: float = 5.0) -> float:
        return self._balance.read_weight(settle_time=settle_time_s)

    def loaded_materials(self) -> dict[str, str]:
        return {pen: entry["material"] for pen, entry in self._config["pens"].items()}

    def check_status(self) -> None:
        """Always reachable."""

    def close(self) -> None:
        """Nothing to close."""
