"""The export command: what it prints, what it exits with, and that it leaves the sample store alone."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tests.helpers import AS_OF, SAMPLE, SAMPLE_FILES as N, copy_store, run  # noqa: E402


class ExportCommand(unittest.TestCase):
    def test_export_then_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = copy_store(tmp)
            code, out, err = run("export_dashboard.py", "--store", str(store), "--as-of", AS_OF)
            self.assertEqual(code, 0, out + err)
            lines = out.splitlines()
            self.assertEqual(len([line for line in lines if line.startswith("WROTE ") and line != "WROTE STATE.md"]), N)
            self.assertIn("WROTE STATE.md", lines)
            self.assertIn("WROTE week/2026-11-02.json", lines)
            self.assertTrue(any(line.startswith("NOTE ") and "weekly.csv" in line for line in lines))
            self.assertEqual(lines[-1], f"PASS export ({N} written, 0 unchanged, 0 removed)")
            self.assertTrue((store / "data" / "hypotheses.json").is_file())

            code, out, _ = run("export_dashboard.py", "--store", str(store), "--as-of", AS_OF)
            self.assertEqual(out.splitlines()[-1], f"PASS export (0 written, {N} unchanged, 0 removed)")

            code, out, _ = run("export_dashboard.py", "--store", str(store), "--as-of", AS_OF, "--check")
            self.assertEqual((code, out.splitlines()[-1]), (0, f"PASS check ({N} files)"))

            (store / "data" / "events.json").write_text("{}\n", encoding="utf-8")
            code, out, _ = run("export_dashboard.py", "--store", str(store), "--as-of", AS_OF, "--check")
            self.assertEqual((code, out.splitlines()[-1]), (1, "FAIL check: events.json"))

    def test_an_earlier_day_than_the_data_holds_is_refused_unless_rewound(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = copy_store(tmp)
            run("export_dashboard.py", "--store", str(store), "--as-of", AS_OF)
            held = sorted(p.name for p in (store / "data" / "snapshot").glob("*.json"))
            code, out, _ = run("export_dashboard.py", "--store", str(store), "--as-of", "2026-10-20")
            self.assertEqual(code, 1)
            self.assertIn("--rewind", out)
            self.assertEqual(sorted(p.name for p in (store / "data" / "snapshot").glob("*.json")), held)     # nothing was removed
            code, out, _ = run("export_dashboard.py", "--store", str(store), "--as-of", "2026-10-20", "--check")
            self.assertNotIn("--rewind", out)                                                              # a comparison writes nothing
            code, out, _ = run("export_dashboard.py", "--store", str(store), "--as-of", "2026-10-20", "--rewind")
            self.assertEqual(code, 0, out)
            self.assertIn("REMOVED ", out)

    def test_a_damaged_day_file_does_not_hide_a_newer_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = copy_store(tmp)
            run("export_dashboard.py", "--store", str(store), "--as-of", AS_OF)
            (store / "data" / "events.json").write_text("{}\n", encoding="utf-8")                # keys.json still says AS_OF
            code, out, _ = run("export_dashboard.py", "--store", str(store), "--as-of", "2026-10-20")
            self.assertEqual(code, 1)
            self.assertIn("--rewind", out)
            code, out, _ = run("export_dashboard.py", "--store", str(store), "--as-of", AS_OF)     # the same day repairs it
            self.assertEqual(code, 0, out)
            for name in ("events.json", "keys.json", "hypotheses.json"):                            # no entity says its day
                (store / "data" / name).write_text("{}\n", encoding="utf-8")
            code, out, _ = run("export_dashboard.py", "--store", str(store), "--as-of", AS_OF)
            self.assertEqual(code, 1)
            self.assertIn("none says which day", out)
            self.assertEqual(run("export_dashboard.py", "--store", str(store), "--as-of", AS_OF, "--rewind")[0], 0)

    def test_check_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = copy_store(tmp)
            code, out, _ = run("export_dashboard.py", "--store", str(store), "--as-of", AS_OF, "--check")
            self.assertEqual(code, 1)
            self.assertFalse((store / "data").exists())

    def test_as_of_is_required_and_the_store_must_exist(self):
        code, _, err = run("export_dashboard.py", "--store", str(SAMPLE))
        self.assertEqual(code, 2)
        self.assertIn("--as-of", err)
        code, _, err = run("export_dashboard.py", "--store", "/nonexistent/store", "--as-of", AS_OF)
        self.assertEqual(code, 2)

    def test_the_sample_store_is_never_written(self):
        self.assertFalse((SAMPLE / "data").exists())

    def test_copilot_export_uses_today_and_says_so(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = copy_store(tmp)
            code, out, err = run("copilot.py", "export", "--store", str(store), "--as-of", AS_OF)
            self.assertEqual(code, 0, out + err)
            self.assertEqual(out.splitlines()[0], f"as of {AS_OF}")
            self.assertEqual(out.splitlines()[-1], f"PASS export ({N} written, 0 unchanged, 0 removed)")
            code, out, _ = run("copilot.py", "export", "--store", str(store), "--check")
            self.assertRegex(out.splitlines()[0], r"^as of \d{4}-\d{2}-\d{2}$")


if __name__ == "__main__":
    unittest.main()
