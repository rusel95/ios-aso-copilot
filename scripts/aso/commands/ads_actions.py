"""Everything that changes something outside the store. No collection command imports this module."""

import datetime as dt
import json
import re
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

from aso import queue_gate
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
    """Reply to one App Store review. The one review command that changes something outside the store, and
    public: it runs only against an entry of queue.md whose Command line is exactly this reply."""
    store = Path(args.store).resolve()
    resolve_app_identity(store)
    if not args.review_id or not args.response:
        print("Error: --review-id and --response are required for respond action.")
        sys.exit(1)
    command = ["asc", "reviews", "respond", "--review-id", args.review_id, "--response", args.response]
    queue_id = getattr(args, "queue_id", None)
    why = queue_gate.refusal(store, queue_id, command)
    if why:
        print(f"REFUSED reviews respond: {why}")
        return 1
    if getattr(args, "dry_run", False):
        print(f"DRY RUN: {queue_id} would run: {shlex.join(command)}")
        return 0
    result = subprocess.run(command)
    if result.returncode == 0:
        queue_gate.record_execution(store, queue_id, f"replied to review {args.review_id}")
    return result.returncode


def pages_url(remote: str, path: str = ""):
    """Where GitHub Pages serves a repository's page (and a folder of it), or None when the remote is not on github.com."""
    found = re.match(r"(?:https://(?:[^@/]+@)?github\.com/|git@github\.com:)([^/]+)/([^/]+?)(?:\.git)?/?$", remote or "")
    return f"https://{found.group(1)}.github.io/{found.group(2)}/{path.strip('/') + '/' if path else ''}" if found else None


def pages_target(store: Path, args) -> tuple:
    """(remote, branch, folder) to publish to: what the command line says, else the `**Pages repository**`,
    `**Pages branch**` and `**Pages path**` lines of the store's config.md, else the store's own repository and
    its `gh-pages` branch."""
    said = {}
    config = store / "config.md"
    for line in config.read_text(encoding="utf-8").splitlines() if config.is_file() else []:
        found = re.match(r"\*\*(Pages repository|Pages branch|Pages path)\*\*:\s*(\S+)", line.strip())
        if found and not found.group(2).upper().startswith("TODO"):
            said[found.group(1)] = found.group(2)
    return (args.remote or said.get("Pages repository"), args.branch or said.get("Pages branch") or "gh-pages",
            args.path if args.path is not None else said.get("Pages path", ""))


def cmd_publish(args):
    """Push the built page, and only the page, to where GitHub Pages serves it. Nothing is pushed unless data/ is
    what the store exports for its day and the clean check passes. The app's own checkout is never touched.

    With a folder (`--path`, or `**Pages path**` in config.md) the page goes into that folder of a repository that
    serves other pages too: the branch is cloned to a temporary folder, the one file is written, and a commit is
    pushed on top; nothing else there is changed and nothing is ever rewritten. With no folder the page is the
    whole of its own branch, which is replaced each time. A published page is public to whoever has its address."""
    store = Path(args.store).resolve()
    data = store / "data"
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
            said = (done.stderr or done.stdout).strip().splitlines()
            raise RuntimeError(re.sub(r"//[^@/]+@", "//", said[-1]) if said else "git failed")     # never a token
        return done.stdout.strip()

    remote, branch, folder = pages_target(store, args)
    parts = Path(folder).parts if folder else ()
    if folder and (Path(folder).is_absolute() or ".." in parts or not [p for p in parts if p != "."]):
        print(f"FAIL publish: the path {folder!r} must name a folder inside the repository")
        return 1
    try:
        remote = remote or git("remote", "get-url", "origin", cwd=store)
    except RuntimeError as exc:
        print(f"FAIL publish: the store's repository has no origin remote ({exc}); pass --remote")
        return 1
    shown = re.sub(r"//[^@/]+@", "//", remote)
    tokens = read_brand_tokens(store)
    name = tokens[0].capitalize() if tokens else "App"

    def identity(key, fallback):
        try:
            return git("config", key, cwd=store) or fallback
        except RuntimeError:
            return fallback
    author = ["-c", f"user.name={identity('user.name', 'aso-copilot')}",
              "-c", f"user.email={identity('user.email', 'aso-copilot@users.noreply.github.com')}"]

    with tempfile.TemporaryDirectory() as tmp:
        built, work = Path(tmp) / "built", Path(tmp) / "work"
        if site.build(data, built, name) != 0:
            return 1
        size = (built / "index.html").stat().st_size
        where = f"{folder.strip('/')}/index.html" if folder else "index.html"
        if args.dry_run:
            print(f"would push {where} ({size} bytes, as of {as_of}) to {branch} of {shown}")
            return 0
        try:
            if folder:                                   # a folder of a branch that holds other pages: add, never rewrite
                git("clone", "-q", "--depth", "1", "--branch", branch, remote, str(work))
                target = work / folder / "index.html"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((built / "index.html").read_bytes())
                git("add", "--", where, cwd=work)
                if not git("status", "--porcelain", "--", where, cwd=work):
                    print(f"SAME {where} on {branch} of {shown}: the page there is already this one")
                    return 0
                git(*author, "commit", "-q", "-m", f"ASO dashboard: {name} as of {as_of}", "--", where, cwd=work)
                git("push", "-q", "origin", f"HEAD:{branch}", cwd=work)
            else:                                        # a branch of its own: one commit, one page, replaced each time
                (built / ".nojekyll").write_text("", encoding="utf-8")
                git("init", "-q", "-b", branch, cwd=built)
                git("add", "-A", cwd=built)
                git(*author, "commit", "-q", "-m", f"page as of {as_of}", cwd=built)
                git("push", "-q", "--force", remote, f"{branch}:{branch}", cwd=built)
        except RuntimeError as exc:
            print(f"FAIL publish: {exc}")
            return 1
    url = pages_url(remote, folder)
    print(f"PUBLISHED {folder.strip('/') + ' on ' if folder else ''}{branch} of {shown}: index.html, {size} bytes, as of {as_of}"
          + (f"\n{url}" if url else ""))
    return 0
