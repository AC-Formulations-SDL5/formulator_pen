"""MADSci node for Formulator Pen weighing: two Pens, a tool changer, an XYZ gantry, a balance.

One node holds every device of the station, as in the formulation cell:

- ``xyz_gantry`` and ``tool_changer``: SiLA 2 servers on the cell-side
  Raspberry Pi 5.
- ``formulator_pen``: the Pen-side Raspberry Pi 5, reached over SSH. Each
  command runs ``formulator_pen/run_job.py`` there, which connects to the
  Pen's Pico W over WiFi and to the balance over USB serial, runs one
  ``IntegratedDispenser`` job, and returns its record.

Geometry comes from the Location Manager: every location this node uses
carries a representation keyed ``formulator_pen_weighing_node`` (seeded from
``locations.yaml``).

- ``gantry_params``: ``safe_y_no_tool``, ``normal_speed``, ``slow_speed``.
- ``tool_offset_<pen>``: the Pen's parking seat (``home_x/home_y/home_z``,
  ``return_buffer_y``) and its nozzle offset (``dispense_dx/dy/dz``).
- any other location with ``x/y/z``: a tube position on the balance.

A location without ``taught_at`` refuses motion. A Pen's travel Y is the
lowest nozzle Y it reaches over any taught position, so moves between the
parking band and a position never pass below the envelope verified while
teaching. Which material each Pen holds is set on the Pen side
(``formulator_pen/pen_config.yaml``); a material must also be registered in
the Resource Manager as a Formulator Pen material. A failed or cancelled
action stops where it stands.
"""

import logging
import os
import threading
from dataclasses import dataclass
from typing import ClassVar, Optional

from madsci.common.types.action_types import ActionFailed, ActionSucceeded
from madsci.common.types.admin_command_types import AdminCommandResponse
from madsci.common.types.node_types import RestNodeConfig
from madsci.node_module.helpers import action
from madsci.node_module.rest_node_module import RestNode
from pydantic import BaseModel

from modules.device_requirements import RequiredDeviceUnavailableError, requires_devices
from modules.materials import check_registered


REPRESENTATION_KEY = "formulator_pen_weighing_node"
GANTRY_MAX_SPEED = 2000.0  # mm/min, hardware specification
RETURN_APPROACH_DZ = 20.0  # mm above the seat before sliding a tool back in
RETURN_INSERT_DY = 15.0  # mm of slow partial insertion before lowering onto the seat
TOOL_PREFIX = "tool_offset_"


class SilaEndpoint(BaseModel):
    host: str
    sila_port: int
    insecure: bool = True


class PenSideSsh(BaseModel):
    """Where run_job.py lives on the Pen-side Pi. Host, user, and password come from .env."""

    port: int = 22
    remote_dir: str = "formulator_pen_madsci"
    python: str = "python3"
    command_timeout_s: float = 3600.0


class FormulatorPenWeighingNodeConfig(RestNodeConfig, yaml_file=("settings.yaml", "node.settings.yaml")):
    """Settings from modules/formulator_pen_weighing_node/node.settings.yaml."""

    _extra_search_dirs: ClassVar[tuple[str, ...]] = ("modules/formulator_pen_weighing_node",)

    interface_type: str = "fake"
    xyz_gantry: SilaEndpoint = SilaEndpoint(host="localhost", sila_port=50053)
    tool_changer: SilaEndpoint = SilaEndpoint(host="localhost", sila_port=50054)
    formulator_pen: PenSideSsh = PenSideSsh()


@dataclass(frozen=True)
class MotionStep:
    """One device command. ``None`` for an axis keeps its current coordinate."""

    label: str
    kind: str  # "move", "lock" or "unlock"
    x: Optional[float] = None
    y: Optional[float] = None
    z: Optional[float] = None
    speed: Optional[float] = None


class MotionAborted(RuntimeError):
    """Raised at a step boundary after an operator cancel."""


# --- Motion planning (pure: geometry in, steps out) -------------------------


