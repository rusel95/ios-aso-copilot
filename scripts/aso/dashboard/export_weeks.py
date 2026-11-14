"""The week families: flows summed over closed Monday weeks. One function per family; each returns the weeks it
holds, and whether its series is stored at all."""
from __future__ import annotations

import datetime as dt
from pathlib import Path

from aso.dashboard.contract import OPEN_KEY
from aso.dashboard.series import by_closed_week, counted, divided, latest_rows, share, total, unavailable
from aso.dashboard.weeks import closed
from aso.store import parse_date, read_csv


# ------------------------------------------------------------------ period files
COLLECTOR_ROWS = "live:asc analytics daily"       # how pull_funnel.py tags the weeks it folds from the daily reports


FUNNEL_COLUMNS = {"impressions": "impressions", "page_views": "product_page_views", "first_downloads": "downloads"}


FUNNEL_RATIOS = {"view_rate": ("page_views", "impressions"), "page_cvr": ("first_downloads", "page_views"),
                 "impression_cvr": ("first_downloads", "impressions")}


NOT_STORED_YET = {
    "lifecycle": "Install and deletion counts are not stored by week yet.",
    "money": "Proceeds and Apple Ads spend are not stored by week yet.",
    "ads": "Apple Ads results are not stored by week yet.",
    "in_app": "In-app events are not stored by week yet.",
}


NOTHING_THAT_WEEK = {
    "store_funnel": "The store holds no funnel row the collector wrote for this week.",
    "lifecycle": "The store holds no install and deletion row for this week.",
    "money": "The store holds no cashflow row for this week.",
    "ads": "The store holds no Apple Ads row for this week.",
    "in_app": "The store holds no in-app row for this week.",
}


LIFECYCLE_COLUMNS = {"optin_installs": "first_installs_optin", "optin_deletions": "deletions_optin",
                     "deleted_within_1d": "deleted_within_1d"}


def collector_weeks(store: Path, name: str, columns: dict, as_of: dt.date, notes: list) -> tuple:
    """(week start -> {segment: counts}, stored) from the closed Monday weeks the collector wrote into one file.

    A row a person typed, a week still open, and a row recorded after `as_of` are left out and counted. Among
    rows for the same week and segment the latest `recorded` wins, then the later line: a correction is a new row.
    `stored` says whether the collector ever wrote a row there."""
    chosen, left, stored = {}, {"hand": 0, "open": 0, "later": 0}, False
    for n, r in enumerate(read_csv(store / "metrics" / name), 2):
        week, recorded = parse_date(r.get("week_start")), parse_date(r.get("recorded"))
        if not (r.get("source") or "").startswith(COLLECTOR_ROWS) or week is None or week.weekday() or recorded is None:
            left["hand"] += 1
            continue
        stored = True
        if recorded > as_of:
            left["later"] += 1
        elif not closed(week, as_of):
            left["open"] += 1
        else:
            counts = {}
            for key, column in columns.items():
                cell = (r.get(column) or "").strip()
                try:
                    counts[key] = int(cell) if cell else None
                except ValueError:
                    notes.append(f"metrics/{name}:{n}: {column} {cell!r} is not a number; the row is skipped")
                    counts = None
                    break
            key = (week, (r.get("segment") or "").strip().lower())
            if counts is not None and (key not in chosen or recorded >= chosen[key]["recorded"]):
                chosen[key] = {"recorded": recorded, **counts}
    if any(left.values()):
        notes.append(f"metrics/{name}: {sum(left.values())} rows left out ({left['hand']} not written by the collector "
                     f"as Monday weeks, {left['open']} of weeks still open on {as_of}, {left['later']} recorded after {as_of})")
    weeks = {}
    for (week, segment), row in sorted(chosen.items()):
        weeks.setdefault(week, {})[segment] = row
    return weeks, stored


def whole_and_markets(segments: dict) -> tuple:
    """The week's `all` row (or None) and its two-letter storefront rows, in order."""
    return segments.get("all"), {s: row for s, row in sorted(segments.items()) if len(s) == 2 and s.isalpha()}


def count_figure(whole, markets: dict, key: str) -> dict:
    if whole is None or whole[key] is None:
        return unavailable("no_data", "The report holds no total for the week.")
    return {"value": whole[key], **({"by_market": {m: row[key] for m, row in markets.items()}} if markets else {})}


def family(source: str, segments: dict, figures: dict) -> dict:
    return {"source": source, "fetched_at": max(row["recorded"] for row in segments.values()).isoformat(), "figures": figures}


def funnel_weeks(store: Path, as_of: dt.date, notes: list) -> dict:
    """week start -> the store_funnel family, from the closed Monday weeks the collector wrote."""
    out = {}
    for week, segments in collector_weeks(store, "weekly.csv", FUNNEL_COLUMNS, as_of, notes)[0].items():
        total, markets = whole_and_markets(segments)
        figures = {key: count_figure(total, markets, key) for key in FUNNEL_COLUMNS}
        for key, (top, bottom) in FUNNEL_RATIOS.items():
            value = share(total[top], total[bottom]) if total else None
            if value is None:
                figures[key] = unavailable("no_data", "Nothing to divide by: a total of the week is missing or zero.")
            else:
                figures[key] = {"value": value, "numerator": total[top], "denominator": total[bottom],
                                **({"by_market": {m: share(row[top], row[bottom]) for m, row in markets.items()}}
                                   if markets else {})}
        out[week] = family("asc-analytics", segments, figures)
    return out


