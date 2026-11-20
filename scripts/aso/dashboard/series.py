"""Reading the store's series the way every family does: the latest row per key as known on a day, sums with
their splits, ratios with both totals, and the word for a figure that is missing."""
from __future__ import annotations

import datetime as dt
from pathlib import Path

from aso.dashboard.weeks import closed
from aso.store import parse_date, read_csv, read_ranks


def ranks_until(store: Path, as_of: dt.date) -> list:
    """Rank observations dated on or before `as_of`, in the order the store holds them."""
    return read_ranks(store, as_of)


def unavailable(code: str, reason: str) -> dict:
    return {"unavailable": {"code": code, "reason": reason}}


def share(numerator, denominator):
    """A ratio to six places, or None when there is nothing to divide by."""
    return round(numerator / denominator, 6) if numerator is not None and denominator else None


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


def by_closed_week(rows: list, as_of: dt.date) -> dict:
    """week start -> rows, for the rows whose `week_start` is a Monday of a week closed by `as_of`."""
    weeks = {}
    for r in rows:
        week = parse_date(r.get("week_start"))
        if week is not None and not week.weekday() and closed(week, as_of):
            weeks.setdefault(week, []).append(r)
    return dict(sorted(weeks.items()))
