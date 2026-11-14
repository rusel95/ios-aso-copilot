"""The ledger report as text: sections A, B and C and the bands table, printed from the pure functions."""
from __future__ import annotations

import datetime as dt
from pathlib import Path

from aso.ledger_state import hypothesis_states, priority
from aso.ranks import band_of, brand_hit, coverage, demand_label, movers, series, zero_result_keys
from aso.store import (PROBLEMS, demand_lookup, print_problems, read_brand_tokens, read_hypotheses, read_markets,
                       read_ranks)

NO_BASKET = {"funnel": "funnel — not rank-measured", "no-markets": "no `markets:`",
             "no-queries": "no `queries:` — unjudgeable"}


def section_a(hyps, pairs, markets, empty=frozenset(), as_of=None):
    as_of = as_of or dt.date.today()
    print("\n## A · Hypothesis ledger — close before proposing\n")
    print("| ID | Markets | Live since | Window | State | Its own basket ↑/↓/→ | Action |")
    print("|---|---|---|---|---|---|---|")
    counts = {"judged": 0, "due": 0, "open": 0, "not-shipped": 0}
    for s in hypothesis_states(hyps, pairs, empty, as_of):
        counts[s["state"]] += 1
        if s["state"] == "judged":
            state, action = f"judged: {s['verdict']}", "closed"
        elif s["state"] == "not-shipped":
            state, action = "not shipped", "ship it or drop it"
        elif s["state"] == "due":
            state, action = f"DUE ({s['age_days']}d ≥ {s['window']}d)", "judge now"
        else:
            state, action = f"open ({s['window'] - s['age_days']}d left)", "wait"
        b = s["basket"]
        if b is None:
            keys = NO_BASKET[s["basket_reason"]]
        else:
            keys = (f"{b['up']} / {b['down']} / {b['flat']}" + (f" (+{b['unpaired']} unpaired)" if b["unpaired"] else "")
                    + (f" (+{b['unmeasurable']} zero-result: unmeasurable)" if b["unmeasurable"] else ""))
        print(f"| {s['id']} | {','.join(s['markets']) or '—'} | {s['live'] or '—'} | "
              f"{s['window']}d | {state} | {keys} | {action} |")
    print(f"\n{counts['judged']} judged · {counts['due']} due · {counts['open']} open · "
          f"{counts['not-shipped']} not shipped")
    return counts


def section_b(pairs, markets, limit, brand=()):
    print("\n## B · Every tracked key — progress and regress (non-brand)\n")
    brand_skipped = sum(any(brand_hit(token, keyword) for token in brand) for _, keyword in pairs)
    rows = [(r["market"], r["keyword"], r["first_date"], r["first"], r["last_date"], r["last"], r["delta"], r["label"])
            for r in movers(pairs, list(brand))]
    numeric, censored = [r for r in rows if r[6] is not None], [r for r in rows if r[6] is None]
    if brand_skipped:
        print(f"_{brand_skipped} brand-term keys excluded: rank on brand measures indexation only, not demand._\n")
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


def section_c(pairs, markets, hyps, limit, brand, demand=None):
    """Prints the priority order; returns it as the tuples older callers read."""
    print("\n## C · What to do next, ordered by money at stake\n")
    print("_Order = net proceeds per paying subscriber in that storefront (live ASC price record) "
          "× gain (how much of a top-3 position is unclaimed) × reach (how movable the current "
          "position is). Gain and reach are declared ordering assumptions printed on every row, not "
          "measured tap share. No currency total is implied: this ranks WHAT FIRST, it does not "
          "forecast revenue. A key whose last observation was a failed request is absent here — an "
          "outage is not an opportunity._\n")
    print("_\"Dominant\" below means a verified top-3 position (top-5 for us/gb/de/fr/jp/cn) as of "
          "the LATEST observation — not merely that an open hypothesis targets that market. A "
          "hypothesis in flight with the key still outside that band is still open ground: it is "
          "labelled `open hypothesis, not yet dominant`, not `covered`._\n")
    brand_skipped = sum(any(brand_hit(token, keyword) for token in brand) for _, keyword in pairs)
    unpriced = sum(markets.get(market) is None and not any(brand_hit(token, keyword) for token in brand)
                   for market, keyword in pairs)
    rows = priority(pairs, markets, hyps, list(brand), demand)
    scored = [(r["score"], r["market"], r["keyword"], r["position"], r["band"], r["proceeds"],
               f"{r['gain']}×{r['reach']}", r["status"]) for r in rows]
    shown = bool(demand and demand[1])         # a store that never ran the radar keeps its old table
    if shown:
        print("_Demand is Apple's own search popularity (`radar.py pull` → metrics/popularity*.csv): `head N` is its "
              "1–100 score for a term in the published head list; `below N` means not listed, so under the lowest "
              "score listed for that storefront: volume unknown, not zero; `no data` means Apple lists nothing "
              "there; `—` means never pulled. It informs the order; it is not part of the score._\n")
    print("| Score | Market | Key |" + (" Demand |" if shown else "") + " Position now | Band | Net proceeds/sub | Gain×Reach | Status |")
    print("|---:|---|---|" + ("---|" if shown else "") + "---:|---|---:|---:|---|")
    for s in scored[:limit]:
        pos = s[3] if s[3] is not None else f">depth"
        cell = f" {demand_label(demand, s[1], s[2])} |" if shown else ""
        print(f"| {s[0]} | {s[1]} | {s[2]} |{cell} {pos} | {s[4]} | ${s[5]:.2f} | {s[6]} | {s[7]} |")
    if brand_skipped:
        print(f"\n{brand_skipped} brand-term keys excluded: rank on our own name shows we are indexed, "
              f"not that anyone searches for us. Set `**Brand tokens**:` in config.md to change the list.")
    if unpriced:
        print(f"\n{unpriced} tracked keys sit in storefronts with no `proceeds_usd` in "
              f"metrics/markets.csv — ranked nowhere rather than ranked at zero.")
    return scored


