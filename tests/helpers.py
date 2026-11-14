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
# What the sample store exports on AS_OF. A task that stores a new series changes these, and the golden manifest.
SAMPLE_WEEKS = ["2026-10-19", "2026-10-26", "2026-11-02"]
SAMPLE_SNAPSHOTS = ["2026-10-05", "2026-10-19", "2026-10-31", "2026-11-02", "2026-11-03", "2026-11-09", "2026-11-10"]
SAMPLE_FILES = len(SAMPLE_WEEKS) + len(SAMPLE_SNAPSHOTS) + 3

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


def exported_store(tmp, as_of: str = AS_OF) -> Path:
    """A copy of the sample store with its data folder written, ready for the page build."""
    import datetime as dt
    from aso.dashboard import export
    store = copy_store(tmp)
    files, _ = export.build_all(store, dt.date.fromisoformat(as_of))
    export.write(store, files)
    return store
