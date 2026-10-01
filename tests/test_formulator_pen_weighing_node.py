"""The combined node against fake gantry, tool changer, Pens, and balance."""

import copy
from types import SimpleNamespace

import pytest
from conftest import EventLogger, LocationClient
from madsci.common.types.action_types import ActionFailed, ActionSucceeded

from devices.formulator_pen_ssh_fake import FormulatorPenSshFake
from formulator_pen import dispense_system
from modules.formulator_pen_weighing_node import formulator_pen_weighing_node as wn
from modules.materials import DISPENSING_DEVICE, template_name_for

GEOMETRY = {
    "L4": {"x": 307.0, "y": 177.5, "z": -44.0, "taught_at": "2026-09-30T10:00"},
    "L5": {"x": 288.0, "y": 204.5, "z": -44.0, "taught_at": "2026-09-30T10:00"},
    "tool_offset_formulator_pen_1": {
        "home_x": 119.0, "home_y": 71.0, "home_z": -66.0, "return_buffer_y": 70.0,
        "dispense_dx": 17.0, "dispense_dy": 89.5, "dispense_dz": 14.0,
        "taught_at": "2026-08-06T17:17",
    },
    "tool_offset_formulator_pen_2": {
        "home_x": 298.0, "home_y": 71.0, "home_z": -65.0, "return_buffer_y": 68.0,
        "dispense_dx": 16.0, "dispense_dy": 88.5, "dispense_dz": 14.0,
        "taught_at": "2026-08-06T17:08",
    },
    "gantry_params": {"safe_y_no_tool": 109.5, "normal_speed": 2000, "slow_speed": 300.0},
}
PEN_CONFIG = {
    "pens": {
        "formulator_pen_1": {"host": "fake", "material": "Bluesilv12", "fluid_profile": "BLUESILV12"},
        "formulator_pen_2": {"host": "fake", "material": "Siltech60", "fluid_profile": "SILTECH60"},
    },
}


class ResourceClient:
    """Resource Manager stub holding material templates by name."""

    def __init__(self, *materials):
        self.templates = {
            template_name_for(name): SimpleNamespace(
                attributes={"material_name": name, "dispensing_device": DISPENSING_DEVICE}
            )
            for name in materials
        }

    def get_template(self, template_name):
        return self.templates.get(template_name)


@pytest.fixture
def node(monkeypatch):
    async def no_wait(_seconds):
        return None

    monkeypatch.setattr(dispense_system.asyncio, "sleep", no_wait)
    real_init = FormulatorPenSshFake.__init__
    monkeypatch.setattr(FormulatorPenSshFake, "__init__",
                        lambda self, **kw: real_init(self, **kw, pen_config=PEN_CONFIG))
    node = object.__new__(wn.FormulatorPenWeighingNode)
    node.config = wn.FormulatorPenWeighingNodeConfig(interface_type="fake")
    node.logger = EventLogger()
    node.location_client = LocationClient(copy.deepcopy(GEOMETRY), wn.REPRESENTATION_KEY)
    node._resources = ResourceClient("Bluesilv12", "Siltech60")
    monkeypatch.setattr(wn.FormulatorPenWeighingNode, "resource_client",
                        property(lambda self: self._resources))
    node.startup_handler()
    node.xyz_gantry._latency = 0.0
    node.tool_changer._latency = 0.0
    return node


# --- Motion planning ---


def test_tool_travel_y_is_the_lowest_nozzle_y_over_taught_positions():
    assert wn.tool_travel_y(GEOMETRY, "formulator_pen_1") == pytest.approx(177.5 + 89.5)


def test_pickup_locks_at_the_seat_then_lifts_to_travel_y():
    steps = wn.pickup_tool_steps(GEOMETRY, "formulator_pen_1")
    lock = [s.kind for s in steps].index("lock")
    assert steps[lock - 1].y == 71.0 and steps[lock - 1].speed == 300.0
    assert steps[-1].y == pytest.approx(267.0)


def test_move_refuses_an_untaught_position():
    geometry = copy.deepcopy(GEOMETRY)
    geometry["L6"] = {"x": 0.0, "y": 300.0, "z": 0.0}
    with pytest.raises(ValueError, match="not been taught"):
        wn.move_to_position_steps(geometry, "formulator_pen_1", "L6")


# --- Motion actions ---


def test_pickup_move_return_puts_the_nozzle_over_the_tube(node):
    assert isinstance(node.pickup_tool("formulator_pen_2"), ActionSucceeded)
    assert node.tool_changer.is_locked
    assert isinstance(node.move_to_position("L5"), ActionSucceeded)
    assert node.xyz_gantry.current_position == {"x": 304.0, "y": 293.0, "z": -30.0}
    assert isinstance(node.return_tool("formulator_pen_2"), ActionSucceeded)
    assert not node.tool_changer.is_locked
    assert node.xyz_gantry.current_position["y"] == 109.5
    assert node._mounted_tool is None


def test_second_pickup_wrong_return_and_home_with_tool_are_refused(node):
    node.pickup_tool("formulator_pen_1")
    assert isinstance(node.pickup_tool("formulator_pen_2"), ActionFailed)
    assert isinstance(node.return_tool("formulator_pen_2"), ActionFailed)
    assert isinstance(node.home(), ActionFailed)


