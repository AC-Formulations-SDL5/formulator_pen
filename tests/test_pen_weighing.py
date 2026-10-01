"""The workflow generated from a condition table."""

from pathlib import Path

import pytest
from madsci.common.types.workflow_types import WorkflowDefinition

from experiments.pen_weighing import build_workflow, read_conditions

ROOT = Path(__file__).resolve().parents[1]
LOADED = {"formulator_pen_1": "Bluesilv12", "formulator_pen_2": "Siltech60"}
NODE = "formulator_pen_weighing_node"


def calls(definition):
    return [(s["node"], s["action"], s["args"]) for s in definition["steps"]]


def test_rows_are_grouped_by_material_with_one_tool_change_each():
    conditions = [
        {"position": "L4", "material": "Bluesilv12", "target_g": 1.0},
        {"position": "L5", "material": "Siltech60", "target_g": 0.3},
        {"position": "L6", "material": "Bluesilv12", "target_g": 0.5},
    ]
    definition = build_workflow(conditions, LOADED)
    WorkflowDefinition.model_validate(definition)
    assert calls(definition) == [
        (NODE, "pickup_tool", {"tool": "formulator_pen_1"}),
        (NODE, "move_to_position", {"position": "L4"}),
        (NODE, "dispense", {"material": "Bluesilv12", "target_g": 1.0, "position": "L4"}),
        (NODE, "move_to_position", {"position": "L6"}),
        (NODE, "dispense", {"material": "Bluesilv12", "target_g": 0.5, "position": "L6"}),
        (NODE, "return_tool", {"tool": "formulator_pen_1"}),
        (NODE, "pickup_tool", {"tool": "formulator_pen_2"}),
        (NODE, "move_to_position", {"position": "L5"}),
        (NODE, "dispense", {"material": "Siltech60", "target_g": 0.3, "position": "L5"}),
        (NODE, "return_tool", {"tool": "formulator_pen_2"}),
        (NODE, "home", {}),
    ]


def test_a_material_in_no_pen_or_in_both_pens_is_refused():
    with pytest.raises(ValueError, match="No Pen holds"):
        build_workflow([{"position": "L4", "material": "Water", "target_g": 1.0}], LOADED)
    with pytest.raises(ValueError, match="loaded in both"):
        build_workflow([], {"formulator_pen_1": "Water", "formulator_pen_2": "Water"})


def test_example_table_and_checked_in_example_workflow_agree():
    import yaml

    generated = build_workflow(read_conditions(ROOT / "experiments/conditions/example.csv"), LOADED)
    checked_in = yaml.safe_load((ROOT / "workflows/pen_weighing.example.workflow.yaml").read_text(encoding="utf-8"))
    assert generated == checked_in


def test_bad_rows_are_refused(tmp_path):
    table = tmp_path / "bad.csv"
    table.write_text("position,material,target_g\nL4,Bluesilv12,-1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="must be > 0"):
        read_conditions(table)


def test_consecutive_dispenses_into_one_tube_move_once():
    conditions = [
        {"position": "L4", "material": "Bluesilv12", "target_g": 1.0},
        {"position": "L4", "material": "Bluesilv12", "target_g": 1.0},
    ]
    assert [c[1] for c in calls(build_workflow(conditions, LOADED))] == [
        "pickup_tool", "move_to_position", "dispense", "dispense", "return_tool", "home",
    ]
