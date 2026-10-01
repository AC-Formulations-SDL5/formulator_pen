"""Register the materials loaded in the Formulator Pens in the Resource Manager.

    python resources/register_materials.py [--workcell-url http://localhost:8005]
                                           [--resource-url http://localhost:8003]

Reads which material each Pen holds from the running
formulator_pen_weighing_node (which reads it from the Pen side) and creates,
or recreates, each material's ``material.<slug>`` ResourceTemplate with the
material name and the dispensing device. Calibration data is not registered:
it stays in Programming/formulator_pen/dispense_system.py.
"""

import argparse
import sys
from pathlib import Path

from madsci.client.resource_client import ResourceClient
from madsci.client.workcell_client import WorkcellClient
from madsci.common.types.resource_types import Consumable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules.materials import DISPENSING_DEVICE, template_name_for  # noqa: E402

NODE = "formulator_pen_weighing_node"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--workcell-url", default="http://localhost:8005")
    parser.add_argument("--resource-url", default="http://localhost:8003")
    args = parser.parse_args()

    state = WorkcellClient(workcell_server_url=args.workcell_url).get_node(NODE).state or {}
    loaded = state.get("loaded_materials") or {}
    if not loaded:
        sys.exit(f"{NODE} reports no loaded materials; check Programming/formulator_pen/pen_config.yaml and the node")

    client = ResourceClient(resource_server_url=args.resource_url)
    for material in dict.fromkeys(loaded.values()):
        name = template_name_for(material)
        if client.get_template(name) is not None:
            client.delete_template(name)
        client.create_template(
            resource=Consumable(
                resource_name=name,
                resource_class="liquid",
                quantity=0.0,
                attributes={"material_name": material, "dispensing_device": DISPENSING_DEVICE},
            ),
            template_name=name,
            description=f"{material} (dispensed by a Formulator Pen)",
            required_overrides=["resource_name"],
            tags=["material", DISPENSING_DEVICE],
        )
        print(f"registered {name}")


if __name__ == "__main__":
    main()
