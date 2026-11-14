#!/usr/bin/env python3
"""
rank_audit.py — App Store keyword discovery observations with explicit provenance.

Keyword discovery strategy (in order of preference):
  1. --expand-from-hints  : auto-generate queries from Apple's own autocomplete for seed terms
                            This is the RIGHT approach — keywords come from what users actually type.
  2. --keywords "a,b,c"   : manual override for specific terms
  3. DEFAULT_SEEDS + hints : falls back to seeded expansion if no override given

Market-proportional query budgets (bigger market = more queries):
  weight ≥ 50 (US, JP, CN)             : 80–100 queries
  weight 20–49 (DE, GB, FR, KR, IT, …) : 40–60 queries
  weight 10–19 (BR, RU, NL, MX, IN, …) : 25–40 queries
  weight < 10  (UA, SA, IL, SE, …)      : 15–20 queries

Usage:
    # Full auto — uses Apple hints to generate queries, proportional per market
    python3 rank_audit.py --bundle "com.your.app" --markets all

    # Specific markets with hint expansion
    python3 rank_audit.py --bundle "com.your.app" --markets us,de --expand-from-hints

    # Manual keyword list (bypass hint expansion)
    python3 rank_audit.py --bundle "com.your.app" --markets us --keywords "white noise,sleep sounds"

    # Save report
    python3 rank_audit.py --bundle "com.your.app" --markets all \
        --output marketing/reports/aso_rank_audit_$(date +%Y-%m-%d).md

    # Test API connectivity
    python3 rank_audit.py --self-check

Opportunity score formula:
    market_weight × volume_proxy × rank_reachability × (1 − difficulty / 130)
    - market_weight    : iOS install/revenue size, US=100 (see MARKET_WEIGHT)
    - volume_proxy     : log-scaled total search results (0–100)
    - rank_reachability: 1.0 if #1–10, 0.7 if #11–20, … 0.005 if absent
    - difficulty       : log-scaled top-1 competitor rating count (0–100)
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

# ── Market configuration ──────────────────────────────────────────────────────


# Apple storefront header values for the MZSearchHints autocomplete endpoint — imported from the
# single shared source (storefronts.py) covering all 155 App Store storefronts. Previously this
# dict hard-coded only 24 markets and was missing `ro`, `no`, and others that this skill actually
# tracks hypotheses for markets such as `no` or `ro` — meaning
# `--expand-from-hints` silently produced 0 queries for any market outside this list, with no error,
# because `country in STOREFRONTS` in `run_audit()` just fell through to the fallback branch.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from storefronts import STOREFRONTS  # noqa: E402
from aso.rank_audit_data import (  # noqa: E402,F401
    ALL_MARKETS,
    BABY_SEED_TERMS,
    COMPRESS_SEED_TERMS,
    DEFAULT_MARKET_WEIGHT,
    FALLBACK_KEYWORDS,
    FLAGS,
    MARKET_WEIGHT,
    SEED_TERMS,
)


def _query_budget(country: str) -> int:
    """Return appropriate query count for a market, proportional to its weight."""
    w = MARKET_WEIGHT.get(country, DEFAULT_MARKET_WEIGHT)
    if w >= 50:   return 90    # US, JP, CN
    if w >= 20:   return 50    # DE, GB, FR, KR, IT, ES, AU, CA
    if w >= 10:   return 30    # BR, RU, NL, MX, IN, TR, PL
    return 20                  # UA, SA, IL, SE, HK, SG, TW, and every unweighted storefront


def _get(url: str, headers: dict | None = None, timeout: float = 8.0, deadline: float = 30.0) -> bytes:
    """GET with a TOTAL deadline. `timeout` bounds each socket wait, so a throttled server that drips
    a 200-result body byte by byte never trips it: on 2026-10-07 the `us` storefront sat for 46 minutes
    on one such response. Past `deadline` seconds the request becomes an `error` row, like any other."""
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "Mozilla/5.0"})
    start, chunks = time.monotonic(), []
    with urllib.request.urlopen(req, timeout=timeout) as r:
        while True:
            chunk = r.read(65536)
            if not chunk:
                return b"".join(chunks)
            chunks.append(chunk)
            if time.monotonic() - start > deadline:
                raise TimeoutError(f"response still arriving after {deadline:.0f}s")


def fetch_hints(term: str, country: str) -> list[str]:
    """Fetch Apple autocomplete hints for `term` in `country`.
    Returns suggestions for discovery; ordering is not calibrated search volume.
    """
    storefront = STOREFRONTS.get(country)
    if not storefront:
        return []
    url = (
        "https://search.itunes.apple.com/WebObjects/MZSearchHints.woa/wa/hints"
        f"?clientApplication=Software&term={urllib.parse.quote(term)}"
    )
    try:
        body = _get(url, headers={
            "X-Apple-Store-Front": storefront,
            "User-Agent": "iTunes/12.0 (Macintosh)",
        })
        root = ET.fromstring(body)
        hints_array = root.find("./dict/array")
        if hints_array is None:
            return []
        return [
            d.findtext("string", "")
            for d in hints_array.findall("dict")
            if d.findtext("string")
        ]
    except Exception:
        return []


def expand_keywords(seeds: list[str], country: str, budget: int) -> tuple[list[str], dict[str, int]]:
    """
    Expand seed terms using Apple autocomplete hints.
    Returns deduplicated list of up to `budget` terms, seeds-first,
    along with a dictionary mapping term -> hint_rank (observed suggestion order, not popularity).
    """
    seen: set[str] = set()
    result: list[str] = []
    hint_ranks: dict[str, int] = {}

    def add(term: str, rank: int | None) -> None:
        t = term.strip().lower()
        if t and t not in seen:
            seen.add(t)
            result.append(term.strip())
            hint_ranks[term.strip()] = rank
        elif t and rank is not None:
            canonical = next(x for x in result if x.lower() == t)
            if hint_ranks[canonical] is None:
                hint_ranks[canonical] = rank

    # A supplied seed is not an observed first autocomplete result.
    for s in seeds:
        add(s, None)

    # Level 1: hints for each seed
    level1: list[str] = []
    for seed in seeds:
        hints = fetch_hints(seed, country)
        for i, h in enumerate(hints):
            add(h, i + 1)
            level1.append(h)
        time.sleep(0.2)

    # Level 2: hints for level-1 hints (if budget allows)
    if len(result) < budget:
        for term in level1[:10]:  # limit level-2 expansion to top 10 hints
            if len(result) >= budget:
                break
            for i, h in enumerate(fetch_hints(term, country)):
                add(h, 10 + i + 1)
            time.sleep(0.2)

    return result[:budget], hint_ranks


def search_itunes(term: str, country: str, limit: int = 200) -> list[dict]:
    params = urllib.parse.urlencode({
        "term": term, "country": country,
        "media": "software", "entity": "software", "limit": limit,
    })
    data = json.loads(_get(f"https://itunes.apple.com/search?{params}"))
    if not isinstance(data, dict) or not isinstance(data.get("results"), list):
        raise ValueError("Invalid iTunes response: missing results list")
    if any(not isinstance(app, dict) for app in data["results"]):
        raise ValueError("Invalid iTunes result row")
    return data["results"]


def audit_keyword(term: str, country: str, bundle_id: str, hint_rank: int | None = None) -> dict:
    provenance = {"source": "itunes-search-api", "rank_kind": "api_order_proxy",
                  "observed_at": datetime.now(timezone.utc).isoformat(),
                  "bundle_id": bundle_id, "query_limit": 200}
    try:
        results = search_itunes(term, country)
    except (OSError, ValueError, TimeoutError) as exc:
        return {"term": term, "country": country, "hint_rank": hint_rank,
                "our_rank": None, "total_results": None, "query_status": "error",
                "error": f"{type(exc).__name__}: {exc}", **provenance}
    total = len(results)

    our_rank: Optional[int] = None
    for i, app in enumerate(results, 1):
        if app.get("bundleId") == bundle_id:
            our_rank = i
            break

    competitors = [a for a in results[:10] if a.get("bundleId") != bundle_id][:3]
    top1 = competitors[0] if len(competitors) > 0 else {}
    top2 = competitors[1] if len(competitors) > 1 else {}
    top3 = competitors[2] if len(competitors) > 2 else {}

    top3_ratings = [c.get("userRatingCount", 0) for c in competitors]
    top3_avg_ratings = int(sum(top3_ratings) / max(len(top3_ratings), 1))
    top3_names = [c.get("trackName", "") for c in competitors]

    term_words = [w for w in re.sub(r'[^\w\s]', '', term.lower()).split() if len(w) > 1]
    top3_has_title_match = False
    for name in top3_names:
        clean_name = re.sub(r'[^\w\s]', '', name.lower())
        if term.lower() in name.lower() or (term_words and all(w in clean_name for w in term_words)):
            top3_has_title_match = True
            break

    return {
        **provenance,
        "query_status": "ok",
        "term": term,
        "country": country,
        "hint_rank": hint_rank,
        "total_results": total,
        "our_rank": our_rank,
        "top1_name": top1.get("trackName", "?")[:30],
        "top1_ratings_total": top1.get("userRatingCount", 0),
        "top1_ratings_current": top1.get("userRatingCountForCurrentVersion", 0),
        "top1_score": top1.get("averageUserRating", 0.0),
        "top2_name": top2.get("trackName", "?")[:30] if top2 else "—",
        "top2_ratings_total": top2.get("userRatingCount", 0) if top2 else 0,
        "top3_name": top3.get("trackName", "?")[:30] if top3 else "—",
        "top3_ratings_total": top3.get("userRatingCount", 0) if top3 else 0,
        "top3_avg_ratings": top3_avg_ratings,
        "top3_has_title_match": top3_has_title_match,
    }


def compute_scores(row: dict, country: str) -> dict:
    """Retire uncalibrated volume, takeover and ROI scores; keep raw observations."""
    return {"score_kind": "unavailable_without_demand_and_outcome_evidence",
            **{key: None for key in ("volume_proxy", "popularity", "vol_index", "difficulty",
                                    "kei", "top3_score", "asa_score", "opportunity")},
            "strategy": "Validate exact-query demand, relevance and conversion before prioritizing",
            "asa_action": "No spend recommendation from API order or review counts"}


def run_audit(
    bundle_id: str,
    markets: list[str],
    expand_hints: bool = True,
    manual_keywords: Optional[dict[str, list[str]]] = None,
    custom_seeds: Optional[list[str]] = None,
    niche: str = "whitenoise",
    delay: float = 0.35,
) -> dict[str, list[dict]]:
    all_results: dict[str, list[dict]] = {}

    for country in markets:
        w = MARKET_WEIGHT.get(country, 3)
        budget = _query_budget(country)
        flag = FLAGS.get(country, country.upper())

        hint_ranks: dict[str, int] = {}
        if manual_keywords and country in manual_keywords:
            # An explicit --keywords list is the caller's basket, not a hint-expansion candidate
            # pool — the market-weight budget below exists to cap autocomplete fan-out, and
            # silently slicing an explicit list to that same cap drops real, already-tracked
            # keywords with no signal anywhere in stdout/stderr. Take the full explicit list; if a
            # future caller passes something larger than a sane hard ceiling, say so instead of
            # quietly truncating.
            requested = manual_keywords[country]
            hard_ceiling = max(budget, 200)
            queries = requested[:hard_ceiling]
            if len(queries) < len(requested):
                dropped = requested[len(queries):]
                print(f"\n  ⚠ TRUNCATED {country.upper()}: {len(dropped)} of {len(requested)} "
                      f"explicit keywords dropped (hard ceiling {hard_ceiling}): {dropped}",
                      file=sys.stderr, flush=True)
            hint_ranks = {q: None for q in queries}
            src = "manual"
        elif expand_hints and country in STOREFRONTS:
            if custom_seeds:
                seeds = custom_seeds
            elif niche == "baby":
                seeds = BABY_SEED_TERMS.get(country, [])
            elif niche in ["compress", "media"]:
                seeds = COMPRESS_SEED_TERMS.get(country, [])
            else:
                seeds = SEED_TERMS.get(country, [])
            print(f"  {flag} {country.upper():3} expanding hints from {len(seeds)} seeds… ", end="", flush=True)
            queries, hint_ranks = expand_keywords(seeds, country, budget)
            src = f"hints({len(queries)})"
        else:
            fallback = FALLBACK_KEYWORDS.get(country, [])
            queries = fallback[:budget]
            hint_ranks = {q: None for q in queries}
            src = f"fallback({len(queries)})"

        print(f"  {flag} {country.upper():3} [{src}] {len(queries)} queries…", end=" ", flush=True)

        rows = []
        # A market with 50-90 queries at a mandatory 3s delay runs for several minutes with no
        # output at all otherwise — indistinguishable from a hang. One dot per completed query
        # (a distinct marker on error) keeps this CLI honest about being alive mid-market, without
        # cluttering the one-line-per-market summary the rest of the pipeline greps/reads.
        for i, term in enumerate(queries, 1):
            h_rank = hint_ranks.get(term)
            row = audit_keyword(term, country, bundle_id, hint_rank=h_rank)
            scores = compute_scores(row, country)
            rows.append({**row, **scores})
            marker = "x" if row.get("query_status") == "error" else "."
            print(marker, end="", flush=True)
            if i % 10 == 0:
                print(f"{i}", end="", flush=True)
            time.sleep(delay)
        print(" ", end="", flush=True)

        found = sum(1 for r in rows if r["our_rank"])
        best  = min((r["our_rank"] for r in rows if r["our_rank"]), default=None)
        print(f"{found}/{len(queries)} ranked, best #{best or '—'}")

        all_results[country] = rows

    return all_results


def format_report(bundle_id: str, results: dict[str, list[dict]]) -> str:
    rows = [r for items in results.values() if isinstance(items, list) for r in items]
    errors = sum(r.get("query_status") == "error" for r in rows)
    lines = ["# App Store discovery observations", "",
             f"Bundle: `{bundle_id}`. Report generated: {datetime.now(timezone.utc).isoformat()}.",
             f"Queries: {len(rows)}. Errors: {errors}.", "",
             "Positions are iTunes Search API order, not verified organic device rankings.",
             "Missing provenance in older snapshots stays unverified. Report generation is not a fresh observation.",
             "Review counts, autocomplete order and result counts do not establish demand, competitiveness, ROI or a paid-to-organic lift.",
             "Legacy predictive scores are retired; keyword research needs exact-query evidence.", ""]
    for country, items in sorted(results.items()):
        if not isinstance(items, list):
            continue
        lines += [f"## {country.upper()}", "", "| Query | API position | Status | Observed at | First other result | Ratings |", "|---|---:|---|---|---|---:|"]
        for row in items:
            status = row.get("query_status", "legacy provenance unverified")
            position = row.get("our_rank")
            if status == "error":
                pos = "unknown"
            else:
                pos = str(position) if position is not None else "not observed in returned results"
            cells = [row["term"], pos, status, row.get("observed_at", "unknown"), row.get("top1_name", "unknown"), str(row.get("top1_ratings_total", "unknown"))]
            lines.append("| " + " | ".join(str(x).replace("|", r"\|").replace("\n", " ") for x in cells) + " |")
        lines.append("")
    return "\n".join(lines)


def self_check() -> None:
    from unittest.mock import patch
    with patch(__name__ + "._get", side_effect=TimeoutError("test timeout")):
        failed = audit_keyword("compress photo", "us", "com.test")
        assert failed["query_status"] == "error" and failed["total_results"] is None
    with patch(__name__ + "._get", return_value=b'{"results": []}'):
        absent = audit_keyword("compress photo", "us", "com.test")
        assert absent["query_status"] == "ok" and absent["total_results"] == 0
    with patch(__name__ + ".fetch_hints", return_value=[]), patch(__name__ + ".time.sleep"):
        _, ranks = expand_keywords(["unmeasured seed"], "us", 1)
        assert ranks["unmeasured seed"] is None
    assert compute_scores(absent, "us")["popularity"] is None
    assert "unknown | error" in format_report("com.test", {"us": [failed]})

    class Drip:                      # a throttled server: one byte per read, forever
        def __enter__(self): return self
        def __exit__(self, *exc): return False
        def read(self, n): return b"x"
    ticks = iter(range(0, 10_000, 20))
    with patch(__name__ + ".urllib.request.urlopen", return_value=Drip()), \
            patch(__name__ + ".time.monotonic", side_effect=lambda: next(ticks)):
        try:
            _get("https://example.invalid/")
            raise AssertionError("a dripping response must hit the total deadline")
        except TimeoutError as exc:
            assert "still arriving" in str(exc)
    print("OK: request errors stay unknown; a dripping response times out; supplied seeds have no measured popularity; no forecast scores")


def main() -> None:
    p = argparse.ArgumentParser(description="App Store keyword rank + opportunity audit")
    p.add_argument("--bundle", help="Exact app bundle ID; required outside self-check")
    p.add_argument("--markets", default="all",
                   help="Comma-separated codes or 'all'")
    p.add_argument("--expand-from-hints", action="store_true",
                   help="Use Apple autocomplete to generate queries (recommended)")
    p.add_argument("--keywords", default=None,
                   help="Manual comma-separated keywords (bypasses hint expansion). A keyword "
                        "that itself contains a comma cannot round-trip through this flag — it "
                        "will be split at that comma like any other separator. Use "
                        "--keywords-file for a basket where that matters.")
    p.add_argument("--keywords-file", default=None,
                   help="Path to a newline-delimited keyword list (UTF-8, one keyword per line, "
                        "blank lines ignored). Safe for keywords that contain commas; "
                        "takes precedence over --keywords if both are given.")
    p.add_argument("--seeds", default=None,
                   help="Custom comma-separated seed terms for hint expansion")
    p.add_argument("--niche", default="whitenoise", choices=["whitenoise", "baby", "compress", "media"],
                   help="Seed niche profile (whitenoise, baby, compress, media)")
    p.add_argument("--output",  default=None)
    p.add_argument("--delay",   type=float, default=0.35)
    p.add_argument("--reanalyze", default=None,
                   help="Path to an existing audit JSON file to recompute scores without querying Apple APIs")
    p.add_argument("--self-check", action="store_true")
    args = p.parse_args()

    if args.self_check:
        self_check()
        return

    if not args.bundle:
        p.error("--bundle is required; never infer the app from its name")

    if args.reanalyze:
        json_path = Path(args.reanalyze)
        if not json_path.exists():
            print(f"Error: file not found: {args.reanalyze}", file=sys.stderr)
            sys.exit(1)
        print(f"Re-analyzing existing audit data from: {json_path}")
        with open(json_path) as f:
            results = json.load(f)

        # Re-score all rows across all markets
        for country, rows in results.items():
            if not isinstance(rows, list):
                continue
            for r in rows:
                new_scores = compute_scores(r, country)
                r.update(new_scores)

        out_md_path = Path(args.output) if args.output else json_path.with_suffix(".md")
        out_json_path = out_md_path.with_suffix(".json")

        report = format_report(args.bundle, results)
        out_md_path.write_text(report)
        out_json_path.write_text(json.dumps(results, indent=2, ensure_ascii=False))
        print(f"Updated report written → {out_md_path}")
        print(f"Updated JSON written → {out_json_path}")
        return

    markets = ALL_MARKETS if args.markets == "all" else [m.strip() for m in args.markets.split(",")]

    manual_kw: Optional[dict] = None
    if args.keywords_file:
        kws_path = Path(args.keywords_file)
        if not kws_path.exists():
            p.error(f"--keywords-file not found: {kws_path}")
        kws = [line.strip() for line in kws_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        manual_kw = {m: kws for m in markets}
    elif args.keywords:
        kws = [k.strip() for k in args.keywords.split(",")]
        manual_kw = {m: kws for m in markets}

    # An explicit basket replaces the niche lists, so the header must not name a niche (it printed
    # another app's "[Niche: whitenoise]") nor a "fallback" mode that is not running.
    if manual_kw is not None:
        print(f"ASO Rank Audit — {args.bundle} [explicit basket]")
        print(f"Markets: {', '.join(markets)}  |  Queries: {sum(len(v) for v in manual_kw.values())}")
        print("  Mode: explicit basket (--keywords-file / --keywords)\n")
    else:
        print(f"ASO Rank Audit — {args.bundle} [Niche: {args.niche}]")
        print(f"Markets: {', '.join(markets)}  |  Budget: ~{sum(_query_budget(m) for m in markets)} queries")
        if args.expand_from_hints:
            print("  Mode: Apple autocomplete hint expansion (proportional budgets)\n")
        else:
            print("  Mode: fallback keyword lists (use --expand-from-hints for better coverage)\n")

    seeds_list: Optional[list[str]] = None
    if args.seeds:
        seeds_list = [s.strip() for s in args.seeds.split(",") if s.strip()]

    results = run_audit(
        args.bundle, markets,
        expand_hints=args.expand_from_hints or (manual_kw is None),
        manual_keywords=manual_kw,
        custom_seeds=seeds_list,
        niche=args.niche,
        delay=args.delay,
    )
    report = format_report(args.bundle, results)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report)
        print(f"\nReport → {args.output}")
        # Save structured machine-readable snapshot JSON alongside markdown report
        json_path = out_path.with_suffix(".json")
        json_path.write_text(json.dumps(results, indent=2, ensure_ascii=False))
        print(f"Snapshot JSON → {json_path}")
    else:
        print("\n" + report)


if __name__ == "__main__":
    main()
