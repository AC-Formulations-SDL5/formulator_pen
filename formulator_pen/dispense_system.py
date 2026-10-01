"""Formulator Pen dispensing logic (runs on the Pen-side Raspberry Pi 5).

The Pen's Pico W is driven over WiFi/TCP by ``FormulatorDriver`` and the balance
is read over USB serial by ``Balance``. ``IntegratedDispenser`` executes one
dispense job at a time: fill, dispense (tare -> stroke -> settled weight read),
or priming. The fluid profiles below hold each fluid's volume calibration and
the stepped-motion limits pushed to the Pico at connect time.

``run_job.py`` runs one job of this module per call; the MADSci node starts it
over SSH. Gantry motion and tool changes are not part of this module.
"""

import asyncio
import math
import time
from pathlib import Path

import pandas as pd

# Formulator Calibration (reference profile used by firmware)
# Formula: target_percent = (volume_ml + CALIBRATION_OFFSET) / CALIBRATION_SLOPE
# Calibrated from: 15% ≈ 1mL, 90% ≈ 7mL → 75% movement over 6mL range → 12.5%/mL slope
# Slope = 1/12.5 = 0.08; Offset = 15% × 0.08 = 1.2
CALIBRATION_OFFSET = 1.2
CALIBRATION_SLOPE = 0.08
DEFAULT_HOME_POSITION = 15.0

# Formulator Motion
FORMULATOR_PWM_PERCENT = 30  # Actuator speed (0-100)
FORMULATOR_FLUID_PROFILE = "SILTECH60"  # Must match Pico profile names (e.g., WATER, GLYCERIN, BLUESIL)

# Formulator operation mode, set per job (DispenseJob.operation_mode)
# - NORMAL: volume-based fill / dispense
# - PRIMING: explicit stepped targets in the 0-40% firmware window
PRIMING_IN_TARGET_PERCENT = 25.0
PRIMING_OUT_TARGET_PERCENT = 2.0

# Fluid profiles.
# - formulator_profile: token sent to Pico firmware (viscosity profile)
# - calibration_*: fluid-specific dispensed-vs-commanded fit coefficients
#     dispensed = (calibration_slope * commanded) + calibration_offset
#   the dispenser inverts this fit to get commanded from desired:
#     commanded = (desired - calibration_offset) / calibration_slope
# - pwm_in_percent / pwm_out_percent: per-direction actuator speed
# - in_/out_ step-limit fields: the stepped-motion limits per direction, pushed to
#   the Pico at runtime by sync_all_fluid_profiles(), so adding or tuning a fluid
#   needs no firmware change.
# - multi_dispense_offset: separate from calibration_offset. In repeated fill ->
#   partial dispense measurements, excluding dispense #1, each fluid settles to a
#   fixed ABSOLUTE gram offset from target that is roughly constant across volumes
#   -- e.g. glycerin overshoots by ~+0.055g whether the target is 1g or 0.2g, not by
#   a fixed %. calibration_offset cannot correct for this (it is a full-round-trip
#   term that a mid-stroke partial dispense never reaches -- see
#   _apply_profile_delta_correction). It is applied only to action="DISPENSE"
#   (delta) moves; 0.0 means no correction.
#
# Keep the reference profile at offset=0, slope=1, multi_dispense_offset=0 (no correction).
FLUID_PROFILES = {
    "WATER": {
        "formulator_profile": "WATER",
        "calibration_offset": 0.0981,
        "calibration_slope": 0.9627,
        "multi_dispense_offset": 0.0,  # no correction
        "pwm_in_percent": 30,
        "pwm_out_percent": 30,
        "relief_enabled": False,
        "in_enabled": False, "in_min_step": 0.1, "in_max_step": 3.0, "in_pause_ms": 0,
        "out_enabled": False, "out_min_step": 1.0, "out_max_step": 3.0, "out_pause_ms": 0,
    },
    "GLYCERIN": {
        "formulator_profile": "GLYCERIN",
        "calibration_offset": -0.0206,
        "calibration_slope": 1.2165,
        "multi_dispense_offset": 0.055,  # measured: excl.#1 settled +0.047g@1g, +0.053g@0.5g, +0.065g@0.2g
        "pwm_in_percent": 30,
        "pwm_out_percent": 30,
        "relief_enabled": True,
        "in_enabled": True, "in_min_step": 1.0, "in_max_step": 3.0, "in_pause_ms": 2000,
        "out_enabled": False, "out_min_step": 1.0, "out_max_step": 3.0, "out_pause_ms": 0,
    },
    "BLUESIL": {
        "formulator_profile": "BLUESIL",
        "calibration_offset": -0.2001,
        "calibration_slope": 0.9446,
        "multi_dispense_offset": 0.0,  # no correction
        "pwm_in_percent": 25,
        "pwm_out_percent": 30,
        "relief_enabled": True,
        "in_enabled": True, "in_min_step": 0.6, "in_max_step": 2.4, "in_pause_ms": 4000,
        "out_enabled": True, "out_min_step": 0.6, "out_max_step": 42.0, "out_pause_ms": 4000,
    },
    "BLUESILV12": {
        "formulator_profile": "BLUESILV12",
        "calibration_offset": -0.1238,
        "calibration_slope": 0.9319,
        "multi_dispense_offset": 0.020,  # measured: excl.#1 settled +0.023g@1g, +0.015g@0.5g, +0.022g@0.2g
        "pwm_in_percent": 25,
        "pwm_out_percent": 25,
        "relief_enabled": True,
        "in_enabled": True, "in_min_step": 0.3, "in_max_step": 1.2, "in_pause_ms": 4000,
        "out_enabled": True, "out_min_step": 0.3, "out_max_step": 10.0, "out_pause_ms": 5000,
    },
    "BLUESILV30": {
        "formulator_profile": "BLUESILV30",
        "calibration_offset": 0,
        "calibration_slope": 1,
        "multi_dispense_offset": 0.0,  # no correction
        "pwm_in_percent": 25,
        "pwm_out_percent": 25,
        "relief_enabled": True,
        "in_enabled": True, "in_min_step": 0.6, "in_max_step": 1.2, "in_pause_ms": 5000,
        "out_enabled": True, "out_min_step": 0.6, "out_max_step": 8.0, "out_pause_ms": 5000,
    },
    "SILTECH60": {
        "formulator_profile": "SILTECH60",
        "calibration_offset": -0.0957,
        "calibration_slope": 0.9452,
        "multi_dispense_offset": -0.02,  # measured: excl.#1 settled -0.008g@1g, -0.030g@0.5g, -0.025g@0.2g
        "pwm_in_percent": 25,
        "pwm_out_percent": 25,
        "relief_enabled": True,
        "in_enabled": True, "in_min_step": 0.4, "in_max_step": 1.2, "in_pause_ms": 10000,
        "out_enabled": True, "out_min_step": 0.6, "out_max_step": 8.0, "out_pause_ms": 5000,
    },
     "BLUESILV60": {
        "formulator_profile": "BLUESILV60",
        "calibration_offset": -0.0724,
        "calibration_slope": 0.9307,
        "multi_dispense_offset": 0.0,  # no correction
        "pwm_in_percent": 25,
        "pwm_out_percent": 25,
        "relief_enabled": True,
        "in_enabled": True, "in_min_step": 0.4, "in_max_step": 1.2, "in_pause_ms": 5000,
        "out_enabled": True, "out_min_step": 0.6, "out_max_step": 8.0, "out_pause_ms": 7000,
    },
}


