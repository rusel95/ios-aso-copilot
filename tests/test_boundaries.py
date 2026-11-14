"""Where things are allowed to live: what changes the outside world, and what collection may reach."""
import ast
import sys
import unittest
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
    return None


def outside_changes(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return sorted({found for node in ast.walk(tree) if isinstance(node, ast.List)
                   if (found := outside_change(node.elts))})


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
                                                    "replies to a review"])
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


class Sizes(unittest.TestCase):
    def test_no_long_files(self):
        long = {str(p.relative_to(ROOT)): n for p in SCRIPTS.rglob("*.py")
                if (n := len(p.read_text(encoding="utf-8").splitlines())) > 600}
        self.assertEqual(long, {})


if __name__ == "__main__":
    unittest.main()
