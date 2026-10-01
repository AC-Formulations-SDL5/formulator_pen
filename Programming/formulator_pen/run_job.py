"""Run one Formulator Pen job on the Pen-side Raspberry Pi 5 and print its record.

This is the execution script: it connects to the selected Pen's Pico W over
WiFi and to the balance over USB serial, runs one ``IntegratedDispenser`` job,
prints the job record, and exits. The MADSci node on the lab PC starts it over
SSH once per command.

    python -m formulator_pen.run_job dispense --pen formulator_pen_1 --volume 1.0 --location L4
    python -m formulator_pen.run_job draw-and-dispense --pen formulator_pen_1 --volume 1.0 --location L4
    python -m formulator_pen.run_job fill --pen formulator_pen_1 --volume 5.0
    python -m formulator_pen.run_job prime --pen formulator_pen_1 --cycles 2
    python -m formulator_pen.run_job read-weight --settle 5
    python -m formulator_pen.run_job loaded-materials

Which material each Pen holds and the fluid profile it is dispensed with are
set in ``Programming/formulator_pen/pen_config.yaml``. The last line of the output is
``RESULT_JSON: <record>``; the exit code is 0 only when the job completed.
"""

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

import yaml

from .dispense_system import (
    FLUID_PROFILES,
    DispenseJob,
    IntegratedDispenser,
    reconnect_formulator_after_reset,
    sync_all_fluid_profiles,
)

RESULT_MARKER = "RESULT_JSON: "
DEFAULT_CONFIG = Path(__file__).with_name("pen_config.yaml")


def load_config(path: Path) -> dict:
    config = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    for pen, entry in config["pens"].items():
        if str(entry["fluid_profile"]).strip().upper() not in FLUID_PROFILES:
            raise ValueError(f"{pen}: unknown fluid profile {entry['fluid_profile']!r}")
    return config


def connect(formulator) -> None:
    """Open the Pico link and push every fluid profile, resetting the Pico once on failure."""
    formulator.open()
    if sync_all_fluid_profiles(formulator):
        return
    formulator.reset()
    if not asyncio.run(reconnect_formulator_after_reset(formulator)):
        raise RuntimeError("Formulator did not come back online after reset")
    if not sync_all_fluid_profiles(formulator):
        raise RuntimeError("Fluid profile sync failed after reset")


def execute(formulator, balance, pen: str, pen_config: dict, results_path: Path, **job_args) -> dict:
    """Run one IntegratedDispenser job on connected devices and return its record."""
    results_path.parent.mkdir(parents=True, exist_ok=True)
    dispenser = IntegratedDispenser(formulator, balance, results_path=results_path)
    job = DispenseJob(fluid_profile=pen_config["fluid_profile"], **job_args)
    # Wait out the Pico's duty-cycle cooldown before the job.
    while not formulator.is_ready():
        time.sleep(formulator.get_cooldown_time() + 1)
    asyncio.run(dispenser._execute_dispense(job))
    return {"pen": pen, "material": pen_config["material"], **dispenser.result_row(job)}


def job_succeeded(record: dict) -> bool:
    return record.get("status") == "COMPLETED" and record.get("dispense_status") == "OK"


def run(args, config: dict) -> dict:
    """Connect the real devices for one command, run it, and disconnect."""
    from .balance_api import Balance
    from .formulator_driver import FormulatorDriver

    if args.command == "loaded-materials":
        return {pen: entry["material"] for pen, entry in config["pens"].items()}

    balance = Balance(balance_id="balance", **config["balance"])
    balance.open()
    try:
        if args.command == "read-weight":
            return {"weight_g": balance.read_weight(settle_time=args.settle)}
        pen_config = config["pens"][args.pen]
        formulator = FormulatorDriver(
            host=pen_config["host"],
            port=pen_config.get("port", 8888),
            pump_timeout_s=config.get("pump_timeout_s", 2000.0),
            formulator_id=pen_config.get("formulator_id", args.pen),
        )
        connect(formulator)
        try:
            return execute(formulator, balance, args.pen, pen_config, Path(config["results_path"]),
                           **job_arguments(args))
        finally:
            formulator.close()
    finally:
        balance.close()


def job_arguments(args) -> dict:
    """DispenseJob arguments for a job command."""
    if args.command == "dispense":
        return {"volume_ml": args.volume, "location": args.location, "action": "DISPENSE"}
    if args.command == "draw-and-dispense":
        return {"volume_ml": args.volume, "location": args.location, "action": "BOTH"}
    if args.command == "fill":
        return {"volume_ml": args.volume, "action": "FILL"}
    if args.command == "prime":
        return {"operation_mode": "PRIMING", "cycles": args.cycles}
    raise ValueError(f"{args.command} is not a job command")


def parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one Formulator Pen job and print its record.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    commands = parser.add_subparsers(dest="command", required=True)
    dispense = commands.add_parser("dispense", help="dispense from what the Pen holds, then weigh")
    dispense.add_argument("--pen", required=True)
    dispense.add_argument("--volume", type=float, required=True,
                          help="target; the fluid profile is calibrated against weighed mass [g]")
    dispense.add_argument("--location", default=None)
    draw = commands.add_parser("draw-and-dispense", help="draw the target in, then dispense all of it and weigh")
    draw.add_argument("--pen", required=True)
    draw.add_argument("--volume", type=float, required=True,
                      help="target; the fluid profile is calibrated against weighed mass [g]")
    draw.add_argument("--location", default=None)
    fill = commands.add_parser("fill", help="draw into the Pen and hold it")
    fill.add_argument("--pen", required=True)
    fill.add_argument("--volume", type=float, required=True)
    prime = commands.add_parser("prime", help="priming purge cycles")
    prime.add_argument("--pen", required=True)
    prime.add_argument("--cycles", type=int, default=1)
    weight = commands.add_parser("read-weight", help="read the balance")
    weight.add_argument("--settle", type=float, default=5.0)
    commands.add_parser("loaded-materials", help="which material each Pen holds")
    return parser


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    try:
        record = run(args, load_config(Path(args.config)))
        ok = args.command not in ("dispense", "draw-and-dispense", "fill", "prime") or job_succeeded(record)
    except Exception as error:
        record, ok = {"error": f"{type(error).__name__}: {error}"}, False
    print(RESULT_MARKER + json.dumps(record, default=str))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