def sync_all_fluid_profiles(formulator):
    """Push every FLUID_PROFILES entry's step-limit config down to the Pico.

    Call once after connecting -- the Pico then has all fluids' step-limit
    profiles cached in RAM, and per-job code only needs to select which one
    is active (via set_default_fluid / the profile token passed per command).

    Returns:
        bool: True only if every profile synced successfully. A job run with a
        stale/missing step-limit profile on the Pico (leftover firmware defaults,
        or a profile from whatever fluid ran last) can silently mis-dispense, so
        callers should treat a False return as fatal rather than a warning.
    """
    print("[INIT] Syncing fluid step-limit profiles to formulator...")
    all_ok = True
    for key, profile in FLUID_PROFILES.items():
        token = str(profile.get("formulator_profile", key)).strip().upper()
        ok = formulator.sync_fluid_profile(
            token,
            in_min_step=profile["in_min_step"], in_max_step=profile["in_max_step"],
            in_pause_ms=profile["in_pause_ms"], in_enabled=profile["in_enabled"],
            out_min_step=profile["out_min_step"], out_max_step=profile["out_max_step"],
            out_pause_ms=profile["out_pause_ms"], out_enabled=profile["out_enabled"],
        )
        if not ok:
            print(f"[INIT] WARNING: Failed to sync profile {token}")
            all_ok = False
    return all_ok


async def reconnect_formulator_after_reset(formulator, initial_wait_s=5.0, max_attempts=10, retry_interval_s=2.0):
    """Wait for the Pico to reboot and reassociate with WiFi, then reopen the connection.

    formulator.reset() closes the connection immediately and reboots the board --
    the Pico needs real time to come back up on WiFi before a fresh open() can
    succeed, so this retries on an interval rather than trying exactly once
    right after reset().

    Returns:
        bool: True once open() succeeds and the formulator responds to READY?,
        False if it never comes back within the attempt budget.
    """
    print(f"[INIT] Waiting {initial_wait_s:.0f}s for formulator to reboot...")
    await asyncio.sleep(initial_wait_s)

    for attempt in range(1, max_attempts + 1):
        try:
            formulator.open()
            if formulator.is_ready():
                print(f"[INIT] Formulator back online (attempt {attempt}/{max_attempts})")
                return True
        except (OSError, RuntimeError) as e:
            print(f"[INIT] Reconnect attempt {attempt}/{max_attempts} failed: {e}")
        await asyncio.sleep(retry_interval_s)

    return False

