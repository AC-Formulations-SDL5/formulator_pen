"""Material names as registered in the MADSci Resource Manager.

The Resource Manager holds only what MADSci needs to know about a material:
its name and that it is dispensed by a Formulator Pen. Each material is a
ResourceTemplate ``material.<slug>``. How a material is dispensed (volume
calibration, stepped-motion limits, PWM) stays on the Pen side, in
``formulator_pen.dispense_system.FLUID_PROFILES``.
"""

import re

DISPENSING_DEVICE = "formulator_pen"


def template_name_for(material_name: str) -> str:
    """ResourceTemplate name of a material (template names must be lowercase)."""
    slug = re.sub(r"[^a-z0-9]+", "-", material_name.lower()).strip("-")
    return f"material.{slug}"


def check_registered(resource_client, material_name: str) -> None:
    """Raise unless the material is registered as a Formulator Pen material."""
    template = resource_client.get_template(template_name_for(material_name))
    if template is None:
        raise ValueError(
            f"Material {material_name!r} is not registered in the Resource Manager "
            "(run resources/register_materials.py)"
        )
    device = (template.attributes or {}).get("dispensing_device")
    if device != DISPENSING_DEVICE:
        raise ValueError(
            f"Material {material_name!r} is registered for {device!r}, not {DISPENSING_DEVICE!r}"
        )
