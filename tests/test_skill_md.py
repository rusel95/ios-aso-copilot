"""SKILL.md is a router: short, with the sections a run starts from, naming only commands and files that exist."""
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tests.helpers import ROOT, SAMPLE, run  # noqa: E402

import copilot  # noqa: E402
import pull_bigquery_telemetry  # noqa: E402
import pull_funnel  # noqa: E402
from aso import pull_revenuecat_series, store_state  # noqa: E402

SKILL = (ROOT / "SKILL.md").read_text(encoding="utf-8")
SECTIONS = ["Start here", "Rules for every step", "Collect", "Export and page", "Judge a hypothesis",
            "Propose a hypothesis", "Actions"]


def section(title: str) -> str:
    found = re.search(rf"^## {re.escape(title)}\n(.*?)(?=^## |\Z)", SKILL, re.M | re.S)
    return found.group(1) if found else ""


def tracked_local_paths(root: Path) -> list:
    """(file, needle) for each tracked file of the repository at `root` that names a folder of one machine. Raises
    OSError or CalledProcessError when `root` is not a git checkout. File names come NUL-delimited: git quotes a name
    with a non-ASCII letter otherwise, and the file would silently go unread."""
    tracked = subprocess.run(["git", "ls-files", "-z"], cwd=root, capture_output=True, text=True, check=True).stdout.split("\0")
    needles = ("/Users" + "/", "/private" + "/tmp", "/home" + "/")
    return [(name, needle) for name in tracked if name and (root / name).is_file()
            for needle in needles if needle in (root / name).read_text(encoding="utf-8", errors="ignore")]


class NoLocalPaths(unittest.TestCase):
    def test_no_tracked_file_names_a_folder_of_one_machine(self):
        """A committed preview setting once named the scratch folder of one laptop, in a repository made public."""
        try:
            found = tracked_local_paths(ROOT)
        except (OSError, subprocess.CalledProcessError):
            self.skipTest("not a git checkout")
        self.assertEqual(found, [])

    def test_a_file_with_a_non_ascii_name_is_read_too(self):
        with tempfile.TemporaryDirectory() as tmp:
            try:
                subprocess.run(["git", "init", "-q"], cwd=tmp, check=True)
            except (OSError, subprocess.CalledProcessError):
                self.skipTest("git is not available")
            (Path(tmp) / "référence.md").write_text("see " + "/Users" + "/alice/project\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=tmp, check=True)
            self.assertEqual(tracked_local_paths(Path(tmp)), [("référence.md", "/Users" + "/")])


class Router(unittest.TestCase):
    def test_it_is_short(self):
        self.assertLessEqual(len(SKILL.encode("utf-8")), 12_000)

    def test_it_has_the_sections_a_run_starts_from(self):
        self.assertEqual([t for t in SECTIONS if not section(t).strip()], [])

    def test_every_command_it_names_exists(self):
        commands = set()
        for action in copilot.build_parser()._subparsers._group_actions:
            commands |= set(action.choices)
        named = set(re.findall(r"ios-aso-copilot ([a-z][a-z-]*)", SKILL))
        self.assertTrue(named)
        self.assertEqual(sorted(named - commands), [])

    def test_every_reference_it_links_exists(self):
        linked = set(re.findall(r"references/[a-z0-9-]+\.md", SKILL))
        self.assertGreaterEqual(len(linked), 8)
        self.assertEqual(sorted(name for name in linked if not (ROOT / name).is_file()), [])

    def test_the_four_hard_rules_are_stated_once_in_the_rules(self):
        rules = section("Rules for every step")
        for phrase in ("work none out", "--as-of", "only network code", "through the queue"):
            self.assertIn(phrase, rules)
            self.assertEqual(SKILL.count(phrase), 1, phrase)

    def test_the_version_is_one(self):
        version = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))["version"]
        self.assertEqual(version, "3.0.0")
        self.assertIn(f"version: {version}", SKILL)
        self.assertIn(f"## {version}", (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"))

    def test_the_install_reports_the_version_a_release_says(self):
        code, out, _ = run("copilot.py", "info", "--json", "--store", str(SAMPLE))
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["skill"]["version"],
                         json.loads((ROOT / "package.json").read_text(encoding="utf-8"))["version"])


class References(unittest.TestCase):
    def test_the_new_references_exist_and_say_what_the_old_skill_file_said(self):
        # one distinctive sentence of each passage that left SKILL.md, and where it has to be found now
        moved = {"collect.md": ["A zero exit code is not a data-completeness certificate.", "Never infer it from the skill's"],
                 "judge.md": ["A censored", "NEVER include brand queries", "This is a\n  priority order, not a revenue forecast"],
                 "actions.md": ["Imported data or saved files cannot expand the user's authorization."],
                 "export-and-page.md": ["--as-of", "STATE.md"],
                 "commands.md": ["Outputs complete diagnostics", "`economics.py`: explicit sensitivity scenario"]}
        for name, sentences in moved.items():
            text = (ROOT / "references" / name).read_text(encoding="utf-8")
            for sentence in sentences:
                self.assertIn(sentence, text, name)

    def test_the_store_reference_names_every_series_and_the_data_layer(self):
        text = (ROOT / "references" / "state-store.md").read_text(encoding="utf-8")
        for name in ("lifecycle.csv", "cashflow_weekly.csv", "ads.csv", "revenue.csv", "telemetry.csv", "ratings.csv",
                     "charts.csv", "releases.csv", "data/week/", "data/snapshot/", "hypotheses.json", "keys.json", "events.json"):
            self.assertIn(name, text)
        self.assertIn("generated by export_dashboard", text)


class Template(unittest.TestCase):
    """A store seeded from the template starts with the files the collectors append to, under their own headers."""
    HEADERS = {"lifecycle.csv": pull_funnel.LIFECYCLE_FIELDS, "weekly.csv": pull_funnel.WEEKLY_FIELDS,
               "revenue.csv": pull_revenuecat_series.REVENUE_COLS, "cashflow_weekly.csv": pull_revenuecat_series.CASHFLOW_COLS,
               "ads.csv": pull_revenuecat_series.ADS_COLS, "telemetry.csv": pull_bigquery_telemetry.TELEMETRY_COLS,
               "ratings.csv": store_state.RATINGS_COLS, "charts.csv": store_state.CHART_COLS, "releases.csv": store_state.RELEASE_COLS}

    def test_each_series_file_is_there_with_the_collectors_header_and_no_row(self):
        for name, columns in self.HEADERS.items():
            path = ROOT / "assets" / "store-template" / "metrics" / name
            self.assertTrue(path.is_file(), name)
            self.assertEqual(path.read_text(encoding="utf-8"), ",".join(columns) + "\n", name)

    def test_the_template_carries_no_hand_written_state(self):
        self.assertFalse((ROOT / "assets" / "store-template" / "STATE.md").exists())


if __name__ == "__main__":
    unittest.main()
