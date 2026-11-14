"""publish: the built page, and only the page, pushed to a branch of the app's repository."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tests.helpers import AS_OF, exported_store, run  # noqa: E402

from aso.commands import ads_actions  # noqa: E402


def git(*args, cwd=None):
    done = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    return done.stdout.strip()


class Publish(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.remote = root / "remote.git"
        git("init", "-q", "--bare", str(self.remote))
        self.repo = root / "app"
        self.repo.mkdir()
        git("init", "-q", "-b", "main", cwd=self.repo)
        git("remote", "add", "origin", str(self.remote), cwd=self.repo)
        (self.repo / "source.swift").write_text("// the app\n", encoding="utf-8")
        self.store = exported_store(self.repo).rename(self.repo / "marketing")

    def publish(self, *more):
        return run("copilot.py", "publish", "--store", str(self.store), *more)

    def test_the_page_and_nothing_else_lands_on_the_branch(self):
        code, out, err = self.publish()
        self.assertEqual(code, 0, out + err)
        self.assertIn("PUBLISHED gh-pages", out)
        self.assertEqual(sorted(git("ls-tree", "--name-only", "gh-pages", cwd=self.remote).splitlines()), [".nojekyll", "index.html"])
        page = git("show", "gh-pages:index.html", cwd=self.remote)
        self.assertIn("Tidepool", page)
        self.assertNotIn("source.swift", git("ls-tree", "-r", "--name-only", "gh-pages", cwd=self.remote))
        self.assertIn(f"page as of {AS_OF}", git("log", "-1", "--format=%s", "gh-pages", cwd=self.remote))
        self.assertEqual(git("branch", "--list", cwd=self.repo), "")                 # the app's own checkout was not touched
        self.assertEqual(self.publish()[0], 0)                                        # publishing again replaces the page
        self.assertEqual(git("rev-list", "--count", "gh-pages", cwd=self.remote), "1")

    def test_data_that_is_not_what_the_store_exports_is_not_published(self):
        path = self.store / "data" / "events.json"
        path.write_text(path.read_text(encoding="utf-8").replace("Q001", "Q999"), encoding="utf-8")
        code, out, _ = self.publish()
        self.assertEqual(code, 1)
        self.assertIn("events.json", out)
        self.assertEqual(git("branch", "--list", "gh-pages", cwd=self.remote), "")

    def test_data_the_clean_check_refuses_is_not_published(self):
        with (self.store / "queue.md").open("a", encoding="utf-8") as fh:
            fh.write("\n### Q003 · queued 2026-11-13 · write to owner@example.com\n")
        code, _, _ = run("copilot.py", "export", "--store", str(self.store), "--as-of", AS_OF)
        self.assertEqual(code, 0)
        code, out, _ = self.publish()
        self.assertEqual(code, 1)
        self.assertIn("e-mail", out)
        self.assertEqual(git("branch", "--list", "gh-pages", cwd=self.remote), "")

    def test_a_dry_run_pushes_nothing(self):
        code, out, _ = self.publish("--dry-run")
        self.assertEqual(code, 0)
        self.assertIn("would push", out)
        self.assertEqual(git("branch", "--list", "gh-pages", cwd=self.remote), "")

    def test_the_pages_address_of_a_github_remote(self):
        self.assertEqual(ads_actions.pages_url("https://github.com/owner/App.git"), "https://owner.github.io/App/")
        self.assertEqual(ads_actions.pages_url("git@github.com:owner/App.git"), "https://owner.github.io/App/")
        self.assertIsNone(ads_actions.pages_url("/srv/git/app.git"))


if __name__ == "__main__":
    unittest.main()
