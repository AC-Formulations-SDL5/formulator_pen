"""Formulator Pen commands over SSH to the Pen-side Raspberry Pi 5.

Each command starts ``Programming/formulator_pen/run_job.py`` on the Pen-side Pi, which
connects to the Pen's Pico W and the balance, runs one job, prints its record,
and exits. The record is parsed from the ``RESULT_JSON:`` line.
"""

import json
import logging
import shlex
import socket
from typing import Optional

RESULT_MARKER = "RESULT_JSON: "


class PenJobError(RuntimeError):
    """A job that did not complete; ``record`` holds what run_job reported."""

    def __init__(self, message: str, record: Optional[dict] = None) -> None:
        super().__init__(message)
        self.record = record or {}


def parse_result(output: str) -> dict:
    """The record printed on run_job's last RESULT_JSON line."""
    for line in reversed(output.splitlines()):
        if line.startswith(RESULT_MARKER):
            return json.loads(line[len(RESULT_MARKER):])
    raise PenJobError("run_job printed no result", {"output_tail": output[-2000:]})


def failure_message(record: dict) -> str:
    if record.get("error"):
        return record["error"]
    if record.get("dispense_status") not in (None, "OK"):
        return record["dispense_status"]
    return f"job status {record.get('status')}"


class FormulatorPenSsh:
    """Runs Formulator Pen jobs on the Pen-side Raspberry Pi 5 over SSH."""

    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        port: int = 22,
        remote_dir: str = "formulator_pen/Programming",
        python: str = "python3",
        command_timeout_s: float = 3600.0,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self._host, self._port = host, port
        self._username, self._password = username, password
        self._remote_dir, self._python = remote_dir, python
        self._timeout = command_timeout_s
        self._logger = logger or logging.getLogger(__name__)
        self.status = "connected"
        self.reachable = False

    def _run(self, *args: str) -> dict:
        import paramiko

        command = (
            f"cd {shlex.quote(self._remote_dir)} && "
            f"{self._python} -m formulator_pen.run_job {shlex.join(args)}"
        )
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(self._host, port=self._port, username=self._username,
                       password=self._password, timeout=10, allow_agent=False, look_for_keys=False)
        try:
            self._logger.info(f"run_job {' '.join(args)}")
            _, stdout, stderr = client.exec_command(command, timeout=self._timeout)
            output = stdout.read().decode("utf-8", errors="replace")
            exit_status = stdout.channel.recv_exit_status()
            errors = stderr.read().decode("utf-8", errors="replace")
        finally:
            client.close()
        record = parse_result(output + "\n" + errors)
        if exit_status != 0:
            raise PenJobError(failure_message(record), record)
        return record

    def dispense(self, pen: str, volume_ml: float, location: str = "") -> dict:
        """Tare, stroke out volume_ml from what the Pen holds, and weigh; returns the job record."""
        args = ["dispense", "--pen", pen, "--volume", repr(float(volume_ml))]
        return self._run(*args, *(["--location", location] if location else []))

    def draw_and_dispense(self, pen: str, volume_ml: float, location: str = "") -> dict:
        """Draw volume_ml in, tare, dispense all of it, and weigh; returns the job record."""
        args = ["draw-and-dispense", "--pen", pen, "--volume", repr(float(volume_ml))]
        return self._run(*args, *(["--location", location] if location else []))

    def fill(self, pen: str, volume_ml: float) -> dict:
        return self._run("fill", "--pen", pen, "--volume", repr(float(volume_ml)))

    def prime(self, pen: str, cycles: int = 1) -> dict:
        return self._run("prime", "--pen", pen, "--cycles", str(int(cycles)))

    def read_weight(self, settle_time_s: float = 5.0) -> float:
        return float(self._run("read-weight", "--settle", repr(float(settle_time_s)))["weight_g"])

    def loaded_materials(self) -> dict[str, str]:
        return self._run("loaded-materials")

    def check_status(self) -> None:
        """Whether the Pen-side Pi accepts SSH connections (no login)."""
        try:
            with socket.create_connection((self._host, self._port), timeout=3):
                self.reachable = True
                self.status = "connected"
        except OSError:
            self.reachable = False
            self.status = "disconnected"

    def close(self) -> None:
        """Nothing is held open between commands."""
