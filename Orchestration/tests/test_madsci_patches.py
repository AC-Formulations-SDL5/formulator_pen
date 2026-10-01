"""Keep the MADSci file patches tied to the MADSci version they were made for.

A patch copied over a different MADSci version would replace code it was never
written for. apply_patches.py refuses that at container start; this catches it
earlier, when compose.yaml's image tag and the patch directory disagree.
"""

import hashlib
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _workcell_service() -> dict:
    compose = yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))
    return compose["services"]["workcell_manager"]


def test_patch_directory_matches_the_image_version():
    service = _workcell_service()
    version = re.search(r":v([\d.]+)$", service["image"]).group(1)
    mounts = [v for v in service.get("volumes", []) if "patches/" in v]
    assert mounts == [f"./patches/madsci-{version}:/home/madsci/patches:ro"]
    assert "apply_patches.py" in service["command"]
    assert (ROOT / "patches" / f"madsci-{version}" / "apply_patches.py").exists()


def test_every_patch_file_exists_and_differs_from_its_official_hash():
    patch_dir = ROOT / "patches" / "madsci-0.8.0"
    sys.path.insert(0, str(patch_dir))
    try:
        import apply_patches
    finally:
        sys.path.remove(str(patch_dir))
    for patch_name, official_sha in apply_patches.PATCHES.values():
        patched = hashlib.sha256((patch_dir / patch_name).read_bytes()).hexdigest()
        assert patched != official_sha
        assert b"\r\n" not in (patch_dir / patch_name).read_bytes()
