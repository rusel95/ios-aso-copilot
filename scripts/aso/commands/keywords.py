"""Keyword research commands: hints, vacuums, popularity, competitors, the review filter."""

import datetime as dt
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

from aso import keyword_registry
from aso.commands.base import SKILL_DIR, log_debug, log_error, log_info, resolve_app_identity, run_cmd
from aso.store import print_problems


def probe_localization_vacuum(term: str, country: str, limit: int = 25):
    """Probe iTunes Search API to detect localization vacuums (unlocalized competitor apps)."""
    log_debug(f"Probing localization vacuum for '{term}' in {country} (limit {limit})...")
    url = f"https://itunes.apple.com/search?term={urllib.parse.quote(term)}&country={country.lower()}&entity=software&limit={limit}"
    headers = {"User-Agent": "iTunes/12.0 (Macintosh)"}
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=12.0) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        log_error(f"iTunes Search API request failed: {exc}")
        return None, str(exc)

    results = payload.get("results", [])
    if not results:
        return {
            "term": term,
            "country": country.upper(),
            "results_count": 0,
            "vacuum_score": 100,
            "verdict": "VACUUM_HIGH",
            "reason": "No apps found for this query in this storefront. Maximum opportunity.",
            "localized_in_top5": 0,
            "avg_top5_ratings": 0.0,
            "apps": []
        }, ""

    words = set(term.casefold().split())
    apps = []
    localized_title_count = 0
    ratings = []

    for i, item in enumerate(results, 1):
        title = item.get("trackName", "")
        seller = item.get("artistName") or item.get("sellerName", "")
        rating_count = int(item.get("userRatingCount", 0))
        avg_rating = float(item.get("averageUserRating", 0.0))
        price = item.get("price", 0.0)
        bundle_id = item.get("bundleId", "")

        title_words = set(title.casefold().split())
        has_word_match = bool(words & title_words)
        is_localized = has_word_match
        if is_localized:
            localized_title_count += 1
        ratings.append(rating_count)

        apps.append({
            "rank": i,
            "title": title,
            "developer": seller,
            "ratings_count": rating_count,
            "average_rating": avg_rating,
            "price": price,
            "bundle_id": bundle_id,
            "localized_title": is_localized
        })

    top5 = apps[:5]
    top5_ratings = [a["ratings_count"] for a in top5]
    avg_top5_ratings = sum(top5_ratings) / max(len(top5_ratings), 1)
    localized_in_top5 = sum(1 for a in top5 if a["localized_title"])

    loc_penalty = (localized_in_top5 / 5.0) * 50.0
    rating_penalty = min(avg_top5_ratings / 200.0, 1.0) * 50.0
    vacuum_score = max(0, min(100, int(100 - loc_penalty - rating_penalty)))

    if vacuum_score >= 70:
        verdict = "VACUUM_HIGH"
        reason = f"Top apps lack localized titles ({localized_in_top5}/5) and average only {avg_top5_ratings:.0f} ratings in {country.upper()}. High ASO & Exact Ads potential!"
    elif vacuum_score >= 40:
        verdict = "VACUUM_MODERATE"
        reason = f"Moderate competition: {localized_in_top5}/5 top apps have localized titles, avg ratings {avg_top5_ratings:.0f}. Exact keywords & metadata optimization viable."
    else:
        verdict = "COMPETITIVE"
        reason = f"Established local competitors dominate top positions ({localized_in_top5}/5 localized, avg ratings {avg_top5_ratings:.0f}). High bidding required."

    data = {
        "term": term,
        "country": country.upper(),
        "results_count": len(results),
        "vacuum_score": vacuum_score,
        "verdict": verdict,
        "reason": reason,
        "localized_in_top5": localized_in_top5,
        "avg_top5_ratings": avg_top5_ratings,
        "apps": apps
    }
    return data, ""


