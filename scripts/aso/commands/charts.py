"""App Store category charts: where the app stands in Top Free, Paid and Grossing."""

from concurrent.futures import ThreadPoolExecutor
import datetime as dt
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

from aso.commands.base import log_debug, log_error, log_warn, resolve_app_identity
from aso.store_state import store_charts


# ---------------------------------------------------------------- category charts
GENRE_MAP = {
    "utilities": 6002,
    "utility": 6002,
    "productivity_utilities": 6002,
    "photo_video": 6008,
    "photo-video": 6008,
    "photo": 6008,
    "productivity": 6007,
    "lifestyle": 6012,
    "business": 6000,
    "education": 6017,
    "entertainment": 6016,
    "finance": 6015,
    "games": 6014,
    "health_fitness": 6013,
    "music": 6011,
    "navigation": 6010,
    "news": 6009,
    "social": 6005,
    "weather": 6001,
}


GENRE_NAMES = {
    6002: "Utilities",
    6008: "Photo & Video",
    6007: "Productivity",
    6012: "Lifestyle",
    6000: "Business",
    6017: "Education",
    6016: "Entertainment",
    6015: "Finance",
    6014: "Games",
    6013: "Health & Fitness",
    6011: "Music",
    6010: "Navigation",
    6009: "News",
    6005: "Social Networking",
    6001: "Weather",
}


CHART_TYPE_MAP = {
    "top-free": "topfreeapplications",
    "free": "topfreeapplications",
    "topfreeapplications": "topfreeapplications",
    "top-paid": "toppaidapplications",
    "paid": "toppaidapplications",
    "toppaidapplications": "toppaidapplications",
    "top-grossing": "topgrossingapplications",
    "grossing": "topgrossingapplications",
    "topgrossingapplications": "topgrossingapplications",
}


def fetch_category_chart(country: str, genre_id: int, chart_type: str = "topfreeapplications", limit: int = 100, timeout: float = 8.0):
    """Fetch App Store Category Chart from Apple's official iTunes RSS feed."""
    log_debug(f"Fetching category chart: country={country}, genre={genre_id}, type={chart_type}, limit={limit}")
    url = f"https://itunes.apple.com/{country.lower()}/rss/{chart_type}/limit={limit}/genre={genre_id}/json"
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        log_error(f"iTunes RSS request failed for {url}: {exc}")
        return None, str(exc)

    entries = data.get("feed", {}).get("entry", [])
    if isinstance(entries, dict):
        entries = [entries]

    apps = []
    for i, e in enumerate(entries, 1):
        app_id = e.get("id", {}).get("attributes", {}).get("im:id", "")
        name = e.get("im:name", {}).get("label", "")
        developer = e.get("im:artist", {}).get("label", "")
        category = e.get("category", {}).get("attributes", {}).get("label", "")
        apps.append({
            "rank": i,
            "app_id": app_id,
            "name": name,
            "developer": developer,
            "category": category,
        })
    return apps, ""


def find_app_in_chart(apps, target_app_id: str, brand_name: str = ""):
    target_id_str = str(target_app_id).strip() if target_app_id else ""
    brand_cf = brand_name.casefold().strip() if brand_name else ""
    for a in apps:
        if target_id_str and str(a.get("app_id", "")).strip() == target_id_str:
            return a
        if brand_cf and brand_cf in a.get("name", "").casefold():
            return a
    return None


def genre_ids(asked, app: dict) -> list:
    """The genres to read: the names or numbers asked for; else the Apple Ads genres the store's config names;
    else utilities and photo & video."""
    ids = []
    if asked:
        for g in asked.split(","):
            g = g.strip().lower().replace(" ", "_")
            if g.isdigit():
                ids.append(int(g))
            elif g in GENRE_MAP:
                ids.append(GENRE_MAP[g])
            elif g:
                log_warn(f"Unknown genre '{g}'; supported: {', '.join(sorted(GENRE_MAP.keys()))}")
        return ids
    for cg in app.get("ads_genres", []):
        cg_clean = cg.lower().replace(" ", "_").replace("-", "_")
        if cg_clean in GENRE_MAP:
            ids.append(GENRE_MAP[cg_clean])
    return ids or [6002, 6008]


