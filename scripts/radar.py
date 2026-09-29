#!/usr/bin/env python3
"""Apple demand radar: what Apple says people search for, read from the app's own Apple Ads account.

Read-only against Apple Ads; appends to the store's metrics/ (references/apple-ads.md §3c).

    radar.py --store marketing pull [--markets jp,us] [--if-configured]
    radar.py --store marketing report
    radar.py --store marketing keywords [--campaign ID] [--start YYYY-MM-DD --end YYYY-MM-DD]
    radar.py --self-check

Popularity lists only each genre's head (~100-350 terms per storefront). A tracked term that is not
listed sits below the cut: volume unknown, never zero. The cut is stored beside the terms so the two
are never confused. Nothing here reads a competitor, a keyword report of somebody else's app, or a
campaign's spend; `keywords` only reads this account's own campaigns.

config.md, all optional; without profile and account the radar refuses to guess an account:
    **Apple Ads profile**: <asc ads profile name>
    **Apple Ads account**: <numeric ad account id>
    **Apple Ads genres**: PHOTO_VIDEO, PRODUCTIVITY_UTILITIES    Apple's spelling of the app's categories
    **Apple Ads topic words**: compress, clean up, 圧縮             head terms containing one are stored too
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import subprocess
import sys
import tempfile
from pathlib import Path

PAGE = 5000
SOURCE = "asc-ads-insights"
TOPIC_CAP = 40  # topical head terms kept per market, most popular first
POP_COLS = ["week", "captured", "market", "genre", "term", "rank_in_genre", "popularity_100",
            "popularity_5", "why", "source"]
CUT_COLS = ["week", "captured", "market", "genre", "listed", "min_popularity_100", "source"]
SHARE_COLS = ["week", "captured", "market", "term", "rank", "popularity_5", "share_low", "share_high",
              "source"]
LABELS = {"**App ID**:": "app_id", "**Apple Ads profile**:": "profile", "**Apple Ads account**:": "account",
          "**Apple Ads genres**:": "genres", "**Apple Ads topic words**:": "topics"}


# ---------------------------------------------------------------- config, store, week
def read_config(store: Path) -> dict:
    cfg = {}
    path = store / "config.md"
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            for label, key in LABELS.items():
                value = line[len(label):].strip() if line.startswith(label) else ""
                if value and not value.upper().startswith("TODO"):
                    cfg[key] = value
    cfg["app_id"] = (cfg.get("app_id") or "").split(maxsplit=1)[0] if cfg.get("app_id") else ""
    cfg["genres"] = [g.strip().upper() for g in cfg.get("genres", "").split(",") if g.strip()]
    cfg["topics"] = [t.strip().casefold() for t in cfg.get("topics", "").split(",") if t.strip()]
    return cfg


def norm(text) -> str:
    return " ".join((text or "").casefold().split())


def read_csv(path: Path) -> list:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def append_csv(path: Path, cols: list, rows: list) -> None:
    if not rows:
        return
    new = not path.is_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=cols, lineterminator="\n")
        if new:
            writer.writeheader()
        writer.writerows(rows)


def read_basket(store: Path):
    """The tracked rank basket as of each market's latest look: ({market: {term}}, {(market, term): position})."""
    rows = read_csv(store / "metrics" / "ranks.csv")
    latest = {}
    for r in rows:
        market = (r.get("market") or "").strip().lower()
        if market:
            latest[market] = max(latest.get(market, ""), r.get("date") or "")
    basket, position = {}, {}
    for r in rows:
        market = (r.get("market") or "").strip().lower()
        if not market or (r.get("date") or "") != latest[market]:
            continue
        term = norm(r.get("keyword"))
        basket.setdefault(market, set()).add(term)
        pos = (r.get("position") or "").strip()
        position[(market, term)] = int(pos) if pos.isdigit() else None
    return basket, position


def latest_complete_week(today: dt.date):
    """Apple's weeks run Sunday-Saturday (UTC). The current week is never complete."""
    end = today - dt.timedelta(days=(today.weekday() - 5) % 7 or 7)
    return end - dt.timedelta(days=6), end


