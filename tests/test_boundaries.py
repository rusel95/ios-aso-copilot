"""Where things are allowed to live: what changes the outside world, and what collection may reach."""
import ast
import sys
import unittest
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tests.helpers import ROOT, run  # noqa: E402

SCRIPTS = ROOT / "scripts"
ACTIONS = SCRIPTS / "aso" / "commands" / "ads_actions.py"
CAMPAIGN_READS = {"find", "list", "get"}


def outside_change(elements):
    """What a command line changes outside the store, or None. `elements` are the items of one list literal."""
    words = [e.value if isinstance(e, ast.Constant) and isinstance(e.value, str) else None for e in elements]
    if "create-bulk" in words:
        return "creates Apple Ads keywords"
    if ("reviews", "respond") in zip(words, words[1:]):
        return "replies to a review"
    if words[:3] == ["asc", "ads", "campaigns"] and len(words) > 3 and words[3] not in CAMPAIGN_READS:
        return "changes an Apple Ads campaign"
    if words[:1] == ["git"] and "push" in words:
        return "pushes to a repository"
    return None


def outside_changes(path: Path):
    """What a file changes outside the store: by a command line written as a list, or by a `git(...)` helper call."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = {what for node in ast.walk(tree) if isinstance(node, ast.List) if (what := outside_change(node.elts))}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "git" and \
                outside_change([ast.Constant("git"), *node.args]):
            found.add("pushes to a repository")
    return sorted(found)


def imported_modules(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.add(node.module or "")
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


class Actions(unittest.TestCase):
    def test_only_actions_module_changes_the_outside(self):
        self.assertEqual(outside_changes(ACTIONS), ["changes an Apple Ads campaign", "creates Apple Ads keywords",
                                                    "pushes to a repository", "replies to a review"])
        elsewhere = {str(p.relative_to(ROOT)): found for p in SCRIPTS.rglob("*.py")
                     if p != ACTIONS and (found := outside_changes(p))}
        self.assertEqual(elsewhere, {})

    def test_collect_never_reaches_actions(self):
        for name in ("cycle.py", "collect.py"):
            with self.subTest(module=name):
                reached = [m for m in imported_modules(SCRIPTS / "aso" / "commands" / name) if "ads_actions" in m]
                self.assertEqual(reached, [])

    def test_collect_is_cycle(self):
        code, collect_help, _ = run("copilot.py", "collect", "--help")
        self.assertEqual(code, 0)
        self.assertEqual(collect_help, run("copilot.py", "cycle", "--help")[1])   # one parser under two names
        self.assertIn("cycle (collect)", run("copilot.py", "--help")[1])


class DashboardIsOffline(unittest.TestCase):
    """Export and build: same input, same bytes. So nothing in aso/dashboard may ask the network or the clock."""

    def test_dashboard_has_no_network_and_no_clock(self):
        banned = {"urllib", "http", "socket", "subprocess", "requests"}
        for path in sorted((SCRIPTS / "aso" / "dashboard").glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            with self.subTest(module=path.name):
                reached = {m.split(".")[0] for m in imported_modules(path)} & banned
                self.assertEqual(reached, set())
                clock = [node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
                         and node.attr in ("today", "now", "utcnow", "time", "monotonic")]
                self.assertEqual(clock, [])


class SelfCheckIsOffline(unittest.TestCase):
    def test_the_copilot_self_check_opens_no_connection(self):
        """Run the self-check with every way out of the machine made to fail loudly."""
        import socket
        from unittest import mock

        import copilot  # noqa: F401 — puts scripts/ on the path the way the entry does
        from aso.commands.selfcheck import self_check
        import contextlib
        import io

        def refuse(*args, **kwargs):
            raise AssertionError("the self-check tried to open a network connection")

        with mock.patch.object(socket, "create_connection", refuse), mock.patch.object(socket.socket, "connect", refuse), \
                contextlib.redirect_stdout(io.StringIO()) as said:
            self_check()
        self.assertIn("OK:", said.getvalue())


class ReviewReplyNeedsApproval(unittest.TestCase):
    """`reviews respond` posts publicly: it runs only against a queue entry whose Command is exactly this reply."""

    REPLY = ["asc", "reviews", "respond", "--review-id", "R1", "--response", "Thank you, it is fixed in 1.0.1"]

    def setUp(self):
        import os
        import tempfile
        import stat
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        from tests.helpers import copy_store
        self.store = copy_store(self.tmp.name)
        bin_dir = Path(self.tmp.name) / "bin"
        bin_dir.mkdir()
        self.calls = Path(self.tmp.name) / "calls.txt"
        fake = bin_dir / "asc"
        fake.write_text(f'#!/bin/sh\necho "$@" >> "{self.calls}"\n', encoding="utf-8")
        fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
        patch = mock.patch.dict(os.environ, {"PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"})
        patch.start()
        self.addCleanup(patch.stop)

    def queue(self, command):
        with (self.store / "queue.md").open("a", encoding="utf-8") as fh:
            fh.write(f"\n### Q003 · queued 2026-11-16 · fence: publishes\n**Effect in plain language**: replies publicly.\n"
                     f"**Command**: {command}\n**Preconditions**: review still unanswered.\n")

    def respond(self, queue_id=None, dry_run=False):
        import argparse
        import contextlib
        import io
        from aso.commands.ads_actions import cmd_reviews_respond
        args = argparse.Namespace(store=str(self.store), review_id="R1", response=self.REPLY[-1],
                                  queue_id=queue_id, dry_run=dry_run)
        with contextlib.redirect_stdout(io.StringIO()) as said:
            code = cmd_reviews_respond(args)
        return code, said.getvalue()

    def calls_made(self):
        return self.calls.read_text(encoding="utf-8").splitlines() if self.calls.exists() else []

    def test_no_queue_id_is_refused_and_asc_is_not_called(self):
        code, said = self.respond()
        self.assertEqual(code, 1)
        self.assertIn("REFUSED", said)
        self.assertEqual(self.calls_made(), [])

    def test_an_id_that_is_not_in_the_queue_is_refused(self):
        self.assertEqual(self.respond("Q099")[0], 1)
        self.assertEqual(self.calls_made(), [])

    def test_an_entry_for_a_different_command_is_refused(self):
        self.queue('asc reviews respond --review-id R2 --response "Another reply"')
        code, said = self.respond("Q003")
        self.assertEqual(code, 1)
        self.assertIn("different command", said)
        self.assertEqual(self.calls_made(), [])

    def test_a_matching_entry_runs_once_and_is_recorded(self):
        import shlex
        self.queue(shlex.join(self.REPLY))
        self.assertEqual(self.respond("Q003", dry_run=True)[0], 0)
        self.assertEqual(self.calls_made(), [])                                  # a dry run calls nothing
        self.assertEqual(self.respond("Q003")[0], 0)
        self.assertEqual(len(self.calls_made()), 1)
        self.assertIn("Q003 approved, executed", (self.store / "decisions.md").read_text(encoding="utf-8"))
        self.assertIn("### Q003", (self.store / "queue.md").read_text(encoding="utf-8"))   # the entry stays
        self.assertEqual(self.respond("Q003")[0], 1)                             # the same entry does not run twice
        self.assertEqual(len(self.calls_made()), 1)


class Sizes(unittest.TestCase):
    def test_no_long_files(self):
        long = {str(p.relative_to(ROOT)): n for p in SCRIPTS.rglob("*.py")
                if (n := len(p.read_text(encoding="utf-8").splitlines())) > 600}
        self.assertEqual(long, {})


if __name__ == "__main__":
    unittest.main()