def read_charts(app: dict, countries: list, genres: list, chart_type: str = "topfreeapplications", limit: int = 100,
                fetch=None) -> list:
    """One result per storefront and genre: where the app stands in that chart, or the error that stopped the read."""
    fetch = fetch or fetch_category_chart
    asked = [(country, gid) for country in countries for gid in genres]
    with ThreadPoolExecutor(max_workers=8) as pool:      # public feeds, one a storefront and genre: asked side by side
        answers = list(pool.map(lambda pair: fetch(pair[0], pair[1], chart_type=chart_type, limit=limit), asked))
    all_results = []
    for (country, gid), (apps, err) in zip(asked, answers):
        gname = GENRE_NAMES.get(gid, f"Genre {gid}")
        if err or apps is None:
            all_results.append({
                "country": country.upper(),
                "genre": gname,
                "genre_id": gid,
                "chart_type": chart_type,
                "error": err,
                "found": False,
                "rank": None,
            })
            continue

        match = find_app_in_chart(apps, app["app_id"], app["brand"])
        res = {
            "country": country.upper(),
            "genre": gname,
            "genre_id": gid,
            "chart_type": chart_type,
            "chart_size": len(apps),
            "found": match is not None,
            "rank": match["rank"] if match else None,
            "matched_app": match,
            "threshold_app": apps[-1] if apps else None,
        }
        if match:
            r = match["rank"]
            res["neighbors"] = {
                "prev": apps[r - 2] if r > 1 else None,
                "next": apps[r] if r < len(apps) else None,
            }
        all_results.append(res)
    return all_results


def cmd_charts(args):
    """Inspect App Store Category Charts (Top Free/Paid/Grossing) for target app standings."""
    store = Path(args.store).resolve()
    app = resolve_app_identity(store)

    country_arg = getattr(args, "country", None) or "ua"
    countries = [c.strip().lower() for c in country_arg.split(",") if c.strip()]

    chart_type_arg = getattr(args, "chart_type", "top-free") or "top-free"
    chart_type = CHART_TYPE_MAP.get(chart_type_arg.lower(), "topfreeapplications")

    limit = getattr(args, "limit", 100) or 100
    all_results = read_charts(app, countries, genre_ids(getattr(args, "genre", None), app), chart_type, limit)

    # the history: what was read is appended to the store. Said on stderr, so --json stays one JSON document.
    gained = store_charts(store, all_results, dt.date.today().isoformat())
    print(f"stored: charts.csv +{gained}", file=sys.stderr)

    if getattr(args, "json", False):
        print(json.dumps(all_results, indent=2, ensure_ascii=False))
        return 0

    print("=================================================================")
    print(f"📈 App Store Category Charts · {app['brand']} (ID: {app['app_id']})")
    print("=================================================================\n")

    for r in all_results:
        c = r["country"]
        g = r["genre"]
        if r.get("error"):
            print(f"⚠️  [{c}] {g} (ID: {r['genre_id']}): Error fetching chart: {r['error']}")
            continue

        if r["found"]:
            m = r["matched_app"]
            print(f"🎉 [{c}] {g}: #{r['rank']} in Top {r['chart_size']}!")
            print(f"    App: {m['name']} (by {m['developer']})")
            nbr = r.get("neighbors", {})
            if nbr.get("prev"):
                print(f"    ▲ #{r['rank']-1}: {nbr['prev']['name']} ({nbr['prev']['developer']})")
            if nbr.get("next"):
                print(f"    ▼ #{r['rank']+1}: {nbr['next']['name']} ({nbr['next']['developer']})")
        else:
            th = r.get("threshold_app")
            th_str = f"#{th['rank']}: {th['name']} by {th['developer']}" if th else "no entries"
            print(f"📊 [{c}] {g}: Not in Top {r['chart_size']}")
            print(f"    Chart cut-off threshold: {th_str}")
        print()

    print("=================================================================")
    return 0
