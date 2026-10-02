<p align="center">
  <img src="media/logo.png" alt="University of Toronto | Acceleration Consortium" width="600">
</p>

<p align="center">
  <img src="media/videos/Formulator_Pen_Demo.gif" alt="Formulator Pen station picking up a Pen, dispensing onto the balance, and parking the Pen (4x speed)" width="600">
</p>

<h1 align="center">Formulator Pen</h1>

<p align="center">
  <b>An open-source gravimetric liquid handler built from a CNC gantry and swappable "Formulator Pen" dispensing tools</b><br>
  orchestrated by <a href="https://github.com/AD-SDL/MADSci">MADSci</a>
</p>

---

## Overview

The Formulator Pen station dispenses liquids by mass. A CNC XYZ gantry carries
a tool changer that picks a **Formulator Pen**, a self-contained syringe
dispenser with its own valve, linear actuator, and WiFi microcontroller, from
a **parking rack**, moves its nozzle over a tube on an analytical balance,
dispenses the weight the user asked for, records the measured mass, and parks
the Pen again. Each Pen holds one liquid, so liquids never share a fluid path
and no washing is needed between materials.

The user enters a table of target masses (which material, how many grams,
which tube). The station turns it into a workflow, picks the right Pen for
each material, tares the balance before every dispense, and stores every
action and every weighed result in the [MADSci](https://github.com/AD-SDL/MADSci)
managers for later analysis.

Highlights:

- **Swappable dispensing tools.** Pens are picked and parked by a tool changer;
  the station grows by adding Pens and rack seats.
- **Viscous liquids.** Per-liquid fluid profiles set the speed and step
  pattern of the actuator so that viscous oils (validated on Bluesil and
  Siltech silicone oils) dispense accurately, and are calibrated against
  weighed mass.
- **Gravimetric verification.** Every dispense is weighed on the balance and
  the measured mass is recorded next to the target.
- **Orchestrated and traceable.** A single MADSci node exposes the whole
  station; workflows, steps, results, and logs are recorded by the MADSci
  managers and visible in its dashboard.
- **Runs without hardware.** A fake mode simulates every device, so the full
  software stack can be tried on any computer with Docker.

<!-- Add a photo or video of the station here, e.g.
<p align="center"><img src="media/images/station.jpg" width="700"></p>
-->

## Repository layout

| Folder | Contents |
|---|---|
| [`CAD_Files/`](CAD_Files) | mechanical design: Formulator Pen, tool changer, parking rack, balance stage, gantry mounts |
| [`Electronics/`](Electronics) | parts list and wiring of the Pens and the station |
| [`Programming/`](Programming) | code that runs on the hardware: Pico W firmware and the Pen-side Raspberry Pi package |
| [`Orchestration/`](Orchestration) | MADSci stack on the lab PC: node, experiment script, workflows, location seeds, result export, tests |
| [`media/`](media) | logo, photos, and videos |
| [`Manuscript/`](Manuscript) | the manuscript, its figures, and data |

Each folder has its own README with the details for that part.

## How it works

```mermaid
flowchart LR
    user["Condition table<br/>(material, target_g, tube)"] --> exp

    subgraph PC["Lab PC (Docker)"]
        exp["Experiment script"] --> wc["MADSci managers<br/>Workcell / Resource / Location / Data / Event"]
        wc --> node["formulator_pen_weighing_node"]
    end

    subgraph CELL["Cell-side Raspberry Pi 5"]
        sg["SiLA 2: XYZ gantry"]
        st["SiLA 2: tool changer"]
    end

    subgraph PEN["Pen-side Raspberry Pi 5"]
        rj["run_job.py"]
    end

    node -- SiLA 2 --> sg --> gantry["CNC gantry (GRBL)"]
    node -- SiLA 2 --> st --> tc["Tool changer"]
    node -- SSH --> rj
    rj -- WiFi / TCP --> p1["Formulator Pen 1<br/>(Pico W)"]
    rj -- WiFi / TCP --> p2["Formulator Pen 2<br/>(Pico W)"]
    rj -- USB serial --> bal["Balance"]
```

| Host | Runs | Connected to |
|---|---|---|
| Lab PC | MADSci managers and `formulator_pen_weighing_node` (Docker), experiment script | both Raspberry Pis over the network |
| Cell-side Raspberry Pi 5 | SiLA 2 servers for the XYZ gantry and the tool changer | gantry controller (GRBL) and tool-changer motor over USB |
| Pen-side Raspberry Pi 5 | `Programming/formulator_pen/run_job.py`, started by the node over SSH | each Pen's Pico W over WiFi/TCP; the balance over USB serial |

The tool changer's magnetic connector powers the mounted Pen only; all Pen
commands travel over WiFi from the Pen-side Pi.

### One run, step by step

For each material in the condition table, in order of first appearance:

1. `pickup_tool` — the gantry drives to the Pen's parking seat and the tool
   changer locks it.
2. For each row of that material: `move_to_position` places the nozzle over
   the tube, then `dispense` tares the balance, opens the valve, strokes the
   actuator by the calibrated amount for the target mass, closes the valve,
   and reads the settled mass.
3. `return_tool` — the Pen is parked back in its own seat.

Then the gantry homes. Each dispense returns a record with the target, the
measured mass, the actuator positions before and after, and timings, which
`Orchestration/analysis/export_results.py` exports to CSV.

## Try it without hardware

Requires Docker Desktop and Python 3.10+.

```bash
git clone <this-repository-url> formulator_pen
cd formulator_pen/Orchestration
cp .env.example .env
docker compose up -d
docker compose run --rm resource_manager python -m madsci.resource_manager.migration_tool --db_url 'postgresql://madsci:madsci@postgres_resources:5432/resources'
docker compose restart resource_manager formulator_pen_weighing_node
pip install -e ".[lab]"
python resources/register_materials.py
python experiments/pen_weighing.py experiments/conditions/example.csv
python analysis/export_results.py data/runs/<timestamp>
```

The simulated run picks up Pen 1, dispenses 1.0 g of Bluesilv12 into tube L4
twice, parks it, does the same with Pen 2 and 0.3 g of Siltech60 into L5, and
homes the gantry. Watch it in the MADSci dashboard at http://localhost:8000.

## Bill of materials

Costs are in USD at the time of purchase. Amazon items are listed by ASIN.
A dash (–) means the part comes with another item in the list.

### Formulator Pen (per Pen)

| Component | Manufacturer / supplier | Part number | Qty | Cost (USD) |
|---|---|---|---|---|
| [Raspberry Pi Pico microcontroller board](https://www.adafruit.com/product/4864) | Raspberry Pi / Adafruit | Pico RP2040; ID 4864 | 1 | 4.00 |
| [DRV8871 DC motor driver breakout board](https://www.adafruit.com/product/3190) | Adafruit | DRV8871; ID 3190 | 1 | 7.50 |
| [Linear actuator with position feedback; 50 mm stroke, 256:1 gearing, 12 V](https://ca.robotshop.com/products/actuonix-p16-linear-actuator-50mm-2561-12v-w-potentiometer-feedback) | Actuonix | P16-50-256-12-P | 1 | 90.00 |
| [High-torque, metal-gear micro servo (MG92B)](https://www.adafruit.com/product/2307) | TowerPro / Adafruit | MG92B; ID 2307 | 1 | 12.00 |
| [12-pin magnetic pogo-pin connector](https://www.amazon.com/dp/B0D1KRQCVC) | Amazon marketplace | ASIN B0D1KRQCVC | 1 pair | 7.00 |
| [PETG filament for custom 3D-printed parts](https://us.store.bambulab.com/products/petg-hf) | Bambu Lab | PETG-HF; 1 kg spool | 200 g | 4.20 |
| [Masterflex three-way large-bore stopcock with male Luer lock](https://avantorsciences.com/ca/en/product/NA5135088/masterflex-large-bore-stopcock-fittings-male-luer-lock-avantor) | VWR | MFLX30600-23 | 10 | 5.00 |
| [BD Luer-Lok syringe, 10 mL (consumable; box of 200)](https://www.bd.com/en-ca/products-and-solutions/products/product-page.302995) | BD / UofT Medstore | REF 302995 | 1 | 0.25 |
| [Tygon E-3603 tubing, 1/8" ID x 3/16" OD; 50 ft](https://www.coleparmer.com/i/tygon-e-3603-tubing-1-8-id-x-3-16-od-50-ft/5010625) | Cole-Parmer / Saint-Gobain | ACF00006 | 1 | 49.00 |
| **Subtotal** | | | | **178.95** |

### Gantry

| Component | Manufacturer / supplier | Part number | Qty | Cost (USD) |
|---|---|---|---|---|
| [CNC positioning platform (USB cable included)](https://www.sainsmart.com/products/genmitsu-4040-pro-semi-assembly-desktop-cnc-machine-for-carving-and-cutting) | SainSmart / Genmitsu | 4040-PRO; SKU 101-60-4040PRO-AJ | 1 | 479.00 |
| [PETG filament for custom 3D-printed parts](https://us.store.bambulab.com/products/petg-hf) | Bambu Lab | PETG-HF; 1 kg spool | 200 g | 4.21 |
| **Subtotal** | | | | **483.21** |

### Balance

| Component | Manufacturer / supplier | Part number | Qty | Cost (USD) |
|---|---|---|---|---|
| [Laboratory balance](https://www.amazon.com/dp/B0F482HRDG) | UXILAII SCIENTIFIC / Amazon | ASIN B0F482HRDG | 2 | 183.80 |
| [USB-to-RS-232 adapter](https://www.amazon.com/dp/B0759HSLP1) | Amazon marketplace | ASIN B0759HSLP1 | 2 | 9.10 |
| [PETG filament for custom 3D-printed parts](https://us.store.bambulab.com/products/petg-hf) | Bambu Lab | PETG-HF; 1 kg spool | 200 g | 4.20 |
| **Subtotal** | | | | **197.10** |

### Tool changer

| Component | Manufacturer / supplier | Part number | Qty | Cost (USD) |
|---|---|---|---|---|
| [Jubilee cable-driven toolchanger hardware-only kit V2.1](https://lukeslabonline.com/products/jubilee-toolchanger-hardware-only-kit) | Luke's Laboratory | Jubilee Toolchanger Kit V2.1 | 1 | 105.00 |
| [Tic T500 stepper motor controller](https://www.pololu.com/product/3134) | Pololu | Tic T500; item #3134 | 1 | |
| [USB A-to-Micro-B cable for the Tic T500](https://www.amazon.com/dp/B0719H12WD) | Amazon marketplace | ASIN B0719H12WD | 1 | 3.40 |
| [PETG filament for custom 3D-printed parts](https://us.store.bambulab.com/products/petg-hf) | Bambu Lab | PETG-HF; 1 kg spool | 200 g | 4.20 |
| [Mating half of the 12-pin magnetic pogo-pin connector](https://www.amazon.com/dp/B0D1KRQCVC) | Amazon marketplace | ASIN B0D1KRQCVC (pair listed under the Pen) | 1 | – |
| [M5 x 60 mm dowel pin](https://lukeslabonline.com/products/jubilee-toolchanger-hardware-only-kit) | Luke's Laboratory | Included in the Jubilee Toolchanger Kit V2.1 | 4 | – |
| [PETG filament for custom 3D-printed parts](https://us.store.bambulab.com/products/petg-hf) | Bambu Lab | PETG-HF; 1 kg spool | 200 g | 4.20 |
| **Subtotal** (excluding the Tic T500) | | | | **116.80** |

### Station setup

| Component | Manufacturer / supplier | Part number | Qty | Cost (USD) |
|---|---|---|---|---|
| [Raspberry Pi 5 starter kit for orchestration; 4 GB RAM](https://www.canakit.com/canakit-raspberry-pi-5-4gb-starter-kit-turbine-black.html) | CanaKit | Turbine Black; PI5-4GB-STR128-C4-BLK | 1 | 205.00 |
| [T-slotted framing rail, 20 mm x 20 mm x 625 mm](https://www.mcmaster.com/6575N401) | McMaster-Carr | 6575N401 | 5 | 65.60 |
| [T-slotted framing rail, 20 mm x 20 mm x 610 mm](https://www.mcmaster.com/6575N401) | McMaster-Carr | 6575N401 | 4 | 51.20 |
| [T-slotted framing rail, 20 mm x 20 mm x 675 mm](https://www.mcmaster.com/6575N401) | McMaster-Carr | 6575N401 | 4 | 56.70 |
| [T-slotted framing corner bracket](https://www.mcmaster.com/5537T441) | McMaster-Carr | 5537T441 | 24 | 223.70 |
| [AC-to-DC switching power supply, 24 V output](https://www.digikey.com/en/products/detail/mornsun-america-llc/LM350-10B24/13168175) | Digi-Key | LM350-10B24 | 1 | 23.00 |
| [DC-DC step-down converter, 24 V to 12 V](https://www.amazon.com/dp/B0D2TS7CBN) | Amazon marketplace | ASIN B0D2TS7CBN | 1 | 3.50 |
| [AWG 24 hookup wire for signal / control wiring](https://www.amazon.com/dp/B09Y82NFV3) | Amazon marketplace | ASIN B09Y82NFV3 | 1 | 16.00 |
| [AWG 22 hookup wire for power wiring](https://www.amazon.com/dp/B0CM2Y7V1Z) | Amazon marketplace | ASIN B0CM2Y7V1Z | 1 | 17.00 |
| [Lever wire connectors for wire distribution](https://www.amazon.com/dp/B0G6D4GLCY) | Amazon marketplace | ASIN B0G6D4GLCY | 1 | 17.00 |
| **Subtotal** | | | | **678.70** |

## Build your own station

The steps below take you from parts to a running station. Every site-specific
value in the repository is a placeholder (`<...>`) with a comment saying what
to enter.

### 1. Fabricate the mechanical parts

Print or machine the parts in [`CAD_Files/`](CAD_Files): one Formulator Pen
per liquid, the tool changer, the parking rack (one seat per Pen), the tube
holder for the balance, and the mounts for your CNC frame. Any CNC gantry with
a GRBL controller and limit switches on all three axes can carry the tool
changer.

### 2. Assemble the electronics

Build each Pen around a Raspberry Pi Pico W, an Actuonix L16 actuator with a
DRV8871 driver, and an MG92B servo valve; connect the gantry and the tool
changer (Pololu Tic T500) to the cell-side Raspberry Pi 5 and the balance to
the Pen-side Raspberry Pi 5. Parts are listed in the
[bill of materials](#bill-of-materials); pin assignments are in
[`Electronics/`](Electronics).

### 3. Flash the Pens

Put your WiFi credentials in `Programming/firmware/pico_api_step.py` and copy
it to each Pico W as `main.py`:

```bash
mpremote cp Programming/firmware/pico_api_step.py :main.py
```

Give each Pico a fixed address (static IP or DHCP reservation). Details:
[`Programming/README.md`](Programming/README.md#firmware-pico-w).

### 4. Set up the Pen-side Raspberry Pi 5

Clone the repository, install `Programming/requirements.txt`, enter each Pen's
Pico W address, its liquid, and fluid profile plus the balance's serial
device in `Programming/formulator_pen/pen_config.yaml`, and enable SSH. Check
it by hand:

```bash
cd Programming
python3 -m formulator_pen.run_job loaded-materials
python3 -m formulator_pen.run_job read-weight
```

### 5. Set up the cell-side Raspberry Pi 5

Run SiLA 2 servers for the gantry (`XyzGantry`, port 50053) and the tool
changer (`ToolChanger`, port 50054). The commands the node expects are listed
in [`Programming/README.md`](Programming/README.md#gantry-and-tool-changer-cell-side-raspberry-pi-5).

### 6. Calibrate your liquids

Each liquid needs a fluid profile in `FLUID_PROFILES`
(`Programming/formulator_pen/dispense_system.py`): a mass calibration
(slope/offset), an offset for repeated dispenses, actuator speeds, and step
limits for viscous liquids. Prime and fill the Pen, dispense a series of
targets with `run_job dispense`, weigh them, and fit the calibration. Profiles
for water, glycerin, and several silicone oils are included as starting
points. Procedure:
[`Programming/README.md`](Programming/README.md#adding-or-calibrating-a-liquid).

### 7. Set up the lab PC and teach the positions

In `Orchestration/`:

1. Copy `.env.example` to `.env`, enter the Pen-side Pi's SSH login, and set
   `LOCATIONS_FILE=./locations.yaml`.
2. In `modules/formulator_pen_weighing_node/node.settings.yaml`, enter the
   cell-side Pi's address, the path of `Programming/` on the Pen-side Pi, and
   set `interface_type: real`.
3. Jog the gantry and teach the tube positions (`L4`-`L6`), each Pen's parking
   seat and nozzle offset, and the gantry clearance and speeds into
   `locations.yaml`, adding `taught_at` to each; an untaught location refuses
   motion.
4. Start the stack and register the liquids the Pens report (same commands as
   in [Try it without hardware](#try-it-without-hardware), up to
   `register_materials.py`). If you ran fake mode before, run
   `docker compose down -v` first so the taught `locations.yaml` is loaded.

Details: [`Orchestration/README.md`](Orchestration/README.md).

### 8. Run an experiment

Fill the Pens, write a condition table such as
[`Orchestration/experiments/conditions/example.csv`](Orchestration/experiments/conditions/example.csv):

```csv
position,material,target_g
L4,Bluesilv12,1.0
L4,Bluesilv12,1.0
L5,Siltech60,0.3
L5,Siltech60,0.3
```

and run it:

```bash
cd Orchestration
python experiments/pen_weighing.py experiments/conditions/example.csv
python analysis/export_results.py data/runs/<timestamp>
```

The table never names a Pen: each material is dispensed by the Pen that holds
it. A material that no Pen holds, or that two Pens hold, stops the run before
anything moves. Table format and generated steps:
[`Orchestration/workflows/pen_weighing.md`](Orchestration/workflows/pen_weighing.md).

### If a step fails

A failed step stops the workflow where it stands and leaves the Pen mounted.
Inspect the failure in the dashboard, then recover with the node's actions:
`return_tool` to park the Pen, or `set_mounted_tool` after a node restart so
the node knows which Pen is on the gantry. A dispense that would need more
liquid than the Pen holds fails as `INSUFFICIENT_VOLUME` without moving; refill
with the `fill` action.

## Tests

The software tests run against simulated devices, without Docker or hardware:

```bash
cd Orchestration
pip install -e ".[dev]"
python -m pytest
```

## Citation

If you use this system or its designs, please cite the accompanying
manuscript (details to be added on publication; see [`Manuscript/`](Manuscript)).

## License

MIT; see [`LICENSE`](LICENSE).
`Orchestration/patches/madsci-0.8.0/workcell_engine.py` is a modified copy of a
MADSci 0.8.0 file, distributed under the MADSci MIT license in
`Orchestration/patches/madsci-0.8.0/LICENSE.MADSci`.

## Acknowledgements

Developed at the University of Toronto with the Acceleration Consortium, in
collaboration with SEKISUI CHEMICAL CO., LTD.

## Contact

**Self-Driving Laboratory (SDL5) Formulation**<br>
Acceleration Consortium<br>
University of Toronto

- Frantz Le Devedec ([frantz.ledevedec@utoronto.ca](mailto:frantz.ledevedec@utoronto.ca))
- Mahdi Rastegardoost ([m.rastegardoost@utoronto.ca](mailto:m.rastegardoost@utoronto.ca))
