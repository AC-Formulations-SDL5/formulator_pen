# pen_weighing workflow

Generated for each run by `experiments/pen_weighing.py` from a condition table;
`pen_weighing.example.workflow.yaml` is the definition generated from
`experiments/conditions/example.csv`.

## Condition table (CSV)

| column | type | rule |
|---|---|---|
| `position` | str | a taught tube position on the Pen-side balance (`L4`-`L6`) |
| `material` | str | a material loaded in one of the Pens (`material` in `Programming/formulator_pen/pen_config.yaml`) and registered in the Resource Manager |
| `target_g` | float | > 0; target mass [g] |

The table never names a Pen: each material is dispensed by the Pen that holds
it, read from the node's `loaded_materials` state. A material held by no Pen,
or held by both, stops the run before anything moves.

## Generated steps

Every step runs on `formulator_pen_weighing_node`. Rows are grouped by
material in order of first appearance:

1. `pickup_tool(tool=<pen>)`
2. per row: `move_to_position(position)` then
   `dispense(material, target_g, position)`; the move is left out when the
   row uses the same tube as the previous one. Every dispense tares the
   balance first, so repeated rows for one tube are weighed separately.
3. `return_tool(tool=<pen>)`

then `home()` once every material is done. `dispense` refuses to run unless
the mounted Pen holds the requested material.

The Pens are filled before the run; `dispense` strokes the actuator from its
current position and fails as `INSUFFICIENT_VOLUME` without moving when the
Pen holds too little.

## Results

Each `dispense` step returns the `IntegratedDispenser` job record printed by
`Programming/formulator_pen/run_job.py` on the Pen-side Pi, plus `pen`, `material`,
`target_g`, and `position`. The record's `volume_ml` holds the same target as
`target_g` (the fluid profiles are calibrated against weighed mass). The record includes the measured mass
(`actual_weight_g`), the actuator position before and after the dispense
(reservoir fill level), and the job duration. MADSci stores it as a Data
Manager datapoint referenced from the step result;
`analysis/export_results.py` joins the records with the step timestamps into a
CSV.

A failed step stops the workflow where it stands: the Pen stays mounted.
Recover with the node's actions (`return_tool`, or `set_mounted_tool`
after a node restart).
