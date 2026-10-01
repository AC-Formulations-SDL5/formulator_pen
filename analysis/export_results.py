"""Collect the dispense records of one run into a CSV.

    python analysis/export_results.py data/runs/<timestamp>

Reads ``run.json`` written by ``experiments/pen_weighing.py``, fetches the
workflow from the Workcell Manager, and resolves every dispense step's result
datapoint from the Data Manager. Writes ``results.csv`` next to ``run.json``,
one row per dispense, with the step's start and end time.
"""

import csv
import json
import sys
from pathlib import Path

from madsci.client.data_client import DataClient
from madsci.client.workcell_client import WorkcellClient

WORKCELL_URL = "http://localhost:8005"
DATA_URL = "http://localhost:8004"


def datapoint_ids(value) -> list[str]:
    """Flatten the nested datapoint-ID mapping of a step result."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [item for child in value.values() for item in datapoint_ids(child)]
    if isinstance(value, list):
        return [item for child in value for item in datapoint_ids(child)]
    return []


def as_dict(model) -> dict:
    return model.model_dump(mode="json") if hasattr(model, "model_dump") else dict(model)


def export(run_dir: Path) -> Path:
    record = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    workcell = WorkcellClient(workcell_server_url=WORKCELL_URL)
    data = DataClient(data_server_url=DATA_URL)
    workflow = as_dict(workcell.query_workflow(record["workflow_id"]))
    rows = []
    for step in workflow.get("steps") or []:
        if step.get("action") != "dispense":
            continue
        result = step.get("result") or {}
        for datapoint_id in dict.fromkeys(datapoint_ids(result.get("datapoints") or {})):
            value = data.get_datapoint_value(datapoint_id)
            if isinstance(value, dict):
                rows.append({
                    "workflow_id": record["workflow_id"],
                    "step": step.get("key"),
                    "step_status": result.get("status"),
                    "step_start_time": step.get("start_time"),
                    "step_end_time": step.get("end_time"),
                    "datapoint_id": datapoint_id,
                    **value,
                })
    out = run_dir / "results.csv"
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return out


if __name__ == "__main__":
    print(export(Path(sys.argv[1])))
