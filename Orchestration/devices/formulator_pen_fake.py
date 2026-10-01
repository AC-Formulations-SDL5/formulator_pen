"""Fake Formulator Pen (Pico W) and fake balance for running without hardware.

Same public API as ``formulator_pen.FormulatorDriver`` and
``formulator_pen.Balance``, so ``IntegratedDispenser`` runs unchanged on them.
Liquid pushed OUT through the THRU valve lands on the linked fake balance at
1 g/mL, using the firmware's volume <-> actuator-percent relation.
"""

import threading

ML_PER_PERCENT = 0.08  # firmware CALIBRATION_SLOPE
FIRMWARE_OFFSET_ML = 1.2  # firmware CALIBRATION_OFFSET
DENSITY_G_PER_ML = 1.0


class FakeBalance:
    """Balance with the ``Balance`` API; mass is added by linked fake pens."""

    def __init__(self, serial_port, balance_id, baud_rate=9600, timeout=1.0):
        self.balance_id = balance_id
        self.serial_port = serial_port
        self._lock = threading.Lock()
        self._gross_g = 0.0
        self._tare_g = 0.0
        self.is_open = False

    def open(self):
        self.is_open = True

    def add_mass(self, grams):
        with self._lock:
            self._gross_g += grams

    def read_weight(self, settle_time: float = 5.0):
        with self._lock:
            return round(self._gross_g - self._tare_g, 3)

    def tare(self):
        with self._lock:
            self._tare_g = self._gross_g

    def zero(self):
        self.tare()

    def close(self):
        self.is_open = False


class FakeFormulatorDriver:
    """Pico W formulator with the ``FormulatorDriver`` API and no network access."""

    def __init__(self, host, port=8888, timeout=2.0, pump_timeout_s=700.0, formulator_id="formulator1"):
        self.host = host
        self.port = port
        self.formulator_id = formulator_id
        self.connection = None
        self.balance = None  # set by the node in fake mode
        self._position = 15.0
        self._valve = "CLOSED"

    def preload(self, volume_ml):
        """Start as if volume_ml had been drawn in and the valve closed."""
        self._position = (float(volume_ml) + FIRMWARE_OFFSET_ML) / ML_PER_PERCENT
        self._valve = "CLOSED"

    def open(self):
        self.connection = True

    def close(self):
        self.connection = None

    def _deposit(self, percent_out):
        if self._valve == "THRU" and percent_out > 0 and self.balance is not None:
            self.balance.add_mass(percent_out * ML_PER_PERCENT * DENSITY_G_PER_ML)

    def _move(self, target_percent):
        target = max(0.0, min(100.0, float(target_percent)))
        self._deposit(self._position - target)
        self._position = target
        return True

    def send_raw(self, command, timeout_s=5.0):
        return "OK"

    def valve_move(self, position):
        self._valve = position
        return True

    def set_operation_mode(self, mode):
        return True

    def set_default_fluid(self, name):
        return True

    def set_viscosity_profile(self, name, direction, min_step, max_step, pause_ms, enabled=True):
        return True

    def sync_fluid_profile(self, name, in_min_step, in_max_step, in_pause_ms, in_enabled,
                           out_min_step, out_max_step, out_pause_ms, out_enabled):
        return True

    def reset(self):
        self.close()
        return True

    def move_to_percent_stepped(self, target_percent, direction, pwm_percent=None,
                                viscosity_profile=None, steps=None, timeout_s=None):
        return self._move(target_percent)

    def pump_volume(self, volume_ml, direction, pwm_percent=None, viscosity_profile=None,
                    home_position=10.0, home_tolerance=2.0, timeout_s=None):
        target = (float(volume_ml) + FIRMWARE_OFFSET_ML) / ML_PER_PERCENT
        if direction == "OUT":
            target = FIRMWARE_OFFSET_ML / ML_PER_PERCENT
        return self._move(target)

    def get_position(self):
        return self._position

    def get_status(self):
        return {"POS": self._position, "DUTY": 0.0, "READY": True, "SPEED": 1.0,
                "STEP_SIZE": 1.0, "SETTLE_TIME": 0.0}

    def is_ready(self):
        return True

    def get_cooldown_time(self):
        return 0.0
