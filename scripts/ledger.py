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
    for r in rows:
        raw = (r.get("position") or "").strip()
        # Stores written before `status` existed use a word in this column ("absent", "not found")
        # to mean the same thing. Read it, do not crash on it, and do not read it as a number.
        r["position"] = int(raw) if raw.lstrip("-").isdigit() else None
        if not (r.get("status") or "").strip():
            r["status"] = "ok" if r["position"] is not None else ("beyond-depth" if raw else "unknown")
        r["depth"] = (r.get("depth") or "").strip()
        r["legacy"] = not r["depth"]
        # In the wild this column holds a whole sentence:
        # "itunes-search-api@2026-08-28 limit=182 hypothesis=H003". Comparability keys on the
        # provider; the rest of the string is a note, and matching it exactly would make every
        # pair incomparable for the sole reason that each observation described itself.
        r["provider"] = re.split(r"[@\s]", (r.get("source") or "").strip(), 1)[0]
    return rows


def read_markets(store: Path):
    path = store / "metrics" / "markets.csv"
    out = {}
    if not path.exists():
        return out
    with path.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            code, usd = (r.get("storefront") or "").strip().lower(), (r.get("proceeds_usd") or "").strip()
            if code and usd:
                out[code] = float(usd)
    return out


def read_hypotheses(store: Path):
    out = []
    for path in sorted((store / "hypotheses").glob("H*.md")):
        text = path.read_text(encoding="utf-8")
        match = re.match(r"^---\n(.*?)\n---", text, re.S)
        if not match:
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
        out.append(meta)
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
    existing = {(r["date"], r["market"], r["keyword"], r["source"]) for r in read_ranks(store)}
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
            if (date, market, term, source) in existing:
                continue
            writer.writerow([date, market, term, group, pos if pos is not None else "",
                             "", "", source, depth or "", status])
            new += 1
    print(f"ingested {new} rows into {target} (date={date} source={source} depth={depth})")
    return new


# ---------------------------------------------------------------- report
def series(rows):
    """(market, keyword) -> observations sorted by date."""
    out = {}
    for r in rows:
        out.setdefault((r["market"], r["keyword"]), []).append(r)
    for key in out:
        out[key].sort(key=lambda r: r["date"])
    return out


def movement(first, last):
    """Return (label, delta) — a censored pair never becomes a numeric delta."""
    if first["provider"] != last["provider"]:
        return f"incomparable provider ({first['provider']} vs {last['provider']})", None
    if not (first["legacy"] or last["legacy"]) and first["depth"] != last["depth"]:
        return f"incomparable depth ({first['depth']} vs {last['depth']})", None
    if "error" in (first.get("status"), last.get("status")):
        return "a request in this pair failed", None
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


def section_a(hyps, ranks_by_market, markets):
    print("\n## A · Hypothesis ledger — close before proposing\n")
    print("| ID | Markets | Live since | Window | State | Keys improved / regressed / flat | Action |")
    print("|---|---|---|---|---|---|---|")
    counts = {"judged": 0, "due": 0, "open": 0, "not-shipped": 0}
    for h in hyps:
        live, verdict = parse_date(h.get("went_live")), (h.get("verdict") or "").strip()
        mkts = [m.strip().lower() for m in (h.get("markets") or "").split(",") if m.strip()]
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
        up = down = flat = 0
        for market in mkts:
            for pair in ranks_by_market.get(market, []):
                label, delta = movement(pair[0], pair[-1])
                if delta is None:
                    continue
                up, down, flat = up + (delta > 0), down + (delta < 0), flat + (delta == 0)
        keys = f"{up} / {down} / {flat}" if mkts else "no `markets:` field"
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


