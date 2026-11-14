"""The collection pass runs its independent sources at the same time, and still reads top to bottom."""
import argparse
import contextlib
import io
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tests.helpers import copy_store  # noqa: E402

import pull_funnel  # noqa: E402
from aso.commands import collect, cycle  # noqa: E402

WAIT = 5        # seconds a test waits for the other threads before it calls the run sequential


def run(stages, jobs):
    with contextlib.redirect_stdout(io.StringIO()) as said, contextlib.redirect_stderr(io.StringIO()):
        clean = cycle.run_stages(stages, jobs)
    return clean, said.getvalue()


class Stages(unittest.TestCase):
    def test_they_run_at_the_same_time(self):
        together = threading.Barrier(3, timeout=WAIT)        # passes only if all three are inside a stage at once

        def stage():
            together.wait()
            print("  read")
            return True
        clean, said = run([("One", stage), ("Two", stage), ("Three", stage)], jobs=3)
        self.assertEqual(clean, [True, True, True])
        self.assertEqual(said.count("  read"), 3)

    def test_the_output_is_in_stage_order_whichever_finishes_first(self):
        second_done = threading.Event()

        def slow():
            second_done.wait(WAIT)
            print("  the slow one")
            return True

        def fast():
            print("  the fast one")
            second_done.set()
            return True
        _, said = run([("Slow", slow), ("Fast", fast)], jobs=2)
        self.assertEqual([line for line in said.splitlines() if line.strip()],
                         ["▶ [1/2] Slow...", "  the slow one", "▶ [2/2] Fast...", "  the fast one"])

    def test_a_stage_that_breaks_says_why_and_the_others_finish(self):
        def broken():
            raise RuntimeError("the source is down\nand a traceback nobody reads")
        clean, said = run([("Broken", broken), ("Fine", lambda: print("  fine") or True)], jobs=2)
        self.assertEqual(clean, [False, True])
        self.assertIn("⚠️ Broken failed: the source is down", said)
        self.assertNotIn("traceback nobody reads", said)
        self.assertIn("  fine", said)

    def test_one_job_runs_them_in_order_and_prints_as_it_goes(self):
        seen = []

        def stage(name):
            def body():
                seen.append((name, threading.current_thread() is threading.main_thread()))
                return True
            return body
        run([("A", stage("a")), ("B", stage("b")), ("C", stage("c"))], jobs=1)
        self.assertEqual(seen, [("a", True), ("b", True), ("c", True)])


class ThePlan(unittest.TestCase):
    def plan(self, **flags):
        with tempfile.TemporaryDirectory() as tmp:
            store = copy_store(tmp)
            args = argparse.Namespace(store=str(store), skip_pull=False, skip_ga=False, skip_rc=False, ranks=False, jobs=6)
            vars(args).update(flags)
            together, after = cycle.stage_plan(args, store, {"app_id": "1000000001", "brand": "tidepool", "version": "1.0.0",
                                                             "ga4_property_id": None, "rc_project_id": None})
            return [title for title, _ in together], [title for title, _ in after]

    def test_the_sources_run_together_and_the_ledger_report_after_them(self):
        together, after = self.plan()
        self.assertEqual(len(together), 7)
        self.assertEqual(len(after), 1)
        self.assertIn("Ledger", after[0])
        self.assertFalse(any("Rank Sweep" in title for title in together))

    def test_the_rank_sweep_joins_them_when_asked(self):
        together, after = self.plan(ranks=True)
        self.assertEqual(len(together), 8)
        self.assertTrue(any("Rank Sweep" in title for title in together))
        self.assertIn("Ledger", after[0])              # the report reads the sweep: it waits for it

    def test_a_sweep_needs_the_bundle_id_from_the_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = copy_store(tmp)
            with contextlib.redirect_stdout(io.StringIO()) as said, \
                    mock.patch.object(cycle.subprocess, "Popen", side_effect=AssertionError("must not run")):
                self.assertFalse(cycle.stage_ranks(store))
            self.assertIn("Bundle ID", said.getvalue())


