"""What the store keeps of the App Store's own state: ratings per read, chart positions per read, and the day a
version went live. Each is appended, never rewritten."""
from __future__ import annotations

import datetime as dt

import json
from pathlib import Path

from aso.store import append_changed, append_csv, read_csv

RATINGS_COLS = ["captured", "market", "ratings_count", "rating_average", "reviews", "reviews_unanswered", "source"]
CHART_COLS = ["captured", "market", "genre", "chart_type", "position", "depth", "status", "source"]
RELEASE_COLS = ["version", "state", "state_date", "source", "captured"]


def ratings_rows(ratings: dict, unanswered, captured: str) -> list:
    """One row for all storefronts together and one per storefront that has ratings. `unanswered` is the reply of
    the unresponded-reviews read, or None; its total goes on the `all` row. A cell nothing filled is blank."""
    if not isinstance(ratings, dict) or "averageRating" not in ratings or "totalCount" not in ratings:
        return []
    paging = ((unanswered or {}).get("meta") or {}).get("paging") if isinstance(unanswered, dict) else None
    waiting = paging.get("total") if isinstance(paging, dict) and isinstance(paging.get("total"), int) else ""

    def row(market, count, average, left=""):
        return {"captured": captured, "market": market, "ratings_count": count, "rating_average": average, "reviews": "",
                "reviews_unanswered": left, "source": "itunes-ratings"}

    countries = [c for c in ratings.get("byCountry") or [] if isinstance(c, dict) and c.get("country")]
    return [row("all", ratings["totalCount"], ratings["averageRating"], waiting)] + sorted(
        (row(c["country"].lower(), c.get("ratingCount", ""), c.get("averageRating", "")) for c in countries),
        key=lambda r: r["market"])


def chart_rows(results: list, captured: str) -> list:
    """One row per storefront, genre and chart asked. Not in the chart is `beyond-depth` with the chart's size as
    depth; a failed request is `error`. Neither is a position."""
    rows = []
    for r in results:
        if r.get("error"):
            status = "error"
        else:
            status = "ok" if r.get("rank") else "beyond-depth"
        rows.append({"captured": captured, "market": str(r.get("country", "")).lower(), "genre": r.get("genre", ""),
                     "chart_type": r.get("chart_type", ""), "position": r["rank"] if status == "ok" else "",
                     "depth": r.get("chart_size", ""), "status": status, "source": "itunes-rss"})
    return rows


def first_release_day(lookup):
    """The day the public store lookup says the app was first released, or None. It is where an app's history
    starts: collectors that can ask for a span ask from here."""
    found = (lookup.get("results") or [None])[0] if isinstance(lookup, dict) else None
    try:
        return dt.date.fromisoformat(str((found or {}).get("releaseDate") or "")[:10]).isoformat()
    except ValueError:
        return None


def release_row(lookup: dict, captured: str):
    """The version the store shows now and the day the store says it was released, or None when the lookup holds
    no app. The versions list of App Store Connect carries no such day; the public lookup does."""
    found = (lookup.get("results") or [None])[0] if isinstance(lookup, dict) else None
    if not isinstance(found, dict) or not found.get("version") or not found.get("currentVersionReleaseDate"):
        return None
    return {"version": found["version"], "state": "live", "state_date": found["currentVersionReleaseDate"][:10],
            "source": "itunes-lookup", "captured": captured}


def loads(text):
    try:
        return json.loads(text) if text else None
    except (TypeError, ValueError):
        return None


def store_ratings(store: Path, ratings_text, unanswered_text, captured: str) -> int:
    rows = ratings_rows(loads(ratings_text), loads(unanswered_text), captured)
    return append_changed(store / "metrics" / "ratings.csv", RATINGS_COLS, rows, ("captured", "market"))


def store_charts(store: Path, results: list, captured: str) -> int:
    return append_changed(store / "metrics" / "charts.csv", CHART_COLS, chart_rows(results, captured),
                          ("captured", "market", "genre", "chart_type"))


def store_release(store: Path, lookup: dict, captured: str) -> int:
    """A version is stored as live once: a later read of the same version adds nothing."""
    row = release_row(lookup, captured)
    path = store / "metrics" / "releases.csv"
    if row is None or any((r["version"], r["state"]) == (row["version"], row["state"]) for r in read_csv(path)):
        return 0
    append_csv(path, RELEASE_COLS, [row])
    return 1
