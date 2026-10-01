"""Apply this project's MADSci 0.8.0 file patches inside a manager container.

Runs before the manager starts (see its `command:` in compose.yaml). The official
image is used unchanged; each patched file is copied over the installed one only
after checking that the installed file is EXACTLY the official 0.8.0 file it was
made from. Anything else -- a newer MADSci, an upstream fix, a different image --
stops the container with an error instead of silently replacing code this patch
was never written for. See README.md in this directory.
"""

import hashlib
import importlib.util
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

# module whose source file is replaced -> (patch file here, sha256 of the official file)
PATCHES = {
    "madsci.workcell_manager.workcell_engine": (
        "workcell_engine.py",
        "8950aa0ab3bd99ba9cabaea5d0666d15ca863cf259d8d5441969d50fc3c1cd31",
    ),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    for module, (patch_name, official_sha) in PATCHES.items():
        spec = importlib.util.find_spec(module)
        if spec is None or spec.origin is None:
            print(f"[patches] {module} is not installed in this image", file=sys.stderr)
            return 1
        target = Path(spec.origin)
        patch = HERE / patch_name
        current = sha256(target)
        if current == sha256(patch):
            print(f"[patches] {module}: already patched")
            continue
        if current != official_sha:
            print(
                f"[patches] {module}: installed file is not the official MADSci 0.8.0 "
                f"file this patch was made from (sha256 {current}). MADSci has changed; "
                "review patches/madsci-0.8.0/README.md before starting this manager.",
                file=sys.stderr,
            )
            return 1
        shutil.copyfile(patch, target)
        print(f"[patches] {module}: patched")
    return 0


if __name__ == "__main__":
    sys.exit(main())
