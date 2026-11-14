"""Shared paths and runners for the tests. Nothing here reaches the network."""
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "assets" / "sample" / "store"
GOLDEN = ROOT / "tests" / "golden"
AS_OF = "2026-11-14"

sys.path.insert(0, str(ROOT / "scripts"))

# argparse wraps help to the terminal width; a fixed width keeps recorded help texts comparable.
ENV = {**os.environ, "COLUMNS": "100", "PYTHONDONTWRITEBYTECODE": "1"}


def run(script: str, *args: str):
    """Run `python3 scripts/<script> <args>` from the repository root -> (exit code, stdout, stderr)."""
    done = subprocess.run([sys.executable, str(Path("scripts") / script), *args],
                          cwd=ROOT, capture_output=True, text=True, env=ENV)
    return done.returncode, done.stdout, done.stderr


def copy_store(tmp) -> Path:
    """A writable copy of the sample store. Tests never write under assets/sample/store."""
    target = Path(tmp) / "store"
    shutil.copytree(SAMPLE, target)
    return target
