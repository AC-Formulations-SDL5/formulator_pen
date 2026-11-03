# Data

## formulatorpen.csv

Every gravimetric dispense of the four liquid-handling strategies; one row per strategy, fluid,
data type and target mass, with up to ten repeated dispenses in `Run1`-`Run10`. Each repeat is a
complete, independent aspiration-to-dispense cycle. `NULL` marks an empty field.

| Column | Meaning |
|---|---|
| `Prototype` | strategy: 3 Fill-and-Dispense, 4 Remote-Reservoir, 5 On-Board Reservoir, 6 Pressurized On-Board |
| `Data Type` | `Calibration` (fit of the calibration profile), `Test` (validation, never used in a fit), `Test (2x)` / `Test (3x)` (Fill-and-Dispense with doubled / tripled actuator step), `Calibration_tighter` / `Test_tighter` (exploratory low-mass runs, not used in the manuscript) |
| `Fluid` | fluid key; see `fluids.csv` |
| `Viscosity (cP)` | nominal viscosity grade; the measured value is in `fluids.csv` |
| `Dispense Tip Gauge` | blunt dispensing tip, gauge (16 G ≈1.2 mm, 14 G ≈1.5 mm nominal ID) |
| `PWM%In`, `PWM%Out` | actuator speed (PWM duty, %) for intake and dispense |
| `Step%In`, `Step%Out` | maximum step of the stepped motion (% of actuator stroke); empty = continuous motion |
| `SettleIn (s)`, `SettleOut (s)` | pause after each step (s) |
| `Volume (g)` | target mass (g) |
| `Run1`-`Run10` | delivered mass of each repeat (g), balance readability 0.001 g |
| `Mean Job Time In (s)`, `Mean Job Time Out (s)`, `Mean Job Time Misc (s)` | mean intake, dispense and remaining time per cycle (s); recorded for the reservoir-fed strategies |
| `Mean Job Time Total (s)` | mean total time per cycle, from job start to the final balance reading (s) |

## platform_validation.csv

The multi-pen tool-changing run of Section 4.2 (two trials, two pens, eight vials).

| Column | Meaning |
|---|---|
| `vial`, `trial` | vial number in execution order, trial number |
| `pen`, `fluid` | white pen (Bluesil FLD 47V12500) or black pen (Siltech F-60000) |
| `target_g` | target mass (g) |
| `syringe_fill_before_pct`, `syringe_fill_after_pct` | dosing-syringe fill level, read from the actuator position (% of stroke) |
| `dispense_speed_mm_s`, `dispense_time_s`, `dispense_flow_mL_s` | plunger speed, dispense duration and mean flow rate |
| `actual_weight_g` | delivered mass (g) |
| `job_duration_s` | total time per vial including travel, tool exchange and taring (s) |

## fluids.csv

Test fluids (Table 2 of the manuscript): fluid key, nominal grade, commercial grade, material
type, measured viscosity (Brookfield DV2T-RV, CP51 cone, ≈20 °C, 45-55% torque), density at 20 °C
and dispensing tip gauge.
