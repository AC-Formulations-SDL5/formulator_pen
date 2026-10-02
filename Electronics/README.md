# Electronics

Wiring and parts for the station. Pin numbers come from
`Programming/firmware/pico_api_step.py`; change them there if you wire
differently.

## Formulator Pen (one per Pen)

| Part | Role |
|---|---|
| Raspberry Pi Pico W | runs the firmware, receives commands over WiFi |
| Actuonix L16 linear actuator (50 mm stroke, with position feedback) | moves the plunger |
| DRV8871 motor driver | drives the actuator |
| MG92B servo | turns the three-way valve (`UP` intake, `CLOSED`, `THRU` dispense) |
| Magnetic connector (Pen side) | receives power from the tool changer when the Pen is mounted |

| Pico W pin | Connected to |
|---|---|
| GP4 | DRV8871 IN1 |
| GP5 | DRV8871 IN2 |
| GP27 (ADC1) | L16 position feedback (wiper) |
| GP3 | MG92B signal |

The tool changer's magnetic connector carries power only; all Pen commands
travel over WiFi from the Pen-side Raspberry Pi 5.

## Station

| Part | Connected to | Link |
|---|---|---|
| CNC XYZ gantry with GRBL controller and limit switches | cell-side Raspberry Pi 5 | USB serial |
| Tool changer: stepper motor, Pololu Tic T500 controller, lock-side limit switch | cell-side Raspberry Pi 5 | USB |
| Analytical balance with serial output | Pen-side Raspberry Pi 5 | USB serial (9600 baud by default) |
| Raspberry Pi 5 (cell side) | lab PC | network (SiLA 2) |
| Raspberry Pi 5 (Pen side) | lab PC; each Pen's Pico W | network (SSH); WiFi/TCP |
| Lab PC | both Raspberry Pis | network |

The balance driver (`Programming/formulator_pen/balance_api.py`) sends `R`
(read), `T` (tare), and `Z` (zero); a balance with a different command set
needs its own driver with the same methods.

## To add here

- Wiring diagram / schematic of the Pen electronics and the tool-changer power path
- Full bill of materials: see [Bill of materials](../README.md#bill-of-materials) in the main README
- Power supply ratings for the actuator and servo
