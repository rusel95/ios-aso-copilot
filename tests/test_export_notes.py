"""The prose the export carries: a hypothesis's verdict reasoning, the newest decisions, the latest cycle report."""
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tests.helpers import SAMPLE, copy_store, exported_store, run  # noqa: E402

from aso import store as store_module  # noqa: E402
from aso.dashboard import clean, contract, export, export_notes  # noqa: E402

DAY = date(2026, 11, 14)


class VerdictReasoning(unittest.TestCase):
    def read(self, body: str):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "H001-x.md"
            path.write_text("---\nid: H001\n---\n\n" + body, encoding="utf-8")
            return export_notes.verdict_reasoning(path)

    def test_the_sample_hypotheses_carry_theirs(self):
        h = {x["id"]: x for x in export.hypotheses(SAMPLE, DAY)["hypotheses"]}
        self.assertEqual(h["H001"]["reasoning"]["date"], "2026-10-28")
        self.assertTrue(h["H001"]["reasoning"]["text"].startswith("**Judged 2026-10-28: `worked`.**"))
        self.assertEqual(h["H003"]["reasoning"]["date"], None)               # a heading with no day
        self.assertIsNone(h["H005"]["reasoning"])                             # nothing written

    def test_a_section_ends_at_the_next_heading_but_keeps_its_own_subheadings(self):
        got = self.read("## Verdict reasoning\n\nWhy.\n\n### Detail\n\nMore.\n\n## Amendment 2026-11-01\n\nNot this.\n")
        self.assertEqual(got, {"date": None, "text": "Why.\n\n### Detail\n\nMore."})

    def test_the_newest_day_wins_wherever_it_stands_in_the_file(self):
        got = self.read("## Verdict reasoning (2026-10-25)\n\nNewer.\n\n## Verdict reasoning (2026-09-26 post-window snapshot)\n\nOlder.\n")
        self.assertEqual(got, {"date": "2026-10-25", "text": "Newer."})

    def test_a_dated_section_beats_an_undated_one_and_of_two_undated_the_later_stands(self):
        self.assertEqual(self.read("## Verdict reasoning (2026-10-25)\n\nDated.\n\n## Verdict reasoning\n\nUndated.\n")["text"], "Dated.")
        self.assertEqual(self.read("## Verdict reasoning\n\nFirst.\n\n## Verdict reasoning\n\nSecond.\n")["text"], "Second.")

    def test_a_lead_in_before_the_words_is_still_the_reasoning(self):
        got = self.read("## Original verdict reasoning — recorded 2026-09-17\n\nBecause.\n")
        self.assertEqual(got, {"date": "2026-09-17", "text": "Because."})

    def test_no_section_or_an_empty_one_is_none(self):
        self.assertIsNone(self.read("## Reasoning\n\nBefore the window.\n"))
        self.assertIsNone(self.read("## Verdict reasoning\n\n## Amendment 2026-11-01\n\nSomething.\n"))

    def test_the_same_file_gives_the_same_bytes(self):
        a, b = export.hypotheses(SAMPLE, DAY), export.hypotheses(SAMPLE, DAY)
        self.assertEqual(contract.canonical(a), contract.canonical(b))


