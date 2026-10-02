# CAD Files

Mechanical design files for the custom parts of the station. Design files are
provided in the formats currently available; native source files are included
where available.

```
CAD_Files/
  Formulator_Pen/                  Pen body, syringe/reservoir holder, actuator and valve mounts, nozzle
  XYZ_Positioning_Platform/
    Parts/                         CNC risers and mounting parts
    Assemblies/                    CNC positioning-platform assemblies
  Balance_System/
    Parts/                         balance, vial-holder, and mounting parts
    Assemblies/                    balance-system assemblies
  Tool_Changer_System/
    Tool_Changer/
      Parts/                       carriage and motor-mount parts
      Assemblies/                  tool-changer assemblies
    Tool_Dock/
      Parts/                       docking parts
      Assemblies/                  tool-dock assemblies
  Assembly/                        full-station assembly
```

## Conventions

- Units: millimetres.
- For each printed part, note the material, layer height, infill, and
  orientation in a `print_settings.md` next to the STL.
- Positions taught on the station (tube positions, Pen seats, nozzle offsets)
  are not fixed by the CAD; they are entered in
  `Orchestration/locations.yaml` after assembly (see the top-level README).