def test_cancel_stops_before_the_next_step_and_keeps_the_mount_state(node):
    moves = []
    move_to = node.xyz_gantry.move_to

    def move_then_cancel(*args):
        move_to(*args)
        moves.append(args)
        node.cancel()

    node.xyz_gantry.move_to = move_then_cancel
    assert isinstance(node.pickup_tool("formulator_pen_1"), ActionFailed)
    assert len(moves) == 1
    assert node._mounted_tool is None
    assert not node.tool_changer.is_locked


# --- Dispensing ---


def test_state_reports_which_material_each_pen_holds(node):
    node.state_handler()
    assert node.node_state["loaded_materials"] == {
        "formulator_pen_1": "Bluesilv12",
        "formulator_pen_2": "Siltech60",
    }


def test_dispense_with_the_mounted_pen_records_the_weighed_mass(node):
    node.fill("formulator_pen_1", 5.0)
    node.pickup_tool("formulator_pen_1")
    node.move_to_position("L4")
    first = node.dispense("Bluesilv12", 1.0, "L4")
    second = node.dispense("Bluesilv12", 1.0, "L4")
    assert isinstance(first, ActionSucceeded) and isinstance(second, ActionSucceeded)
    record = second.json_result
    assert record["pen"] == "formulator_pen_1" and record["material"] == "Bluesilv12"
    assert record["target_g"] == 1.0 and record["position"] == "L4"
    assert record["formulator_fluid_profile"] == "BLUESILV12"
    # Fake Pen at 1 g/mL through BLUESILV12's delta correction; tared before each dispense.
    assert record["actual_weight_g"] == pytest.approx((1.0 - 0.020) / 0.9319, abs=1e-3)
    # The second dispense starts where the first ended (one fill, two dispenses).
    assert record["form_percent_pre_dispense"] == first.json_result["form_percent_post_dispense"]


def test_dispense_refuses_a_material_the_mounted_pen_does_not_hold(node):
    node.fill("formulator_pen_1", 5.0)
    node.pickup_tool("formulator_pen_1")
    position = node.formulator_pen._pens["formulator_pen_1"].get_position()
    result = node.dispense("Siltech60", 0.3, "L4")
    assert isinstance(result, ActionFailed)
    assert "holds 'Bluesilv12'" in str(result.errors[0])
    assert node.formulator_pen._pens["formulator_pen_1"].get_position() == position


def test_dispense_refuses_an_unregistered_material_and_without_a_pen(node):
    assert isinstance(node.dispense("Bluesilv12", 1.0, "L4"), ActionFailed)  # nothing mounted
    del node._resources.templates[template_name_for("Bluesilv12")]
    node.pickup_tool("formulator_pen_1")
    result = node.dispense("Bluesilv12", 1.0, "L4")
    assert isinstance(result, ActionFailed)
    assert "not registered" in str(result.errors[0])


def test_dispense_beyond_what_is_held_fails_without_moving(node):
    node.fill("formulator_pen_2", 0.3)
    node.pickup_tool("formulator_pen_2")
    result = node.dispense("Siltech60", 2.0, "L5")
    assert isinstance(result, ActionFailed)
    assert result.json_result["dispense_status"] == "INSUFFICIENT_VOLUME"
    assert result.json_result["form_percent_pre_dispense"] == result.json_result["form_percent_post_dispense"]


def test_prime_and_read_weight(node):
    assert isinstance(node.prime("formulator_pen_1", cycles=2), ActionSucceeded)
    assert isinstance(node.read_weight(0.0), ActionSucceeded)


def test_fake_pens_hold_the_example_materials_and_start_filled_without_a_pen_config():
    from devices.formulator_pen_ssh_fake import FAKE_INITIAL_FILL_ML, FormulatorPenSshFake

    fake = FormulatorPenSshFake(host="", username="", password="")  # pen_config.yaml holds placeholders
    assert fake.loaded_materials() == {"formulator_pen_1": "Bluesilv12", "formulator_pen_2": "Siltech60"}
    assert fake._pens["formulator_pen_1"].get_position() == pytest.approx((FAKE_INITIAL_FILL_ML + 1.2) / 0.08)


def test_example_geometry_plans_every_move_of_the_example_trial():
    import yaml

    from conftest import ROOT

    seed = yaml.safe_load((ROOT / "locations.example.yaml").read_text(encoding="utf-8"))
    geometry = {loc["location_name"]: loc["representations"][wn.REPRESENTATION_KEY] for loc in seed["locations"]}
    for pen, position in (("formulator_pen_1", "L4"), ("formulator_pen_2", "L5")):
        assert wn.pickup_tool_steps(geometry, pen)
        assert wn.move_to_position_steps(geometry, pen, position)
        assert wn.return_tool_steps(geometry, pen)


def test_draw_and_dispense_draws_the_target_and_dispenses_all_of_it(node):
    node.pickup_tool("formulator_pen_2")
    result = node.draw_and_dispense("Siltech60", 0.3, "L5")
    assert isinstance(result, ActionSucceeded)
    record = result.json_result
    assert record["action"] == "BOTH" and record["material"] == "Siltech60"
    # Draws (target - offset) / slope and pushes it all out at 1 g/mL.
    assert record["actual_weight_g"] == pytest.approx((0.3 + 0.0957) / 0.9452, abs=1e-3)
    assert isinstance(node.draw_and_dispense("Bluesilv12", 1.0, "L5"), ActionFailed)
