"""The SwiftBar plugin prints a title, a `---` line and one block per store; it reads files and never the network."""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tests.helpers import ROOT, copy_store  # noqa: E402

PLUGIN = ROOT / "assets" / "swiftbar" / "ios-aso-copilot.5m.sh"
SCRIPTS = ["ios-aso-copilot.5m.sh", "aso-run.sh", "install.sh"]


def plugin(stores_file: Path, home: Path):
    env = {**os.environ, "ASO_STORES": str(stores_file), "HOME": str(home)}
    done = subprocess.run(["/bin/bash", str(PLUGIN)], capture_output=True, text=True, env=env)
    return done.returncode, done.stdout.splitlines()


class SwiftBarPluginTest(unittest.TestCase):
    def test_scripts_parse(self):
        for name in SCRIPTS:
            done = subprocess.run(["/bin/bash", "-n", str(ROOT / "assets" / "swiftbar" / name)], capture_output=True, text=True)
            self.assertEqual(done.returncode, 0, f"{name}: {done.stderr}")

    def test_no_stores_says_where_to_add_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, lines = plugin(Path(tmp) / "missing", Path(tmp))
            self.assertEqual(code, 0)
            self.assertEqual(lines[0], "ASO ?")
            self.assertEqual(lines[1], "---")
            self.assertIn("No stores yet", lines[2])

    def test_store_that_does_not_exist_is_named(self):
        with tempfile.TemporaryDirectory() as tmp:
            conf = Path(tmp) / "stores"
            conf.write_text(f"# a comment\n{tmp}/nowhere/marketing\n", encoding="utf-8")
            code, lines = plugin(conf, Path(tmp))
            self.assertEqual(code, 0)
            self.assertTrue(any("store not found" in line for line in lines))

    def test_sample_store_shows_due_sweep_date_and_actions(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = copy_store(tmp)
            conf = Path(tmp) / "stores"
            conf.write_text(f"{store}\n", encoding="utf-8")
            code, lines = plugin(conf, Path(tmp))
            self.assertEqual(code, 0)
            self.assertRegex(lines[0], r"^ASO( \d+| ✓| ⟳)$")
            self.assertEqual(lines[1], "---")
            text = "\n".join(lines)
            self.assertIn(" due · ", text)
            self.assertIn("Last rank sweep: 20", text)
            self.assertIn("aso-run.sh", text)
            self.assertTrue((Path(tmp) / ".cache" / "ios-aso-copilot" / "swiftbar-last-run").exists())


if __name__ == "__main__":
    unittest.main()
