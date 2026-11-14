"""What writes rank observations into the store: snapshot ingest, the refresh run, and the hypothesis draft."""
from __future__ import annotations

import csv
import datetime as dt
import json
import math
import re
import sys
from pathlib import Path

from aso.ranks import brand_hit, series
from aso.store import (RANK_HEADER, hyp_markets, print_problems, read_brand_tokens, read_hypotheses, read_markets,
                       read_ranks)

# Apple documents an approximate, changeable limit; this 3s minimum is a local guard, not a guarantee.
DEFAULT_DELAY = 3.0


def load_snapshot(path: Path):
    """Accept both known snapshot shapes; reject impossible positions rather than storing them."""
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    if isinstance(data, dict):
        for country, entries in data.items():
            if isinstance(entries, list):
                rows += [dict(r, country_code=r.get("country", country)) for r in entries]
    elif isinstance(data, list):
        rows = data
    out, rejected = [], []
    for r in rows:
        market = str(r.get("country_code") or r.get("country") or "").lower()
        term, pos = r.get("term"), r.get("our_rank")
        total = r.get("total_results")
        if not market or not term:
            continue
        # A position deeper than the result list the query actually returned cannot have been
        # observed by that query — this is the check that catches a carried-over stale value.
        if pos is not None and isinstance(total, int) and pos > total:
            rejected.append((market, term, pos, total))
            continue
        # A failed request observed nothing. It is not "absent within depth", which is a successful
        # query that looked and did not find us — collapsing the two turns an outage into a rank loss.
        status = "error" if r.get("query_status") == "error" else ("ok" if pos is not None else "beyond-depth")
        if status == "beyond-depth" and str(total) == "0":
            status = "no-results"        # an empty result list shows nothing about our absence
        out.append((market, str(term), pos if status == "ok" else None, status))
    return out, rejected


def ingest(store: Path, path: Path, date: str, source: str, depth, group: str):
    rows, rejected = load_snapshot(path)
    if rejected:
        print(f"REFUSED {len(rejected)} rows: position deeper than the result list that query "
              f"returned (stale value carried across snapshots), e.g. {rejected[:3]}", file=sys.stderr)
    target = store / "metrics" / "ranks.csv"
    # Keyed on the observation itself, not just its address: re-ingesting the same file changes
    # nothing, but a retry that finally succeeds appends a correction on the same date, which is
    # what the append-only rule asks for (a correction is a new row, never an edited one).
    existing = {(r["date"], r["market"], r["keyword"], r["source"], r["status"],
                 r["position"]) for r in read_ranks(store)}
    new = 0
    head = target.read_text(encoding="utf-8").splitlines() if target.exists() else []
    if len(head) == 1 and head[0].split(",") != RANK_HEADER:
        # header-only file from an older schema: upgrade it rather than appending wider rows under it
        target.write_text(",".join(RANK_HEADER) + "\n", encoding="utf-8")
    elif head and head[0].split(",") != RANK_HEADER:
        sys.exit(f"{target} uses an older column set and already holds data; migrate it before ingesting")
    with target.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        if not target.stat().st_size:
            writer.writerow(RANK_HEADER)
        for market, term, pos, status in rows:
            key = (date, market, term, source, status, pos if status == "ok" else None)
            if key in existing:
                continue
            existing.add(key)          # a snapshot that lists a query twice writes it once
            writer.writerow([date, market, term, group, pos if pos is not None else "",
                             "", "", source, depth or "", status])
            new += 1
    print(f"ingested {new} rows into {target} (date={date} source={source} depth={depth})")
    return new