# ---------------------------------------------------------------- Apple Ads calls
def asc_ads(cfg: dict, resource: list, payload: dict, timeout: int = 180):
    """`asc ads <resource...>` with the JSON payload on stdin; the parsed reply, or RuntimeError."""
    cmd = ["asc", "ads", *resource, "--ads-profile", cfg["profile"], "--ad-account", cfg["account"],
           "--file", "-"]
    label = " ".join(resource)
    try:
        res = subprocess.run(cmd, input=json.dumps(payload), capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"{label}: {exc}") from exc
    if res.returncode != 0:
        raise RuntimeError(f"{label}: exit {res.returncode}: {(res.stderr or res.stdout).strip()[:300]}")
    try:
        return json.loads(res.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{label}: reply is not JSON ({exc})") from exc


def paged_rows(run, cfg, resource, payload) -> list:
    rows, offset = [], 0
    while True:
        reply = run(cfg, resource, dict(payload, pagination={"offset": offset, "pageSize": PAGE}))
        page = reply["result"]["rows"]
        rows += page
        if len(page) < PAGE:
            return rows
        offset += PAGE


def listed(run, cfg, resource, filters, size=1000) -> list:
    """Every record of a `find` endpoint, whose reply is {"result": [...]} rather than {"result": {"rows": [...]}}."""
    out, offset = [], 0
    while True:
        payload = {"pagination": {"offset": offset, "pageSize": size}}
        if filters:
            payload["filters"] = filters
        page = run(cfg, resource, payload)["result"]
        out += page
        if len(page) < size:
            return out
        offset += size


# ---------------------------------------------------------------- pull
def pull_popularity(store, cfg, markets, week_start, captured, run=asc_ads):
    """Append the week's popularity for each market. -> (stored_week or None, markets stored, failures)."""
    metrics = store / "metrics"
    basket, _ = read_basket(store)
    done = {(r["week"], r["market"]) for r in read_csv(metrics / "popularity_cut.csv")}
    failures = []
    for week in (week_start, week_start - dt.timedelta(days=7)):  # a lagging week falls back once
        todo = [m for m in markets if (week.isoformat(), m) not in done]
        if not todo:
            return week.isoformat(), [], failures
        end = week + dt.timedelta(days=6)
        results, failures = {}, []
        for market in todo:
            payload = {"timeRange": {"start": week.isoformat(), "end": end.isoformat(), "timeZone": "UTC",
                                     "granularity": "WEEKLY_SUN_SAT"},
                       "filters": [{"field": "countryOrRegion", "operator": "EQUALS", "value": market.upper()},
                                   {"field": "genre", "operator": "IN", "value": cfg["genres"]}],
                       "sorting": [{"field": "rankInGenre", "sortOrder": "ASC"}]}
            try:
                results[market] = paged_rows(run, cfg, ["insights", "search-term-popularity", "find"], payload)
            except (RuntimeError, KeyError, TypeError) as exc:
                failures.append((market, str(exc)))
        if not any(results.values()):
            continue  # nothing anywhere: Apple has not published this week yet
        pop_rows, cut_rows = [], []
        for market, rows in results.items():
            wanted, by_genre, topical = basket.get(market, set()), {}, []
            for r in rows:
                by_genre.setdefault(r["genre"], []).append(r)
                term = norm(r["searchTerm"])
                base = {"week": week.isoformat(), "captured": captured, "market": market, "genre": r["genre"],
                        "term": term, "rank_in_genre": r["rankInGenre"], "popularity_100": r["searchPopularity1to100"],
                        "popularity_5": r.get("searchPopularity1to5", ""), "source": SOURCE}
                if term in wanted:
                    pop_rows.append(dict(base, why="basket"))
                elif any(t in term for t in cfg["topics"]):
                    topical.append(dict(base, why="topic"))
            topical.sort(key=lambda r: -int(r["popularity_100"]))
            pop_rows += topical[:TOPIC_CAP]
            for genre, listed in sorted(by_genre.items()):
                cut_rows.append({"week": week.isoformat(), "captured": captured, "market": market, "genre": genre,
                                 "listed": len(listed), "source": SOURCE,
                                 "min_popularity_100": min(int(r["searchPopularity1to100"]) for r in listed)})
            if not rows:  # Apple returns nothing for some storefronts (RU, LT, MD in 2026-09): say so
                cut_rows.append({"week": week.isoformat(), "captured": captured, "market": market, "genre": "",
                                 "listed": 0, "min_popularity_100": "", "source": SOURCE})
        append_csv(metrics / "popularity.csv", POP_COLS, pop_rows)
        append_csv(metrics / "popularity_cut.csv", CUT_COLS, cut_rows)
        return week.isoformat(), sorted(results), failures
    return None, [], failures


def pull_share(store, cfg, week_start, captured, run=asc_ads):
    """Impression share of the app's own ads for the four weeks ending with `week_start`'s week."""
    path = store / "metrics" / "impression_share.csv"
    have = {(r["week"], r["market"], r["term"]) for r in read_csv(path)}
    payload = {"filters": [{"field": "promotedObjectId", "operator": "IN", "value": [cfg["app_id"]]}],
               "options": {"impressionShareReportType": "ALL_SLOTS"},
               "timeRange": {"start": (week_start - dt.timedelta(days=21)).isoformat(),
                             "end": (week_start + dt.timedelta(days=6)).isoformat(), "timeZone": "UTC",
                             "granularity": "WEEKLY_SUN_SAT"}}
    fresh, fetched = [], paged_rows(run, cfg, ["insights", "impression-share", "find"], payload)
    for r in fetched:
        key = (r["week"], r["countryOrRegion"].lower(), norm(r["searchTerm"]))
        if key not in have:
            have.add(key)
            fresh.append({"week": key[0], "captured": captured, "market": key[1], "term": key[2],
                          "rank": r.get("rank", ""), "popularity_5": r.get("searchPopularity1to5", ""),
                          "share_low": r.get("lowImpressionShare", ""), "share_high": r.get("highImpressionShare", ""),
                          "source": SOURCE})
    append_csv(path, SHARE_COLS, fresh)
    return len(fetched), len(fresh)


def cmd_pull(args, run=asc_ads, today=None):
    store = Path(args.store).resolve()
    cfg = read_config(store)
    if not (cfg.get("profile") and cfg.get("account")):
        note = "Apple Ads profile/account are not set in config.md; radar skipped (not a failure)."
        if args.if_configured:
            print(note)
            return 0
        print(note + " Set `**Apple Ads profile**:` and `**Apple Ads account**:`; see references/apple-ads.md §3c.")
        return 2
    if not cfg["genres"] or not cfg["app_id"].isdigit():
        print(f"Set a numeric **App ID** and `**Apple Ads genres**:` (Apple's spelling, e.g. PHOTO_VIDEO, "
              f"PRODUCTIVITY_UTILITIES) in {store / 'config.md'}; refusing to guess.")
        return 2
    markets = [m.strip().lower() for m in args.markets.split(",")] if args.markets else sorted(read_basket(store)[0])
    if not markets:
        print("No markets: metrics/ranks.csv has no basket yet and --markets was not given.")
        return 2
    captured = (today or dt.datetime.now(dt.timezone.utc).date()).isoformat()
    week_start, _ = latest_complete_week(today or dt.datetime.now(dt.timezone.utc).date())
    partial = False
    week, stored, failures = pull_popularity(store, cfg, markets, week_start, captured, run)
    if week is None:
        print(f"Popularity: Apple returned no rows for {week_start} or the week before; nothing stored.")
        partial = True
    elif not stored and not failures:
        print(f"Popularity: week {week} is already stored for all {len(markets)} markets.")
    else:
        print(f"Popularity: week {week} stored for {len(stored)} of {len(markets)} markets "
              f"[live:asc ads insights search-term-popularity find@{captured}].")
    for market, why in failures:
        print(f"  ⚠️ {market}: {why}")
        partial = True
    try:
        fetched, fresh = pull_share(store, cfg, week_start, captured, run)
        print(f"Impression share: {fresh} new of {fetched} term rows for the 4 weeks to {week_start + dt.timedelta(days=6)}"
              f"{' (the app ran no ads there)' if not fetched else ''} [live:asc ads insights impression-share find@{captured}].")
    except (RuntimeError, KeyError, TypeError) as exc:
        print(f"  ⚠️ impression share: {exc}")
        partial = True
    return 2 if partial else 0


# ---------------------------------------------------------------- read side (report, ledger)
def demand_lookup(store: Path):
    """(heads, cuts) from the latest stored week per market.
    heads[(market, term)] = (popularity_100, week); cuts[market] = (lowest listed score or None, week);
    a None score means Apple listed nothing for that storefront."""
    cut_rows = read_csv(store / "metrics" / "popularity_cut.csv")
    latest = {}
    for r in cut_rows:
        latest[r["market"]] = max(latest.get(r["market"], ""), r["week"])
    cuts = {}
    for market, week in latest.items():
        scores = [int(r["min_popularity_100"]) for r in cut_rows
                  if r["market"] == market and r["week"] == week and r["min_popularity_100"] != ""]
        cuts[market] = (min(scores) if scores else None, week)
    heads = {}
    for r in read_csv(store / "metrics" / "popularity.csv"):
        if r["why"] == "basket" and r["week"] == latest.get(r["market"]):
            key = (r["market"], r["term"])
            heads[key] = (max(int(r["popularity_100"]), heads.get(key, (0, ""))[0]), r["week"])
    return heads, cuts


def demand_label(demand, market: str, keyword: str) -> str:
    """One cell for a tracked key: `head 55`, `below 44` (unlisted: unknown, not zero), `no data`, or `—` (never pulled)."""
    heads, cuts = demand
    market = market.lower()
    if (market, norm(keyword)) in heads:
        return f"head {heads[(market, norm(keyword))][0]}"
    if market not in cuts:
        return "—"
    return f"below {cuts[market][0]}" if cuts[market][0] is not None else "no data"


def cmd_report(args):
    store = Path(args.store).resolve()
    cut_rows = read_csv(store / "metrics" / "popularity_cut.csv")
    if not cut_rows:
        print("No radar data yet: run `radar.py pull` (needs the Apple Ads lines in config.md).")
        return 2
    week = max(r["week"] for r in cut_rows)
    week_cuts = [r for r in cut_rows if r["week"] == week]
    captured = max(r["captured"] for r in week_cuts)
    heads, cuts = demand_lookup(store)
    basket, position = read_basket(store)
    print(f"## Apple demand radar · week {week}, captured {captured} "
          f"[store:metrics/popularity_cut.csv#{week}; live:asc ads insights search-term-popularity find@{captured}]\n")
    print("_Apple lists only each genre's head. A tracked term that is not listed is below the cut: "
          "its volume is unknown, not zero. Popularity is relative (1-100), not searches._\n")
    print("| Market | Lowest score listed (cut) | Tracked terms | In the head |")
    print("|---|---:|---:|---:|")
    silent = []
    for market in sorted({r["market"] for r in week_cuts}):
        cut = cuts[market][0]
        if cut is None:
            silent.append(market)
            continue
        inside = sum(1 for (m, _t) in heads if m == market)
        print(f"| {market} | {cut} | {len(basket.get(market, ()))} | {inside} |")
    if silent:
        print(f"\nNo data (Apple lists nothing for these storefronts): {', '.join(silent)}.")
    pop = [r for r in read_csv(store / "metrics" / "popularity.csv") if r["week"] == week]
    tracked = sorted((r for r in pop if r["why"] == "basket"), key=lambda r: (r["market"], -int(r["popularity_100"])))
    print("\n### Tracked terms inside Apple's head\n")
    if tracked:
        print("| Market | Term | Genre | Rank in genre | Popularity | Our position (search-API proxy) |")
        print("|---|---|---|---:|---:|---:|")
        for r in tracked:
            ours = position.get((r["market"], r["term"]))
            print(f"| {r['market']} | {r['term']} | {r['genre']} | {r['rank_in_genre']} | {r['popularity_100']} | "
                  f"{ours if ours is not None else 'beyond depth'} |")
    else:
        print("_None: every tracked term sits below the cut._")
    topical = sorted((r for r in pop if r["why"] == "topic" and r["term"] not in basket.get(r["market"], set())),
                     key=lambda r: -int(r["popularity_100"]))
    print("\n### Head terms on our topic that we do not track (top 15 across markets)\n")
    if topical:
        print("| Market | Term | Genre | Rank in genre | Popularity |")
        print("|---|---|---|---:|---:|")
        for r in topical[:15]:
            print(f"| {r['market']} | {r['term']} | {r['genre']} | {r['rank_in_genre']} | {r['popularity_100']} |")
        print("\n_A candidate is a reason to observe the term (rank_audit / `ledger ingest`), then draft a hypothesis; "
              "it is not a keyword to ship. Generic topic words match brand names._")
    else:
        print("_None (set `**Apple Ads topic words**:` in config.md to store topical head terms)._")
    share = read_csv(store / "metrics" / "impression_share.csv")
    if share:
        latest = max(r["week"] for r in share)
        rows = [r for r in share if r["week"] == latest]
        print(f"\n### Impression share, our own ads, week {latest}: {len(rows)} terms "
              f"[store:metrics/impression_share.csv#{latest}]")
        print("_Share is of the searches our ads entered; total volume ≈ our impressions ÷ share._\n")
        print("| Market | Term | Ad rank | Popularity 1-5 | Impression share |")
        print("|---|---|---:|---:|---:|")
        for r in sorted(rows, key=lambda r: -float(r["share_high"] or 0))[:10]:
            low, high = float(r["share_low"] or 0), float(r["share_high"] or 0)
            print(f"| {r['market']} | {r['term']} | {r['rank']} | {r['popularity_5']} | "
                  f"{f'{high:.0%}' if low == high else f'{low:.0%}–{high:.0%}'} |")
    return 0


# ---------------------------------------------------------------- keyword lens
def money(value) -> float:
    return float((value or {}).get("amount") or 0)


def keyword_lens(cfg, campaign: str, start: str, end: str, run=asc_ads) -> None:
    """A campaign's keyword report joined to the keyword text, plus how much of it Apple withholds."""
    span = {"start": start, "end": end, "timeZone": "ORTZ", "granularity": "DAILY"}
    select = [{"field": "campaignId", "operator": "EQUALS", "value": str(campaign)}]
    texts = {k["id"]: k for k in listed(run, cfg, ["targeting-keywords", "find"], select)}
    kw = paged_rows(run, cfg, ["reports", "apps", "keywords"],
                    {"timeRange": span, "filters": select, "groupBy": [],
                     "fields": ["impressions", "taps", "localSpend", "tapInstalls"]})
    terms = paged_rows(run, cfg, ["reports", "apps", "search-terms"],
                       {"timeRange": span, "filters": select, "groupBy": [],
                        "fields": ["impressions", "taps", "localSpend"]})
    print(f"\n### Campaign {campaign} · {start} → {end} (ORTZ) "
          f"[live:asc ads reports apps keywords|search-terms + targeting-keywords find@{dt.date.today()}]\n")
    print("| Keyword | Match | Bid | Status | Impr | Taps | Spend | Installs | CPT | CPI |")
    print("|---|---|---:|---|---:|---:|---:|---:|---:|---:|")
    table = []
    for row in kw:
        m, t = row["metadata"], row["totalMetrics"]
        info = texts.get(m["id"], {})
        table.append((money(t.get("localSpend")), info.get("text", f"(keyword {m['id']})"), info.get("matchType", "?"),
                      money(info.get("bid")), info.get("status", "?"), t.get("impressions", 0), t.get("taps", 0),
                      t.get("tapInstalls", 0)))
    for spend, text, match, bid, status, imp, taps, inst in sorted(table, reverse=True)[:25]:
        cpt = f"${spend / taps:.2f}" if taps else "—"
        cpi = f"${spend / inst:.2f}" if inst else "—"
        print(f"| {text} | {match} | ${bid:.2f} | {status} | {imp} | {taps} | ${spend:.2f} | {inst} | {cpt} | {cpi} |")
    total = sum(r[0] for r in table)
    hidden = [r for r in terms if r["metadata"].get("searchTermText") is None]
    hidden_spend = sum(money(r["totalMetrics"].get("localSpend")) for r in hidden)
    all_spend = sum(money(r["totalMetrics"].get("localSpend")) for r in terms)
    share = f"{hidden_spend / all_spend:.0%}" if all_spend else "n/a"
    print(f"\nKeyword report spend ${total:.2f}. Search-term report: ${hidden_spend:.2f} of ${all_spend:.2f} "
          f"({share}) sits under terms Apple withholds (<10 impressions), so the keyword report is the per-query lens.")
    named = sorted((r for r in terms if r["metadata"].get("searchTermText")),
                   key=lambda r: -money(r["totalMetrics"].get("localSpend")))[:10]
    for r in named:
        keyword = texts.get(r["metadata"].get("keyword", {}).get("id"), {})
        print(f"  term `{r['metadata']['searchTermText']}` ← keyword `{keyword.get('text', '?')}` "
              f"({keyword.get('matchType', '?')}): {r['totalMetrics'].get('impressions', 0)} impr, "
              f"{r['totalMetrics'].get('taps', 0)} taps, ${money(r['totalMetrics'].get('localSpend')):.2f}")


def cmd_keywords(args, run=asc_ads):
    store = Path(args.store).resolve()
    cfg = read_config(store)
    if not (cfg.get("profile") and cfg.get("account")):
        print("Set `**Apple Ads profile**:` and `**Apple Ads account**:` in config.md; refusing to guess an account.")
        return 2
    end = args.end or (dt.date.today() - dt.timedelta(days=1)).isoformat()
    start = args.start or (dt.date.fromisoformat(end) - dt.timedelta(days=13)).isoformat()
    try:
        ids = [args.campaign] if args.campaign else [
            str(c["id"]) for c in listed(run, cfg, ["campaigns", "find"], [], 50) if not c.get("deleted")]
        for campaign in ids:
            keyword_lens(cfg, campaign, start, end, run)
        if not ids:
            print("The ad account has no campaigns.")
    except (RuntimeError, KeyError, TypeError) as exc:
        print(f"⚠️ {exc}")
        return 2
    return 0


# ---------------------------------------------------------------- self-check
def self_check():
    import contextlib
    import io

    assert latest_complete_week(dt.date(2026, 9, 29)) == (dt.date(2026, 9, 20), dt.date(2026, 9, 26))  # Tuesday
    assert latest_complete_week(dt.date(2026, 9, 27)) == (dt.date(2026, 9, 20), dt.date(2026, 9, 26))  # Sunday
    assert latest_complete_week(dt.date(2026, 9, 26)) == (dt.date(2026, 9, 13), dt.date(2026, 9, 19))  # Saturday

    with tempfile.TemporaryDirectory() as tmp:
        store = Path(tmp) / "marketing"
        (store / "metrics").mkdir(parents=True)
        (store / "config.md").write_text(
            "**App ID**: 1234567890 note\n**Apple Ads profile**: Test Ads\n**Apple Ads account**: 42\n"
            "**Apple Ads genres**: photo_video, PRODUCTIVITY_UTILITIES\n**Apple Ads topic words**: 圧縮, clean up\n"
            "**Apple Ads topic words unrelated**: ignored\n", encoding="utf-8")
        cfg = read_config(store)
        assert cfg["genres"] == ["PHOTO_VIDEO", "PRODUCTIVITY_UTILITIES"] and cfg["topics"] == ["圧縮", "clean up"]
        assert cfg["app_id"] == "1234567890" and cfg["profile"] == "Test Ads"
        (store / "config.md").write_text("**App ID**: 1\n**Apple Ads profile**: TODO — set me\n", encoding="utf-8")
        assert "profile" not in read_config(store)
        (store / "config.md").write_text(
            "**App ID**: 1234567890\n**Apple Ads profile**: Test Ads\n**Apple Ads account**: 42\n"
            "**Apple Ads genres**: PHOTO_VIDEO\n**Apple Ads topic words**: 圧縮, clean up\n", encoding="utf-8")
        cfg = read_config(store)
        (store / "metrics" / "ranks.csv").write_text(
            "date,market,keyword,group,position,popularity,difficulty,source,depth,status\n"
            "2026-09-27,jp,動画圧縮,target,160,,,itunes-search-api,200,ok\n"
            "2026-09-27,jp,写真 圧縮,target,,,,itunes-search-api,200,beyond-depth\n"
            "2026-09-27,ru,сжать видео,target,,,,itunes-search-api,200,beyond-depth\n"
            "2026-09-27,us,clean up iphone,target,,,,itunes-search-api,200,beyond-depth\n", encoding="utf-8")
        basket, position = read_basket(store)
        assert basket["jp"] == {"動画圧縮", "写真 圧縮"} and position[("jp", "動画圧縮")] == 160

        calls = []

        def row(week, market, genre, term, rank, pop):
            return {"week": week, "countryOrRegion": market, "genre": genre, "searchTerm": term,
                    "rankInGenre": rank, "searchPopularityInGenre": 50, "searchPopularity1to100": pop,
                    "searchPopularity1to5": 3}

        def fake(cfg_, resource, payload):
            calls.append((resource, payload))
            if resource[1] == "search-term-popularity":
                week = payload["timeRange"]["start"]
                market = payload["filters"][0]["value"]
                assert payload["filters"][1] == {"field": "genre", "operator": "IN", "value": ["PHOTO_VIDEO"]}
                if week == "2026-09-20" and lag:
                    return {"result": {"rows": []}}
                rows = {"JP": [row(week, "JP", "PHOTO_VIDEO", "動画編集", 3, 75),
                               row(week, "JP", "PHOTO_VIDEO", "動画圧縮", 185, 55),
                               row(week, "JP", "PHOTO_VIDEO", "画像圧縮アプリ", 220, 49),
                               row(week, "JP", "PHOTO_VIDEO", "capcut", 1, 90)],
                        "US": [row(week, "US", "PHOTO_VIDEO", "clean up iphone", 159, 63)]}.get(market, [])
                return {"result": {"rows": rows}}
            assert resource[1] == "impression-share"
            assert payload["filters"] == [{"field": "promotedObjectId", "operator": "IN", "value": ["1234567890"]}]
            return {"result": {"rows": [{"week": "2026-09-20", "rank": 1, "searchTerm": "Video Compressor",
                                         "countryOrRegion": "PL", "searchPopularity1to5": 2,
                                         "lowImpressionShare": 0.63, "highImpressionShare": 0.63}]}}

        lag = False
        args = argparse.Namespace(store=str(store), markets=None, if_configured=False)
        with contextlib.redirect_stdout(io.StringIO()) as out:
            assert cmd_pull(args, fake, dt.date(2026, 9, 29)) == 0
        pops = read_csv(store / "metrics" / "popularity.csv")
        assert {(r["market"], r["term"], r["why"]) for r in pops} == {
            ("jp", "動画圧縮", "basket"), ("jp", "画像圧縮アプリ", "topic"), ("us", "clean up iphone", "basket")}
        cuts = {(r["market"], r["genre"]): (r["listed"], r["min_popularity_100"])
                for r in read_csv(store / "metrics" / "popularity_cut.csv")}
        assert cuts[("jp", "PHOTO_VIDEO")] == ("4", "49") and cuts[("ru", "")] == ("0", "")  # min of the listed rows
        assert len(read_csv(store / "metrics" / "impression_share.csv")) == 1
        n = len(calls)
        with contextlib.redirect_stdout(io.StringIO()) as out:
            assert cmd_pull(args, fake, dt.date(2026, 9, 29)) == 0
        assert "already stored" in out.getvalue() and len(read_csv(store / "metrics" / "impression_share.csv")) == 1
        assert len(calls) == n + 1  # only the impression-share query re-ran; markets are not pulled twice

        demand = demand_lookup(store)
        assert demand_label(demand, "jp", "動画圧縮") == "head 55"
        assert demand_label(demand, "JP", "写真 圧縮") == "below 49"
        assert demand_label(demand, "ru", "сжать видео") == "no data"
        assert demand_label(demand, "de", "komprimieren") == "—"  # never pulled: unknown, not "below"
        with contextlib.redirect_stdout(io.StringIO()) as out:
            assert cmd_report(argparse.Namespace(store=str(store))) == 0
        text = out.getvalue()
        assert "動画圧縮 | PHOTO_VIDEO | 185 | 55 | 160" in text and "No data" in text and "ru" in text
        assert "| pl | video compressor | 1 | 2 | 63% |" in text

        lag_store = Path(tmp) / "lag"
        (lag_store / "metrics").mkdir(parents=True)
        (lag_store / "config.md").write_text((store / "config.md").read_text(encoding="utf-8"), encoding="utf-8")
        (lag_store / "metrics" / "ranks.csv").write_text((store / "metrics" / "ranks.csv").read_text(encoding="utf-8"),
                                                          encoding="utf-8")
        lag = True  # Apple has not published the newest week: fall back once, store nothing for the empty week
        with contextlib.redirect_stdout(io.StringIO()):
            cmd_pull(argparse.Namespace(store=str(lag_store), markets="jp", if_configured=False), fake,
                     dt.date(2026, 9, 29))
        assert {r["week"] for r in read_csv(lag_store / "metrics" / "popularity_cut.csv")} == {"2026-09-13"}

        for order in (["--store", str(store), "report"], ["report", "--store", str(store)]):
            with contextlib.redirect_stdout(io.StringIO()) as out:
                assert main(order) == 0 and "week 2026-09-20" in out.getvalue(), order  # the named store, not cwd
        with contextlib.redirect_stdout(io.StringIO()) as out:
            missing = cmd_pull(argparse.Namespace(store=str(Path(tmp) / "none"), markets=None, if_configured=True), fake)
        assert missing == 0 and "skipped" in out.getvalue()
        with contextlib.redirect_stdout(io.StringIO()):
            assert cmd_pull(argparse.Namespace(store=str(Path(tmp) / "none"), markets=None, if_configured=False), fake) == 2

        def lens(cfg_, resource, payload):
            if resource == ["targeting-keywords", "find"]:
                return {"result": [{"id": 7, "text": "стиснути відео", "matchType": "BROAD",
                                    "bid": {"amount": "0.4", "currency": "USD"}, "status": "PAUSED"}]}
            metrics = {"localSpend": {"amount": "1.50", "currency": "USD"}, "impressions": 30, "taps": 3,
                       "tapInstalls": 2}
            if resource[2] == "keywords":
                return {"result": {"rows": [{"totalMetrics": metrics, "metadata": {"id": 7, "campaignId": 1}}]}}
            hidden = {"totalMetrics": {"localSpend": {"amount": "1.20"}, "impressions": 5, "taps": 1},
                      "metadata": {"searchTermText": None, "keyword": {"id": 7}}}
            named = {"totalMetrics": {"localSpend": {"amount": "0.30"}, "impressions": 25, "taps": 2},
                     "metadata": {"searchTermText": "capcut", "keyword": {"id": 7}}}
            return {"result": {"rows": [hidden, named]}}

        with contextlib.redirect_stdout(io.StringIO()) as out:
            keyword_lens(cfg, "1", "2026-09-16", "2026-09-28", lens)
        text = out.getvalue()
        assert "стиснути відео | BROAD | $0.40 | PAUSED | 30 | 3 | $1.50 | 2 | $0.50 | $0.75" in text
        assert "$1.20 of $1.50 (80%)" in text and "term `capcut` ← keyword `стиснути відео` (BROAD)" in text
    print("OK: config parsing, week math, cut vs head vs no-data, lag fallback, idempotent pulls, ledger labels, keyword join")


def main(argv=None) -> int:
    # `--store` works before or after the subcommand. A subparser that repeated the default would overwrite
    # `radar.py --store OTHER pull` with cwd/marketing and quietly act on the wrong app's store.
    parent = argparse.ArgumentParser(add_help=False)
    parent.add_argument("--store", default=argparse.SUPPRESS, help="Path to the marketing store directory")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--store", default=str(Path.cwd() / "marketing"), help="Path to the marketing store directory")
    parser.add_argument("--self-check", action="store_true", help="offline checks with canned Apple replies")
    sub = parser.add_subparsers(dest="command")
    pull = sub.add_parser("pull", parents=[parent], help="Append this week's popularity and impression share")
    pull.add_argument("--markets", help="comma list; default: every market in metrics/ranks.csv")
    pull.add_argument("--if-configured", action="store_true", help="exit 0 quietly when config.md has no Apple Ads account")
    sub.add_parser("report", parents=[parent], help="Print the stored radar; no network")
    kw = sub.add_parser("keywords", parents=[parent], help="Keyword report joined to keyword text (live, read-only)")
    kw.add_argument("--campaign", help="campaign id; default: every campaign")
    kw.add_argument("--start")
    kw.add_argument("--end")
    args = parser.parse_args(argv)
    if args.self_check:
        self_check()
        return 0
    return {"pull": cmd_pull, "report": cmd_report, "keywords": cmd_keywords}.get(
        args.command, lambda _a: parser.print_help() or 0)(args)


if __name__ == "__main__":
    sys.exit(main())