# Results Logging
RESULTS_XLSX = Path(__file__).parent / "dispense_results.xlsx"


# =====================================================
# DISPENSER QUEUE CLASS
# =====================================================

class DispenseJob:
    """Represents a single dispense job.

    Args:
        volume_ml: Target to dispense (required for NORMAL, ignored for PRIMING). The
            fluid profile's calibration relates it to the weighed mass in grams.
        container_id: Optional identifier for this job
        location: Optional position name, recorded with the result
        fluid_profile: Optional profile override (e.g., WATER, GLYCERIN, BLUESIL)
        operation_mode: Optional mode ("NORMAL" or "PRIMING", default: "NORMAL")
        action: Optional NORMAL-mode sub-action ("FILL", "DISPENSE", or "BOTH", default: "BOTH")
            - BOTH: draw volume_ml in, then dispense it back out (draw-and-dispense)
            - FILL: draw volume_ml in and hold (valve closes, nothing dispensed)
            - DISPENSE: dispense volume_ml from whatever is currently held, computed as a
              calibrated %-delta move from the current actuator position (not an absolute
              volume command). If not enough travel remains above the reference position,
              the move is skipped entirely (actuator stays put) and the job is flagged
              INSUFFICIENT_VOLUME. FILL followed by DISPENSE jobs is fill-then-dispense.
        cycles: Optional PRIMING-mode number of IN/OUT purge cycles (default: 1). Ignored
            for NORMAL mode.
    """

    VALID_ACTIONS = ("FILL", "DISPENSE", "BOTH")

    def __init__(self, volume_ml=None, container_id=None, location=None, fluid_profile=None, operation_mode=None, action=None, cycles=None):
        self.location = location
        self.volume_ml = volume_ml
        self.container_id = container_id or f"VIAL_{time.time()}"
        self.fluid_profile = fluid_profile or FORMULATOR_FLUID_PROFILE
        self.operation_mode = operation_mode or "NORMAL"  # NORMAL or PRIMING
        if self.operation_mode == "NORMAL":
            self.action = (action or "BOTH").strip().upper()
            if self.action not in DispenseJob.VALID_ACTIONS:
                raise ValueError(f"Unknown action '{action}'. Must be one of {DispenseJob.VALID_ACTIONS}")
        else:
            self.action = "N/A"
        self.cycles = int(cycles) if cycles is not None else 1  # PRIMING mode only: number of IN/OUT purge cycles
        if self.cycles < 1:
            raise ValueError(f"cycles must be >= 1, got {self.cycles}")
        self.dispense_status = "OK"  # OK or INSUFFICIENT_VOLUME (set when a DISPENSE/BOTH move is clamped)
        self.formulator_profile_token = None
        self.command_volume_ml = None
        self.target_percent = None
        self.profile_calibration_offset = None
        self.profile_calibration_slope = None
        self.profile_multi_dispense_offset = None
        self.profile_pwm_in_percent = None
        self.profile_pwm_out_percent = None
        self.relief_enabled = False
        self.status = "QUEUED"  # QUEUED, IN_PROGRESS, COMPLETED, FAILED
        self.actual_weight = None
        self.form_percent_pre_dispense = None
        self.form_percent_post_dispense = None
        self.form_speed_in_mms = None
        self.form_speed_out_mms = None
        self.form_time_in_s = None
        self.form_time_out_s = None
        self.timestamp = None
        self.job_duration_s = None
        self.calculated_step_size_percent = None
        self.settle_time_used_ms = None
        self.error = None  # "<ExceptionType>: <message>" when status is FAILED