def draft(store: Path, market: str, queries: list, window: int, out: Path | None, as_of=None):
    """Scaffold a hypothesis that is measurable BEFORE it is written.

    The deterministic half only: id, storefront, basket, the baseline each query actually has, the
    dates the window opens and closes, a kill criterion carrying real numbers, and every collision
    with work already in flight. The argument — change and mechanism — is not scaffolding and is
    left blank on purpose; a generated mechanism is a guess wearing a hypothesis's clothes.
    """
    as_of = as_of or dt.date.today()
    pairs, markets, hyps = series(read_ranks(store)), read_markets(store), read_hypotheses(store)
    market = market.lower()
    queries = [q.strip().lower() for q in queries if q.strip()]
    if not queries:
        sys.exit("--queries is required: an experiment with no basket cannot be judged")
    # 0. Brand queries are strictly excluded: they measure indexation only, never demand or acquisition.
    brands = read_brand_tokens(store)
    brand_queries = [q for q in queries if any(brand_hit(b, q) for b in brands)]
    if brand_queries:
        sys.exit(f"Refusing to draft: {brand_queries} contains brand token(s). "
                 f"Brand queries measure indexation only, not demand. "
                 f"Brand terms must not be hypothesis targets.")

    # 1. Refuse first, scaffold second. This is the failure this store already has nine of.
    # A row whose only observation is a failed request is a term we tried to look up, not one we
    # measured. Drafting against it opens a window on nothing, same as no row at all.
    unmeasurable = [q for q in queries
                    if not any(o["status"] != "error" for o in pairs.get((market, q), []))]
    if unmeasurable:
        sys.exit(f"Refusing to draft: {market} has no successful observation for {unmeasurable}. Add these to "
                 f"the tracked basket and ingest a snapshot first, or the window closes on nothing. "
                 f"({len(pairs)} keys tracked, {sum(1 for m, _ in pairs if m == market)} in {market})")
    if market not in markets:
        print(f"WARNING: {market} has no proceeds_usd in metrics/markets.csv — this hypothesis "
              f"cannot be ranked against others by value.", file=sys.stderr)

    # 2. Collisions: same storefront in flight, and same query claimed by another hypothesis.
    inflight = [h for h in hyps if not (h.get("verdict") or "").strip() and market in hyp_markets(h)]
    claimed = {q: h["id"] for h in hyps for q in
               [x.strip().lower() for x in (h.get("queries") or "").split(";") if x.strip()]
               if q in queries}
    judged = [(h["id"], h.get("verdict")) for h in hyps
              if (h.get("verdict") or "").strip() and market in hyp_markets(h)]

    ids = [int(re.sub(r"\D", "", h.get("id") or "0") or 0) for h in hyps]
    hid = f"H{max(ids + [0]) + 1:03d}"
    opens, closes = as_of, as_of + dt.timedelta(days=window)

    lines = [f"---", f"id: {hid}", f"markets: {market}", f"queries: {'; '.join(queries)}",
             "status: draft", "phase_at_start:                  # P2-cold / P3-measure",
             "change: >", "  # WHAT changes, field by field, as a reviewable diff of the live text",
             "mechanism: >", "  # WHY that should move these queries. The causal story, not the hope.",
             "prediction: >", "  # A number and a date, per query. Baselines are listed below."]
    for q in queries:
        obs = pairs[(market, q)][-1]
        pos = obs["position"] if obs["position"] is not None else f"beyond depth {obs['depth'] or '?'}"
        lines.append(f"  #   {q}: now {pos} (observed {obs['date']}, {obs['provider']}, "
                     f"status {obs['status']})")
    worst = "; ".join(
        f"{q} not better than {pairs[(market, q)][-1]['position']}"
        if pairs[(market, q)][-1]["position"] is not None else f"{q} still beyond depth"
        for q in queries)
    lines += ["kill_criterion: >",
              f"  On {closes.isoformat()}, measured the same way: {worst}.",
              f"kill_criterion_written: {opens.isoformat()}",
              "went_live:                       # the date it is PUBLIC, never the submission date",
              f"window_days: {window}", "primary_signal: rank", "verdict:", "confounds: []", "---", "",
              "## Reasoning", "",
              f"<!-- Baseline on {opens.isoformat()}, from metrics/ranks.csv. Window {opens} → {closes}. -->", ""]
    if market in markets:
        lines.append(f"Storefront value: ${markets[market]:.2f} net proceeds per paying subscriber "
                     f"(`live:asc subscriptions pricing prices list`).")
    if judged:
        lines.append("\nAlready judged in this storefront — explain what new evidence changes, or do "
                     "not repeat it: " + ", ".join(f"{i} ({v})" for i, v in judged) + ".")
    if inflight:
        lines.append("\nIn flight in this storefront right now: " + ", ".join(h["id"] for h in inflight)
                     + ". Two changes to one storefront inside one window cannot be told apart — "
                     "record this as a confound or wait.")
    if claimed:
        lines.append("\nQueries already claimed by another hypothesis: "
                     + ", ".join(f"{q} → {i}" for q, i in claimed.items())
                     + ". Sharing a query means neither verdict is attributable.")
    text = "\n".join(lines) + "\n"
    if out:
        out.write_text(text, encoding="utf-8")
        print(f"drafted {hid} → {out}")
    else:
        print(text)
    return hid


