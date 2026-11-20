"""Store -> the dashboard data files. Offline and clockless: the store and `as_of` decide every byte.

Nothing here computes a figure of its own. Hypothesis states, rank movement and the priority order come from the
same functions the ledger report prints, so the page and the report cannot disagree.
"""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

from aso.dashboard.contract import ENTITIES, SCHEMA, canonical, load_catalog, validate
from aso.dashboard.series import ranks_until, unavailable
from aso.dashboard.export_weeks import (NOTHING_THAT_WEEK, NOT_STORED_YET, ads_family_weeks, funnel_weeks, in_app_weeks,
                                        lifecycle_weeks, money_weeks)
from aso.dashboard.clean import identifiers, mask, whole
from aso.dashboard.state import ours, state_md
from aso.dashboard.export_snapshots import (chart_snapshots, insight_snapshots, rank_snapshots, ratings_snapshots, subscription_snapshots)
from aso.ledger_state import hypothesis_states, priority
from aso.ranks import brand_hit, loose_index, movers, resolve_key, series, zero_result_keys
from aso.store import (PROBLEMS, demand_lookup, parse_date, problem, read_brand_tokens, read_csv, read_hypotheses, read_markets)

POSITION_MARK = {"beyond-depth": "b", "error": "e", "no-results": "z"}
QUEUE_HEADING = re.compile(r"^###\s+(Q\d+)\s+·\s+\S+\s+(\d{4}-\d{2}-\d{2})\s+·\s+(.+?)\s*$")


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
        ranked = s["basket"] is not None and s["age_days"] is not None       # live on the day exported, and measured by rank
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
    return {**header(as_of), "releases": releases(store, as_of), "queue": queue(store, as_of)}


VERDICT_NOTE = ("hypothesis files carry no history: a verdict is read as it stands in the file today, "
                "whatever --as-of says")


def period_file(as_of: dt.date, kind: str, start: dt.date, end: dt.date, families: dict) -> dict:
    return {**header(as_of), "period": {"kind": kind, "id": start.isoformat(), "start": start.isoformat(),
                                        "end": end.isoformat()}, "families": families}


def releases(store: Path, as_of: dt.date) -> list:
    """Versions with the day each went live, earliest first; a version appears once."""
    first = {}
    for r in read_csv(store / "metrics" / "releases.csv"):
        day = parse_date(r.get("state_date"))
        if r.get("state") == "live" and r.get("version") and day is not None and day <= as_of:
            first[r["version"]] = min(day, first.get(r["version"], day))
    return [{"version": version, "date": day.isoformat()} for version, day in sorted(first.items(), key=lambda kv: (kv[1], kv[0]))]


def build_all(store: Path, as_of: dt.date) -> tuple:
    """(relative path under data/ -> object, notes). The notes say what the store could not show and why."""
    PROBLEMS.clear()
    notes, files = [], {}
    funnel = funnel_weeks(store, as_of, notes)
    money, money_stored = money_weeks(store, as_of, notes)
    ads, ads_stored = ads_family_weeks(store, as_of, notes)
    in_app, in_app_stored = in_app_weeks(store, as_of, notes)
    known = {"store_funnel": (funnel, True), "lifecycle": lifecycle_weeks(store, as_of, notes), "money": (money, money_stored),
             "ads": (ads, ads_stored), "in_app": (in_app, in_app_stored)}
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
    for source in (insight_snapshots(store, as_of, notes), subscription_snapshots(store, as_of, notes),
                   ratings_snapshots(store, as_of, notes), chart_snapshots(store, as_of, notes)):
        for day, families in source.items():
            snapshots.setdefault(day, {}).update(families)
    for day, families in sorted(snapshots.items()):
        files[f"snapshot/{day}.json"] = period_file(as_of, "snapshot", day, day, families)
    files["hypotheses.json"] = hypotheses(store, as_of)
    files["keys.json"] = keys(store, as_of)
    files["events.json"] = events(store, as_of)
    # A person types an account id into a confound or a queue title. It is not carried into data/: the page may be
    # published, and the clean check would refuse the file. The store's own file is left as it was written.
    wanted = [(label, whole(value)) for label, value in identifiers(store).items()]
    for path in sorted(files):
        met = set()
        files[path] = mask(files[path], wanted, met)
        if met:
            notes.append(f"{path}: masked the store's {', '.join(sorted(met))} where a text held it")
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
    state, text = store / "STATE.md", state_md(files, dt.date.fromisoformat(files["events.json"]["as_of"]))
    if not ours(state):
        done["state"] = "KEPT STATE.md: written by hand, archive it first"
    elif state.is_file() and state.read_text(encoding="utf-8") == text:
        done["state"] = "SAME STATE.md"
    else:
        state.write_text(text, encoding="utf-8")
        done["state"] = "WROTE STATE.md"
    return done


def check(store: Path, files: dict) -> list:
    """Paths that differ from a fresh export: changed, missing, or present and no longer produced."""
    data = store / "data"
    differ = [path for path, obj in files.items()
              if not (data / path).is_file() or (data / path).read_text(encoding="utf-8") != canonical(obj)]
    state = store / "STATE.md"       # a generated STATE.md is part of what the export owns; a hand-written one is not
    if state.is_file() and ours(state) and state.read_text(encoding="utf-8") != state_md(files, dt.date.fromisoformat(files["events.json"]["as_of"])):
        differ.append("STATE.md")
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
    print(done["state"])
    for note in notes:
        print(f"NOTE {note}")
    print(f"PASS export ({len(done['written'])} written, {len(done['unchanged'])} unchanged, {len(done['removed'])} removed)")
    return 0