def section_c(pairs, markets, hyps, limit):
    print("\n## C · What to do next, ordered by money at stake\n")
    print("_Order = net proceeds per paying subscriber in that storefront (live ASC price record) "
          "× gain (how much of a top-3 position is unclaimed) × reach (how movable the current "
          "position is). Gain and reach are declared ordering assumptions printed on every row, not "
          "measured tap share. No currency total is implied: this ranks WHAT FIRST, it does not "
          "forecast revenue. A key whose last observation was a failed request is absent here — an "
          "outage is not an opportunity._\n")
    covered = {m.strip().lower() for h in hyps if not (h.get("verdict") or "").strip()
               for m in (h.get("markets") or "").split(",") if m.strip()}
    scored, unpriced = [], 0
    for (market, keyword), obs in pairs.items():
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
    if unpriced:
        print(f"\n{unpriced} tracked keys sit in storefronts with no `proceeds_usd` in "
              f"metrics/markets.csv — ranked nowhere rather than ranked at zero.")
    return scored


def report(store: Path, limit: int):
    rows = read_ranks(store)
    markets, hyps = read_markets(store), read_hypotheses(store)
    pairs = series(rows)
    by_market = {}
    for (market, _), obs in pairs.items():
        by_market.setdefault(market, []).append(obs)
    print(f"# Marketing ledger · {TODAY} · store {store}")
    print(f"\n{len(hyps)} hypotheses · {len(pairs)} tracked keys · {len(rows)} rank observations · "
          f"{len(markets)} priced storefronts")
    if not rows:
        print("\n**metrics/ranks.csv is empty — no observation ledger exists yet.** Sections B and C "
              "cannot be computed from nothing; ingest a snapshot first. This is the honest state, "
              "not a bug.")
    section_a(hyps, by_market, markets)
    section_b(pairs, markets, limit)
    section_c(pairs, markets, hyps, limit)


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
        pairs = series(read_ranks(store))
        assert movement(*[pairs[("de", "fotos komprimieren")][i] for i in (0, -1)]) == ("improved", 32)
        label, delta = movement(*[pairs[("de", "video komprimieren")][i] for i in (0, -1)])
        assert delta is None and label.startswith("ENTERED"), "censored → number is not a delta"
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
            "---\nid: H001\nmarkets: de\nwent_live: 2026-08-01\nwindow_days: 21\nverdict:\n---\n", encoding="utf-8")
        (store / "hypotheses" / "H002-x.md").write_text(
            "---\nid: H002\nmarkets: de\nwent_live:\nwindow_days: 21\nverdict:\n---\n", encoding="utf-8")
        hyps = read_hypotheses(store)
        assert [h["id"] for h in hyps] == ["H001", "H002"]
        by_market = {"de": [obs for (m, _), obs in pairs.items() if m == "de"]}
        counts = section_a(hyps, by_market, read_markets(store))
        assert counts["due"] == 1 and counts["not-shipped"] == 1, counts
        scored = section_c(pairs, read_markets(store), hyps, 10)
        assert scored and scored[0][1] == "de" and scored[0][5] == 29.88
        assert scored[0][2] == "video komprimieren" and scored[-1][2] == "fotos komprimieren", (
            "a #30 with room must outrank a #8 that is nearly top3")
        assert all(s[0] > 0 for s in scored), "score must use real proceeds, never a stored opportunity field"
    print("\nOK: stale positions, failed requests, dedupe, censored pairs, legacy free-text provenance,\n    window states, proceeds-weighted order")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", nargs="?", choices=["report", "ingest"], default="report")
    p.add_argument("snapshot", nargs="?")
    p.add_argument("--store", type=Path)
    p.add_argument("--date", default=str(TODAY))
    p.add_argument("--source", default="itunes-search-api")
    p.add_argument("--depth", type=int)
    p.add_argument("--group", default="target")
    p.add_argument("--limit", type=int, default=25)
    p.add_argument("--self-check", action="store_true")
    args = p.parse_args()
    if args.self_check:
        return self_check()
    if not args.store or not args.store.exists():
        p.error("--store must point at the app repo's marketing/ directory")
    if args.command == "ingest":
        if not args.snapshot:
            p.error("ingest needs a snapshot JSON path")
        return ingest(args.store, Path(args.snapshot), args.date, args.source, args.depth, args.group)
    report(args.store, args.limit)


if __name__ == "__main__":
    main()
