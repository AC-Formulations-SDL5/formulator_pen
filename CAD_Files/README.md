# CAD Files

Mechanical design files for every custom part of the station. Each part is
provided as a neutral exchange format (STEP) for editing in any CAD package
and as STL for 3D printing; native source files are included where available.

```
CAD_Files/
  Formulator_Pen/      Pen body, syringe/reservoir holder, actuator and valve mounts, nozzle
  Tool_Changer/        gantry-side tool-changer head and Pen-side coupling (magnetic power connector)
  Parking_Rack/        rack that holds the parked Pens, one seat per Pen
  Balance_Stage/       tube holder on the balance (positions L4-L6)
  Gantry_Mounts/       brackets that fix the tool changer, rack, and balance to the CNC frame
  Assembly/            full-station assembly
```

> The design files are being added. Until they are, the folders above describe
> where each part belongs.

## Conventions

- One subfolder per assembly; file names `<part>_v<version>.<ext>`.
- Units: millimetres.
- For each printed part, note the material, layer height, infill, and
  orientation in a `print_settings.md` next to the STL.
- Positions taught on the station (tube positions, Pen seats, nozzle offsets)
  are not fixed by the CAD; they are entered in
  `Orchestration/locations.yaml` after assembly (see the top-level README).
