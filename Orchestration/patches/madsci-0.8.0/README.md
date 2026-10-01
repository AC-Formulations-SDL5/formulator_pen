# MADSci 0.8.0 patches

The official image `ghcr.io/ad-sdl/madsci:v0.8.0` is used unchanged. The files
here are copied over the installed ones when a manager container starts, by
`apply_patches.py`, which first checks that the installed file is exactly the
official 0.8.0 file each patch was made from. If it is not, the container stops
with an error: MADSci has changed and the patch must be reviewed, not applied.

`workcell_engine.py` is a copy of `madsci/workcell_manager/workcell_engine.py`
from MADSci 0.8.0 with the change below; MADSci is distributed under the MIT
license in `LICENSE.MADSci`.

## Patches

### `workcell_engine.py` — idle busy loop in the Workcell engine

- **Symptom:** with nothing running, `workcell_manager` uses about 75% of a CPU
  core and `valkey` about 22%. The engine re-reads `workcell_info` from Valkey
  roughly 3,000 times per second.
- **Cause:** `WorkcellEngine.spin()` runs node updates every
  `node_update_interval` (2 s) and the scheduler every
  `scheduler_update_interval` (5 s), but its loop sleeps only after an exception,
  so between ticks it spins continuously.
- **Change:** one `time.sleep(0.2)` at the end of the loop body. Ticks are
  delayed by at most 0.2 s.
- **Measured:** workcell_manager 75% → 1%, valkey 22% → 3.5%; workflows run
  unchanged.
- **Upstream:** https://github.com/AD-SDL/MADSci/issues/379

## When MADSci is upgraded, or the Workcell Manager stops with a `[patches]` error

1. Check whether the new version fixes the problem (look for a sleep or wait in
   `WorkcellEngine.spin()`).
2. Fixed upstream: delete this directory, remove the `patches` volume from
   `workcell_manager` in `compose.yaml`, and restore its `command:` to
   `python -m madsci.workcell_manager.workcell_server --cold_start_delay 0`.
3. Not fixed: make a new `patches/madsci-<version>/` from the new official file,
   record its sha256 in `apply_patches.py`, and point `compose.yaml` at it.

`tests/test_madsci_patches.py` fails if the image version in `compose.yaml` and
this directory's version disagree.
