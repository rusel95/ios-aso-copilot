"""Tracked campaign links for channels outside the store."""

import subprocess
import sys
from pathlib import Path

from aso.commands.base import SKILL_DIR


def cmd_campaign(args):
    """Delegate to campaign_link.py."""
    store = Path(args.store).resolve()
    script = SKILL_DIR / "scripts" / "campaign_link.py"
    if not script.exists():
        print(f"campaign_link.py not found at {script}")
        return 1
    forward_args = [sys.executable, str(script), "--store", str(store)]
    if getattr(args, "list", False):
        forward_args.append("--list")
    if getattr(args, "campaign", ""):
        forward_args.extend(["--campaign", args.campaign])
    if getattr(args, "channel", ""):
        forward_args.extend(["--channel", args.channel])
    if getattr(args, "type", ""):
        forward_args.extend(["--type", args.type])
    if getattr(args, "pt", ""):
        forward_args.extend(["--pt", args.pt])
    if getattr(args, "target", ""):
        forward_args.extend(["--target", args.target])
    if getattr(args, "scaffold_hypo", False):
        forward_args.append("--scaffold-hypo")
    if getattr(args, "force", False):
        forward_args.append("--force")
    return subprocess.run(forward_args).returncode
