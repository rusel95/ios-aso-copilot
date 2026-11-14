"""Store -> the dashboard data files. Offline and clockless: the store and `as_of` decide every byte.

Nothing here computes a figure of its own. Hypothesis states, rank movement and the priority order come from the
same functions the ledger report prints, so the page and the report cannot disagree.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

from aso.dashboard.contract import ENTITIES, OPEN_KEY, SCHEMA, canonical, is_number, load_catalog, validate
from aso.dashboard.weeks import closed
from aso.ledger_state import hypothesis_states, priority
from aso.ranks import brand_hit, coverage, loose_index, movers, resolve_key, series, sweep_bands, zero_result_keys
from aso.store import (PROBLEMS, demand_lookup, parse_date, problem, read_brand_tokens, read_csv, read_hypotheses,
                       read_markets, read_ranks)

POSITION_MARK = {"beyond-depth": "b", "error": "e", "no-results": "z"}
QUEUE_HEADING = re.compile(r"^###\s+(Q\d+)\s+·\s+\S+\s+(\d{4}-\d{2}-\d{2})\s+·\s+(.+?)\s*$")


def ranks_until(store: Path, as_of: dt.date) -> list:
    """Rank observations dated on or before `as_of`, in the order the store holds them."""
    return [r for r in read_ranks(store) if (r.get("date") or "") <= as_of.isoformat()]


def header(as_of: dt.date) -> dict:
    return {"schema": SCHEMA, "as_of": as_of.isoformat()}


# ------------------------------------------------------------------ hypotheses.json
def list_field(path: Path, name: str) -> list:
    """A frontmatter field written as a YAML list, item by item. The ledger reader joins the lines of a field into
    one string, which is right for prose and loses where one list item ends."""
    items, inside = [], False
    for line in path.read_text(encoding="utf-8").splitlines()[1:]:
        if line.strip() == "---":
            break
        field = re.match(r"^([a-z_]+):\s*(.*)$", line)
        if field:
            inside = field.group(1) == name
            inline = field.group(2).strip()
            if inside and inline and inline != "[]":
                items.append(inline)
        elif inside and line.strip().startswith("- "):
            items.append(line.strip()[2:].strip())
    return [item.strip("\"'") for item in items]


def basket_of(queries: list, markets: list, rows: list) -> list:
    """The tracked keys a hypothesis's queries name, each resolved as the ledger resolves it. A query that names no
    tracked key is absent: the page draws what was read, and resolves nothing itself."""
    tracked = {(r["market"], r["keyword"]) for r in rows}
    index = loose_index(tracked)
    found = {resolve_key(tracked, index, market, query.lower()) for market in markets for query in queries}
    return sorted(key for key in found if key is not None)


def reads_in_window(basket: list, live: dt.date, end: dt.date, rows: list) -> int:
    """Sweep dates inside the window that read at least one key of the basket: a position, or beyond depth."""
    keys = set(basket)
    return len({r["date"] for r in rows
                if (r["market"], r["keyword"]) in keys and r["status"] in ("ok", "beyond-depth")
                and live.isoformat() <= r["date"] <= end.isoformat()})


def hypotheses(store: Path, as_of: dt.date) -> dict:
    hyps = read_hypotheses(store, kinds=("H", "C"))
    rows = ranks_until(store, as_of)
    states = hypothesis_states(hyps, series(rows), zero_result_keys(rows), as_of)
    out = []
    for h, s in zip(hyps, states):
        channel = s["id"].startswith("C")
        end = s["live"] + dt.timedelta(days=s["window"]) if s["live"] else None
        queries = [q.strip() for q in (h.get("queries") or "").split(";") if q.strip()]
        basket = basket_of(queries, s["markets"], rows) if s["basket"] is not None else []
        ranked = s["basket"] is not None and s["live"] is not None
        out.append({
            "id": s["id"],
            "kind": "C" if channel else "H",
            "title": re.sub(r"^[A-Z]\d+-", "", Path(h["_path"]).stem).replace("-", " "),
            "markets": s["markets"],
            "queries": queries,
            "status": (h.get("status") or "").strip() or None,
            "verdict": s["verdict"] or None,
            "signal": "channel" if channel else s["signal"],
            "went_live": s["live"].isoformat() if s["live"] else None,
            "window_days": s["window"],
            "window_end": end.isoformat() if end else None,
            "state": s["state"],
            "age_days": s["age_days"],
            "days_past_window": (as_of - end).days if s["state"] == "due" else None,
            "reads_in_window": reads_in_window(basket, s["live"], min(end, as_of), rows) if ranked else None,
            "basket": s["basket"],
            "basket_keys": [list(key) for key in basket],
            "prediction": (h.get("prediction") or "").strip() or None,
            "kill_criterion": (h.get("kill_criterion") or "").strip() or None,
            "confounds": list_field(store / "hypotheses" / h["_path"], "confounds"),
        })
    return {**header(as_of), "hypotheses": sorted(out, key=lambda h: h["id"])}


# ------------------------------------------------------------------ keys.json
def keys(store: Path, as_of: dt.date) -> dict:
    rows = ranks_until(store, as_of)
    dates = sorted({r["date"] for r in rows})
    at = {date: n for n, date in enumerate(dates)}
    brand = read_brand_tokens(store)
    pairs = series(rows)
    moved = {(m["market"], m["keyword"]): m for m in movers(pairs, [])}
    wanted = priority(pairs, read_markets(store), read_hypotheses(store), brand, demand_lookup(store, as_of))
    targets = {(p["market"], p["keyword"]): p for p in wanted}
    found = {}
    for r in rows:                                         # a later row for the same key and day is the correction
        key = (r["market"], r["keyword"])
        entry = found.setdefault(key, {"group": "", "positions": [None] * len(dates)})
        entry["group"] = r.get("group") or ""
        entry["positions"][at[r["date"]]] = r["position"] if r["status"] == "ok" else POSITION_MARK.get(r["status"])
    out = []
    for (market, keyword), entry in sorted(found.items()):
        move, target = moved.get((market, keyword)), targets.get((market, keyword))
        out.append({
            "market": market,
            "keyword": keyword,
            "group": entry["group"],
            "brand": any(brand_hit(token, keyword) for token in brand),
            "positions": entry["positions"],
            "movement": {k: move[k] for k in ("first_date", "first", "last_date", "last", "delta", "label")} if move else None,
            "priority": {k: target[k] for k in ("score", "position", "band", "proceeds", "gain", "reach", "status",
                                                 "demand")} if target else None,
        })
    return {**header(as_of), "dates": dates, "keys": out}


# ------------------------------------------------------------------ events.json
def queue(store: Path, as_of: dt.date) -> list:
    path = store / "queue.md"
    if not path.is_file():
        return []
    out = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.startswith("### "):
            continue
        heading = QUEUE_HEADING.match(line)
        if not heading or parse_date(heading.group(2)) is None:
            problem(f"queue.md:{n}", f"heading `{line.strip()}` is not `### Q<n> · <word> <date> · <title>`; left out")
        elif heading.group(2) <= as_of.isoformat():
            out.append({"id": heading.group(1), "date": heading.group(2), "title": heading.group(3)})
    return out


def events(store: Path, as_of: dt.date) -> dict:
    return {**header(as_of), "releases": [], "queue": queue(store, as_of)}


# ------------------------------------------------------------------ period files
COLLECTOR_ROWS = "live:asc analytics daily"       # how pull_funnel.py tags the weeks it folds from the daily reports
FUNNEL_COLUMNS = {"impressions": "impressions", "page_views": "product_page_views", "first_downloads": "downloads"}
FUNNEL_RATIOS = {"view_rate": ("page_views", "impressions"), "page_cvr": ("first_downloads", "page_views"),
                 "impression_cvr": ("first_downloads", "impressions")}
NOT_STORED_YET = {
    "lifecycle": "No command stores install and deletion counts by week yet.",
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
VERDICT_NOTE = ("hypothesis files carry no history: a verdict is read as it stands in the file today, "
                "whatever --as-of says")


def unavailable(code: str, reason: str) -> dict:
    return {"unavailable": {"code": code, "reason": reason}}


def share(numerator, denominator):
    """A ratio to six places, or None when there is nothing to divide by."""
    return round(numerator / denominator, 6) if numerator is not None and denominator else None


def period_file(as_of: dt.date, kind: str, start: dt.date, end: dt.date, families: dict) -> dict:
    return {**header(as_of), "period": {"kind": kind, "id": start.isoformat(), "start": start.isoformat(),
                                        "end": end.isoformat()}, "families": families}


def funnel_weeks(store: Path, as_of: dt.date, notes: list) -> dict:
    """week start -> the store_funnel family, from the closed Monday weeks the collector wrote.

    A row a person typed, a week still open, and a row recorded after `as_of` are left out and counted. Among
    rows for the same week and segment the latest `recorded` wins, then the later line: a correction is a new row.
    """
    chosen, left = {}, {"hand": 0, "open": 0, "later": 0}
    for n, r in enumerate(read_csv(store / "metrics" / "weekly.csv"), 2):
        week, recorded = parse_date(r.get("week_start")), parse_date(r.get("recorded"))
        if not (r.get("source") or "").startswith(COLLECTOR_ROWS) or week is None or week.weekday() or recorded is None:
            left["hand"] += 1
        elif recorded > as_of:
            left["later"] += 1
        elif not closed(week, as_of):
            left["open"] += 1
        else:
            counts = {}
            for key, column in FUNNEL_COLUMNS.items():
                cell = (r.get(column) or "").strip()
                try:
                    counts[key] = int(cell) if cell else None
                except ValueError:
                    notes.append(f"metrics/weekly.csv:{n}: {column} {cell!r} is not a number; the row is skipped")
                    counts = None
                    break
            key = (week, (r.get("segment") or "").strip().lower())
            if counts is not None and (key not in chosen or recorded >= chosen[key]["recorded"]):
                chosen[key] = {"recorded": recorded, **counts}
    if any(left.values()):
        notes.append(f"metrics/weekly.csv: {sum(left.values())} rows left out ({left['hand']} not written by the collector "
                     f"as Monday weeks, {left['open']} of weeks still open on {as_of}, {left['later']} recorded after {as_of})")
    weeks = {}
    for (week, segment), row in chosen.items():
        weeks.setdefault(week, {})[segment] = row
    out = {}
    for week, segments in sorted(weeks.items()):
        total = segments.get("all")
        markets = {s: row for s, row in sorted(segments.items()) if len(s) == 2 and s.isalpha()}
        figures = {}
        for key in FUNNEL_COLUMNS:
            if total is None or total[key] is None:
                figures[key] = unavailable("no_data", "The report holds no total for the week.")
            else:
                figures[key] = {"value": total[key], **({"by_market": {m: row[key] for m, row in markets.items()}}
                                                        if markets else {})}
        for key, (top, bottom) in FUNNEL_RATIOS.items():
            value = share(total[top], total[bottom]) if total else None
            if value is None:
                figures[key] = unavailable("no_data", "Nothing to divide by: a total of the week is missing or zero.")
            else:
                figures[key] = {"value": value, "numerator": total[top], "denominator": total[bottom],
                                **({"by_market": {m: share(row[top], row[bottom]) for m, row in markets.items()}}
                                   if markets else {})}
        out[week] = {"source": "asc-analytics", "fetched_at": max(row["recorded"] for row in segments.values()).isoformat(),
                     "figures": figures}
    return out


def number(cell: str):
    """A stored cell as a number: an int when it is one, else a float; None for a blank. Raises ValueError otherwise."""
    cell = (cell or "").strip()
    if not cell:
        return None
    value = float(cell)
    return int(value) if value.is_integer() and "." not in cell else value


def latest_rows(store: Path, name: str, key: tuple, numbers: tuple, as_of: dt.date, notes: list) -> tuple:
    """(rows, stored): the latest row per key of one series file, as known on `as_of`, numbers parsed.

    Rows captured after `as_of` are not known yet. Among rows for one key the later `captured` wins, then the later
    line. A row with an unreadable cell is named and skipped. `stored` says whether the file holds any row at all,
    which is the difference between "nothing stores this" and "nothing that week"."""
    found, stored = {}, False
    for n, r in enumerate(read_csv(store / "metrics" / name), 2):
        stored = True
        captured = parse_date(r.get("captured"))
        if captured is None:
            notes.append(f"metrics/{name}:{n}: captured is not a date; the row is skipped")
            continue
        if captured > as_of:
            continue
        row = dict(r, captured=captured)
        try:
            for column in numbers:
                row[column] = number(r.get(column))
        except ValueError:
            notes.append(f"metrics/{name}:{n}: {column} {r.get(column)!r} is not a number; the row is skipped")
            continue
        at = tuple(r.get(k, "") for k in key)
        if at not in found or captured >= found[at]["captured"]:
            found[at] = row
    return list(found.values()), stored


def total(rows: list, column: str, places=None):
    """The sum of a column over rows that hold it; None when none does."""
    held = [r[column] for r in rows if r[column] is not None]
    if not held:
        return None
    return round(sum(held), places) if places is not None else sum(held)


def split(rows: list, by: str, value) -> dict:
    """{who: value(their rows)} for one figure, names in order."""
    groups = {}
    for r in rows:
        groups.setdefault(r[by].lower(), []).append(r)
    return {who: value(theirs) for who, theirs in sorted(groups.items())}


def counted(rows: list, column: str, by: tuple, places=None) -> dict:
    """A summed figure with its splits, or unavailable when no row holds the column."""
    value = total(rows, column, places)
    if value is None:
        return unavailable("no_data", "The stored rows hold no such count for the week.")
    return {"value": value, **{f"by_{name}": split(rows, column_of, lambda theirs: total(theirs, column, places))
                              for name, column_of in by}}


def divided(rows: list, top: str, bottom: str, by: tuple) -> dict:
    """A ratio of two summed columns, with both totals and its splits; unavailable when there is nothing to divide by."""
    upper, lower = total(rows, top), total(rows, bottom)
    if share(upper, lower) is None:
        return unavailable("no_data", "Nothing to divide by: a total of the week is missing or zero.")
    return {"value": share(upper, lower), "numerator": upper, "denominator": lower,
            **{f"by_{name}": split(rows, column_of, lambda theirs: share(total(theirs, top), total(theirs, bottom)))
               for name, column_of in by}}


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


def by_closed_week(rows: list, as_of: dt.date) -> dict:
    """week start -> rows, for the rows whose `week_start` is a Monday of a week closed by `as_of`."""
    weeks = {}
    for r in rows:
        week = parse_date(r.get("week_start"))
        if week is not None and not week.weekday() and closed(week, as_of):
            weeks.setdefault(week, []).append(r)
    return dict(sorted(weeks.items()))


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


def build_all(store: Path, as_of: dt.date) -> tuple:
    """(relative path under data/ -> object, notes). The notes say what the store could not show and why."""
    PROBLEMS.clear()
    notes, files = [], {}
    funnel = funnel_weeks(store, as_of, notes)
    money, money_stored = money_weeks(store, as_of, notes)
    ads, ads_stored = ads_family_weeks(store, as_of, notes)
    in_app, in_app_stored = in_app_weeks(store, as_of, notes)
    known = {"store_funnel": (funnel, True), "lifecycle": ({}, False), "money": (money, money_stored), "ads": (ads, ads_stored),
             "in_app": (in_app, in_app_stored)}
    for week in sorted({w for weeks, _ in known.values() for w in weeks}):
        families = {}
        for name, (weeks, stored) in known.items():
            if week in weeks:
                families[name] = weeks[week]
            elif stored:
                families[name] = unavailable("no_data", NOTHING_THAT_WEEK[name])
            else:
                families[name] = unavailable("no_source", NOT_STORED_YET[name])
        files[f"week/{week}.json"] = period_file(as_of, "week", week, week + dt.timedelta(days=6), families)
    snapshots = {}
    for day, families in rank_snapshots(store, as_of).items():
        snapshots.setdefault(parse_date(day), {}).update(families)
    for source in (insight_snapshots(store, as_of, notes), subscription_snapshots(store, as_of, notes)):
        for day, families in source.items():
            snapshots.setdefault(day, {}).update(families)
    for day, families in sorted(snapshots.items()):
        files[f"snapshot/{day}.json"] = period_file(as_of, "snapshot", day, day, families)
    files["hypotheses.json"] = hypotheses(store, as_of)
    files["keys.json"] = keys(store, as_of)
    files["events.json"] = events(store, as_of)
    notes += [f"{where}: {why}" for where, why in dict.fromkeys(PROBLEMS)]
    notes.append(VERDICT_NOTE)
    return files, notes


# ------------------------------------------------------------------ the data folder
def data_files(store: Path) -> list:
    """Relative paths of what a data folder holds that this export owns; anything else in it is left alone."""
    data = store / "data"
    found = [f"{kind}/{p.name}" for kind in ("week", "snapshot") for p in sorted((data / kind).glob("*.json"))]
    return found + [name for name in ENTITIES if (data / name).is_file()]


def write(store: Path, files: dict) -> dict:
    data, done = store / "data", {"written": [], "unchanged": [], "removed": []}
    for path, obj in sorted(files.items()):
        target, text = data / path, canonical(obj)
        if target.is_file() and target.read_text(encoding="utf-8") == text:
            done["unchanged"].append(path)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
            done["written"].append(path)
    for path in data_files(store):
        if path not in files:
            (data / path).unlink()
            done["removed"].append(path)
    return done


def check(store: Path, files: dict) -> list:
    """Paths that differ from a fresh export: changed, missing, or present and no longer produced."""
    data = store / "data"
    differ = [path for path, obj in files.items()
              if not (data / path).is_file() or (data / path).read_text(encoding="utf-8") != canonical(obj)]
    return sorted(set(differ) | (set(data_files(store)) - set(files)))


def run(store: Path, as_of: dt.date, check_only: bool = False) -> int:
    """The export command: build, refuse to write what breaks the contract, then write or compare."""
    files, notes = build_all(store, as_of)
    catalog = load_catalog()
    broken = [(path, found) for path, obj in sorted(files.items()) for found in validate(path, canonical(obj), catalog)]
    for path, found in broken:
        print(f"INVALID {path}: {found}")
    if broken:
        print("FAIL export: the data would break the contract; nothing written")
        return 1
    if check_only:
        differ = check(store, files)
        for note in notes:
            print(f"NOTE {note}")
        print(f"FAIL check: {', '.join(differ)}" if differ else f"PASS check ({len(files)} files)")
        return 1 if differ else 0
    done = write(store, files)
    for path in sorted(files):
        print(("WROTE " if path in done["written"] else "SAME ") + path)
    for path in done["removed"]:
        print(f"REMOVED {path}")
    for note in notes:
        print(f"NOTE {note}")
    print(f"PASS export ({len(done['written'])} written, {len(done['unchanged'])} unchanged, {len(done['removed'])} removed)")
    return 0