def cmd_keywords(args):
    """Manage keyword discovery, hints, localization vacuums, and filtering."""
    subaction = getattr(args, "keywords_action", None)
    if subaction == "hints":
        return cmd_keywords_hints(args)
    elif subaction == "vacuum":
        return cmd_keywords_vacuum(args)
    elif subaction == "popularity":
        return cmd_keywords_popularity(args)
    elif subaction == "competitors":
        return cmd_keywords_competitors(args)
    elif subaction == "filter":
        return cmd_keywords_filter(args)
    elif subaction == "registry":
        return cmd_keywords_registry(args)
    else:
        print("Unknown keywords subcommand. Use: hints, vacuum, popularity, competitors, filter, registry")
        return 1


def record_found(args, market, terms, source):
    """`--record` on a network command: put what it just found into the keyword registry, dated today (the clock is read
    here, in the command, never in the registry). Reports on stderr so `--json` output stays whole; never fails the command."""
    store = Path(args.store).resolve()
    try:
        done = keyword_registry.add(store, market, terms, source, dt.date.today())
    except (ValueError, OSError) as exc:
        log_error(f"Not recorded in the keyword registry: {exc}")
        return
    log_info(f"Recorded {len(terms)} {source} keyword(s) for {market} in {keyword_registry.REGISTRY}: appended {done['appended']} rows"
             + (f"; refused {len(done['refused'])} brand keyword(s), never tracked" if done["refused"] else ""))


def cmd_keywords_registry(args):
    """build / show / add the keyword registry. Offline: it reads and writes files under the store, nothing else."""
    store = Path(args.store).resolve()
    if not store.is_dir():
        print(f"Store not found: {store}")
        return 2
    action = getattr(args, "registry_action", None)
    as_of = dt.date.fromisoformat(args.as_of) if getattr(args, "as_of", None) else dt.date.today()
    if action in ("build", "add"):
        print(f"as of {as_of}")
        try:
            if action == "add":
                done = keyword_registry.add(store, args.market, args.terms, args.source, as_of)
            else:
                done = keyword_registry.build(store, as_of)
        except ValueError as exc:
            print(f"Error: {exc}")
            return 2
        print(f"registry {action}: appended {done['appended']} rows ({done['new']} new keys) to {keyword_registry.REGISTRY}; "
              f"{done['keys']} keys in all")
        if done["dropped"]:
            print(f"dropped {done['dropped']} brand keys an older registry held (a brand key is never tracked)")
        if done["refused"]:
            names = [f"{m} {k}" for m, k in done["refused"]]
            print(f"refused {len(names)} brand keys (never tracked): " + ", ".join(names[:8]) + (" ..." if len(names) > 8 else ""))
        print("read, keys by source: " + " · ".join(f"{name} {n}" for name, n in done["read"].items()))
        for where, why in done["skipped"][:12]:
            print(f"NOTE {where}: {why}")
        if len(done["skipped"]) > 12:
            print(f"NOTE ... and {len(done['skipped']) - 12} more files or rows that name no storefront")
        print_problems()
        return 0
    if action == "show":
        rows = keyword_registry.read_registry(store)
        if not rows:
            print(f"No keyword registry yet at {store / keyword_registry.REGISTRY}: run `copilot.py keywords registry build`.")
            return 1
        shown = keyword_registry.summary(rows, args.limit)
        if getattr(args, "json", False):
            print(json.dumps(shown, indent=2, ensure_ascii=False))
            return 0
        print(f"keyword registry: {shown['keys']} keys in {keyword_registry.REGISTRY}")
        if shown["excluded"]:
            print("kept apart, left out of candidates and overlaps: " + ", ".join(f"{n} {why}" for why, n in shown["excluded"].items()))
        print(f"\n{'market':<8}{'keys':>6}{'tracked':>9}{'candidates':>12}{'excluded':>10}")
        for market, m in shown["by_market"].items():
            print(f"{market:<8}{m['keys']:>6}{m['tracked']:>9}{m['candidates']:>12}{m['excluded']:>10}")
        print("\nby source (a key counts once for each source that named it): " + " · ".join(f"{k} {n}" for k, n in shown["by_source"].items()))
        print("\nlargest overlaps (keys two sources both name):")
        for o in shown["overlaps"]:
            print(f"  {o['sources'][0]} + {o['sources'][1]}: {o['keys']}")
        if shown["twins"]:
            print("\ntwo queries to Apple, one to a person (U+0027 vs U+2019; both kept, ranked apart):")
            for t in shown["twins"]:
                print(f"  {t['market']}  " + "  |  ".join(t["keywords"]))
        print(f"\ncandidates not tracked, most-named first (first {len(shown['candidates'])}):")
        for c in shown["candidates"]:
            print(f"  {c['market']}  {c['keyword']}  [{'; '.join(c['sources'])}]" + (f"  {c['popularity']}" if c["popularity"] else ""))
        return 0
    print("Unknown registry action. Use: build, show, add")
    return 1


