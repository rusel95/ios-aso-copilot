"""The snapshot families: stocks read at a moment. One function per family, keyed by the day of the read."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from aso.dashboard.contract import is_number
from aso.dashboard.series import latest_rows, ranks_until, share, split, unavailable
from aso.ranks import coverage, sweep_bands
from aso.store import parse_date, problem, read_brand_tokens, read_csv


def rank_snapshots(store: Path, as_of: dt.date) -> dict:
    """sweep date -> the ranks and coverage families of that day."""
    rows, brand, out = ranks_until(store, as_of), read_brand_tokens(store), {}
    for day in sorted({r["date"] for r in rows}):
        if parse_date(day) is None:
            problem("metrics/ranks.csv", f"date {day!r} is not a date; its rows are in no snapshot")
            continue
        bands = sweep_bands(rows, brand, day)
        split = bands["by_market"]
        figures = {name: {"value": bands[name], "by_market": {m: counts[name] for m, counts in split.items()}}
                   for name in ("tracked_keys", "keys_read", "top10", "top30", "top100", "top200", "beyond",
                                "no_results", "errors")}
        for name, bands_in in (("share_top10", ("top10",)), ("share_top30", ("top10", "top30"))):
            inside = sum(bands[b] for b in bands_in)
            if not bands["keys_read"]:
                figures[name] = unavailable("no_data", "No key was read that day.")
            else:
                figures[name] = {"value": share(inside, bands["keys_read"]), "numerator": inside,
                                 "denominator": bands["keys_read"],
                                 "by_market": {m: share(sum(c[b] for b in bands_in), c["keys_read"]) for m, c in split.items()}}
        seen = coverage([r for r in rows if r["date"] <= day])
        providers = [r["provider"] for r in rows if r["date"] == day and r["provider"]]
        source = max(sorted(set(providers)), key=providers.count) if providers else "unknown"
        out[day] = {
            "ranks": {"source": source, "fetched_at": day, "figures": figures},
            "coverage": {"source": source, "fetched_at": day, "figures": {
                "paired_keys": {"value": seen["paired"]}, "unmeasurable_keys": {"value": seen["unmeasurable"]},
                "failed_requests": {"value": seen["failed"]}, "observations": {"value": seen["observations"]}}},
        }
    return out


def captured_rows(store: Path, name: str, as_of: dt.date, numbers: dict, notes: list) -> dict:
    """capture day -> rows of one Apple Ads insights file, numbers parsed. `numbers` maps a column to int or float;
    a blank cell is null; a row with an unreadable cell is named and skipped."""
    out = {}
    for n, r in enumerate(read_csv(store / "metrics" / name), 2):
        day, week = parse_date(r.get("captured")), parse_date(r.get("week"))
        if day is None or week is None:
            notes.append(f"metrics/{name}:{n}: week or captured is not a date; the row is skipped")
            continue
        if day > as_of:
            continue
        row = {"_week": week}
        try:
            for column in r:
                cell = (r[column] or "").strip()
                row[column] = (numbers[column](cell) if cell else None) if column in numbers else cell
        except ValueError:
            notes.append(f"metrics/{name}:{n}: a number column holds {cell!r}; the row is skipped")
            continue
        out.setdefault(day, []).append(row)
    return out


def insight_family(rows: list, key: tuple, lists: dict) -> dict:
    """One family from the rows of one capture day. `lists` maps a list name to (source rows, columns)."""
    weeks = [r["_week"] for group, _ in lists.values() for r in group] or [r["_week"] for r in rows]
    family = {"source": "asc-ads-insights", "fetched_at": key[0].isoformat(),
              "measured": {"start": min(weeks).isoformat(), "end": (max(weeks) + dt.timedelta(days=6)).isoformat()}}
    for name, (group, columns) in lists.items():
        latest = {}
        for r in group:                                    # a repeated row is the same fact; the later line stands
            latest[tuple(r[c] for c in columns[:-1] if not isinstance(r[c], (int, float)))] = {c: r[c] for c in columns}
        family[name] = [latest[k] for k in sorted(latest, key=lambda k: tuple(str(x) for x in k))]
    return family


def insight_snapshots(store: Path, as_of: dt.date, notes: list) -> dict:
    """capture day -> the demand and impression_share families Apple's own figures were stored on."""
    popularity = captured_rows(store, "popularity.csv", as_of, {"popularity_100": int}, notes)
    cuts = captured_rows(store, "popularity_cut.csv", as_of, {"listed": int, "min_popularity_100": int}, notes)
    shares = captured_rows(store, "impression_share.csv", as_of, {"rank": int, "share_low": float, "share_high": float},
                           notes)
    out = {}
    for day in sorted(set(popularity) | set(cuts)):
        out.setdefault(day, {})["demand"] = insight_family([], (day,), {
            "rows": (popularity.get(day, []), ["market", "genre", "term", "popularity_100"]),
            "cuts": (cuts.get(day, []), ["market", "genre", "listed", "min_popularity_100"])})
    for day in sorted(shares):
        out.setdefault(day, {})["impression_share"] = insight_family([], (day,), {
            "rows": (shares[day], ["market", "term", "rank", "share_low", "share_high"])})
    return out