def report(store: Path, limit: int, as_of=None):
    as_of = as_of or dt.date.today()
    PROBLEMS.clear()
    rows = read_ranks(store)
    markets, hyps = read_markets(store), read_hypotheses(store)
    pairs = series(rows)
    seen = coverage(rows)
    dates = sorted({r["date"] for r in rows})
    empty = zero_result_keys(rows)
    no_results = sorted(empty)
    print(f"# Marketing ledger · {as_of} · store {store}")
    print(f"\n{len(hyps)} hypotheses · {seen['tracked']} tracked keys · {seen['observations']} observations on "
          f"{len(dates)} dates ({', '.join(dates[:1] + dates[-1:])}) · {len(markets)} priced storefronts")
    print(f"\n**Coverage: {seen['paired']} of {seen['tracked']} keys have a comparable pair, "
          f"{seen['unobserved']} have no successful observation at all; {seen['failed']} requests failed.** "
          f"A thin section below is thin because of this line, not because nothing moved.")
    if no_results:
        by_market = {}
        for market, _ in no_results:
            by_market[market] = by_market.get(market, 0) + 1
        print(f"\n**{len(no_results)} tracked keys are unmeasurable by this method: the API returns zero results "
              f"for them** ({', '.join(f'{m} {n}' for m, n in sorted(by_market.items()))}). They are left out "
              f"of every section below; a hypothesis whose basket is only such keys cannot be judged on rank.")
    if not rows:
        print("\n**metrics/ranks.csv is empty — no observation ledger exists yet.** Sections B and C "
              "cannot be computed from nothing; ingest a snapshot first. This is the honest state, "
              "not a bug.")
    print_problems()
    brand = read_brand_tokens(store)
    section_a(hyps, pairs, markets, empty, as_of)
    section_b(pairs, markets, limit, brand)
    section_c(pairs, markets, hyps, limit, brand, demand_lookup(store))


def bands(store: Path):
    """Top-200 at a glance: for every storefront, how many tracked non-brand keys sit in each band now, and how many
    were inside the top 200 at their first observation and at the previous refresh date. Empty-result keys are out."""
    rows = read_ranks(store)
    brand = read_brand_tokens(store)
    pairs = series(rows)
    dates = sorted({r["date"] for r in rows if r["status"] != "error"})
    if not dates:
        print("No observations in metrics/ranks.csv.")
        return
    latest = dates[-1]
    prev = dates[-2] if len(dates) > 1 else None
    per = {}
    for (market, key), obs in pairs.items():
        if any(brand_hit(b, key) for b in brand):
            continue
        c = per.setdefault(market, {"keys": 0, "first_in": 0, "prev_in": 0, "best": None,
                                    **{f"now_{b}": 0 for b in ("t10", "t30", "t100", "t200", "out")}})
        last = obs[-1]
        before = [o for o in obs if prev and o["date"] <= prev][-1:] or [obs[0]]
        c["keys"] += 1
        c[f"now_{band_of(last['position'])}"] += 1
        c["first_in"] += obs[0]["position"] is not None
        c["prev_in"] += before[0]["position"] is not None
        if last["position"] is not None:
            c["best"] = last["position"] if c["best"] is None else min(c["best"], last["position"])
    empty = sorted({m for m, _ in zero_result_keys(rows)})
    print(f"\nTOP-200 BANDS (non-brand keys; latest refresh {latest}, previous {prev or '—'}; "
          f"iTunes Search order, not device rank)")
    print(f"{'market':<7}{'keys':>5} | {'top10':>5}{'top30':>6}{'top100':>7}{'top200':>7}{'out':>5} | "
          f"{'in@first':>9}{'in@prev':>8}{'in@now':>7} | best")
    tot = {k: 0 for k in ("keys", "t10", "t30", "t100", "t200", "out", "first_in", "prev_in")}

    def score(c):
        return (-c["now_t10"], -c["now_t30"], -c["now_t100"], -c["now_t200"])
    for market, c in sorted(per.items(), key=lambda kv: score(kv[1])):
        now_in = c["keys"] - c["now_out"]
        print(f"{market:<7}{c['keys']:>5} | {c['now_t10']:>5}{c['now_t30']:>6}{c['now_t100']:>7}{c['now_t200']:>7}"
              f"{c['now_out']:>5} | {c['first_in']:>9}{c['prev_in']:>8}{now_in:>7} | {c['best'] or '—'}")
        tot["keys"] += c["keys"]
        for b in ("t10", "t30", "t100", "t200", "out"):
            tot[b] += c[f"now_{b}"]
        tot["first_in"] += c["first_in"]
        tot["prev_in"] += c["prev_in"]
    print(f"{'TOTAL':<7}{tot['keys']:>5} | {tot['t10']:>5}{tot['t30']:>6}{tot['t100']:>7}{tot['t200']:>7}{tot['out']:>5} | "
          f"{tot['first_in']:>9}{tot['prev_in']:>8}{tot['keys'] - tot['out']:>7} |")
    if empty:
        print(f"Unmeasurable (API returns no results, left out above): storefronts {', '.join(empty)}")