class FunnelCache(unittest.TestCase):
    """The daily reports are immutable once published: the skill's collector keeps them per app and asks only for
    the days it does not hold, so a pass after the first takes minutes."""

    def test_the_skills_collector_resumes_in_one_folder_per_app(self):
        own = collect.SKILL_DIR / "scripts" / "pull_funnel.py"
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"XDG_CACHE_HOME": tmp}):
            store = copy_store(tmp)
            first, raw1, _ = collect.prepare_funnel_pull(own, store, "1000000001")
            second, raw2, _ = collect.prepare_funnel_pull(own, store, "1000000001")
            _, other, _ = collect.prepare_funnel_pull(own, store, "2000000002")
            self.assertEqual(raw1, raw2)
            self.assertEqual(raw1, Path(tmp).resolve() / "ios-aso-copilot" / "funnel" / "1000000001")
            self.assertNotEqual(raw1, other)                # two projects never share a folder
            self.assertIn("--resume", first)
            self.assertEqual(first, second)

    def test_the_three_reports_are_asked_for_at_once(self):
        together = threading.Barrier(3, timeout=WAIT)

        def fetch(request_id, report, raw_dir, prefix, **_):
            together.wait()
            return [], 0, 0, None
        with tempfile.TemporaryDirectory() as tmp:
            argv = ["pull_funnel.py", "--app", "1000000001", "--out", tmp, "--raw-dir", str(Path(tmp) / "raw")]
            with mock.patch.object(pull_funnel, "request_and_reports", return_value=("req", {})), \
                    mock.patch.object(pull_funnel, "snapshot_reports", return_value=None), \
                    mock.patch.object(pull_funnel, "fetch_report", side_effect=fetch), mock.patch.object(sys, "argv", argv), \
                    contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()) as said:
                pull_funnel.main()
            self.assertNotIn("Partial funnel stage", said.getvalue())      # no thread timed out waiting for the others

    def test_a_folder_left_by_an_older_request_starts_over_and_another_apps_folder_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp)
            pull_funnel.save_manifest(raw, {"app_id": "1000000001", "request_id": "old", "reports": {"r14": {"x": ["y"]}}})
            self.assertEqual(pull_funnel.load_manifest(raw, "new", app_id="1000000001"),
                             {"app_id": "1000000001", "request_id": "new", "reports": {}})
            with self.assertRaises(RuntimeError):
                pull_funnel.load_manifest(raw, "old", app_id="2000000002")


if __name__ == "__main__":
    unittest.main()


class WhereTheFetchSettingsComeFrom(unittest.TestCase):
    """A project names its own credentials in its config.md; when that file is not on this machine, the machine's
    own settings are used rather than a path that leads nowhere."""

    def test_the_projects_own_file_wins_when_it_exists(self):
        from aso.store import credentials_path
        with tempfile.TemporaryDirectory() as tmp:
            key = Path(tmp) / "key.json"
            key.write_text("{}", encoding="utf-8")
            self.assertEqual(credentials_path(str(key), {"GOOGLE_APPLICATION_CREDENTIALS": "/global.json"}), (str(key), ""))

    def test_a_named_file_that_is_missing_falls_back_to_the_machines_settings_and_says_so(self):
        from aso.store import credentials_path
        path, said = credentials_path("/nowhere/app-adc.json", {"GOOGLE_APPLICATION_CREDENTIALS": "/global.json"})
        self.assertEqual(path, "/global.json")
        self.assertIn("/nowhere/app-adc.json", said)
        path, said = credentials_path("/nowhere/app-adc.json", {})
        self.assertIsNone(path)              # the client library then looks for gcloud's application-default login
        self.assertIn("gcloud auth application-default login", said)

    def test_nothing_named_is_not_a_warning(self):
        from aso.store import credentials_path
        self.assertEqual(credentials_path("", {}), (None, ""))


class TheLatestObservation(unittest.TestCase):
    """History can be ingested after the fact, so the last line of ranks.csv is not always a key's newest read."""

    def test_a_key_is_retried_by_its_newest_day_not_its_last_line(self):
        from aso.ledger_ingest import refresh_basket
        rows = [{"date": "2026-11-02", "market": "us", "keyword": "tide times", "group": "target", "status": "error"},
                {"date": "2026-11-02", "market": "us", "keyword": "moon phase", "group": "asa-observed", "status": "ok"},
                {"date": "2026-08-26", "market": "us", "keyword": "tide times", "group": "target", "status": "ok"}]   # backfilled later
        basket, groups = refresh_basket(rows, None, failed_only=True)
        self.assertEqual(basket, {"us": ["tide times"]})
        self.assertEqual(groups[("us", "moon phase")], "asa-observed")
        self.assertEqual(refresh_basket(rows, {"ua"}, failed_only=False)[0], {})
        self.assertEqual(refresh_basket(rows, None, failed_only=False)[0], {"us": ["tide times", "moon phase"]})
