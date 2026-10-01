# Programming

Code that runs on the hardware: the MicroPython firmware on each Formulator
Pen's Pico W, and the Python package on the Pen-side Raspberry Pi 5 that
drives the Pens and the balance. The lab PC never talks to a Pen directly; the
MADSci node ([`../Orchestration`](../Orchestration)) runs
`formulator_pen/run_job.py` here over SSH, one job per call.

```
firmware/
  pico_api_step.py           MicroPython firmware for each Pen's Pico W (valve, actuator, WiFi/TCP command server)
formulator_pen/
  formulator_driver.py       Pico W WiFi/TCP driver
  balance_api.py             balance serial driver
  dispense_system.py         IntegratedDispenser: fill / dispense / priming jobs, FLUID_PROFILES
  run_job.py                 execution script: one job per call, prints its record
  pen_config.yaml            Pico W addresses, loaded materials, balance serial link
requirements.txt           Pen-side Python requirements
```

## Firmware (Pico W)

Each Pen carries a Raspberry Pi Pico W that drives an MG92B servo three-way
valve (`UP` intake, `CLOSED`, `THRU` dispense) and an Actuonix L16 linear
actuator through a DRV8871 motor driver, reading the actuator's position
feedback on an ADC pin. Pin assignments are at the top of
`firmware/pico_api_step.py` and in [`../Electronics`](../Electronics).

The firmware listens on TCP port 8888 for line commands from the Pen-side Pi:

| Command | Meaning |
|---|---|
| `VALVE:<UP\|CLOSED\|THRU>` | move the valve |
| `PUMP:<volume>,<dir>[,<pwm>]` | move the actuator by a volume |
| `POS`, `STATUS`, `READY?` | position and state queries |
| `SETPROFILE:<name>,<IN\|OUT>,<enabled>,<min>,<max>,<pause_ms>` | stepped-motion limits for a fluid |
| `SETFLUID:<name>` | runtime default fluid profile |
| `RESET` | reset the Pen |

The fluid profiles are pushed from the Pen-side Pi at every connect, so adding
or tuning a liquid needs no reflashing.

To flash a Pen:

1. Install MicroPython on the Pico W and `pip install mpremote` on your computer.
2. In `firmware/pico_api_step.py`, set `WIFI_SSID` and `WIFI_PASSWORD` (the
   network the Pen-side Pi is on), `FORMULATOR_ID` (used in log lines), and
   optionally `STATIC_IP`. Leave `STATIC_IP = None` and give the Pico a DHCP
   reservation on your router if you prefer.
3. From the repository root: `mpremote cp Programming/firmware/pico_api_step.py :main.py`
4. Reset the Pico; it prints its address and `WiFi command handler ready on port 8888`.

Do not commit your WiFi password: revert the file after flashing.

## Pen-side Raspberry Pi 5

1. Clone this repository and install the requirements:
   ```bash
   git clone <this-repository-url> ~/formulator_pen
   cd ~/formulator_pen/Programming
   python3 -m pip install -r requirements.txt
   ```
2. In `formulator_pen/pen_config.yaml`, set each Pen's Pico W address, the
   material it holds and its fluid profile (a key of `FLUID_PROFILES` in
   `formulator_pen/dispense_system.py`), and the balance serial device
   (prefer the stable `/dev/serial/by-id/...` path).
3. Enable SSH login with a password for the user the node will use.
4. Check it by hand, from `Programming/`:
   ```bash
   python3 -m formulator_pen.run_job loaded-materials
   python3 -m formulator_pen.run_job read-weight --settle 5
   python3 -m formulator_pen.run_job prime --pen formulator_pen_1 --cycles 2
   python3 -m formulator_pen.run_job fill --pen formulator_pen_1 --volume 5.0
   python3 -m formulator_pen.run_job dispense --pen formulator_pen_1 --volume 1.0 --location L4
   ```

Each call prints its job record on a final `RESULT_JSON:` line and appends it
to `data/dispense_results.xlsx`. The node's `remote_dir` setting must point at
this `Programming/` folder.

## Adding or calibrating a liquid

A fluid profile in `FLUID_PROFILES` (`formulator_pen/dispense_system.py`) holds:

- `calibration_slope`, `calibration_offset`: the fit
  `dispensed_g = slope * commanded + offset`, which the dispenser inverts.
  Start a new liquid at slope 1, offset 0, dispense a series of targets
  (e.g. 0.2, 0.5, 1.0 g, several repeats each), weigh them, and fit
  dispensed mass against commanded value.
- `multi_dispense_offset`: the roughly constant gram offset that remains on
  repeated partial dispenses from one fill (dispense #1 excluded); applied to
  fill-then-dispense moves only.
- `pwm_in_percent`, `pwm_out_percent`: actuator speed per direction.
- `in_*` / `out_*` step limits and pauses: stepped motion for viscous liquids,
  so pressure relaxes between steps. Viscous oils need small steps and long
  pauses; water needs none.

Then name the profile in `pen_config.yaml` for the Pen that holds the liquid
and register the material in MADSci (`Orchestration/resources/register_materials.py`).

## Gantry and tool changer (cell-side Raspberry Pi 5)

The node reaches the XYZ gantry (GRBL controller) and the tool changer
(Pololu Tic T500 stepper controller with a lock-side limit switch) through
SiLA 2 servers on a second Raspberry Pi 5. Those servers are not part of this
folder; any SiLA 2 server that implements the features below works with the
node (see `Orchestration/devices/xyz_gantry_sila.py` and
`Orchestration/devices/tool_changer_sila.py`):

| Feature | Commands / properties | Default port |
|---|---|---|
| `XyzGantry` | `MoveTo(X, Y, Z, Speed)` in mm and mm/min, `ReturnHome()` (staged Z, X, Y), `Homing()` (limit switches), `Status`, `CurrentPosition` | 50053 |
| `ToolChanger` | `Lock()`, `Unlock()` (each returning `Success`), `Status`, `IsLocked` | 50054 |