def gantry_speeds(geometry: dict) -> tuple[float, float]:
    """Return (normal_speed, slow_speed) in mm/min."""
    params = geometry.get("gantry_params") or {}
    try:
        normal = float(params["normal_speed"])
        slow = float(params["slow_speed"])
    except KeyError as exc:
        raise ValueError(f"gantry_params missing {exc} (see locations.yaml)") from exc
    if not 0 < normal <= GANTRY_MAX_SPEED:
        raise ValueError(f"normal_speed must be > 0 and <= {GANTRY_MAX_SPEED:g} mm/min")
    if not 0 < slow <= normal:
        raise ValueError("slow_speed must be > 0 and <= normal_speed")
    return normal, slow


def safe_y_no_tool(geometry: dict) -> float:
    try:
        return float(geometry["gantry_params"]["safe_y_no_tool"])
    except (KeyError, TypeError) as exc:
        raise ValueError("gantry_params.safe_y_no_tool missing (see locations.yaml)") from exc


def positions(geometry: dict) -> dict[str, dict]:
    """Tube positions: every location with x/y/z that is not a tool or gantry_params."""
    return {
        name: rep
        for name, rep in geometry.items()
        if name != "gantry_params"
        and not name.startswith(TOOL_PREFIX)
        and all(axis in rep for axis in ("x", "y", "z"))
    }


def tool_geometry(geometry: dict, tool: str) -> dict:
    rep = geometry.get(f"{TOOL_PREFIX}{tool}")
    required = ("home_x", "home_y", "home_z", "return_buffer_y",
                "dispense_dx", "dispense_dy", "dispense_dz")
    if rep is None or any(key not in rep for key in required) or not rep.get("taught_at"):
        raise ValueError(
            f"Tool {tool!r} has no complete taught geometry at {TOOL_PREFIX}{tool} "
            f"({', '.join(required)}, taught_at)"
        )
    return rep


def tool_travel_y(geometry: dict, tool: str) -> float:
    """The lowest nozzle Y this tool reaches over any taught position."""
    dy = float(tool_geometry(geometry, tool)["dispense_dy"])
    taught = [rep for rep in positions(geometry).values() if rep.get("taught_at")]
    if not taught:
        raise ValueError("No taught tube position to derive the tool travel Y from")
    return min(float(rep["y"]) + dy for rep in taught)


def pickup_tool_steps(geometry: dict, tool: str) -> list[MotionStep]:
    """Approach the parked tool from no-tool clearance, lock it, and lift it out."""
    seat = tool_geometry(geometry, tool)
    normal, slow = gantry_speeds(geometry)
    home_x, home_y, home_z = seat["home_x"], seat["home_y"], seat["home_z"]
    return [
        MotionStep("Raise Z to travel height", "move", z=0.0, speed=normal),
        MotionStep("Retreat Y to no-tool clearance", "move", y=safe_y_no_tool(geometry), speed=normal),
        MotionStep("Move X over the parked tool", "move", x=home_x, speed=normal),
        MotionStep("Lower Z to the tool", "move", z=home_z, speed=normal),
        MotionStep("Slow Y approach to seat", "move", y=home_y, speed=slow),
        MotionStep("Lock tool changer", "lock"),
        MotionStep("Parallel retreat to tool-change buffer", "move",
                   y=home_y + seat["return_buffer_y"], speed=normal),
        MotionStep("Raise Z after parallel retreat", "move", z=0.0, speed=normal),
        MotionStep("Move Y to tool travel clearance", "move",
                   y=tool_travel_y(geometry, tool), speed=normal),
    ]


def return_tool_steps(geometry: dict, tool: str) -> list[MotionStep]:
    """Carry the tool back to its own seat, unlock, and retreat to no-tool clearance."""
    seat = tool_geometry(geometry, tool)
    normal, slow = gantry_speeds(geometry)
    home_x, home_y, home_z = seat["home_x"], seat["home_y"], seat["home_z"]
    buffer_y = seat["return_buffer_y"]
    return [
        MotionStep("Raise Z to travel height", "move", z=0.0, speed=normal),
        MotionStep("Travel X and Y to parking column at tool travel Y", "move",
                   x=home_x, y=tool_travel_y(geometry, tool), speed=normal),
        MotionStep(f"Descend above seat (home_z + {RETURN_APPROACH_DZ:g}) at buffer Y", "move",
                   y=home_y + buffer_y, z=home_z + RETURN_APPROACH_DZ, speed=normal),
        MotionStep(f"Slow partial insertion (-{RETURN_INSERT_DY:g} mm)", "move",
                   y=home_y + buffer_y - RETURN_INSERT_DY, speed=slow),
        MotionStep("Slow lower Z to the seat", "move", z=home_z, speed=slow),
        MotionStep("Slow final Y to parking", "move", y=home_y, speed=slow),
        MotionStep("Unlock tool changer", "unlock"),
        MotionStep("Retreat Y to no-tool safe position", "move",
                   y=safe_y_no_tool(geometry), speed=normal),
    ]


