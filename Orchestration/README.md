# Orchestration

The MADSci 0.8.0 stack that runs the station from the lab PC: the MADSci
managers, the `formulator_pen_weighing_node` that holds every device, the
experiment script that turns a condition table into a workflow, and the result
export. Run every command on this page from this folder (`Orchestration/`).

```
devices/                   device wrappers used by the node, and their fakes
modules/formulator_pen_weighing_node/   the MADSci node
modules/materials.py       material names as registered in the Resource Manager
resources/                 registration of the loaded materials in the Resource Manager
experiments/               condition tables and the script that runs them
workflows/                 contract and an example of the generated workflow
analysis/                  export of the recorded dispense results to CSV
tests/                     tests against the fake devices (no Docker or hardware)
locations.yaml             Location Manager seed for the real station (tube positions, Pen seats, nozzle offsets)
locations.example.yaml     illustrative geometry for fake mode
compose.yaml               MADSci managers + the node on the lab PC
Dockerfile                 node image: MADSci base + SiLA 2, SSH, and serial libraries
patches/                   hash-checked patch for a MADSci 0.8.0 Workcell busy loop
```

The Pen-side code the node calls over SSH is in [`../Programming`](../Programming).
The node container mounts the whole repository so that the fake Pen can import
`formulator_pen` from there.

## The node

`formulator_pen_weighing_node` holds every device of the station:

| Device | Reached through | Commands |
|---|---|---|
| `xyz_gantry` | SiLA 2 server on the cell-side Pi | move, home |
| `tool_changer` | SiLA 2 server on the cell-side Pi | lock, unlock |
| `formulator_pen` | SSH to the Pen-side Pi, one `run_job.py` call per command | dispense, draw-and-dispense, fill, prime, read weight, loaded materials |

| Action | What it does |
|---|---|
| `pickup_tool(tool)` | picks a Pen up from its own parking seat |
| `move_to_position(position)` | places the mounted Pen's nozzle over a tube |
| `dispense(material, target_g, position)` | fill-then-dispense: checks that the mounted Pen holds the material and that the material is registered, then tares, dispenses from what the Pen holds, and weighs on the Pen side |
| `draw_and_dispense(material, target_g, position)` | draw-and-dispense: the same checks, then draws the target in, tares, dispenses all of it, and weighs |
| `return_tool(tool)` | parks the mounted Pen in its own seat |
| `home()` | homes the gantry (no Pen mounted) |
| `fill(pen, volume_ml)`, `prime(pen, cycles)`, `read_weight(settle_time_s)` | Pen-side jobs for preparation and checks |
| `set_mounted_tool(tool)` | records which Pen is mounted, for recovery after a restart |

A dispense opens the valve, tares the balance, strokes the actuator from its
current position by the fluid profile's calibrated amount, closes the valve,
and reads the settled mass; the Pens are filled before a run. The fluid
profiles are calibrated against weighed mass, so targets are in grams. The job
record (target, command volume, actuator positions before and after, timings,
measured mass) is the action result. A failed action stops where it stands.

## Where each kind of information lives

| Information | Kept in |
|---|---|
| How a material is dispensed: volume calibration (slope/offset), fill-then-dispense offset, stepped-motion limits, PWM | `FLUID_PROFILES` in `Programming/formulator_pen/dispense_system.py`, pushed to each Pico at connect |
| Which material each Pen holds, and its fluid profile | `Programming/formulator_pen/pen_config.yaml` (Pen side) |
| Which materials exist and that they are dispensed by a Formulator Pen | Resource Manager, one ResourceTemplate `material.<slug>` per material |
| Tube positions, Pen parking seats, nozzle offsets, gantry clearance and speeds | Location Manager, seeded from `locations.yaml` (real station) or `locations.example.yaml` (fake mode) |
| Pico W addresses and the balance serial link | `Programming/formulator_pen/pen_config.yaml` (Pen side) |
| SiLA 2 server addresses; where `Programming/` is on the Pen-side Pi | `modules/formulator_pen_weighing_node/node.settings.yaml` |
| SSH login to the Pen-side Pi | `.env` (not in the repository) |
| Workflow and step history; dispense records; logs | Workcell, Data, and Event Managers |

