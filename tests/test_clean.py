"""The clean check: what must not be in data/ before it is published."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tests.helpers import exported_store, run  # noqa: E402

from aso.dashboard import clean  # noqa: E402


class Clean(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = exported_store(self.tmp.name)
        self.data = self.store / "data"

    def plant(self, text, name="events.json"):
        path = self.data / name
        path.write_text(path.read_text(encoding="utf-8") + text + "\n", encoding="utf-8")

    def test_the_samples_own_data_passes(self):
        self.assertEqual(clean.check(self.data, self.store), [])

    def test_the_stores_own_identifiers_are_flagged_and_the_file_is_named(self):
        self.plant('"app": 1000000001', "week/2026-11-02.json")          # the sample's App ID
        problems = clean.check(self.data, self.store)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("week/2026-11-02.json", problems[0])
        self.assertIn("App ID", problems[0])
        self.assertNotIn("1000000001", problems[0])                      # the report does not repeat the value

    def test_a_longer_number_holding_the_identifier_is_not_it(self):
        self.plant('"impressions": 91000000001')
        self.assertEqual(clean.check(self.data, self.store), [])

    def test_every_configured_identifier_is_looked_for(self):
        with (self.store / "config.md").open("a", encoding="utf-8") as fh:
            fh.write("**Provider Token**: 7654321\n**GA4 Property ID**: 345678901\n**Firebase Project ID**: demo-tide-1a2b3\n"
                     "**RevenueCat Project ID**: proj9z8y7x\n")
        self.plant("demo-tide-1a2b3 and proj9z8y7x and 345678901 and 7654321")
        named = " ".join(clean.check(self.data, self.store))
        for label in ("Provider Token", "GA4 Property ID", "Firebase Project ID", "RevenueCat Project ID"):
            self.assertIn(label, named)

    def test_a_value_written_in_backticks_or_quotes_is_still_looked_for(self):
        with (self.store / "config.md").open("a", encoding="utf-8") as fh:
            fh.write('**GA4 Property ID**: `345678901`\n**GA4 Stream ID**: "9876543210"\n**Firebase Project Number**: 112233445566 (prod)\n'
                     "**Bundle ID**: com.example.tidepool\n")
        self.plant("345678901 9876543210 112233445566 com.example.tidepool")
        named = " ".join(clean.check(self.data, self.store))
        for label in ("GA4 Property ID", "GA4 Stream ID", "Firebase Project Number", "Bundle ID"):
            self.assertIn(label, named)

    def test_an_address_and_anything_shaped_like_a_key_are_flagged(self):
        for text, word in (("write to owner@example.com", "e-mail"),
                           ("-----BEGIN PRIVATE KEY-----", "key"),
                           ("token 9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822c", "key"),
                           ("eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N", "key")):
            store = exported_store(tempfile.mkdtemp(dir=self.tmp.name))
            path = store / "data" / "events.json"
            path.write_text(path.read_text(encoding="utf-8") + text + "\n", encoding="utf-8")
            problems = clean.check(store / "data", store)
            self.assertEqual(len(problems), 1, (text, problems))
            self.assertIn(word, problems[0])
            self.assertIn("events.json", problems[0])

    def test_ordinary_long_words_are_not_keys(self):
        self.plant("Rindfleischetikettierungsueberwachungsaufgabenuebertragungsgesetz H081-a-very-long-hypothesis-slug-of-2026")
        self.assertEqual(clean.check(self.data, self.store), [])

    def test_the_export_masks_the_stores_own_identifiers_in_prose(self):
        """A person types an account id into a confound; the export does not carry it into data/, and says so."""
        import datetime as dt
        from aso.dashboard import export
        path = self.store / "hypotheses" / "H005-ua-tide-phrases.md"
        text = path.read_text(encoding="utf-8").replace("confounds: []", 'confounds:\n  - "seen in app 1000000001, and in 91000000001 rows"')
        path.write_text(text, encoding="utf-8")
        files, notes = export.build_all(self.store, dt.date(2026, 11, 14))
        confound = next(h for h in files["hypotheses.json"]["hypotheses"] if h["id"] == "H005")["confounds"][0]
        self.assertEqual(confound, "seen in app [redacted], and in 91000000001 rows")        # a longer number is not the id
        self.assertTrue(any("hypotheses.json" in n and "masked" in n and "App ID" in n for n in notes), notes)
        export.write(self.store, files)
        self.assertEqual(clean.check(self.data, self.store), [])

    def decide(self, line):
        """The store's config.md with its `**Never publish**:` line replaced by `line`, or removed when it is None."""
        path = self.store / "config.md"
        kept = [l for l in path.read_text(encoding="utf-8").splitlines() if not l.startswith("**Never publish**")]
        path.write_text("\n".join(kept + ([line] if line is not None else [])) + "\n", encoding="utf-8")

    def test_what_the_owner_lists_is_flagged(self):
        self.decide('**Never publish**: "proceeds_usd"; "ad_spend_usd"')
        problems = clean.check(self.data, self.store)
        self.assertTrue(problems and all("Never publish" in p for p in problems), problems)
        self.assertTrue(any("week/2026-11-02.json" in p and '"proceeds_usd"' in p for p in problems))
        self.assertTrue(any('"ad_spend_usd"' in p for p in problems))

    def test_nothing_is_published_until_the_owner_has_decided(self):
        """A gate that passes while nobody has said what is private publishes the revenue and the keyword basket."""
        for line in (None, "**Never publish**:", "**Never publish**: TODO — decide before publish"):
            self.decide(line)
            problems = clean.check(self.data, self.store)
            self.assertEqual(len(problems), 1, (line, problems))
            self.assertIn("**Never publish**", problems[0])
            self.assertIn("none", problems[0])                                   # and how to say that nothing is held back
            code, out, _ = run("copilot.py", "check", "--store", str(self.store))
            self.assertEqual(code, 1, line)

    def test_none_is_a_decision(self):
        self.decide("**Never publish**: none")
        self.assertEqual(clean.check(self.data, self.store), [])
        self.decide("**Never publish**: NONE")
        self.assertEqual(clean.check(self.data, self.store), [])

    def test_a_pattern_that_is_not_one_is_named_and_does_not_crash_the_check(self):
        self.decide('**Never publish**: "proceeds_usd"; (unclosed')
        problems = clean.check(self.data, self.store)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("(unclosed", problems[0])
        self.assertIn("regular expression", problems[0])

    def test_publish_refuses_while_the_owner_has_not_decided(self):
        import subprocess
        self.decide(None)
        subprocess.run(["git", "init", "-q", "--bare", str(Path(self.tmp.name) / "r.git")], check=True)
        code, out, _ = run("copilot.py", "publish", "--store", str(self.store), "--remote", str(Path(self.tmp.name) / "r.git"))
        self.assertEqual(code, 1)
        self.assertIn("Never publish", out)
        self.assertIn("FAIL publish", out)

    def test_the_command(self):
        code, out, err = run("copilot.py", "check", "--store", str(self.store))
        self.assertEqual((code, out.strip()), (0, "PASS clean"), err)
        self.plant('"app": 1000000001')
        code, out, _ = run("copilot.py", "check", "--store", str(self.store))
        self.assertEqual(code, 1)
        self.assertEqual(len(out.strip().splitlines()), 1)
        self.assertIn("events.json", out)

    def test_no_data_folder_is_a_problem_not_a_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            empty = Path(tmp)
            self.assertTrue(clean.check(empty / "data", empty))


if __name__ == "__main__":
    unittest.main()