def ingest_by_observed_day(store: Path, snapshot: dict, group: str = "target", groups: dict | None = None) -> int:
    """Ingest a snapshot dict, dating each entry by the local day its own `observed_at` names.

    A long refresh can cross midnight, and a crash must not cost the markets that already finished:
    refresh calls this once per market as it completes, instead of once at the end under one date.
    """
    import tempfile
    by_day: dict = {}
    for country, entries in snapshot.items():
        for e in entries:
            try:
                day = dt.datetime.fromisoformat(e["observed_at"]).astimezone().date().isoformat()
            except (KeyError, TypeError, ValueError):
                day = str(dt.date.today())              # an entry that names no time falls back to the run's date
            # `groups` carries each key's own group (e.g. `asa-observed`) through a refresh instead of
            # relabelling every re-observed key as `target`
            g = (groups or {}).get((str(e.get("country") or country).lower(), e.get("term")), group)
            by_day.setdefault((day, g), {}).setdefault(country, []).append(e)
    new = 0
    with tempfile.TemporaryDirectory() as tmp:
        for n, ((day, g), snap) in enumerate(sorted(by_day.items())):
            path = Path(tmp) / f"{n}_{day}.json"
            path.write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8")
            new += ingest(store, path, day, "itunes-search-api", 200, g)
    return new


