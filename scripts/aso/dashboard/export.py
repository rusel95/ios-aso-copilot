"""Store -> the dashboard data files. Offline and clockless: the store and `as_of` decide every byte.

Nothing here computes a figure of its own. Hypothesis states, rank movement and the priority order come from the
same functions the ledger report prints, so the page and the report cannot disagree.
"""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

from aso.dashboard.contract import SCHEMA
from aso.ledger_state import hypothesis_states, priority
from aso.ranks import brand_hit, loose_index, movers, resolve_key, series, zero_result_keys
from aso.store import (demand_lookup, hyp_markets, parse_date, problem, read_brand_tokens, read_hypotheses, read_markets,
                       read_ranks)

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


def reads_in_window(queries: list, markets: list, live: dt.date, end: dt.date, rows: list) -> int:
    """Sweep dates inside the window that read at least one key of the basket: a position, or beyond depth."""
    tracked = {(r["market"], r["keyword"]) for r in rows}
    index = loose_index(tracked)
    basket = {resolve_key(tracked, index, market, query.lower()) for market in markets for query in queries}
    return len({r["date"] for r in rows
                if (r["market"], r["keyword"]) in basket and r["status"] in ("ok", "beyond-depth")
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
            "reads_in_window": reads_in_window(queries, s["markets"], s["live"], min(end, as_of), rows) if ranked else None,
            "basket": s["basket"],
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