class Decisions(unittest.TestCase):
    def test_the_newest_come_first_and_a_tie_goes_to_the_later_entry(self):
        got = export_notes.decisions(SAMPLE, DAY)
        self.assertEqual([(d["date"], d["title"]) for d in got],
                         [("2026-11-12", "Stage the 1.0.1 keyword field"), ("2026-10-28", "Keep the moon phase key out of the next subtitle"),
                          ("2026-10-28", "Judge H001 as worked"), ("2026-10-01", "The first window is 21 days for a keyword change")])
        self.assertIn("**Decision**: record `worked`; keep the title.", got[2]["text"])
        self.assertFalse(any(d["truncated"] for d in got))

    def test_as_of_hides_later_entries(self):
        self.assertEqual([d["date"] for d in export_notes.decisions(SAMPLE, date(2026, 10, 28))], ["2026-10-28", "2026-10-28", "2026-10-01"])

    def test_only_the_newest_few_are_carried(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = copy_store(tmp)
            (store / "decisions.md").write_text("".join(f"## 2026-10-{n:02d} — Entry {n}\nBody.\n\n" for n in range(1, 21)), encoding="utf-8")
            got = export_notes.decisions(store, DAY)
        self.assertEqual(len(got), export_notes.DECISIONS_SHOWN)
        self.assertEqual(got[0]["title"], "Entry 20")

    def test_a_long_entry_is_cut_at_a_line_and_says_so(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = copy_store(tmp)
            (store / "decisions.md").write_text("## 2026-10-01 — Long\n" + "A line of the entry.\n" * 1000, encoding="utf-8")
            (got,) = export_notes.decisions(store, DAY)
        self.assertTrue(got["truncated"])
        self.assertLessEqual(len(got["text"]), export_notes.DECISION_CAP)
        self.assertTrue(got["text"].endswith("A line of the entry."))

    def test_a_heading_that_is_not_an_entry_is_reported_and_left_out(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = copy_store(tmp)
            with (store / "decisions.md").open("a", encoding="utf-8") as fh:
                fh.write("\n## Undated thoughts\nText.\n")
            store_module.PROBLEMS.clear()
            got = export_notes.decisions(store, DAY)
            self.assertEqual(len(got), 4)
            self.assertTrue(any("decisions.md" in where and "Undated thoughts" in why for where, why in store_module.PROBLEMS))
            store_module.PROBLEMS.clear()

    def test_no_file_is_no_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(export_notes.decisions(Path(tmp), DAY), [])


class CycleReport(unittest.TestCase):
    def test_the_newest_cycle_report_by_the_day_in_its_name(self):
        got = export_notes.cycle_report(SAMPLE, DAY)
        self.assertEqual((got["name"], got["date"], got["truncated"]), ("aso_cycle_2026-11-10.md", "2026-11-10", False))
        self.assertIn("| us | 5 | 2 |", got["text"])

    def test_as_of_hides_a_later_report(self):
        self.assertEqual(export_notes.cycle_report(SAMPLE, date(2026, 11, 9))["name"], "aso_cycle_2026-10-27.md")
        self.assertIsNone(export_notes.cycle_report(SAMPLE, date(2026, 10, 1)))

    def test_a_file_that_is_not_a_dated_cycle_report_is_not_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            reports = Path(tmp) / "reports"
            reports.mkdir()
            (reports / "aso_cycle_notes.md").write_text("undated", encoding="utf-8")
            (reports / "aso_audit_2026-11-01.md").write_text("an audit", encoding="utf-8")
            self.assertIsNone(export_notes.cycle_report(Path(tmp), DAY))
            (reports / "aso_full_cycle_2026-11-03.md").write_text("the one", encoding="utf-8")
            self.assertEqual(export_notes.cycle_report(Path(tmp), DAY)["name"], "aso_full_cycle_2026-11-03.md")

    def test_a_long_report_is_cut_and_says_so(self):
        with tempfile.TemporaryDirectory() as tmp:
            reports = Path(tmp) / "reports"
            reports.mkdir()
            (reports / "aso_cycle_2026-11-01.md").write_text("A line of the report.\n" * 5000, encoding="utf-8")
            got = export_notes.cycle_report(Path(tmp), DAY)
        self.assertTrue(got["truncated"])
        self.assertLessEqual(len(got["text"]), export_notes.REPORT_CAP)


class Catalog(unittest.TestCase):
    def test_the_catalog_states_the_limits_the_export_keeps(self):
        prose = contract.load_catalog()["prose"]
        self.assertEqual((prose["decisions"]["limit"], prose["decisions"]["cap"], prose["report"]["cap"]),
                         (export_notes.DECISIONS_SHOWN, export_notes.DECISION_CAP, export_notes.REPORT_CAP))
        self.assertEqual(sorted(prose), ["decisions", "reasoning", "report"])


class TheFile(unittest.TestCase):
    def test_the_file_is_valid_and_a_broken_one_fails(self):
        catalog = contract.load_catalog()
        notes = {**export.header(DAY), **export_notes.notes(SAMPLE, DAY)}
        self.assertEqual(contract.validate("notes.json", contract.canonical(notes), catalog), [])
        notes["report"]["text"] = " "
        self.assertTrue(contract.validate("notes.json", contract.canonical(notes), catalog))
        notes = {**export.header(DAY), **export_notes.notes(SAMPLE, DAY)}
        notes["decisions"][0].pop("title")
        self.assertTrue(contract.validate("notes.json", contract.canonical(notes), catalog))

    def test_a_hypothesis_with_a_malformed_reasoning_fails(self):
        catalog = contract.load_catalog()
        hyps = export.hypotheses(SAMPLE, DAY)
        hyps["hypotheses"][0]["reasoning"] = {"text": "no date key"}
        self.assertTrue(contract.validate("hypotheses.json", contract.canonical(hyps), catalog))

    def test_an_empty_store_gives_an_empty_file_that_is_valid(self):
        with tempfile.TemporaryDirectory() as tmp:
            notes = {**export.header(DAY), **export_notes.notes(Path(tmp), DAY)}
        self.assertEqual((notes["decisions"], notes["report"]), ([], None))
        self.assertEqual(contract.validate("notes.json", contract.canonical(notes), contract.load_catalog()), [])

    def test_export_writes_it_and_check_passes_on_the_same_day(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = copy_store(tmp)
            self.assertEqual(run("export_dashboard.py", "--store", str(store), "--as-of", "2026-11-14")[0], 0)
            self.assertTrue((store / "data" / "notes.json").is_file())
            code, out, _ = run("export_dashboard.py", "--store", str(store), "--as-of", "2026-11-14", "--check")
            self.assertEqual(code, 0, out)


class Clean(unittest.TestCase):
    """The prose is published with the rest of data/, so the clean check reads it like everything else."""

    def refused(self, edit):
        with tempfile.TemporaryDirectory() as tmp:
            store = copy_store(tmp)
            edit(store)
            from aso.dashboard import export as exporter
            files, _ = exporter.build_all(store, DAY)
            exporter.write(store, files)
            return clean.check(store / "data", store)

    def append(self, relative: str, text: str):
        def edit(store):
            with (store / relative).open("a", encoding="utf-8") as fh:
                fh.write(text)
        return edit

    def test_an_address_in_a_verdict_reasoning_is_refused_by_file_and_kind(self):
        problems = self.refused(self.append("hypotheses/H003-us-moon-phase.md", "\nAsk owner@example.com.\n"))
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("hypotheses.json", problems[0])
        self.assertIn("e-mail", problems[0])
        self.assertNotIn("owner@example.com", problems[0])

    def test_a_token_in_a_decision_or_in_the_report_is_refused(self):
        token = "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822c"
        for relative, text in (("decisions.md", f"\n## 2026-11-13 — Key\nkey {token}\n"),
                               ("reports/aso_cycle_2026-11-10.md", f"\nkey {token}\n")):
            with self.subTest(file=relative):
                problems = self.refused(self.append(relative, text))
                self.assertEqual(len(problems), 1, problems)
                self.assertIn("notes.json", problems[0])
                self.assertIn("key", problems[0])

    def test_what_the_owner_lists_is_found_in_the_prose_too(self):
        def edit(store):
            (store / "config.md").write_text((store / "config.md").read_text(encoding="utf-8").replace(
                "**Never publish**: none", "**Never publish**: Invented for the sample store"), encoding="utf-8")
        problems = self.refused(edit)
        self.assertTrue(any(p.startswith("notes.json:") for p in problems), problems)
        self.assertTrue(any(p.startswith("hypotheses.json:") for p in problems), problems)

    def test_the_stores_own_identifier_is_masked_in_the_prose_and_the_export_says_so(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = exported_store(tmp)
            with (store / "decisions.md").open("a", encoding="utf-8") as fh:
                fh.write("\n## 2026-11-13 — Account\nThe app 1000000001 was checked.\n")
            with (store / "hypotheses" / "H003-us-moon-phase.md").open("a", encoding="utf-8") as fh:     # its reasoning is the last section
                fh.write("\nApp 1000000001 again.\n")
            files, notes = export.build_all(store, DAY)
        self.assertIn("The app [redacted] was checked.", files["notes.json"]["decisions"][0]["text"])
        self.assertTrue(any("notes.json" in n and "masked" in n for n in notes), notes)
        self.assertTrue(any("hypotheses.json" in n and "masked" in n for n in notes), notes)
        reasoning = next(h for h in files["hypotheses.json"]["hypotheses"] if h["id"] == "H003")["reasoning"]["text"]
        self.assertIn("App [redacted] again.", reasoning)


if __name__ == "__main__":
    unittest.main()
