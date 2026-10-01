"""The Pen-side execution script and how the SSH wrapper reads its output."""

import json

import pytest

from devices.formulator_pen_ssh import PenJobError, parse_result
from formulator_pen import run_job


def test_commands_map_to_integrated_dispenser_jobs():
    args = run_job.parser().parse_args(["dispense", "--pen", "formulator_pen_1", "--volume", "1.0", "--location", "L4"])
    assert run_job.job_arguments(args) == {"volume_ml": 1.0, "location": "L4", "action": "DISPENSE"}
    args = run_job.parser().parse_args(["fill", "--pen", "formulator_pen_2", "--volume", "5"])
    assert run_job.job_arguments(args) == {"volume_ml": 5.0, "action": "FILL"}
    args = run_job.parser().parse_args(["prime", "--pen", "formulator_pen_2", "--cycles", "2"])
    assert run_job.job_arguments(args) == {"operation_mode": "PRIMING", "cycles": 2}


def test_loaded_materials_needs_no_hardware(tmp_path, capsys):
    config = tmp_path / "pen_config.yaml"
    config.write_text(
        "pens:\n"
        "  formulator_pen_1: {host: x, material: Bluesilv12, fluid_profile: BLUESILV12}\n"
        "  formulator_pen_2: {host: y, material: Siltech60, fluid_profile: SILTECH60}\n",
        encoding="utf-8",
    )
    assert run_job.main(["--config", str(config), "loaded-materials"]) == 0
    record = parse_result(capsys.readouterr().out)
    assert record == {"formulator_pen_1": "Bluesilv12", "formulator_pen_2": "Siltech60"}


def test_an_unknown_fluid_profile_is_reported_as_a_failed_result(tmp_path, capsys):
    config = tmp_path / "pen_config.yaml"
    config.write_text("pens:\n  formulator_pen_1: {host: x, material: M, fluid_profile: NOPE}\n", encoding="utf-8")
    assert run_job.main(["--config", str(config), "loaded-materials"]) == 1
    assert "unknown fluid profile" in parse_result(capsys.readouterr().out)["error"]


def test_the_result_is_the_last_marked_line_after_the_job_log():
    output = "[DISPENSE] lots of log\n" + run_job.RESULT_MARKER + json.dumps({"actual_weight_g": 1.01}) + "\n"
    assert parse_result(output) == {"actual_weight_g": 1.01}
    with pytest.raises(PenJobError):
        parse_result("no result here\n")


def test_draw_and_dispense_is_a_both_job():
    args = run_job.parser().parse_args(["draw-and-dispense", "--pen", "formulator_pen_1", "--volume", "1.0"])
    assert run_job.job_arguments(args) == {"volume_ml": 1.0, "location": None, "action": "BOTH"}