def per_100(top, bottom):
    """How many of the first for every hundred of the second, to one place; None when there is nothing to divide by."""
    return round(100 * top / bottom, 1) if top is not None and bottom else None


def lifecycle_weeks(store: Path, as_of: dt.date, notes: list) -> tuple:
    """(week start -> the lifecycle family, stored), from the closed weeks of opt-in installs and deletions the
    collector folded. A sample of devices, and not a cohort: the catalog says so beside every figure."""
    weeks, stored = collector_weeks(store, "lifecycle.csv", LIFECYCLE_COLUMNS, as_of, notes)
    out = {}
    for week, segments in weeks.items():
        whole, markets = whole_and_markets(segments)
        figures = {key: count_figure(whole, markets, key) for key in LIFECYCLE_COLUMNS}
        gone, came = (whole["optin_deletions"], whole["optin_installs"]) if whole else (None, None)
        if per_100(gone, came) is None:
            figures["deletions_per_100"] = unavailable("no_data", "Nothing to divide by: the week holds no opt-in install.")
        else:
            figures["deletions_per_100"] = {
                "value": per_100(gone, came), "numerator": gone, "denominator": came,
                **({"by_market": {m: per_100(row["optin_deletions"], row["optin_installs"]) for m, row in markets.items()}}
                   if markets else {})}
        out[week] = family("asc-analytics", segments, figures)
    return out, stored


def money_weeks(store: Path, as_of: dt.date, notes: list) -> tuple:
    """(week start -> the money family, stored), from the closed weeks of cashflow the collector folded per storefront."""
    numbers = ("transactions", "new_trials", "gross_revenue_usd", "proceeds_usd", "ad_spend_usd")
    rows, stored = latest_rows(store, "cashflow_weekly.csv", ("week_start", "country"), numbers, as_of, notes)
    out = {}
    for week, theirs in by_closed_week(rows, as_of).items():
        for r in theirs:
            r["net"] = None if r["proceeds_usd"] is None or r["ad_spend_usd"] is None else r["proceeds_usd"] - r["ad_spend_usd"]
        market = (("market", "country"),)
        out[week] = {"source": "revenuecat+apple-ads", "fetched_at": max(r["captured"] for r in theirs).isoformat(), "figures": {
            "proceeds_usd": counted(theirs, "proceeds_usd", market, 2), "ad_spend_usd": counted(theirs, "ad_spend_usd", market, 2),
            "net_cashflow_usd": counted(theirs, "net", market, 2), "transactions": counted(theirs, "transactions", market),
            "new_trials": counted(theirs, "new_trials", market)}}
    return out, stored


def ads_family_weeks(store: Path, as_of: dt.date, notes: list) -> tuple:
    """(week start -> the ads family, stored), from the closed weeks of Apple Ads results stored per campaign."""
    rows, stored = latest_rows(store, "ads.csv", ("week_start", "campaign_id"), ("spend_usd", "impressions", "taps", "installs"),
                               as_of, notes)
    by = (("market", "market"), ("campaign", "campaign_id"))
    out = {}
    for week, theirs in by_closed_week(rows, as_of).items():
        out[week] = {"source": "apple-ads", "fetched_at": max(r["captured"] for r in theirs).isoformat(), "figures": {
            "spend_usd": counted(theirs, "spend_usd", by, 2), "impressions": counted(theirs, "impressions", by),
            "taps": counted(theirs, "taps", by), "installs": counted(theirs, "installs", by),
            "ttr": divided(theirs, "taps", "impressions", by), "cpi_usd": divided(theirs, "spend_usd", "installs", by)}}
    return out, stored


def in_app_weeks(store: Path, as_of: dt.date, notes: list) -> tuple:
    """(week start -> the in_app family, stored), from whatever the app's own telemetry stored for closed weeks. The
    family is open: its keys are `<section>.<metric>` as the collector named them."""
    rows, stored = latest_rows(store, "telemetry.csv", ("week_start", "section", "metric"), ("numerator", "denominator"), as_of, notes)
    out = {}
    for week, theirs in by_closed_week(rows, as_of).items():
        figures = {}
        for r in theirs:
            key = f"{r['section']}.{r['metric']}"
            if not OPEN_KEY.match(key) or r["numerator"] is None:
                notes.append(f"metrics/telemetry.csv: {key!r} of {week} is not a readable figure; left out")
            elif r["denominator"] is None:
                figures[key] = {"value": r["numerator"]}
            elif share(r["numerator"], r["denominator"]) is None:
                figures[key] = unavailable("no_data", "Nothing to divide by: the week's total is zero.")
            else:
                figures[key] = {"value": share(r["numerator"], r["denominator"]), "numerator": r["numerator"],
                                "denominator": r["denominator"]}
        if figures:
            out[week] = {"source": "bigquery", "fetched_at": max(r["captured"] for r in theirs).isoformat(), "figures": figures}
    return out, stored
