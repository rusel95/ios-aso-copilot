#!/usr/bin/env python3
"""Deterministic hypothesis + keyword ledger. Same store, same output, every run.

Three questions, in this order, before anything new is proposed:

  A. What happened to the hypotheses that are already live? (close them, or say why not)
  B. Which tracked keys moved, which regressed, which are still unobserved?
  C. Given per-market net proceeds, which untaken action is worth doing first?

What this does NOT do: invent a verdict, invent a rank, or print a revenue forecast.
Section C is a priority ORDER built from declared inputs, all printed inline — not a
cash projection (references/provenance.md, references/aso-loop.md).

    ledger.py --store PATH report
    ledger.py --store PATH ingest SNAPSHOT.json --date 2026-09-08 --depth 200
    ledger.py --self-check
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
import sys
from pathlib import Path

RANK_HEADER = ["date", "market", "keyword", "group", "position", "popularity",
               "difficulty", "source", "depth", "status"]
# status vocabulary: ok = found at `position`; beyond-depth = queried, absent within `depth`;
# error = request failed. A keyword never queried has no row at all — that is not the same thing.
TODAY = dt.date.today()
# Apple documents the iTunes Search API at "approximately 20 calls per minute"; over it, 429.
# https://performance-partners.apple.com/search-api
DEFAULT_DELAY = 3.0

# Every input this run could not use. A store file that cannot be parsed must never be skipped
# quietly: a dropped hypothesis reads exactly like a hypothesis that does not exist, and a ledger
# that hides its own blind spots is worse than no ledger.
PROBLEMS: list = []


def problem(where: str, why: str):
    PROBLEMS.append((where, why))

# Section C model. Two declared factors, both printed with every row, neither measured by this
# toolkit: `gain` is how much of the top-3 position is still unclaimed, `reach` is how close the
# current position is to being moved at all. A key we already rank #8 for is a far cheaper target
# than one we are nowhere for, even though the second has more theoretical headroom — without the
# second factor this section degenerates into "every keyword you don't rank for, sorted by price".
BANDS = [(3, "top3", 0.00, 1.00), (10, "top10", 0.45, 1.00), (30, "top30", 0.80, 0.70),
         (200, "deep", 0.95, 0.35)]
BEYOND = ("beyond-depth", 1.00, 0.10)


def band(pos):
    """-> (name, gain, reach)"""
    if pos is None:
        return BEYOND
    for limit, name, gain, reach in BANDS:
        if pos <= limit:
            return name, gain, reach
    return BEYOND


# ---------------------------------------------------------------- store readers
def read_ranks(store: Path):
    path = store / "metrics" / "ranks.csv"
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    for i, r in enumerate(rows, 2):
        raw = (r.get("position") or "").strip()
        # Stores written before `status` existed use a word in this column ("absent", "not found")
        # to mean the same thing, and a hand-edited file can hold anything at all. Read what is
        # readable, flag what is not, and never let an unreadable value become a position.
        r["position"] = None
        if raw:
            try:
                value = int(raw)
            except ValueError:
                value = None
            if value is None:
                if raw.lower() not in ("absent", "not found", "none", "-"):
                    problem(f"metrics/ranks.csv:{i}", f"position {raw!r} is neither a number nor a "
                                                      f"known word for absent; read as not observed")
            elif value < 1:
                problem(f"metrics/ranks.csv:{i}", f"position {raw!r} is not a rank; read as not observed")
            else:
                r["position"] = value
        if not (r.get("market") or "").strip() or not (r.get("keyword") or "").strip():
            problem(f"metrics/ranks.csv:{i}", "row has no market or no keyword; it can never be paired")
        if not (r.get("status") or "").strip():
            r["status"] = "ok" if r["position"] is not None else ("beyond-depth" if raw else "unknown")
        r["depth"] = (r.get("depth") or "").strip()
        r["legacy"] = not r["depth"]
        # In the wild this column holds a whole sentence:
        # "itunes-search-api@2026-08-28 limit=182 hypothesis=H003". Comparability keys on the
        # provider; the rest of the string is a note, and matching it exactly would make every
        # pair incomparable for the sole reason that each observation described itself.
        r["provider"] = re.split(r"[@\s]", (r.get("source") or "").strip(), maxsplit=1)[0]
    return rows


def read_markets(store: Path):
    path = store / "metrics" / "markets.csv"
    out = {}
    if not path.exists():
        return out
    with path.open(encoding="utf-8") as fh:
        for i, r in enumerate(csv.DictReader(fh), 2):
            code, usd = (r.get("storefront") or "").strip().lower(), (r.get("proceeds_usd") or "").strip()
            if not code:
                continue                      # territory with no storefront code: expected, not a fault
            if not usd:
                problem(f"metrics/markets.csv:{i}", f"{code} has no proceeds_usd; it cannot be ranked by value")
                continue
            try:
                out[code] = float(usd)
            except ValueError:
                problem(f"metrics/markets.csv:{i}", f"{code} proceeds_usd {usd!r} is not a number")
    return out


def hyp_markets(h):
    return [m.strip().lower() for m in (h.get("markets") or "").split(",") if m.strip()]


def read_brand_tokens(store: Path):
    """Brand queries measure whether we are indexed, never demand. Nobody searches a brand they have
    not heard of, so a brand term is not an acquisition target and must not be ranked as one."""
    config = store / "config.md"
    if not config.exists():
        return []
    found = re.search(r"^\*\*Brand tokens\*\*:\s*(.+)$", config.read_text(encoding="utf-8"), re.M)
    return [b.strip().lower() for b in found.group(1).split(",") if b.strip()] if found else []


def read_hypotheses(store: Path):
    out = []
    for path in sorted((store / "hypotheses").glob("H*.md")):
        text = path.read_text(encoding="utf-8")
        match = re.match(r"^---\n(.*?)\n---", text, re.S)
        if not match:
            problem(f"hypotheses/{path.name}", "no YAML frontmatter — NOT in the ledger at all, so it "
                                               "can never be judged, closed or counted")
            continue
        meta, key = {}, None
        for line in match.group(1).splitlines():
            field = re.match(r"^([a-z_]+):\s*(.*)$", line)
            if field:
                key = field.group(1)
                # frontmatter written from the template keeps its inline "# what this field means"
                value = re.sub(r"\s+#.*$", "", field.group(2)).strip().strip(">|").strip()
                meta[key] = value
            elif key and line.strip():
                meta[key] = (meta[key] + " " + line.strip()).strip()
        meta["_path"] = path.name
        if not (meta.get("id") or "").strip():
            problem(f"hypotheses/{path.name}", "frontmatter has no `id:` — NOT in the ledger")
            continue
        if not (meta.get("markets") or "").strip():
            problem(f"hypotheses/{meta['id']}", "frontmatter has no `markets:`; rank exposure cannot be joined")
        if (meta.get("primary_signal") or "rank").strip() != "funnel" and not (meta.get("queries") or "").strip():
            problem(f"hypotheses/{meta['id']}", "rank hypothesis has no `queries:` basket; it cannot be judged")
        out.append(meta)
    seen = {}
    for h in out:
        seen.setdefault(h["id"], []).append(h["_path"])
    for hid, files in seen.items():
        if len(files) > 1:
            problem(f"hypotheses/{hid}", f"id claimed by {len(files)} files ({', '.join(files)}); "
                                         f"ids are never reused, so one of them is mislabelled")
    return out


def parse_date(value):
    try:
        return dt.date.fromisoformat((value or "").strip()[:10])
    except ValueError:
        return None


# ---------------------------------------------------------------- ingest
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


# ---------------------------------------------------------------- report
def series(rows):
    """(market, keyword) -> observations sorted by date, failed requests dropped.

    A failed request is kept in the CSV as a record of what was attempted, but it is not an
    observation: leaving it in the series would let one outage block a key's delta forever.
    """
    out = {}
    for r in rows:
        if r["status"] == "error":
            continue
        out.setdefault((r["market"], r["keyword"]), []).append(r)
    for key in out:
        out[key].sort(key=lambda r: r["date"])
    return {k: v for k, v in out.items() if v}


def movement(first, last):
    """Return (label, delta) — a censored pair never becomes a numeric delta.

    A key seen once is not "flat": comparing a row with itself yields delta 0, which reads as
    "measured twice, did not move" when the truth is "measured once". That is the same substitution
    of absence-of-evidence for evidence-of-absence the rest of this file exists to refuse.
    """
    if first["date"] == last["date"]:
        return "only one observation date", None
    if first["provider"] != last["provider"]:
        return f"incomparable provider ({first['provider']} vs {last['provider']})", None
    if not (first["legacy"] or last["legacy"]) and first["depth"] != last["depth"]:
        return f"incomparable depth ({first['depth']} vs {last['depth']})", None

    a, b = first["position"], last["position"]
    if a is None and b is None:
        return "never observed within depth", None
    if a is None:
        return "ENTERED (was beyond depth)", None
    if b is None:
        return "EXITED (now beyond depth)", None
    label = "improved" if b < a else "regressed" if b > a else "flat"
    # Rows predating the depth/status columns pair with each other, but the pair cannot be verified
    # comparable — it carries that caveat rather than being silently promoted or silently dropped.
    return (label + (" · legacy, depth not recorded" if first["legacy"] else "")), a - b


def section_a(hyps, pairs, markets):
    print("\n## A · Hypothesis ledger — close before proposing\n")
    print("| ID | Markets | Live since | Window | State | Its own basket ↑/↓/→ | Action |")
    print("|---|---|---|---|---|---|---|")
    counts = {"judged": 0, "due": 0, "open": 0, "not-shipped": 0}
    for h in hyps:
        live, verdict = parse_date(h.get("went_live")), (h.get("verdict") or "").strip()
        mkts = hyp_markets(h)
        if verdict:
            state, action, counts["judged"] = f"judged: {verdict}", "closed", counts["judged"] + 1
        elif not live:
            state, action, counts["not-shipped"] = "not shipped", "ship it or drop it", counts["not-shipped"] + 1
        else:
            age = (TODAY - live).days
            window = re.match(r"\s*(\d+)", h.get("window_days") or "")
            window = int(window.group(1)) if window else 21
            if age >= window:
                state, action, counts["due"] = f"DUE ({age}d ≥ {window}d)", "judge now", counts["due"] + 1
            else:
                state, action, counts["open"] = f"open ({window - age}d left)", "wait", counts["open"] + 1
        # Only the hypothesis's own declared query basket. Counting every key in the storefront
        # would put a number next to the hypothesis that has nothing to do with it, and a number
        # in that column will be read as its effect.
        basket = [q.strip().lower() for q in (h.get("queries") or "").split(";") if q.strip()]
        if (h.get("primary_signal") or "").strip() == "funnel":
            # A funnel hypothesis is not measured by rank; an empty basket is correct, not missing.
            keys = "funnel — not rank-measured"
        elif not mkts:
            keys = "no `markets:`"
        elif not basket:
            keys = "no `queries:` — unjudgeable"
        else:
            up = down = flat = miss = 0
            for market in mkts:
                for query in basket:
                    obs = pairs.get((market, query))
                    if not obs:
                        miss += 1
                        continue
                    _, delta = movement(obs[0], obs[-1])
                    if delta is None:
                        miss += 1
                    else:
                        up, down, flat = up + (delta > 0), down + (delta < 0), flat + (delta == 0)
            keys = f"{up} / {down} / {flat}" + (f" (+{miss} unpaired)" if miss else "")
        print(f"| {h.get('id','?')} | {','.join(mkts) or '—'} | {live or '—'} | "
              f"{h.get('window_days','21')}d | {state} | {keys} | {action} |")
    print(f"\n{counts['judged']} judged · {counts['due']} due · {counts['open']} open · "
          f"{counts['not-shipped']} not shipped")
    return counts


def section_b(pairs, markets, limit):
    print("\n## B · Every tracked key — progress and regress\n")
    numeric, censored = [], []
    for (market, keyword), obs in pairs.items():
        label, delta = movement(obs[0], obs[-1])
        row = (market, keyword, obs[0]["date"], obs[0]["position"], obs[-1]["date"],
               obs[-1]["position"], delta, label)
        (numeric if delta is not None else censored).append(row)
    numeric.sort(key=lambda r: (-(r[6] or 0), r[0]))
    if not numeric:
        print("_No paired numeric movement yet — a delta needs two comparable observations "
              "of the same key at the same depth from the same source._\n")
    else:
        print("| Market | Key | First | Pos | Latest | Pos | Δ | |")
        print("|---|---|---|---:|---|---:|---:|---|")
        for r in numeric[:limit] + ([] if len(numeric) <= limit else numeric[-limit:]):
            print(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]} | {r[5]} | "
                  f"{r[6]:+d} | {r[7]} |")
    entered = [r for r in censored if r[7].startswith("ENTERED")]
    exited = [r for r in censored if r[7].startswith("EXITED")]
    never = [r for r in censored if r[7].startswith("never")]
    incomp = [r for r in censored if r[7].startswith("incomparable")]
    print(f"\nEntered ranking: {len(entered)} · Fell out of depth: {len(exited)} · "
          f"Never within depth: {len(never)} · Incomparable pairs: {len(incomp)}")
    for r in entered[:15]:
        print(f"  ENTERED  {r[0]} · {r[1]} → position {r[5]} on {r[4]}")
    for r in exited[:15]:
        print(f"  EXITED   {r[0]} · {r[1]} · was {r[3]} on {r[2]}")
    return numeric, censored


def section_c(pairs, markets, hyps, limit, brand):
    print("\n## C · What to do next, ordered by money at stake\n")
    print("_Order = net proceeds per paying subscriber in that storefront (live ASC price record) "
          "× gain (how much of a top-3 position is unclaimed) × reach (how movable the current "
          "position is). Gain and reach are declared ordering assumptions printed on every row, not "
          "measured tap share. No currency total is implied: this ranks WHAT FIRST, it does not "
          "forecast revenue. A key whose last observation was a failed request is absent here — an "
          "outage is not an opportunity._\n")
    covered = {m for h in hyps if not (h.get("verdict") or "").strip() for m in hyp_markets(h)}
    scored, unpriced, brand_skipped = [], 0, 0
    for (market, keyword), obs in pairs.items():
        if any(token in keyword.lower() for token in brand):
            brand_skipped += 1
            continue
        proceeds = markets.get(market)
        if proceeds is None:
            unpriced += 1
            continue
        if obs[-1]["status"] == "error":
            continue                                # last look failed: unknown, not an opportunity
        pos = obs[-1]["position"]
        name, gain, reach = band(pos)
        if gain <= 0:
            continue                                # already top3: defend, don't attack
        scored.append((round(proceeds * gain * reach, 2), market, keyword, pos, name,
                       proceeds, f"{gain}×{reach}",
                       "covered by an open hypothesis" if market in covered else "UNCLAIMED"))
    scored.sort(reverse=True)
    print("| Score | Market | Key | Position now | Band | Net proceeds/sub | Gain×Reach | Status |")
    print("|---:|---|---|---:|---|---:|---:|---|")
    for s in scored[:limit]:
        pos = s[3] if s[3] is not None else f">depth"
        print(f"| {s[0]} | {s[1]} | {s[2]} | {pos} | {s[4]} | ${s[5]:.2f} | {s[6]} | {s[7]} |")
    if brand_skipped:
        print(f"\n{brand_skipped} brand-term keys excluded: rank on our own name shows we are indexed, "
              f"not that anyone searches for us. Set `**Brand tokens**:` in config.md to change the list.")
    if unpriced:
        print(f"\n{unpriced} tracked keys sit in storefronts with no `proceeds_usd` in "
              f"metrics/markets.csv — ranked nowhere rather than ranked at zero.")
    return scored


def print_problems(stream=sys.stdout):
    """Every command prints this, not just `report` — a command that finds a broken row and says
    nothing is the silent failure this whole section exists to prevent."""
    seen = list(dict.fromkeys(PROBLEMS))       # a refresh reads the store several times per run
    if not seen:
        if stream is sys.stdout:
            print("\n_Every store file parsed cleanly._")
        return
    print(f"\n## ⚠ {len(seen)} inputs this run could not use\n", file=stream)
    print("| Where | What went wrong |\n|---|---|", file=stream)
    for where, why in seen:
        print(f"| `{where}` | {why} |", file=stream)
    print("\nThese are not counted anywhere. Fix them or the ledger is answering a question "
          "about a smaller store than you have.", file=stream)


def report(store: Path, limit: int):
    PROBLEMS.clear()
    rows = read_ranks(store)
    markets, hyps = read_markets(store), read_hypotheses(store)
    pairs = series(rows)
    attempted = {(r["market"], r["keyword"]) for r in rows}
    dates = sorted({r["date"] for r in rows})
    paired = sum(movement(o[0], o[-1])[1] is not None for o in pairs.values())
    failed = sum(r["status"] == "error" for r in rows)
    print(f"# Marketing ledger · {TODAY} · store {store}")
    print(f"\n{len(hyps)} hypotheses · {len(attempted)} tracked keys · {len(rows)} observations on "
          f"{len(dates)} dates ({', '.join(dates[:1] + dates[-1:])}) · {len(markets)} priced storefronts")
    print(f"\n**Coverage: {paired} of {len(attempted)} keys have a comparable pair, "
          f"{len(attempted) - len(pairs)} have no successful observation at all; {failed} requests failed.** "
          f"A thin section below is thin because of this line, not because nothing moved.")
    if not rows:
        print("\n**metrics/ranks.csv is empty — no observation ledger exists yet.** Sections B and C "
              "cannot be computed from nothing; ingest a snapshot first. This is the honest state, "
              "not a bug.")
    print_problems()
    section_a(hyps, pairs, markets)
    section_b(pairs, markets, limit)
    section_c(pairs, markets, hyps, limit, read_brand_tokens(store))


# ---------------------------------------------------------------- draft
def draft(store: Path, market: str, queries: list, window: int, out: Path | None):
    """Scaffold a hypothesis that is measurable BEFORE it is written.

    The deterministic half only: id, storefront, basket, the baseline each query actually has, the
    dates the window opens and closes, a kill criterion carrying real numbers, and every collision
    with work already in flight. The argument — change and mechanism — is not scaffolding and is
    left blank on purpose; a generated mechanism is a guess wearing a hypothesis's clothes.
    """
    pairs, markets, hyps = series(read_ranks(store)), read_markets(store), read_hypotheses(store)
    market = market.lower()
    queries = [q.strip().lower() for q in queries if q.strip()]
    if not queries:
        sys.exit("--queries is required: an experiment with no basket cannot be judged")

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
    opens, closes = TODAY, TODAY + dt.timedelta(days=window)

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

# ---------------------------------------------------------------- refresh
def refresh(store: Path, bundle: str, markets_filter, failed_only: bool, delay: float,
            out_dir: Path):
    """Re-query the basket the store already tracks, then ingest it. One command, so that the
    weekly cadence a 21-day window depends on actually happens.

    The basket is whatever `ranks.csv` already contains — never a list retyped by hand, which is
    how a query silently leaves the basket and a window closes on a different set than it opened on.

    Apple documents the Search API at "approximately 20 calls per minute", and over it returns 429
    (https://performance-partners.apple.com/search-api). Hence DEFAULT_DELAY = 3.0s. Measured here
    on 2026-09-08: 6 workers at 0.1s lost 478 of 649 queries; one worker at 1.0s still lost 135 of
    261. Apple says "approximately", so a legal rate can still 429 in a burst: run the command again
    with --failed-only to pick up what it lost.
    """
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
    script = Path(__file__).resolve().parent / "rank_audit.py"
    out_dir.mkdir(parents=True, exist_ok=True)
    merged, ok, err = {}, 0, 0
    for market in sorted(basket):
        target = out_dir / f"{market}.json"
        print(f"  {market}: {len(basket[market])} queries…", flush=True)
        done = subprocess.run([sys.executable, str(script), "--bundle", bundle, "--markets", market,
                               "--keywords", ",".join(basket[market]), "--output", str(target),
                               "--delay", str(delay)], capture_output=True, text=True)
        if done.returncode or not target.exists():
            tail = (done.stderr or done.stdout or "").strip().splitlines()[-4:]
            print(f"  {market}: FAILED (exit {done.returncode}) — this storefront is unrefreshed, its "
                  f"keys keep their previous observation:\n      " + "\n      ".join(tail),
                  file=sys.stderr, flush=True)
            continue
        for country, entries in json.loads(target.read_text(encoding="utf-8")).items():
            merged.setdefault(country, []).extend(entries)
            ok += sum(e.get("query_status") == "ok" for e in entries)
            err += sum(e.get("query_status") == "error" for e in entries)
    snapshot = out_dir / f"snapshot_{TODAY}.json"
    snapshot.write_text(json.dumps(merged, ensure_ascii=False), encoding="utf-8")
    for market in basket:                      # the per-market files are inputs to the merge above
        (out_dir / f"{market}.json").unlink(missing_ok=True)
    print(f"{ok} observed · {err} failed → {snapshot}")
    if err and not ok:
        sys.exit(f"every query failed — Apple returns 429 above ~20 calls/minute, so --delay must "
                 f"stay >= 3.0 (this run used {delay}). Nothing ingested.")
    return ingest(store, snapshot, str(TODAY), "itunes-search-api", 200, "target")

# ---------------------------------------------------------------- self-check
def self_check():
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        store = Path(tmp)
        (store / "metrics").mkdir()
        (store / "hypotheses").mkdir()
        (store / "metrics" / "markets.csv").write_text(
            "territory,storefront,currency,customer_price,proceeds_local,fx_to_usd,proceeds_usd,source\n"
            "DEU,de,EUR,35.99,25.71,0.86,29.88,test\n", encoding="utf-8")
        snap = store / "s1.json"
        snap.write_text(json.dumps([
            {"country_code": "de", "term": "fotos komprimieren", "our_rank": 40, "total_results": 200},
            {"country_code": "de", "term": "video komprimieren", "our_rank": None, "total_results": 200},
            {"country_code": "de", "term": "stale", "our_rank": 12, "total_results": 5},   # impossible
            {"country_code": "de", "term": "failed", "our_rank": None, "query_status": "error"},
        ]), encoding="utf-8")
        assert ingest(store, snap, "2026-09-01", "itunes-search-api", 200, "target") == 3, "stale row must be refused"
        failed = [r for r in read_ranks(store) if r["keyword"] == "failed"]
        assert failed and failed[0]["status"] == "error", "a failed request is not beyond-depth"
        snap2 = store / "s2.json"
        snap2.write_text(json.dumps([
            {"country_code": "de", "term": "fotos komprimieren", "our_rank": 8, "total_results": 200},
            {"country_code": "de", "term": "video komprimieren", "our_rank": 30, "total_results": 200},
        ]), encoding="utf-8")
        ingest(store, snap2, "2026-09-08", "itunes-search-api", 200, "target")
        assert ingest(store, snap2, "2026-09-08", "itunes-search-api", 200, "target") == 0, "must dedupe"
        aside = store / "aside"                # its own store: fixtures must not perturb the rest
        (aside / "metrics").mkdir(parents=True)
        twice = aside / "twice.json"
        twice.write_text(json.dumps([
            {"country_code": "de", "term": "dup", "our_rank": None, "total_results": 200},
            {"country_code": "de", "term": "dup", "our_rank": None, "total_results": 200},
        ]), encoding="utf-8")
        assert ingest(aside, twice, "2026-09-08", "itunes-search-api", 200, "target") == 1, \
            "a snapshot listing one query twice must write one row"
        pairs = series(read_ranks(store))
        assert movement(*[pairs[("de", "fotos komprimieren")][i] for i in (0, -1)]) == ("improved", 32)
        label, delta = movement(*[pairs[("de", "video komprimieren")][i] for i in (0, -1)])
        assert delta is None and label.startswith("ENTERED"), "censored → number is not a delta"
        single = series(read_ranks(store))[("de", "fotos komprimieren")][:1]
        assert movement(single[0], single[0]) == ("only one observation date", None), \
            "one observation is not a flat pair"
        bad = store / "metrics" / "bad.csv"
        bad.write_text("date,market,keyword,group,position,popularity,difficulty,source,depth,status\n"
                       "2026-09-01,de,x,target,--5,,,itunes-search-api,200,ok\n"
                       "2026-09-02,de,y,target,-5,,,itunes-search-api,200,ok\n", encoding="utf-8")
        keep_ranks = (store / "metrics" / "ranks.csv").read_text(encoding="utf-8")
        (store / "metrics" / "ranks.csv").write_text(bad.read_text(encoding="utf-8"), encoding="utf-8")
        PROBLEMS.clear()
        rows = read_ranks(store)               # must not raise on a hand-edited position
        assert all(r["position"] is None for r in rows), "a non-rank must not band as top3"
        assert len(PROBLEMS) == 2, PROBLEMS     # one unreadable value, one non-rank
        PROBLEMS.clear()
        (store / "metrics" / "ranks.csv").write_text(keep_ranks, encoding="utf-8")
        legacy = store / "metrics" / "legacy.csv"
        legacy.write_text("date,market,keyword,group,position,popularity,difficulty,source\n"
            "2026-08-23,de,weisses rauschen,target,43,,,itunes-search-api@2026-08-23 limit=200 baseline\n"
            "2026-09-04,de,weisses rauschen,target,21,,,itunes-search-api@2026-09-04 limit=182 H003\n",
            encoding="utf-8")
        import shutil
        keep = (store / "metrics" / "ranks.csv").read_text(encoding="utf-8")
        shutil.copy(legacy, store / "metrics" / "ranks.csv")
        lrows = series(read_ranks(store))[("de", "weisses rauschen")]
        assert movement(lrows[0], lrows[-1]) == ("improved · legacy, depth not recorded", 22), \
            "a store that writes its provenance as prose must still pair"
        (store / "metrics" / "ranks.csv").write_text(keep, encoding="utf-8")
        (store / "hypotheses" / "H001-x.md").write_text(
            "---\nid: H001\nmarkets: de\nqueries: fotos komprimieren\nwent_live: 2026-08-01\nwindow_days: 21\nverdict:\n---\n", encoding="utf-8")
        (store / "hypotheses" / "H002-x.md").write_text(
            "---\nid: H002\nwent_live:\nwindow_days: 21\nverdict:\n---\n", encoding="utf-8")
        PROBLEMS.clear()
        hyps = read_hypotheses(store)
        assert [h["id"] for h in hyps] == ["H001", "H002"]
        messages = " ".join(message for _, message in PROBLEMS)
        assert "no `markets:`" in messages and "no `queries:`" in messages, \
            "legacy hypotheses must be reported as malformed"
        PROBLEMS.clear()
        by_market = {"de": [obs for (m, _), obs in pairs.items() if m == "de"]}
        counts = section_a(hyps, by_market, read_markets(store))
        assert counts["due"] == 1 and counts["not-shipped"] == 1, counts
        (store / "config.md").write_text("**Brand tokens**: komprimieren\n", encoding="utf-8")
        assert read_brand_tokens(store) == ["komprimieren"]
        assert not section_c(pairs, read_markets(store), hyps, 10, ["komprimieren"]), \
            "a brand term is not an acquisition target"
        scored = section_c(pairs, read_markets(store), hyps, 10, [])
        assert scored and scored[0][1] == "de" and scored[0][5] == 29.88
        assert scored[0][2] == "video komprimieren" and scored[-1][2] == "fotos komprimieren", (
            "a #30 with room must outrank a #8 that is nearly top3")
        assert all(s[0] > 0 for s in scored), "score must use real proceeds, never a stored opportunity field"
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            hid = draft(store, "de", ["fotos komprimieren"], 21, None)
        body = buf.getvalue()
        assert hid == "H003", hid
        assert "queries: fotos komprimieren" in body and "kill_criterion_written:" in body
        assert "not better than 8" in body, "kill criterion must carry the real baseline"
        assert "In flight in this storefront" in body, "must warn about a concurrent experiment"
        for bad in ("never queried", "failed"):   # "failed" exists but only as a failed request
            try:
                draft(store, "de", [bad], 21, None)
                raise AssertionError(f"must refuse a basket it cannot measure: {bad}")
            except SystemExit as exc:
                assert "no successful observation" in str(exc), exc
    print("\nOK: stale positions, failed requests, dedupe, one-observation keys, unreadable positions,\n"
          "    censored pairs, legacy provenance/schema warnings, window states, proceeds-weighted order")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", nargs="?", choices=["report", "ingest", "draft", "refresh"], default="report")
    p.add_argument("snapshot", nargs="?")
    p.add_argument("--store", type=Path)
    p.add_argument("--date", default=str(TODAY))
    p.add_argument("--delay", type=float)
    p.add_argument("--source", default="itunes-search-api")
    p.add_argument("--depth", type=int)
    p.add_argument("--group", default="target")
    p.add_argument("--limit", type=int, default=25)
    p.add_argument("--market")
    p.add_argument("--queries", default="")
    p.add_argument("--window", type=int, default=21)
    p.add_argument("--out", type=Path)
    p.add_argument("--bundle")
    p.add_argument("--markets")
    p.add_argument("--failed-only", action="store_true")
    p.add_argument("--out-dir", type=Path)
    p.add_argument("--self-check", action="store_true")
    args = p.parse_args()
    if args.self_check:
        return self_check()
    if not args.store or not args.store.exists():
        p.error("--store must point at the app repo's marketing/ directory")
    PROBLEMS.clear()
    if args.command == "ingest":
        if not args.snapshot:
            p.error("ingest needs a snapshot JSON path")
        done = ingest(args.store, Path(args.snapshot), args.date, args.source, args.depth, args.group)
        print_problems(sys.stderr)
        return done
    if args.command == "refresh":
        if not args.bundle:
            p.error("refresh needs --bundle (the app's exact bundle id)")
        done = refresh(args.store, args.bundle,
                       [m.strip().lower() for m in (args.markets or "").split(",") if m.strip()],
                       args.failed_only, DEFAULT_DELAY if args.delay is None else args.delay,
                       args.out_dir or args.store / "reports" / "snapshots")
        print_problems(sys.stderr)
        return done
    if args.command == "draft":
        if not args.market:
            p.error("draft needs --market and --queries")
        done = draft(args.store, args.market, args.queries.split(";"), args.window, args.out)
        print_problems(sys.stderr)
        return done
    report(args.store, args.limit)


if __name__ == "__main__":
    main()
