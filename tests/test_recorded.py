"""The behaviour of the commands as recorded, so a refactor that changes a byte of it is seen.

    python3 tests/test_recorded.py --update     re-record every file (say why in the commit)
"""
import argparse
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tests.helpers import AS_OF, GOLDEN, run  # noqa: E402

# pull_ga.py is left out: it exits before argparse unless the google-analytics-data library is installed.
ENTRIES = ["copilot.py", "ledger.py", "radar.py", "pull_funnel.py", "pull_revenuecat.py",
           "pull_bigquery_telemetry.py"]
LEDGER_REPORT = ("ledger.py", "--store", "assets/sample/store", "--as-of", AS_OF, "report")


def copilot_commands():
    """Every command path of the copilot parser, two levels deep: ('status',), ('ads', 'campaigns'), ..."""
    import copilot
    paths = []

    def walk(parser, prefix, depth):
        for action in parser._actions:
            if isinstance(action, argparse._SubParsersAction):
                for name, sub in action.choices.items():
                    paths.append(prefix + (name,))
                    if depth < 2:
                        walk(sub, prefix + (name,), depth + 1)

    walk(copilot.build_parser(), (), 1)
    return sorted(set(paths))


def help_cases():
    """(golden file name, script, arguments) for every recorded help text."""
    cases = [(script[:-3] + ".txt", script, ("--help",)) for script in ENTRIES]
    cases += [("copilot-" + "-".join(path) + ".txt", "copilot.py", path + ("--help",)) for path in copilot_commands()]
    return cases


def update():
    (GOLDEN / "help").mkdir(parents=True, exist_ok=True)
    for name, script, args in help_cases():
        code, out, err = run(script, *args)
        if code != 0:
            sys.exit(f"{script} {' '.join(args)} exited {code}: {err}")
        (GOLDEN / "help" / name).write_text(out, encoding="utf-8")
    code, out, err = run(*LEDGER_REPORT)
    if code != 0:
        sys.exit(f"ledger report exited {code}: {err}")
    (GOLDEN / "ledger_report.txt").write_text(out, encoding="utf-8")
    print(f"recorded {len(help_cases())} help texts and the ledger report")


class Recorded(unittest.TestCase):
    maxDiff = None

    def test_help_texts_unchanged(self):
        for name, script, args in help_cases():
            with self.subTest(name=name):
                path = GOLDEN / "help" / name
                self.assertTrue(path.exists(), f"{name} is not recorded: run tests/test_recorded.py --update")
                code, out, _ = run(script, *args)
                self.assertEqual(code, 0)
                self.assertEqual(out, path.read_text(encoding="utf-8"))

    def test_no_stray_help_file(self):
        recorded = {p.name for p in (GOLDEN / "help").glob("*.txt")}
        self.assertEqual(recorded, {name for name, _, _ in help_cases()})

    def test_ledger_report_unchanged(self):
        code, out, _ = run(*LEDGER_REPORT)
        self.assertEqual(code, 0)
        self.assertEqual(out, (GOLDEN / "ledger_report.txt").read_text(encoding="utf-8"))


if __name__ == "__main__":
    if "--update" in sys.argv:
        update()
    else:
        unittest.main()