def refresh(store: Path, bundle: str, markets_filter, failed_only: bool, delay: float,
            out_dir: Path):
    """Re-query the basket the store already tracks, then ingest it. One command, so that the
    weekly cadence a 21-day window depends on actually happens.

    The basket is whatever `ranks.csv` already contains — never a list retyped by hand, which is
    how a query silently leaves the basket and a window closes on a different set than it opened on.

    Apple currently documents an approximate limit of 20 calls/minute, subject to change
    (https://performance-partners.apple.com/search-api). DEFAULT_DELAY = 3.0s is a local minimum,
    not a guarantee of success. Measured here on 2026-09-08: 6 workers at 0.1s lost 478 of 649
    queries; one worker at 1.0s still lost 135 of 261. Use --failed-only to retry missing observations.
    """
    if not math.isfinite(delay) or delay < DEFAULT_DELAY:
        sys.exit(f"--delay must be at least {DEFAULT_DELAY:.1f} seconds; lower delays are refused")
    import subprocess
    rows = read_ranks(store)
    if not rows:
        sys.exit("nothing tracked yet: ingest a snapshot before refreshing")
    latest = {}
    for r in rows:                                   # last observation per key decides what to redo
        latest[(r["market"], r["keyword"])] = r
    basket = {}
    for (market, keyword), r in latest.items():
        if markets_filter and market not in markets_filter:
            continue
        if failed_only and r["status"] != "error":
            continue
        basket.setdefault(market, []).append(keyword)
    if not basket:
        print("nothing to refresh with those filters")
        return 0
    script = Path(__file__).resolve().parent.parent / "rank_audit.py"
    out_dir.mkdir(parents=True, exist_ok=True)
    merged, ok, err, ingested = {}, 0, 0, 0
    groups = {key: (r.get("group") or "target") for key, r in latest.items()}
    failed_markets: list[str] = []
    missing_by_market: dict[str, list[str]] = {}
    for market in sorted(basket):
        target = out_dir / f"{market}.json"
        print(f"  {market}: {len(basket[market])} queries…", flush=True)
        # A comma-joined --keywords string cannot round-trip a keyword that itself contains a
        # comma (e.g. "compress photos, resize image") — it silently splits into two shorter
        # terms that never match anything in the tracked basket, so the real term is never
        # requeried and stays stale with no error anywhere. A newline-delimited file has no such
        # collision with the query text itself.
        kw_file = out_dir / f"{market}.keywords.txt"
        kw_file.write_text("\n".join(basket[market]) + "\n", encoding="utf-8")
        # A market with 50-90 queries at the mandatory ~3s Apple rate limit runs for several
        # minutes. subprocess.run(capture_output=True) buffers rank_audit.py's own per-query
        # progress dots until the whole market finishes, which looks identical to a hang from
        # this process's stdout — stream it through live instead, while still keeping every line
        # to report on a non-zero exit.
        proc = subprocess.Popen([sys.executable, str(script), "--bundle", bundle, "--markets", market,
                                 "--keywords-file", str(kw_file), "--output", str(target),
                                 "--delay", str(delay)], stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, text=True, bufsize=1)
        captured_lines: list[str] = []
        for line in proc.stdout:
            print(line, end="", flush=True)
            captured_lines.append(line)
        returncode = proc.wait()
        kw_file.unlink(missing_ok=True)
        if returncode or not target.exists():
            tail = "".join(captured_lines).strip().splitlines()[-4:]
            print(f"  {market}: FAILED (exit {returncode}) — this storefront is unrefreshed, its "
                  f"keys keep their previous observation:\n      " + "\n      ".join(tail),
                  file=sys.stderr, flush=True)
            failed_markets.append(market)
            continue
        # A clean exit code is not proof every requested keyword came back — rank_audit.py applies
        # its own per-market query budget and can return fewer rows than were requested with no
        # non-zero exit. Name exactly which keywords never got a response, per market, every run.
        requested = set(basket[market])
        returned_terms = set()
        market_snapshot = json.loads(target.read_text(encoding="utf-8"))
        m_ok = m_err = 0
        for country, entries in market_snapshot.items():
            merged.setdefault(country, []).extend(entries)
            m_ok += sum(e.get("query_status") == "ok" for e in entries)
            m_err += sum(e.get("query_status") == "error" for e in entries)
            returned_terms.update(e.get("term") for e in entries if e.get("term"))
        ok += m_ok
        err += m_err
        if m_err and not m_ok:
            # every query of this storefront failed: an outage, not an observation. Same rule the
            # whole run used to apply at the end, now applied per market so one dead storefront
            # cannot veto the rest and a finished one is never lost to a later crash.
            print(f"  {market}: every query failed — nothing ingested for this storefront",
                  file=sys.stderr, flush=True)
            failed_markets.append(market)
        else:
            ingested += ingest_by_observed_day(store, market_snapshot, groups=groups)
        missing = requested - returned_terms
        if missing:
            missing_by_market[market] = sorted(missing)
            print(f"  ⚠ {market}: MISSING {len(missing)} of {len(requested)} requested keywords — "
                  f"no response at all (not even 'error'), previous observation kept unchanged: "
                  f"{sorted(missing)}", file=sys.stderr, flush=True)
    today = dt.date.today()
    snapshot = out_dir / f"snapshot_{today}.json"
    if merged:
        if snapshot.exists():              # a retry (e.g. --markets us) must not clobber the full run
            snapshot = out_dir / f"snapshot_{today}_{dt.datetime.now():%H%M%S}.json"
        snapshot.write_text(json.dumps(merged, ensure_ascii=False), encoding="utf-8")
    for market in basket:                      # the per-market files are inputs to the merge above
        (out_dir / f"{market}.json").unlink(missing_ok=True)
    total_missing = sum(len(v) for v in missing_by_market.values())
    print(f"{ok} observed · {err} failed" + (f" → {snapshot}" if merged else ""))
    if failed_markets or missing_by_market:
        print(f"\n⚠⚠ INCOMPLETE REFRESH — do not read this as a full basket update:", file=sys.stderr)
        if failed_markets:
            print(f"   {len(failed_markets)} storefront(s) entirely FAILED: {failed_markets}",
                  file=sys.stderr)
        if missing_by_market:
            print(f"   {total_missing} keyword(s) MISSING across {len(missing_by_market)} "
                  f"storefront(s): {missing_by_market}", file=sys.stderr)
        print(f"   Every listed key kept its prior observation unchanged — it was NOT refreshed "
              f"today, whatever `ledger.py report` prints for it next.", file=sys.stderr)
    else:
        print("Every requested keyword in every requested storefront returned a response.")
    print(f"ingested {ingested} new rows in total (each dated by its own observed_at)")
    if err and not ok:
        sys.exit(f"every query failed (this run used --delay {delay}). Nothing ingested; inspect "
                 "the per-query errors and retry only after correcting the cause.")
    if failed_markets or missing_by_market:
        # what finished is already in ranks.csv; the exit code says the basket is NOT complete
        print_problems(sys.stderr)
        sys.exit(3)
    return ingested