def move_to_position_steps(geometry: dict, tool: str, position: str) -> list[MotionStep]:
    """Put the mounted tool's nozzle over a taught position: Z up, XY together, Z down."""
    rep = positions(geometry).get(position)
    if rep is None:
        raise ValueError(f"Unknown position {position!r} (see locations.yaml)")
    if not rep.get("taught_at"):
        raise ValueError(f"{position!r} has not been taught yet (missing taught_at)")
    seat = tool_geometry(geometry, tool)
    normal, _ = gantry_speeds(geometry)
    target_y = float(rep["y"]) + float(seat["dispense_dy"])
    travel_y = tool_travel_y(geometry, tool)
    if target_y < travel_y - 1e-6:
        raise ValueError(f"{position}: target Y {target_y:.2f} < tool travel Y {travel_y:.2f}")
    return [
        MotionStep("Raise Z to travel height", "move", z=0.0, speed=normal),
        MotionStep("Move X and Y together to target", "move",
                   x=float(rep["x"]) + float(seat["dispense_dx"]), y=target_y, speed=normal),
        MotionStep("Lower Z to target", "move",
                   z=float(rep["z"]) + float(seat["dispense_dz"]), speed=normal),
    ]


# --- Node --------------------------------------------------------------------


class FormulatorPenWeighingNode(RestNode):
    """Pick up a Formulator Pen, place its nozzle over a tube, dispense and weigh, return it."""

    config: FormulatorPenWeighingNodeConfig = FormulatorPenWeighingNodeConfig()
    config_model = FormulatorPenWeighingNodeConfig
    xyz_gantry: Optional[object] = None
    tool_changer: Optional[object] = None
    formulator_pen: Optional[object] = None

    def startup_handler(self) -> None:
        self._abort = threading.Event()
        self._mounted_tool: Optional[str] = None
        self._loaded_materials: dict[str, str] = {}
        if self.config.interface_type == "fake":
            from devices.formulator_pen_ssh_fake import FormulatorPenSshFake as Pen
            from devices.tool_changer_sila_fake import ToolChangerSilaFake as ToolChanger
            from devices.xyz_gantry_sila_fake import XyzGantrySilaFake as Gantry
        else:
            from devices.formulator_pen_ssh import FormulatorPenSsh as Pen
            from devices.tool_changer_sila import ToolChangerSila as ToolChanger
            from devices.xyz_gantry_sila import XyzGantrySila as Gantry
        pen_login = {
            "host": os.environ.get("PEN_RPI_HOST", ""),
            "username": os.environ.get("PEN_RPI_USER", ""),
            "password": os.environ.get("PEN_RPI_PASSWORD", ""),
        }
        devices = (
            ("xyz_gantry", Gantry, self.config.xyz_gantry.model_dump()),
            ("tool_changer", ToolChanger, self.config.tool_changer.model_dump()),
            ("formulator_pen", Pen, {**pen_login, **self.config.formulator_pen.model_dump()}),
        )
        for name, cls, kwargs in devices:
            try:
                setattr(self, name, cls(**kwargs, logger=logging.getLogger(name)))
            except Exception as error:
                setattr(self, name, None)
                self.logger.warning(f"{name} unavailable during startup: {error}")
        self._refresh_loaded_materials()

    def _refresh_loaded_materials(self) -> dict[str, str]:
        """Ask the Pen side which material each Pen holds (kept for the state)."""
        if self.formulator_pen is not None:
            try:
                self._loaded_materials = self.formulator_pen.loaded_materials()
            except Exception as error:
                self.logger.warning(f"loaded materials unreadable: {error}")
        return self._loaded_materials

    def shutdown_handler(self) -> None:
        for device in (self.xyz_gantry, self.tool_changer, self.formulator_pen):
            if device is not None:
                device.close()

    def state_handler(self) -> None:
        state = {
            "interface_type": self.config.interface_type,
            "mounted_tool": getattr(self, "_mounted_tool", None),
            "loaded_materials": dict(getattr(self, "_loaded_materials", {})),
        }
        for name in ("xyz_gantry", "tool_changer", "formulator_pen"):
            device = getattr(self, name)
            if device is None:
                state[f"{name}_status"] = "disconnected"
                continue
            try:
                device.check_status()
            except Exception:
                device.status = "disconnected"
            state[f"{name}_status"] = device.status
        if self.xyz_gantry is not None:
            state["xyz_gantry_position_mm"] = self.xyz_gantry.current_position
        if self.tool_changer is not None:
            state["tool_changer_locked"] = self.tool_changer.is_locked
        self.node_state = state

    def _require_connected_devices(self, *device_names: str) -> None:
        unavailable = []
        for name in device_names:
            device = getattr(self, name, None)
            if device is None:
                unavailable.append(name)
                continue
            try:
                device.check_status()
            except Exception:
                device.status = "disconnected"
            if not getattr(device, "reachable", device.status == "connected"):
                unavailable.append(name)
        if unavailable:
            raise RequiredDeviceUnavailableError(
                f"Required device service(s) unavailable: {', '.join(unavailable)}"
            )

    def _geometry(self) -> dict[str, dict]:
        geometry = {}
        for loc in self.location_client.get_locations():
            rep = (loc.representations or {}).get(REPRESENTATION_KEY)
            if rep is not None:
                geometry[loc.location_name] = rep
        if not geometry:
            raise RuntimeError(
                f"No locations with a '{REPRESENTATION_KEY}' representation in the Location Manager "
                "(seed locations.yaml)"
            )
        return geometry

    def _run_plan(self, steps: list[MotionStep]) -> None:
        for step in steps:
            if self._abort.is_set():
                raise MotionAborted(f"Cancelled before: {step.label}")
            self.logger.info(step.label)
            if step.kind == "move":
                current = self.xyz_gantry.current_position
                self.xyz_gantry.move_to(
                    current["x"] if step.x is None else step.x,
                    current["y"] if step.y is None else step.y,
                    current["z"] if step.z is None else step.z,
                    step.speed,
                )
            elif step.kind == "lock":
                self.tool_changer.lock()
            elif step.kind == "unlock":
                self.tool_changer.unlock()
            else:  # pragma: no cover - guards against a new step kind
                raise ValueError(f"Unknown motion step kind {step.kind!r}")

    def _execute(self, plan_builder, result: dict):
        """Build a plan from live geometry and run it; stop in place on any error."""
        self._abort.clear()
        try:
            self._run_plan(plan_builder(self._geometry()))
            return ActionSucceeded(json_result=result)
        except Exception as error:
            return ActionFailed(errors=[error], json_result=result)

    @staticmethod
    def _pen_result(command, context: dict):
        """Run a Pen command and return its record as the action result."""
        try:
            record = command()
        except Exception as error:
            return ActionFailed(errors=[error], json_result={**context, **getattr(error, "record", {})})
        return ActionSucceeded(json_result={**context, **record})

    # --- Motion ---

    @action
    @requires_devices("xyz_gantry", "tool_changer")
    def pickup_tool(self, tool: str):
        """Pick up a parked Formulator Pen with the tool changer."""
        if self._mounted_tool is not None:
            return ActionFailed(errors=[RuntimeError(f"{self._mounted_tool} is already mounted")])
        outcome = self._execute(lambda g: pickup_tool_steps(g, tool), {"tool": tool})
        if isinstance(outcome, ActionSucceeded):
            self._mounted_tool = tool
        return outcome

    @action
    @requires_devices("xyz_gantry", "tool_changer")
    def return_tool(self, tool: str):
        """Return the mounted Formulator Pen to its own parking seat."""
        if self._mounted_tool != tool:
            return ActionFailed(errors=[RuntimeError(f"{tool} is not mounted (mounted: {self._mounted_tool})")])
        outcome = self._execute(lambda g: return_tool_steps(g, tool), {"tool": tool})
        if isinstance(outcome, ActionSucceeded):
            self._mounted_tool = None
        return outcome

    @action
    @requires_devices("xyz_gantry")
    def move_to_position(self, position: str):
        """Put the mounted Pen's nozzle over a taught tube position (gantry motion only)."""
        tool = self._mounted_tool
        if tool is None:
            return ActionFailed(errors=[RuntimeError("No tool is mounted")])
        return self._execute(
            lambda g: move_to_position_steps(g, tool, position),
            {"tool": tool, "position": position},
        )

    @action
    @requires_devices("xyz_gantry")
    def home(self):
        """Return the gantry to its origin; refused while a tool is mounted."""
        if self._mounted_tool is not None:
            return ActionFailed(errors=[RuntimeError(f"Return {self._mounted_tool} before homing")])
        try:
            self.xyz_gantry.return_home()
            return ActionSucceeded()
        except Exception as error:
            return ActionFailed(errors=[error])

    @action
    def set_mounted_tool(self, tool: str = ""):
        """Record which tool is physically mounted ("" = none), for recovery after a restart."""
        self._mounted_tool = tool or None
        return ActionSucceeded(json_result={"mounted_tool": self._mounted_tool})

    # --- Dispensing and weighing ---

    def _weigh_with_mounted_pen(self, command: str, material: str, target_g: float, position: str):
        """Check the mounted Pen and its material, then run a weighed Pen command."""
        pen = self._mounted_tool
        context = {"material": material, "target_g": target_g, "position": position}
        try:
            if pen is None:
                raise RuntimeError("No Pen is mounted")
            loaded = self._refresh_loaded_materials().get(pen)
            if loaded != material:
                raise RuntimeError(f"The mounted {pen} holds {loaded!r}, not {material!r}")
            check_registered(self.resource_client, material)
        except Exception as error:
            return ActionFailed(errors=[error], json_result=context)
        run = getattr(self.formulator_pen, command)
        return self._pen_result(lambda: run(pen, target_g, position), context)

    @action
    @requires_devices("formulator_pen")
    def dispense(self, material: str, target_g: float, position: str = ""):
        """Dispense target_g of a material from what the mounted Pen holds, and weigh it.

        Fill-then-dispense: the mounted Pen must hold the material, and the
        material must be registered as a Formulator Pen material. The Pen side
        tares the balance, strokes the actuator from its current position by the
        fluid profile's calibrated amount, and reads the settled mass; the Pen
        must already hold enough material.
        """
        return self._weigh_with_mounted_pen("dispense", material, target_g, position)

    @action
    @requires_devices("formulator_pen")
    def draw_and_dispense(self, material: str, target_g: float, position: str = ""):
        """Draw target_g of a material into the mounted Pen, then dispense all of it and weigh it.

        Draw-and-dispense: the same checks as dispense; the Pen side draws the
        calibrated amount from the reservoir, tares the balance, dispenses it
        in one stroke, and reads the settled mass.
        """
        return self._weigh_with_mounted_pen("draw_and_dispense", material, target_g, position)

    @action
    @requires_devices("formulator_pen")
    def fill(self, pen: str, volume_ml: float):
        """Draw volume_ml into a Pen and hold it with the valve closed."""
        return self._pen_result(lambda: self.formulator_pen.fill(pen, volume_ml), {"pen": pen})

    @action
    @requires_devices("formulator_pen")
    def prime(self, pen: str, cycles: int = 1):
        """Run priming purge cycles on a Pen and return its actuator home."""
        return self._pen_result(lambda: self.formulator_pen.prime(pen, cycles), {"pen": pen})

    @action
    @requires_devices("formulator_pen")
    def read_weight(self, settle_time_s: float = 5.0):
        """Read the balance after settle_time_s."""
        return self._pen_result(lambda: {"weight_g": self.formulator_pen.read_weight(settle_time_s)}, {})

    def cancel(self) -> AdminCommandResponse:
        """Stop a running motion at the next step boundary (a Pen job runs to its end)."""
        self._abort.set()
        return AdminCommandResponse(success=True)


if __name__ == "__main__":
    FormulatorPenWeighingNode().start_node()