def cmd_keywords_hints(args):
    from harvest_keywords import fetch_hints
    storefront = (getattr(args, "country", None) or getattr(args, "storefront", None) or "us").lower()
    term = args.term
    log_debug(f"Fetching hints for '{term}' in storefront '{storefront}'")
    try:
        hints = fetch_hints(term, storefront)
    except Exception as e:
        log_error(f"Failed to fetch hints: {e}")
        print(f"Error fetching hints: {e}")
        return 1
    if getattr(args, "record", False):
        record_found(args, storefront, hints, "autocomplete-hints")
    if getattr(args, "json", False):
        print(json.dumps({"term": term, "storefront": storefront, "hints": hints}, indent=2))
        return 0
    print(f"\n🔍 Apple Search Autocomplete Hints for '{term}' [{storefront.upper()}]:")
    if not hints:
        print("  (no suggestions returned)")
    for i, h in enumerate(hints, 1):
        print(f"  {i:2d}. {h}")
    return 0


def cmd_keywords_vacuum(args):
    term = args.term
    country = (args.country or "us").lower()
    limit = getattr(args, "limit", 20)
    log_info(f"Auditing localization vacuum for '{term}' in {country.upper()}...")
    data, err = probe_localization_vacuum(term, country, limit)
    if err or not data:
        print(f"Error checking localization vacuum: {err}")
        return 1
    if getattr(args, "json", False):
        print(json.dumps(data, indent=2))
        return 0

    print("\n=================================================================")
    print(f"🌌 Localization Vacuum Audit: '{term}' in {country.upper()}")
    print("=================================================================\n")
    print(f"Verdict:           {data['verdict']} (Score: {data['vacuum_score']}/100)")
    print(f"Analysis:          {data['reason']}")
    print(f"Results Count:     {data['results_count']} apps analyzed")
    print(f"Localized in Top5: {data['localized_in_top5']}/5 apps")
    print(f"Avg Top5 Ratings:  {data['avg_top5_ratings']:.0f}")
    print("\nTop Ranking Apps in Search Index:")
    print(f"{'#':<3} {'Title':<42} {'Localized':<10} {'Ratings':<10} {'Developer'}")
    print("-" * 80)
    for app in data["apps"][:15]:
        loc_badge = "✓ Yes" if app["localized_title"] else "✗ No"
        title_str = (app["title"][:38] + "..") if len(app["title"]) > 40 else app["title"]
        dev_str = (app["developer"][:24] + "..") if len(app["developer"]) > 26 else app["developer"]
        print(f"{app['rank']:<3} {title_str:<42} {loc_badge:<10} {app['ratings_count']:<10} {dev_str}")
    print("=================================================================")
    return 0


