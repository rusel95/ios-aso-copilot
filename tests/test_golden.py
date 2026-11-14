"""The golden test: the invented store must come out byte for byte as recorded: its data files and its page.

A change that alters a figure, a file or the page fails here. When the output is meant to change:

    python3 tests/test_golden.py --update

and say in the commit which files changed and why. A changed manifest with no stated reason does not pass review.
"""
import contextlib
import datetime as dt
import hashlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tests.helpers import AS_OF, GOLDEN, copy_store  # noqa: E402

from aso.dashboard import export, site  # noqa: E402

MANIFEST = GOLDEN / "sample.sha256"


def produced() -> dict:
    """relative path -> sha256 of everything the export and the build write for the sample store."""
    with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
        store, out = copy_store(tmp), Path(tmp) / "public"
        assert export.run(store, dt.date.fromisoformat(AS_OF)) == 0
        assert site.build(store / "data", out, "Tidepool") == 0
        files = {f"data/{p.relative_to(store / 'data').as_posix()}": p for p in sorted((store / "data").rglob("*.json"))}
        files["public/index.html"] = out / "index.html"
        return {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in files.items()}


def recorded() -> dict:
    if not MANIFEST.is_file():
        return {}
    return {name: digest for digest, name in (line.split("  ", 1) for line in MANIFEST.read_text(encoding="utf-8").splitlines())}


class Golden(unittest.TestCase):
    maxDiff = None

    def test_the_sample_comes_out_as_recorded(self):
        made, kept = produced(), recorded()
        self.assertTrue(kept, "no manifest: run python3 tests/test_golden.py --update")
        self.assertEqual(sorted(made), sorted(kept), "the set of files changed")
        changed = sorted(name for name in made if made[name] != kept[name])
        self.assertEqual(changed, [], "these files no longer match the recorded bytes")

    def test_a_second_run_gives_the_same_bytes(self):
        self.assertEqual(produced(), produced())


if __name__ == "__main__":
    if "--update" in sys.argv:
        made = produced()
        MANIFEST.write_text("".join(f"{digest}  {name}\n" for name, digest in sorted(made.items())), encoding="utf-8")
        print(f"recorded {len(made)} files in {MANIFEST.relative_to(GOLDEN.parent.parent)}")
    else:
        unittest.main()