class IntegratedDispenser:
    """Runs dispense jobs on the formulator and the balance, one job per call.
    
    Workflow for NORMAL mode (default action="BOTH"):
    1. Valve moves to UP position
    2. Draw fluid into formulator (IN)
    3. Valve moves to THRU position
    4. Record actuator position before OUT
    5. Tare balance
    6. Dispense fluid (OUT)
    7. Valve moves to CLOSED
    8. Remove fluid from tip post-dispense
    9. Read final weight from balance
    10. Record actuator position after dispense

    NORMAL mode also supports splitting fill and dispense into separate jobs via
    DispenseJob(action=...):
    - action="FILL": steps 1-2 only, then valve closes and holds the drawn fluid.
    - action="DISPENSE": opens the valve and dispenses volume_ml from whatever is
      currently held, computed as a %-delta move from the current actuator position
      (same calibrated volume<->% line, applied as a relative move). If the requested
      volume needs more travel than remains above the reference position, the move is
      skipped entirely (actuator stays put) and the job is flagged INSUFFICIENT_VOLUME
      instead of over- or under-dispensing.

    Workflow for PRIMING mode:
    - N cycles (default 1, set via DispenseJob(cycles=...)) of: Valve UP -> Move IN to target%
      -> Wait 7s -> Valve THRU -> Move OUT to target% -> Wait 7s
    - No volume calibration or balance reading

    Each job specifies its own operation_mode (NORMAL or PRIMING) via DispenseJob(operation_mode=...).
    """
    
    def __init__(self, formulator, balance, results_path=None):
        self.formulator = formulator
        self.balance = balance
        self.results_path = results_path or RESULTS_XLSX

    def _resolve_fluid_profile(self, fluid_profile_name):
        """Resolve profile config from FLUID_PROFILES by name (case-insensitive)."""
        key = (fluid_profile_name or FORMULATOR_FLUID_PROFILE).strip().upper()
        profile = FLUID_PROFILES.get(key)
        if profile is None:
            raise ValueError(f"Unknown fluid profile '{fluid_profile_name}'. Available: {', '.join(FLUID_PROFILES.keys())}")

        token = str(profile.get("formulator_profile", key)).strip().upper()
        offset = float(profile.get("calibration_offset", 0.0))
        slope = float(profile.get("calibration_slope", 1.0))
        multi_dispense_offset = float(profile.get("multi_dispense_offset", 0.0))
        pwm_in = max(0, min(100, int(profile.get("pwm_in_percent", FORMULATOR_PWM_PERCENT))))
        pwm_out = max(0, min(100, int(profile.get("pwm_out_percent", FORMULATOR_PWM_PERCENT))))
        relief_enabled = bool(profile.get("relief_enabled", False))

        return key, token, offset, slope, multi_dispense_offset, pwm_in, pwm_out, relief_enabled

    def _apply_profile_volume_correction(self, requested_volume_ml, profile_offset, profile_slope):
        """Apply inverse fluid TF to requested volume to get command volume.

        Firmware handles the volume->target% conversion with CALIBRATION_OFFSET/SLOPE;
        the fluid correction is applied once, at the volume level.
        """
        if abs(profile_slope) < 1e-9:
            raise ValueError("Profile calibration_slope cannot be 0")

        command_volume = (requested_volume_ml - profile_offset) / profile_slope

        return max(0.0, command_volume)

    def _to_firmware_target_percent(self, command_volume_ml):
        """Convert firmware command volume to actuator target percent used by Pico."""
        return (command_volume_ml + CALIBRATION_OFFSET) / CALIBRATION_SLOPE

    def _to_firmware_delta_percent(self, command_volume_ml):
        """Convert a command volume delta to an actuator percent delta.

        Same linear mapping as _to_firmware_target_percent, but for a relative
        move from the current position rather than an absolute target — the
        offset cancels out since it's a fixed additive constant on both sides.
        """
        return command_volume_ml / CALIBRATION_SLOPE

    def _apply_profile_delta_correction(self, requested_volume_ml, profile_slope, multi_dispense_offset=0.0):
        """Fluid correction for a partial (delta) dispense.

        Deliberately does NOT use profile_offset (_apply_profile_volume_correction's
        offset term) -- that represents a one-time bonus that only shows up on a full
        round trip back to home (e.g. relief/valve-seating on arrival), which a delta
        dispense stops mid-stroke and never reaches.

        Instead applies multi_dispense_offset: a separate, empirically-measured constant
        (from repeated fill -> partial-dispense testing) representing the fixed absolute
        gram offset this fluid settles to once "warmed up" (excluding dispense #1),
        which held roughly constant across tested volumes rather than scaling with them
        -- see FLUID_PROFILES' multi_dispense_offset comment for the measured values.
        """
        if abs(profile_slope) < 1e-9:
            raise ValueError("Profile calibration_slope cannot be 0")
        return max(0.0, (requested_volume_ml - multi_dispense_offset) / profile_slope)

    async def _do_fill(self, job, command_volume_ml, profile_token, pwm_in, pwm_out):
        """Draw fluid into the formulator and leave the valve in the correct holding state.

        For action="BOTH" the valve ends at THRU, ready for the immediate dispense that
        follows in the same job. For action="FILL" the valve ends at CLOSED, sealing the
        drawn fluid until a later DISPENSE job opens it.
        """
        end_valve = "THRU" if job.action == "BOTH" else "CLOSED"

        # -------- STEP 1: Move valve to the correct position before drawing --------
        # A fill normally moves UP in % (drawing fluid in through the intake path), so the
        # valve goes to UP. But if the actuator is already sitting above this fill's target
        # (e.g. left over from a prior job), the "IN" move actually has to travel DOWN to
        # reach it — that's physically a dispense motion, not an intake, so the valve needs
        # to be at THRU for it instead of UP.
        current_pos = self.formulator.get_position()
        if current_pos is not None and job.target_percent is not None and current_pos > job.target_percent:
            draw_valve = "THRU"
            print(
                f"[DISPENSE] Step 1: Actuator ({current_pos:.2f}%) is above fill target "
                f"({job.target_percent:.2f}%); moving valve to THRU instead of UP"
            )
        else:
            draw_valve = "UP"
            print("[DISPENSE] Step 1: Moving valve to UP position")
        self.formulator.valve_move(draw_valve)
        await asyncio.sleep(1)

        # -------- STEP 2: Draw fluid (IN) --------
        print(f"[DISPENSE] Step 2: Drawing {job.volume_ml} mL into formulator")
        time_in_start = time.time()
        ok_in = self.formulator.pump_volume(
            command_volume_ml,
            "IN",
            pwm_percent=pwm_in,
            viscosity_profile=profile_token,
        )
        job.form_time_in_s = time.time() - time_in_start

        if not ok_in:
            print("[DISPENSE] WARNING: Draw pump reported failure, but continuing")

        # Read step size and settle time from formulator status
        try:
            status_in = self.formulator.get_status()
            job.calculated_step_size_percent = status_in.get("STEP_SIZE")
            job.settle_time_used_ms = status_in.get("SETTLE_TIME")
            job.form_speed_in_mms = status_in.get("SPEED")
            if job.form_speed_in_mms is None:
                print("[DISPENSE] IN speed: N/A")
            else:
                print(f"[DISPENSE] IN speed: {job.form_speed_in_mms:.4f} mm/s")
        except Exception as e:
            print(f"[DISPENSE] WARNING: Could not read IN speed: {e}")
            job.form_speed_in_mms = None
        print(f"[DISPENSE] IN time: {job.form_time_in_s:.2f}s")
        await asyncio.sleep(2)  # Wait for formulator to fully complete

        # -------- STEP 3: Apply pressure relief if enabled, then move valve to its holding state --------
        if job.relief_enabled and job.volume_ml > 0.3:
            print(f"[DISPENSE] Step 3a: Applying pressure relief (CLOSED → OUT 1.2% → {end_valve})")
            # Move valve to CLOSED
            self.formulator.valve_move("CLOSED")
            await asyncio.sleep(5)
            # Get current position and move OUT by 1.2%
            try:
                current_pos = self.formulator.get_position()
                if current_pos is not None:
                    relief_target = current_pos - 1.2  # Move OUT by 1.2% for relief
                    self.formulator.move_to_percent_stepped(relief_target, "OUT", pwm_percent=pwm_out)
                    print(f"[DISPENSE] Relief: moved from {current_pos:.2f}% to {relief_target:.2f}%")
                else:
                    print("[DISPENSE] WARNING: Could not read position for relief calculation")
            except Exception as e:
                print(f"[DISPENSE] WARNING: Pressure relief failed: {e}")
            await asyncio.sleep(1)
            if end_valve == "THRU":
                self.formulator.valve_move("THRU")
                await asyncio.sleep(0.5)
            # else: relief already left the valve CLOSED
        else:
            print(f"[DISPENSE] Step 3: Moving valve to {end_valve} position")
            self.formulator.valve_move(end_valve)
            await asyncio.sleep(1)

        # -------- STEP 4: Record actuator position after fill --------
        try:
            job.form_percent_pre_dispense = self.formulator.get_position()
            if job.form_percent_pre_dispense is None:
                print("[DISPENSE] Form% after fill: N/A")
            else:
                print(f"[DISPENSE] Form% after fill: {job.form_percent_pre_dispense:.2f}%")
        except Exception as e:
            print(f"[DISPENSE] WARNING: Could not read Form% after fill: {e}")
            job.form_percent_pre_dispense = None

    async def _do_dispense(self, job, command_volume_ml, profile_token, pwm_out):
        """Dispense fluid via valve OUT, tare/weigh, and record position after.

        For action="BOTH" the valve is already at THRU and job.form_percent_pre_dispense was
        already recorded by _do_fill, so this continues straight to taring/dispensing using
        the full command_volume_ml via the firmware's volume-based PUMP command.

        For action="DISPENSE" the valve starts CLOSED (from an earlier FILL job), so it's
        opened here first and the current position is read fresh — it may have been set by
        a different, earlier job. The dispense amount is then applied as a
        %-delta move from that live position rather than a volume command, since only the
        firmware's PUMP command knows an absolute home-relative volume — a partial dispense
        from mid-stroke has to move by percent. The volume feeding that %-delta is corrected
        via _apply_profile_delta_correction using profile_slope and multi_dispense_offset
        (NOT profile_offset, and NOT job's upfront command_volume_ml) -- profile_offset is a
        full-round-trip-only bonus that a partial dispense never reaches, while
        multi_dispense_offset is a separate empirically-measured constant correcting for the
        fixed settled-state gram offset partial dispenses actually show (see FLUID_PROFILES).
        If the requested delta would move past the DEFAULT_HOME_POSITION reference (i.e. not
        enough fluid remains from the last fill), the move is skipped entirely — the actuator
        stays exactly where it is — and the job
        is flagged INSUFFICIENT_VOLUME instead of dispensing a different amount than asked for.
        """
        if job.action == "DISPENSE":
            print("[DISPENSE] Step: Moving valve to THRU position")
            self.formulator.valve_move("THRU")
            await asyncio.sleep(1)
            try:
                job.form_percent_pre_dispense = self.formulator.get_position()
                if job.form_percent_pre_dispense is None:
                    print("[DISPENSE] Form% before OUT: N/A")
                else:
                    print(f"[DISPENSE] Form% before OUT: {job.form_percent_pre_dispense:.2f}%")
            except Exception as e:
                print(f"[DISPENSE] WARNING: Could not read Form% before OUT: {e}")
                job.form_percent_pre_dispense = None

        # -------- Tare balance --------
        print("[DISPENSE] Step: Taring balance")
        self.balance.tare()
        await asyncio.sleep(2)

        # -------- Dispense fluid (OUT) --------
        print("[DISPENSE] Step: Dispensing fluid (OUT)")
        time_out_start = time.time()

        if job.action == "DISPENSE":
            current_pos = job.form_percent_pre_dispense
            if current_pos is None:
                raise RuntimeError("Could not read actuator position for delta dispense")
            delta_command_volume_ml = self._apply_profile_delta_correction(
                job.volume_ml, job.profile_calibration_slope, job.profile_multi_dispense_offset
            )
            delta_percent = self._to_firmware_delta_percent(delta_command_volume_ml)
            target_percent = current_pos - delta_percent
            job.target_percent = target_percent
            if target_percent < DEFAULT_HOME_POSITION:
                print(
                    f"[DISPENSE] WARNING: Requested {job.volume_ml} mL needs {delta_percent:.2f}% of travel, "
                    f"but only {current_pos - DEFAULT_HOME_POSITION:.2f}% remains above the "
                    f"{DEFAULT_HOME_POSITION:.2f}% reference position. Not enough fluid remains — "
                    f"skipping this dispense (actuator stays at {current_pos:.2f}%) and flagging job "
                    f"INSUFFICIENT_VOLUME."
                )
                job.dispense_status = "INSUFFICIENT_VOLUME"
                ok_out = False
            else:
                ok_out = self.formulator.move_to_percent_stepped(
                    target_percent,
                    "OUT",
                    pwm_percent=pwm_out,
                    viscosity_profile=profile_token,
                )
        else:
            ok_out = self.formulator.pump_volume(
                command_volume_ml,
                "OUT",
                pwm_percent=pwm_out,
                viscosity_profile=profile_token,
            )

        job.form_time_out_s = time.time() - time_out_start
        if not ok_out and job.dispense_status != "INSUFFICIENT_VOLUME":
            print("[DISPENSE] WARNING: Dispense pump failed")
        try:
            status_out = self.formulator.get_status()
            job.form_speed_out_mms = status_out.get("SPEED")
            if job.form_speed_out_mms is None:
                print("[DISPENSE] OUT speed: N/A")
            else:
                print(f"[DISPENSE] OUT speed: {job.form_speed_out_mms:.4f} mm/s")
        except Exception as e:
            print(f"[DISPENSE] WARNING: Could not read OUT speed: {e}")
            job.form_speed_out_mms = None
        print(f"[DISPENSE] OUT time: {job.form_time_out_s:.2f}s")
        await asyncio.sleep(2)  # Wait for formulator to fully complete

        # -------- Move valve to CLOSED position --------
        print("[DISPENSE] Step: Moving valve to CLOSED position")
        self.formulator.valve_move("CLOSED")
        await asyncio.sleep(1)

        # -------- Read final weight --------
        print("[DISPENSE] Step: Reading final weight")
        weight = self.balance.read_weight(settle_time=10.0)
        job.actual_weight = weight
        print(f"[DISPENSE] Target: {job.volume_ml} mL, Actual: {weight:.3f} g")

        # -------- Record actuator position after dispense --------
        try:
            job.form_percent_post_dispense = self.formulator.get_position()
            if job.form_percent_post_dispense is None:
                print("[DISPENSE] Form% after OUT: N/A")
            else:
                print(f"[DISPENSE] Form% after OUT: {job.form_percent_post_dispense:.2f}%")
        except Exception as e:
            print(f"[DISPENSE] WARNING: Could not read Form% after OUT: {e}")
            job.form_percent_post_dispense = None

    async def _do_priming(self, job, profile_token, pwm_in, pwm_out):
        """Run PRIMING mode's repeated purge cycles, then return the actuator home.

        Each cycle: valve UP -> move IN to PRIMING_IN_TARGET_PERCENT -> wait 7s ->
        valve THRU -> move OUT to PRIMING_OUT_TARGET_PERCENT -> wait 7s. The number
        of cycles is job.cycles (set via DispenseJob(cycles=...), default 1). After all
        cycles, the actuator returns to DEFAULT_HOME_POSITION and the valve closes.
        """
        print(f"[DISPENSE] PRIMING MODE: {job.cycles} cycle(s)")
        print(f"[DISPENSE] IN target={PRIMING_IN_TARGET_PERCENT:.2f}%, OUT target={PRIMING_OUT_TARGET_PERCENT:.2f}%")

        for cycle in range(1, job.cycles + 1):
            print(f"\n[DISPENSE] === PRIMING CYCLE {cycle}/{job.cycles} ===")

            # Move valve to UP before IN
            print(f"[DISPENSE] Cycle {cycle}: Moving valve to UP")
            self.formulator.valve_move("UP")
            await asyncio.sleep(1)

            # Move IN to target percent (stepped)
            print(f"[DISPENSE] Cycle {cycle}: Moving IN to {PRIMING_IN_TARGET_PERCENT:.2f}%")
            ok_in = self.formulator.move_to_percent_stepped(
                PRIMING_IN_TARGET_PERCENT,
                "IN",
                pwm_percent=pwm_in,
                viscosity_profile=profile_token,
            )
            if not ok_in:
                print(f"[DISPENSE] WARNING: Cycle {cycle} IN move failed")

            # Wait 7 seconds
            print(f"[DISPENSE] Cycle {cycle}: Waiting 7s...")
            await asyncio.sleep(7)

            # Move valve to THRU before OUT
            print(f"[DISPENSE] Cycle {cycle}: Moving valve to THRU")
            self.formulator.valve_move("THRU")
            await asyncio.sleep(1)

            # Move OUT to target percent (stepped)
            print(f"[DISPENSE] Cycle {cycle}: Moving OUT to {PRIMING_OUT_TARGET_PERCENT:.2f}%")
            ok_out = self.formulator.move_to_percent_stepped(
                PRIMING_OUT_TARGET_PERCENT,
                "OUT",
                pwm_percent=pwm_out,
                viscosity_profile=profile_token,
            )
            if not ok_out:
                print(f"[DISPENSE] WARNING: Cycle {cycle} OUT move failed")

            # Wait 7 seconds before next cycle
            print(f"[DISPENSE] Cycle {cycle}: Waiting 7s...")
            await asyncio.sleep(7)

        # Move valve to UP before returning home
        print("[DISPENSE] Moving valve to UP")
        self.formulator.valve_move("UP")
        await asyncio.sleep(1)

        # Move IN to home position (stepped)
        print(f"[DISPENSE] Moving IN to {DEFAULT_HOME_POSITION:.2f}%")
        ok_in = self.formulator.move_to_percent_stepped(
            DEFAULT_HOME_POSITION,
            "IN",
            pwm_percent=pwm_in,
            viscosity_profile=profile_token,
        )
        if not ok_in:
            print("[DISPENSE] WARNING: IN move failed")

        # Wait 4 seconds
        print("[DISPENSE] Waiting 4s...")
        await asyncio.sleep(4)

        # Close valve at end
        self.formulator.valve_move("CLOSED")
        await asyncio.sleep(90)  # Long wait to ensure that the fluid has rested properly before next dispense, especially for high viscosity fluids like Siltech60.

        print(f"\n[DISPENSE] PRIMING MODE: All {job.cycles} cycle(s) completed")

    async def _execute_dispense(self, job):
        """Execute a single dispense operation.

        Args:
            job: DispenseJob object
        """
        job.status = "IN_PROGRESS"
        job.timestamp = time.time()
        
        print(f"\n{'='*60}")
        print(f"[DISPENSE] {job.container_id}")
        location_note = f" at {job.location}" if job.location else ""
        if job.volume_ml is not None:
            print(f"[DISPENSE] Target: {job.volume_ml} mL{location_note}")
        else:
            print(f"[DISPENSE] Target: PRIMING cycle{location_note}")

        profile_key, profile_token, profile_offset, profile_slope, multi_dispense_offset, pwm_in, pwm_out, relief_enabled = self._resolve_fluid_profile(job.fluid_profile)
        
        # Volume correction only needed for NORMAL mode
        if job.operation_mode == "NORMAL":
            command_volume_ml = self._apply_profile_volume_correction(job.volume_ml, profile_offset, profile_slope)
            if job.action in ("FILL", "BOTH"):
                target_percent = self._to_firmware_target_percent(command_volume_ml)
            else:
                # DISPENSE action: target percent is a delta from the live actuator
                # position, computed later once that position is known
                target_percent = None
        else:
            # PRIMING mode uses target percentages, not volumes
            command_volume_ml = None
            target_percent = None

        job.fluid_profile = profile_key
        job.formulator_profile_token = profile_token
        job.command_volume_ml = command_volume_ml
        job.target_percent = target_percent
        job.profile_calibration_offset = profile_offset
        job.profile_calibration_slope = profile_slope
        job.profile_multi_dispense_offset = multi_dispense_offset
        job.profile_pwm_in_percent = pwm_in
        job.profile_pwm_out_percent = pwm_out
        job.relief_enabled = relief_enabled

        print(f"[DISPENSE] Fluid profile: {profile_key} (firmware={profile_token})")
        print(f"[DISPENSE] Operation mode: {job.operation_mode} (action={job.action})")

        # Only print volume calibration for NORMAL mode
        if job.operation_mode == "NORMAL":
            target_str = f"{target_percent:.2f}%" if target_percent is not None else "computed from live position"
            print(
                f"[DISPENSE] Profile cal: command = desired*slope + offset | offset={profile_offset:.4f}, slope={profile_slope:.4f} | "
                f"Target={target_str} | Cmd vol={command_volume_ml:.4f} mL | PWM IN/OUT={pwm_in}/{pwm_out}%"
            )
        else:
            print(
                f"[DISPENSE] PRIMING targets: IN={PRIMING_IN_TARGET_PERCENT:.2f}%, OUT={PRIMING_OUT_TARGET_PERCENT:.2f}% | PWM IN/OUT={pwm_in}/{pwm_out}%"
            )
        print(f"{'='*60}")
        
        try:
            # Set formulator to job's operation mode
            if not self.formulator.set_operation_mode(job.operation_mode):
                raise RuntimeError(f"Failed to set formulator mode: {job.operation_mode}")
            await asyncio.sleep(0.5)

            # Mark this as the currently-selected fluid on the Pico (runtime state,
            # not firmware-fixed) -- also used as fallback if a bare command omits
            # the profile token.
            self.formulator.set_default_fluid(profile_token)
            
            if job.operation_mode == "NORMAL":
                # ========== NORMAL DISPENSING MODE ==========
                if job.action in ("FILL", "BOTH"):
                    await self._do_fill(job, command_volume_ml, profile_token, pwm_in, pwm_out)

                if job.action in ("DISPENSE", "BOTH"):
                    await self._do_dispense(job, command_volume_ml, profile_token, pwm_out)

                job.status = "COMPLETED"

            elif job.operation_mode == "PRIMING":
                # ========== PRIMING MODE ==========
                await self._do_priming(job, profile_token, pwm_in, pwm_out)
                job.status = "COMPLETED"
            if job.timestamp is not None:
                job.job_duration_s = time.time() - job.timestamp
            print(f"[DISPENSE] ✓ COMPLETED: {job.container_id}")
            
        except Exception as e:
            job.status = "FAILED"
            job.error = f"{type(e).__name__}: {e}"
            if job.timestamp is not None:
                job.job_duration_s = time.time() - job.timestamp
            print(f"[DISPENSE] ✗ FAILED: {job.container_id}")
            print(f"[DISPENSE] Error: {e}")
        
        finally:
            try:
                self._write_result(job)
            except Exception as e:
                print(f"[DISPENSE] WARNING: Could not write result to Excel: {e}")
            print(f"{'='*60}\n")

    def result_row(self, job):
        """Return one job's result record (the row written to Excel)."""
        # Calculate flow rates from speed (syringe diameter = 16mm)
        # Flow rate (mL/s) = (π/4 × diameter² × speed_mm/s) / 1000
        syringe_diameter_mm = 16
        syringe_area_mm2 = math.pi * (syringe_diameter_mm / 2) ** 2
        
        form_flowrate_in_mls = None
        form_flowrate_out_mls = None
        
        if job.form_speed_in_mms is not None:
            form_flowrate_in_mls = (syringe_area_mm2 * job.form_speed_in_mms) / 1000
        
        if job.form_speed_out_mms is not None:
            form_flowrate_out_mls = (syringe_area_mm2 * job.form_speed_out_mms) / 1000
        
        return {
            "formulator_id": self.formulator.formulator_id,
            "container_id": job.container_id,
            "volume_ml": job.volume_ml,
            "location": job.location or "",
            "status": job.status,
            "action": job.action,
            "cycles": job.cycles,
            "dispense_status": job.dispense_status,
            "target_form_percent": job.target_percent,
            "target_percent": job.target_percent,
            "form_percent_pre_dispense": job.form_percent_pre_dispense,
            "form_percent_post_dispense": job.form_percent_post_dispense,
            "form_speed_in_mms": job.form_speed_in_mms,
            "form_speed_out_mms": job.form_speed_out_mms,
            "form_time_in_s": job.form_time_in_s,
            "form_time_out_s": job.form_time_out_s,
            "form_flowrate_in_mls": form_flowrate_in_mls,
            "form_flowrate_out_mls": form_flowrate_out_mls,
            "actual_weight_g": job.actual_weight,
            "job_duration_s": job.job_duration_s,
            "command_volume_ml": job.command_volume_ml,
            "formulator_pwm_in_percent": job.profile_pwm_in_percent,
            "formulator_pwm_out_percent": job.profile_pwm_out_percent,
            "formulator_fluid_profile": job.fluid_profile,
            "formulator_profile_token": job.formulator_profile_token,
            "calculated_step_size_percent": job.calculated_step_size_percent,
            "settle_time_used_ms": job.settle_time_used_ms,
            "multi_dispense_offset_used": job.profile_multi_dispense_offset,
            "error": job.error,
        }

    def _write_result(self, job):
        """Append a single dispense result to Excel."""
        new_df = pd.DataFrame([self.result_row(job)])
        if self.results_path.exists():
            existing_df = pd.read_excel(self.results_path)
            combined_df = pd.concat([existing_df, new_df], ignore_index=True)
        else:
            combined_df = new_df
        combined_df.to_excel(self.results_path, index=False)