Every site-specific value ships as a placeholder (`<...>`) with a comment
saying what to enter.

## Trying it without hardware

The node starts in fake mode: it simulates the gantry, the tool changer, both
Pens, and the balance on the lab PC. The fake Pens hold the two silicone oils
of the reported validation run (Bluesilv12 in Pen 1, Siltech60 in Pen 2) and
start filled, and `.env.example` seeds the Location Manager with the
illustrative geometry in `locations.example.yaml`. Requires Docker Desktop
(the dashboard reaches the managers through `kubernetes.docker.internal`) and
Python 3.10+.

```bash
cp .env.example .env
docker compose up -d
docker compose run --rm resource_manager python -m madsci.resource_manager.migration_tool --db_url 'postgresql://madsci:madsci@postgres_resources:5432/resources'
docker compose restart resource_manager formulator_pen_weighing_node
pip install -e ".[lab]"
python resources/register_materials.py
python experiments/pen_weighing.py experiments/conditions/example.csv
python analysis/export_results.py data/runs/<timestamp>
```

The run picks up Pen 1, dispenses 1.0 g of Bluesilv12 into L4 twice, returns
it, does the same with Pen 2 and 0.3 g of Siltech60 into L5, and homes the
gantry. The fake balance reads the dispensed volume at 1 g/mL, so the masses
are illustrative. Workflows, steps, and results are visible in the MADSci
dashboard at http://localhost:8000.

## Setup for the real station

Set up the Pen side first ([`../Programming/README.md`](../Programming/README.md)).

### Teaching

`locations.yaml` ships without coordinates. Teach the tube positions `L4`-`L6`,
both `tool_offset_formulator_pen_*` seats and nozzle offsets, and
`gantry_params` on your station, and enter them with `taught_at`; a location
without `taught_at` refuses motion.

### Lab PC

1. In `.env`, enter the Pen-side Pi's host, user, and password, and set
   `LOCATIONS_FILE=./locations.yaml`.
2. In `modules/formulator_pen_weighing_node/node.settings.yaml`, set the SiLA 2
   server addresses, the path of the `Programming/` folder on the Pen-side Pi,
   and `interface_type: real`.
3. Start the stack, initialize the Resource Manager database, and register
   the materials the Pen side reports:

```bash
docker compose up -d
docker compose run --rm resource_manager python -m madsci.resource_manager.migration_tool --db_url 'postgresql://madsci:madsci@postgres_resources:5432/resources'
docker compose restart resource_manager formulator_pen_weighing_node
pip install -e ".[lab]"
python resources/register_materials.py
```

The location file seeds an empty Location Manager database only. After a fake
run, `docker compose down -v` clears the databases so that the next start
seeds `locations.yaml`; later changes are made through the Location Manager.

## Running

Fill both Pens, then:

```bash
python experiments/pen_weighing.py experiments/conditions/example.csv
python analysis/export_results.py data/runs/<timestamp>
```

The example table is one trial of the reported run: two 1.0 g dispenses of
Bluesilv12 into L4 and two 0.3 g dispenses of Siltech60 into L5, each tared
before it is weighed. The table format and the generated steps are described
in [`workflows/pen_weighing.md`](workflows/pen_weighing.md).

## Tests

The tests run without Docker or hardware, against the fake gantry, tool
changer, Pens, and balance:

```bash
pip install -e ".[dev]"
python -m pytest
```

## MADSci patch

`patches/madsci-0.8.0/workcell_engine.py` fixes an idle busy loop in the MADSci
0.8.0 Workcell engine; it is applied at container start only if the installed
file is exactly the official one. See
[`patches/madsci-0.8.0/README.md`](patches/madsci-0.8.0/README.md).
