"""Everything that changes something outside the store. No collection command imports this module."""

import datetime as dt
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from aso.commands.base import log_debug, log_error, log_info, resolve_app_identity, run_cmd
from aso.dashboard import clean, export, site
from aso.store import read_brand_tokens


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


def pages_url(remote: str):
    """Where GitHub Pages serves a repository's page, or None when the remote is not on github.com."""
    found = re.match(r"(?:https://(?:[^@/]+@)?github\.com/|git@github\.com:)([^/]+)/([^/]+?)(?:\.git)?/?$", remote or "")
    return f"https://{found.group(1)}.github.io/{found.group(2)}/" if found else None


def cmd_publish(args):
    """Push the built page, and only the page, to a branch of the app's repository; GitHub Pages serves it from
    there. Nothing is pushed unless data/ is what the store exports for its day and the clean check passes. The
    app's own checkout is not touched: the page is committed in a temporary folder and pushed from it, replacing
    the branch, so the branch always holds one commit and one page. A published page is public to whoever has
    its address."""
    store = Path(args.store).resolve()
    data, branch = store / "data", args.branch
    if not (data / "events.json").is_file():
        print(f"FAIL publish: {data} holds no export; run export first")
        return 1
    as_of = dt.date.fromisoformat(json.loads((data / "events.json").read_text(encoding="utf-8"))["as_of"])
    stale = export.check(store, export.build_all(store, as_of)[0])
    if stale:
        print(f"FAIL publish: data/ is not what the store exports for {as_of} ({', '.join(stale)}); run export")
        return 1
    refused = clean.check(data, store)
    if refused:
        print("\n".join(refused))
        print("FAIL publish: the clean check refuses the data")
        return 1

    def git(*words, cwd=None):
        done = subprocess.run(["git", *words], cwd=cwd, capture_output=True, text=True)
        if done.returncode != 0:
            raise RuntimeError((done.stderr or done.stdout).strip().splitlines()[-1] if (done.stderr or done.stdout).strip() else "git failed")
        return done.stdout.strip()

    try:
        remote = args.remote or git("remote", "get-url", "origin", cwd=store)
    except RuntimeError as exc:
        print(f"FAIL publish: the store's repository has no origin remote ({exc}); pass --remote")
        return 1
    shown = re.sub(r"//[^@/]+@", "//", remote)                    # never print a token a remote may carry
    tokens = read_brand_tokens(store)
    with tempfile.TemporaryDirectory() as tmp:
        if site.build(data, Path(tmp), tokens[0].capitalize() if tokens else "App") != 0:
            return 1
        (Path(tmp) / ".nojekyll").write_text("", encoding="utf-8")
        size = (Path(tmp) / "index.html").stat().st_size
        if args.dry_run:
            print(f"would push index.html ({size} bytes, as of {as_of}) to {branch} of {shown}")
            return 0
        try:
            def identity(key, fallback):
                try:
                    return git("config", key, cwd=store) or fallback
                except RuntimeError:
                    return fallback
            name, mail = identity("user.name", "aso-copilot"), identity("user.email", "aso-copilot@users.noreply.github.com")
            git("init", "-q", "-b", branch, cwd=tmp)
            git("add", "-A", cwd=tmp)
            git("-c", f"user.name={name}", "-c", f"user.email={mail}", "commit", "-q", "-m", f"page as of {as_of}", cwd=tmp)
            subprocess_push = ["git", "push", "-q", "--force", remote, f"{branch}:{branch}"]
            done = subprocess.run(subprocess_push, cwd=tmp, capture_output=True, text=True)
            if done.returncode != 0:
                raise RuntimeError(re.sub(r"//[^@/]+@", "//", (done.stderr or "git push failed").strip().splitlines()[-1]))
        except RuntimeError as exc:
            print(f"FAIL publish: {exc}")
            return 1
    url = pages_url(remote)
    print(f"PUBLISHED {branch} of {shown}: index.html, {size} bytes, as of {as_of}" + (f"\n{url}" if url else ""))
    return 0