SUBSCRIPTION_FIGURES = ("active_subscriptions", "active_trials", "mrr_usd", "revenue_28d_usd", "new_customers_28d",
                        "active_users_28d")


def subscription_snapshots(store: Path, as_of: dt.date, notes: list) -> dict:
    """read day -> the subscriptions family. From the stored series; a store that has no series yet still shows the
    one read it holds in `revenuecat_latest.json`."""
    rows, stored = latest_rows(store, "revenue.csv", ("captured",), SUBSCRIPTION_FIGURES, as_of, notes)
    if stored:
        return {r["captured"]: {"subscriptions": {"source": "revenuecat", "fetched_at": r["captured"].isoformat(), "figures": {
            name: {"value": r[name]} if r[name] is not None else unavailable("no_data", "The read holds no such figure.")
            for name in SUBSCRIPTION_FIGURES}}} for r in rows}
    path = store / "metrics" / "revenuecat_latest.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        day = parse_date(data.get("captured_at"))
        overview = data.get("overview") or {}
    except (ValueError, AttributeError):
        day = None
    if day is None:
        notes.append("metrics/revenuecat_latest.json: unreadable, or it names no capture day; left out")
        return {}
    if day > as_of:
        return {}
    names = {"active_subscriptions": "active_subscriptions", "active_trials": "active_trials", "mrr_usd": "mrr",
             "revenue_28d_usd": "revenue", "new_customers_28d": "new_customers", "active_users_28d": "active_users"}
    figures = {}
    for key, theirs in names.items():
        value = (overview.get(theirs) or {}).get("value") if isinstance(overview.get(theirs), dict) else None
        figures[key] = {"value": value} if is_number(value) else unavailable("no_data", "The read holds no such figure.")
    return {day: {"subscriptions": {"source": "revenuecat", "fetched_at": day.isoformat(), "figures": figures}}}


RATING_FIGURES = ("ratings_count", "rating_average", "reviews", "reviews_unanswered")


def ratings_snapshots(store: Path, as_of: dt.date, notes: list) -> dict:
    """read day -> the ratings family: the `all` row as the figure, the storefront rows as its split."""
    rows, _ = latest_rows(store, "ratings.csv", ("captured", "market"), RATING_FIGURES, as_of, notes)
    days = {}
    for r in rows:
        days.setdefault(r["captured"], []).append(r)
    out = {}
    for day, theirs in sorted(days.items()):
        whole = next((r for r in theirs if r["market"] == "all"), None)
        markets = sorted((r for r in theirs if r["market"] != "all"), key=lambda r: r["market"])
        figures = {}
        for name in RATING_FIGURES:
            if whole is None or whole[name] is None:
                figures[name] = unavailable("no_data", "The read holds no such figure.")
            else:
                split = {r["market"]: r[name] for r in markets if r[name] is not None}
                figures[name] = {"value": whole[name], **({"by_market": split} if split else {})}
        out[day] = {"ratings": {"source": "itunes-ratings", "fetched_at": day.isoformat(), "figures": figures}}
    return out


def chart_snapshots(store: Path, as_of: dt.date, notes: list) -> dict:
    """read day -> the charts family: one row per storefront, genre and chart asked that day."""
    rows, _ = latest_rows(store, "charts.csv", ("captured", "market", "genre", "chart_type"), ("position",), as_of, notes)
    days = {}
    for r in rows:
        days.setdefault(r["captured"], []).append({"market": r["market"], "genre": r["genre"], "chart_type": r["chart_type"],
                                                   "position": r["position"], "status": r["status"]})
    return {day: {"charts": {"source": "itunes-rss", "fetched_at": day.isoformat(),
                             "rows": sorted(found, key=lambda r: (r["market"], r["genre"], r["chart_type"]))}}
            for day, found in sorted(days.items())}
