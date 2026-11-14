"""The two workflow templates an app repository may copy: the page, and the scheduled rank reads."""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tests.helpers import ROOT  # noqa: E402

WORKFLOWS = ROOT / "assets" / "workflows"


def read(name: str) -> str:
    path = WORKFLOWS / name
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def runs(text: str) -> str:
    """Everything the workflow executes, comments dropped."""
    return "\n".join(line.split(" #", 1)[0] for line in text.splitlines() if not line.lstrip().startswith("#"))


class Shape(unittest.TestCase):
    def test_both_are_workflows(self):
        for name in ("aso-dashboard.yml", "rank-reads.yml"):
            text = read(name)
            self.assertTrue(text, name)
            self.assertNotIn("\t", text, name)
            for key in ("name", "on", "jobs"):
                self.assertRegex(text, rf"(?m)^{key}:", f"{name}: no top-level {key}")

    def test_the_skill_is_checked_out_at_a_full_commit_hash(self):
        for name in ("aso-dashboard.yml", "rank-reads.yml"):
            self.assertRegex(read(name), r"repository: rusel95/ios-aso-copilot\n\s+ref: [0-9a-f]{40}\b", name)

    def test_neither_holds_a_source_credential(self):
        for name in ("aso-dashboard.yml", "rank-reads.yml"):
            self.assertNotRegex(runs(read(name)), r"secrets\.|API_KEY|PRIVATE_KEY|\.p8\b|GOOGLE_APPLICATION_CREDENTIALS", name)


class Dashboard(unittest.TestCase):
    def test_it_proves_the_data_then_builds_and_collects_nothing(self):
        text = runs(read("aso-dashboard.yml"))
        order = [text.find(step) for step in ("export_dashboard.py", "copilot.py check", "build_site.py")]
        self.assertTrue(all(at >= 0 for at in order), order)
        self.assertEqual(order, sorted(order))                       # a page is built only from data that passed
        self.assertRegex(text, r"export_dashboard\.py .*--as-of .*--check")
        for word in ("collect", "cycle", "refresh", "pull_", "git push", "git commit"):
            self.assertNotIn(word, text, word)

    def test_it_may_read_the_repository_and_publish_pages_and_nothing_more(self):
        text = read("aso-dashboard.yml")
        self.assertRegex(text, r"(?m)^permissions:\n  contents: read\n  pages: write\n  id-token: write\n")


class RankReads(unittest.TestCase):
    def test_it_runs_by_hand_and_on_a_schedule(self):
        text = read("rank-reads.yml")
        self.assertIn("workflow_dispatch:", text)
        self.assertRegex(text, r"schedule:\n\s+- cron: \"[^\"]+\"")

    def test_it_asks_what_is_due_then_reads_only_those_storefronts(self):
        text = runs(read("rank-reads.yml"))
        due, refresh = text.find("copilot.py due"), text.find("ledger.py --store marketing refresh")
        self.assertTrue(0 <= due < refresh, (due, refresh))
        self.assertRegex(text, r"refresh --bundle \"\$BUNDLE\" --markets \"\$MARKETS\"")
        self.assertIn("(missed)", text)                              # a day gone by cannot be read any more
        self.assertNotIn("collect", text)

    def test_it_commits_the_observations_and_nothing_else(self):
        text = runs(read("rank-reads.yml"))
        self.assertEqual(re.findall(r"git add (.+)", text), ["marketing/metrics/ranks.csv"])
        self.assertNotRegex(text, r"git add (-A|\.|--all)|git commit -a")


class PublishReference(unittest.TestCase):
    def test_it_says_what_is_decided_first_and_how_to_install(self):
        text = (ROOT / "references" / "publish.md").read_text(encoding="utf-8")
        for needed in ("public", "private", "NEVER_PUBLISH", "assets/workflows/aso-dashboard.yml", "assets/workflows/rank-reads.yml",
                       ".github/workflows/", "full commit hash", "no source credential"):
            self.assertIn(needed, text)


if __name__ == "__main__":
    unittest.main()
