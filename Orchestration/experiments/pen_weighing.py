"""Weigh the materials of a condition table with the two Formulator Pens.

    python experiments/pen_weighing.py experiments/conditions/example.csv

The condition table has one row per dispense: ``position`` (a tube position,
e.g. L4), ``material``, and ``target_g``. The Pen holding each material is
read from the node's state, so the table never names a Pen. The rows are
grouped by material in order of first appearance, and one workflow is built
(a move is added only when the tube position changes):

    for each material: pickup_tool -> (move_to_position -> dispense) per row -> return_tool
    home

Workflows have no loop syntax, so the step list is generated from the table.
The generated definition, the table, and the workflow ID are written to
``data/runs/<timestamp>/``; the measured masses stay in the MADSci managers
and are collected by ``analysis/export_results.py``.
"""

import csv
import json
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_NAME = "pen_weighing"
NODE = "formulator_pen_weighing_node"


def read_conditions(path: Path) -> list[dict]:
    """Read and check the condition table."""
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError(f"{path} has no rows")
    conditions = []
    for number, row in enumerate(rows, start=2):
        try:
            target = float(row["target_g"])
            position, material = row["position"].strip(), row["material"].strip()
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise ValueError(f"{path}:{number}: needs position, material, and numeric target_g") from exc
        if not position or not material or target <= 0:
            raise ValueError(f"{path}:{number}: position and material are required and target_g must be > 0")
        conditions.append({"position": position, "material": material, "target_g": target})
    return conditions


def build_workflow(conditions: list[dict], loaded_materials: dict[str, str]) -> dict:
    """Build the workflow definition for a condition table.

    ``loaded_materials`` maps each Pen to the material it holds (node state).
    """
    pen_of = {}
    for pen, material in loaded_materials.items():
        if material in pen_of:
            raise ValueError(f"{material!r} is loaded in both {pen_of[material]} and {pen}")
        pen_of[material] = pen
    missing = sorted({row["material"] for row in conditions} - set(pen_of))
    if missing:
        raise ValueError(f"No Pen holds {missing}; loaded: {loaded_materials}")

    steps = []
    for material in dict.fromkeys(row["material"] for row in conditions):
        pen = pen_of[material]
        steps.append({"name": f"Pick up {pen} ({material})", "node": NODE,
                      "action": "pickup_tool", "args": {"tool": pen}})
        position = None
        for row in (r for r in conditions if r["material"] == material):
            # Consecutive dispenses into the same tube stay put; each one tares first.
            if row["position"] != position:
                position = row["position"]
                steps.append({"name": f"Move {pen} to {position}", "node": NODE,
                              "action": "move_to_position", "args": {"position": position}})
            steps.append({"name": f"Dispense {row['target_g']:g} g {material} at {row['position']}",
                          "node": NODE, "action": "dispense",
                          "args": {"material": material, "target_g": row["target_g"], "position": row["position"]}})
        steps.append({"name": f"Return {pen}", "node": NODE,
                      "action": "return_tool", "args": {"tool": pen}})
    steps.append({"name": "Home gantry", "node": NODE, "action": "home", "args": {}})
    for index, step in enumerate(steps, start=1):
        step["key"] = f"step_{index:02d}"
    return {
        "name": WORKFLOW_NAME,
        "metadata": {"description": "Generated from a condition table by experiments/pen_weighing.py"},
        "steps": steps,
    }


def main(conditions_path: str) -> dict:
    from madsci.common.types.experiment_types import ExperimentDesign
    from madsci.common.types.workflow_types import WorkflowDefinition
    from madsci.experiment_application.experiment_script import ExperimentScript

    class PenWeighing(ExperimentScript):
        experiment_design = ExperimentDesign(
            experiment_name="Formulator Pen weighing",
            experiment_description="Two Formulator Pens with different materials, switched by the tool changer.",
        )

        def run_experiment(self, path: str) -> dict:
            conditions = read_conditions(Path(path))
            loaded = self.workcell_client.get_node(NODE).state.get("loaded_materials") or {}
            definition = build_workflow(conditions, loaded)
            run_dir = ROOT / "data" / "runs" / time.strftime("%Y%m%d_%H%M%S")
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "conditions.csv").write_bytes(Path(path).read_bytes())
            (run_dir / f"{WORKFLOW_NAME}.workflow.yaml").write_text(
                yaml.safe_dump(definition, sort_keys=False), encoding="utf-8"
            )
            workflow = self.workcell_client.start_workflow(
                workflow_definition=WorkflowDefinition.model_validate(definition),
                await_completion=True,
                prompt_on_error=False,
                raise_on_failed=False,
            )
            record = {
                "experiment_id": getattr(getattr(self, "experiment", None), "experiment_id", None),
                "workflow_id": workflow.workflow_id,
                "loaded_materials": loaded,
                "conditions": conditions,
            }
            (run_dir / "run.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
            if not workflow.status.completed:
                # Ends the experiment as failed; the run directory is kept for export.
                raise RuntimeError(f"Workflow {workflow.workflow_id} did not complete ({run_dir})")
            return {"run_dir": str(run_dir), "workflow_id": workflow.workflow_id}

    return PenWeighing().run(path=conditions_path)


if __name__ == "__main__":
    print(main(sys.argv[1]))
