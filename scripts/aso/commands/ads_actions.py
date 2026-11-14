"""Everything that changes something outside the store. No collection command imports this module."""

import json
import subprocess
import sys
from pathlib import Path

from aso.commands.base import log_debug, log_error, log_info, resolve_app_identity, run_cmd


def cmd_ads_add_keywords(args, account, profile):
    adgroup_id = getattr(args, "adgroup_id", None)
    if not adgroup_id:
        print("Error: --adgroup-id is required to add keywords.")
        return 1
    terms = []
    if getattr(args, "terms", None):
        terms = [t.strip() for t in args.terms.split(",") if t.strip()]
    elif getattr(args, "file", None):
        p = Path(args.file).resolve()
        if p.is_file():
            terms = [line.strip() for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not terms:
        print("Error: provide --terms <comma-separated> or --file <path-to-txt>")
        return 1

    bid = getattr(args, "bid", "0.30")
    match_type = getattr(args, "match_type", "EXACT").upper()
    log_info(f"Adding {len(terms)} {match_type} keywords (bid ${bid}) to ad group {adgroup_id}...")

    chunk_size = 500
    added = 0
    for i in range(0, len(terms), chunk_size):
        chunk = terms[i:i + chunk_size]
        items = [
            {
                "correlationId": idx + 1,
                "data": {
                    "adGroupId": int(adgroup_id),
                    "text": term,
                    "matchType": match_type,
                    "bid": {"amount": str(bid), "currency": "USD"}
                }
            }
            for idx, term in enumerate(chunk)
        ]
        payload = {"allowPartialSuccess": True, "items": items}
        cmd = ["asc", "ads", "targeting-keywords", "create-bulk", "--ad-account", str(account), "--file", "-", "--confirm"]
        if profile:
            cmd.extend(["--ads-profile", str(profile)])
        rc, out, err = run_cmd(cmd, input_text=json.dumps(payload))
        if rc != 0:
            log_error(f"Failed to add chunk {i // chunk_size + 1}: {err}")
            print(f"Error adding keywords: {err.strip() or f'exit {rc}'}")
            return rc
        try:
            res_data = json.loads(out)
            chunk_results = res_data.get("result", [])
            successful = sum(1 for item in chunk_results if item.get("result") or item.get("id"))
            added += successful if successful > 0 else len(chunk)
            log_debug(f"Added chunk of {len(chunk)} keywords.")
        except Exception:
            added += len(chunk)

    print(f"✓ Successfully added {added} {match_type} keywords to ad group {adgroup_id} at ${bid} CPT.")
    return 0


def cmd_ads_set_campaign_status(args, account, profile, target_status):
    campaign_id = getattr(args, "campaign_id", None)
    if not campaign_id:
        print("Error: --campaign-id is required.")
        return 1
    action = "pause" if target_status == "PAUSED" else "resume"
    log_info(f"{action.capitalize()}ing campaign {campaign_id}...")
    cmd = ["asc", "ads", "campaigns", action, "--ad-account", str(account), "--campaign", str(campaign_id)]
    if action == "resume":
        cmd.append("--confirm")
    if profile:
        cmd.extend(["--ads-profile", str(profile)])
    rc, out, err = run_cmd(cmd)
    if rc == 0:
        print(f"✓ Campaign {campaign_id} {action}d successfully.")
        return 0
    else:
        print(f"Error: {err.strip() or f'exit {rc}'}")
        return rc


def cmd_reviews_respond(args):
    """Reply to one App Store review. The one review command that changes something outside the store."""
    resolve_app_identity(Path(args.store).resolve())
    if not args.review_id or not args.response:
        print("Error: --review-id and --response are required for respond action.")
        sys.exit(1)
    result = subprocess.run(["asc", "reviews", "respond", "--review-id", args.review_id, "--response", args.response])
    return result.returncode
