# CAD Files

Printable parts of the Formulator Pen and the assembled Pen.

```
CAD_Files/
  Formulator_Pen/   STL files of every custom Pen part
  Assembly/         Formulator_Pen_Assembly.3mf: the assembled Pen as a print project
```

| File | Part |
|---|---|
| `Main_Body.stl` | Pen body that carries the syringe, actuator, valve and electronics |
| `Syringe_Holder.stl` | clamp for the 10 mL BD Luer-Lok syringe |
| `Reservoir_Holder.stl` | holder for the 50 mL on-board reservoir syringe |
| `Actuator_Rail_Holder_A.stl`, `Actuator_Rail_Holder_B.stl` | two halves of the rail that guides the Actuonix P16 actuator |
| `Actuator_Lid.stl` | cover of the actuator compartment |
| `Valve_Mount.stl` | mount of the MG92B servo on the Pen body |
| `Valve_Adapter.stl` | coupling between the servo horn and the three-way stopcock |
| `Horizontal_Wing.stl` | wing that registers the Pen in the tool changer and the parking seat |
| `Magnetic_Connector_Cover_12pin.stl` | cover of the Pen-side 12-pin magnetic power connector |

All parts were printed in PETG (Bambu Lab PETG-HF). Dimensions are in millimetres.

The tool changer is the Jubilee cable-driven tool changer (hardware kit V2.1, Luke's
Laboratory); its parts and assembly follow the Jubilee project documentation. The gantry is a
Genmitsu 4040-PRO CNC. Positions taught on the station (tube positions, Pen seats, nozzle
offsets) are not fixed by the CAD; they are entered in `Orchestration/locations.yaml` after
assembly (see the top-level README).