def cmd_keywords_popularity(args):
    store = Path(args.store).resolve()
    cfg = resolve_app_identity(store)
    country = (args.country or "us").upper()
    terms = [t.strip() for t in args.terms.split(",")] if getattr(args, "terms", None) else []
    log_debug(f"Querying popularity for country={country}, terms={terms}")

    if terms:
        # A per-term question gets a per-term answer from the stored weekly radar. Apple lists only each
        # storefront's head, so most terms are "below the cut": unknown, not zero. Never fall through to
        # the whole-store report (it used to, silently ignoring --terms, when the market had no rows).
        from radar import demand_lookup, demand_label
        demand = demand_lookup(store)
        explain = {"—": "market never pulled — run `copilot.py radar pull`",
                   "no data": "Apple lists nothing for this storefront"}
        answers = [{"market": country.lower(), "term": term,
                    "popularity": demand_label(demand, country.lower(), term)} for term in terms]
        if getattr(args, "json", False):
            print(json.dumps(answers, indent=2, ensure_ascii=False))
            return 0
        print(f"\n📊 Apple Search Popularity [{country}] (stored weekly radar; relative 1-100, not searches):")
        for a_ in answers:
            label = a_["popularity"]
            note = explain.get(label) or ("not in Apple's published head: volume unknown, not zero"
                                          if label.startswith("below") else "")
            print(f"  {a_['term']}: {label}" + (f"  ({note})" if note else ""))
        return 0

    pop_csv = store / "metrics" / "popularity.csv"
    if pop_csv.is_file():
        import csv
        rows = list(csv.DictReader(pop_csv.open(encoding="utf-8")))
        matched = [r for r in rows if r.get("market", "").upper() == country]
        if terms:
            matched = [r for r in matched if r.get("term", "").casefold() in [t.casefold() for t in terms]]
        if getattr(args, "json", False):
            print(json.dumps(matched, indent=2))
            return 0
        if matched:
            print(f"\n📊 Stored Apple Search Popularity [{country}]:")
            for r in matched[:30]:
                print(f"  {r.get('term')}: popularity {r.get('popularity_100')}/100 (genre: {r.get('genre')}, rank: {r.get('rank_in_genre')})")
            return 0

    if not cfg.get("ads_account") or not cfg.get("ads_profile"):
        print(f"Apple Ads credentials not configured in {store / 'config.md'} and no stored metrics/popularity.csv found.")
        print("Set **Apple Ads profile**: and **Apple Ads account**: in config.md to query live popularity.")
        return 2

    radar_py = SKILL_DIR / "scripts" / "radar.py"
    rc, out, err = run_cmd([sys.executable, str(radar_py), "--store", str(store), "report"])
    print(out if rc == 0 else f"Error: {err}")
    return rc


def cmd_keywords_competitors(args):
    from harvest_keywords import fetch_competitors
    seeds = [s.strip() for s in args.seeds.split(",") if s.strip()]
    country = (args.country or "us").lower()
    limit = getattr(args, "limit", 25)
    log_debug(f"Fetching competitors for seeds={seeds} in {country} (limit {limit})")
    try:
        comps = fetch_competitors(seeds, country, limit)
    except Exception as e:
        log_error(f"Failed to fetch competitors: {e}")
        print(f"Error fetching competitors: {e}")
        return 1
    if getattr(args, "record", False):
        record_found(args, country, [name for name, _ in comps], "competitor-harvest")
    if getattr(args, "json", False):
        print(json.dumps([{"app": name, "hits": hits} for name, hits in comps], indent=2))
        return 0
    print(f"\n🏆 Top Competitors Discovered [{country.upper()}] (across {len(seeds)} seed terms):")
    print(f"{'#':<3} {'App Name':<50} {'Seed Hits'}")
    print("-" * 65)
    for i, (name, hits) in enumerate(comps, 1):
        app_str = (name[:46] + "..") if len(name) > 48 else name
        print(f"{i:<3} {app_str:<50} {hits} seeds")
    return 0


def cmd_keywords_filter(args):
    from ads_keywords import export
    in_path = Path(args.input).resolve()
    out_dir = Path(args.output).resolve()
    brands = [b.strip() for b in getattr(args, "brand", []) if b.strip()]
    limit = getattr(args, "limit", 5000)
    log_info(f"Filtering candidates from {in_path} to {out_dir} (limit {limit})...")
    try:
        summary = export(in_path, out_dir, brands=brands, limit=limit)
    except Exception as e:
        log_error(f"Filter failed: {e}")
        print(f"Error filtering candidates: {e}")
        return 1
    if getattr(args, "json", False):
        print(json.dumps(summary, indent=2))
        return 0
    print("✓ Keywords filtered successfully:")
    print(f"  Accepted:  {summary['accepted']}")
    print(f"  Rejected:  {summary['rejected']}")
    print(f"  Protected: {summary['protected']}")
    print(f"  Output:    {out_dir}")
    return 0
