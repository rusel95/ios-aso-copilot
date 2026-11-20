"""Every script's own --self-check still passes. They are the behaviour tests the scripts already carried."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tests.helpers import run  # noqa: E402

OFFLINE = ["ads_keywords.py", "campaign_link.py", "copilot.py", "diff_snapshots.py", "economics.py",
           "funnel_visualizer.py", "global_velocity_audit.py", "ledger.py", "radar.py", "rank_audit.py"]
# Left out on purpose: no test reaches the network.
NEEDS_NETWORK = {"harvest_keywords.py": "its self-check asks Apple's hints endpoint for real completions"}


class SelfChecks(unittest.TestCase):
    def test_offline_self_checks_pass(self):
        for script in OFFLINE:
            with self.subTest(script=script):
                code, out, err = run(script, "--self-check")
                self.assertEqual(code, 0, out + err)

    def test_every_self_check_is_accounted_for(self):
        scripts = Path(__file__).resolve().parent.parent / "scripts"
        having = {p.name for p in scripts.glob("*.py") if "--self-check" in p.read_text(encoding="utf-8")}
        self.assertEqual(having, set(OFFLINE) | set(NEEDS_NETWORK))


if __name__ == "__main__":
    unittest.main()
