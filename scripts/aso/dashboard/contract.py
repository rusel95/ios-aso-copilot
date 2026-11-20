"""The dashboard data contract, `aso-copilot/dashboard-data@1`: canonical bytes, and the check every data file
passes before the page may read it.

A period file holds figures grouped by family. A flow is summed over one closed Monday week (`week/<monday>.json`);
a stock is read at a moment (`snapshot/<date>.json`). Static facts about a figure (title, unit, definition) live once,
in the catalog; a data file holds only what changes. A figure that could not be measured carries a code and a
reason, never a zero.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import re
from pathlib import Path

SCHEMA = "aso-copilot/dashboard-data@1"
CODES = ("no_source", "no_data", "not_configured", "unreachable")
ENTITIES = ("hypotheses.json", "keys.json", "events.json")
CATALOG = Path(__file__).resolve().parents[3] / "assets" / "dashboard" / "catalog.json"
OPEN_KEY = re.compile(r"^[a-z0-9_]+(\.[a-z0-9_]+)+$")     # an open family's keys: <section>.<metric>


def canonical(obj) -> str:
    """The one way a data file is written: same object, same bytes."""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=1) + "\n"


def load_catalog() -> dict:
    return json.loads(CATALOG.read_text(encoding="utf-8"))


def as_date(value):
    try:
        return dt.date.fromisoformat(value) if isinstance(value, str) and len(value) == 10 else None
    except ValueError:
        return None


def is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def validate(rel_path: str, text: str, catalog: dict) -> list:
    """Problems of one data file, as sentences; an empty list means the page may read it."""
    try:
        obj = json.loads(text)
    except ValueError as exc:
        return [f"not JSON: {exc}"]
    if not isinstance(obj, dict):
        return ["not a JSON object"]
    problems = []
    if text != canonical(obj):
        problems.append("not in canonical form (sorted keys, one-space indent, one trailing newline)")
    if obj.get("schema") != SCHEMA:
        problems.append(f"schema is {obj.get('schema')!r}, expected {SCHEMA!r}")
    if as_date(obj.get("as_of")) is None:
        problems.append("as_of is not a date")
    folder, _, name = rel_path.rpartition("/")
    if rel_path in ENTITIES:
        return problems + ENTITY_CHECKS[rel_path](obj)
    if folder in ("week", "snapshot") and name.endswith(".json"):
        return problems + check_period(folder, name[:-5], obj, catalog)
    return problems + [f"not a dashboard data file: expected week/<monday>.json, snapshot/<date>.json "
                       f"or one of {', '.join(ENTITIES)}"]


def check_period(kind: str, stem: str, obj: dict, catalog: dict) -> list:
    problems = []
    extra = sorted(set(obj) ^ {"schema", "as_of", "period", "families"})
    if extra:
        problems.append(f"top-level keys must be schema, as_of, period, families; differs by {', '.join(extra)}")
    period = obj.get("period") if isinstance(obj.get("period"), dict) else {}
    start, end = as_date(period.get("start")), as_date(period.get("end"))
    if period.get("kind") != kind or period.get("id") != stem:
        problems.append(f"path does not agree with the period: the file is {kind}/{stem}.json, the period says "
                        f"{period.get('kind')}/{period.get('id')}")
    if start is None or end is None or period.get("start") != period.get("id"):
        problems.append("period.start must be a date equal to period.id, and period.end a date")
    elif kind == "week":
        if start.weekday() != 0:
            problems.append(f"a week starts on a Monday; {start} is not one")
        if end != start + dt.timedelta(days=6):
            problems.append("a week's end must be six days after its start")
    elif end != start:
        problems.append("a snapshot's end must equal its start")
    families = obj.get("families")
    if not isinstance(families, dict):
        return problems + ["families must be an object"]
    for name, family in families.items():
        spec = catalog["families"].get(name)
        if spec is None:
            problems.append(f"unknown family {name}")
        elif spec["kind"] != kind:
            problems.append(f"family {name} is a {spec['kind']} family, found in a {kind} file")
        elif not isinstance(family, dict):
            problems.append(f"family {name} must be an object")
        else:
            problems += check_family(name, family, spec)
    return problems


def check_family(name: str, family: dict, spec: dict) -> list:
    if "unavailable" in family:
        extra = sorted(set(family) - {"unavailable"})
        return ([f"family {name} is unavailable and must carry nothing else; found {', '.join(extra)}"] if extra else []) \
            + check_unavailable(f"family {name}", family["unavailable"])
    problems = []
    lists = spec.get("rows") or {}
    extra = sorted(set(family) - {"source", "fetched_at", "measured", "figures"} - set(lists))
    if extra:
        problems.append(f"family {name} has unexpected keys: {', '.join(extra)}")
    if not isinstance(family.get("source"), str) or not family.get("source"):
        problems.append(f"family {name} must name its source")
    if as_date(family.get("fetched_at")) is None:
        problems.append(f"family {name} must say the day it was fetched (fetched_at)")
    if "measured" in family:
        measured = family["measured"] if isinstance(family["measured"], dict) else {}
        if set(measured) != {"start", "end"} or None in (as_date(measured.get("start")), as_date(measured.get("end"))):
            problems.append(f"family {name}: measured must be a start and an end date")
    if "figures" not in family and not any(key in family for key in lists):
        problems.append(f"family {name} holds neither figures nor rows")
    figures = family.get("figures", {})
    if not isinstance(figures, dict):
        return problems + [f"family {name}: figures must be an object"]
    for key, figure in figures.items():
        label = f"{name}.{key}"
        if key not in spec["figures"] and not (spec.get("open") and OPEN_KEY.match(key)):
            problems.append(f"unknown figure {label}")
        elif not isinstance(figure, dict):
            problems.append(f"figure {label} must be an object")
        else:
            problems += check_figure(label, figure, by_campaign=(name == "ads"))
    for list_name, columns in lists.items():
        if list_name in family:
            problems += check_rows(f"{name}.{list_name}", family[list_name], columns)
    return problems


def check_figure(label: str, figure: dict, by_campaign: bool) -> list:
    has_value, missing = "value" in figure, "unavailable" in figure
    if has_value == missing:
        return [f"figure {label} must hold a value or an unavailable, exactly one"]
    if missing:
        extra = sorted(set(figure) - {"unavailable"})
        return ([f"figure {label} is unavailable and must carry nothing else"] if extra else []) \
            + check_unavailable(f"figure {label}", figure["unavailable"])
    problems = []
    allowed = {"value", "numerator", "denominator", "by_market"} | ({"by_campaign"} if by_campaign else set())
    extra = sorted(set(figure) - allowed)
    if extra:
        problems.append(f"figure {label} has unexpected keys: {', '.join(extra)}")
    for key in ("value", "numerator", "denominator"):
        if key in figure and not is_number(figure[key]):
            problems.append(f"figure {label}: {key} must be a number, found {figure[key]!r}")
    for key in ("by_market", "by_campaign"):
        split = figure.get(key, {})
        if not isinstance(split, dict) or not all(isinstance(k, str) and (v is None or is_number(v))
                                                  for k, v in split.items()):
            problems.append(f"figure {label}: {key} must map a name to a number or null")
    return problems


def check_unavailable(label: str, unavailable) -> list:
    if not isinstance(unavailable, dict) or set(unavailable) != {"code", "reason"}:
        return [f"{label}: unavailable must be a code and a reason"]
    problems = []
    if unavailable["code"] not in CODES:
        problems.append(f"{label}: unknown code {unavailable['code']!r}; the codes are {', '.join(CODES)}")
    if not isinstance(unavailable["reason"], str) or not unavailable["reason"].strip():
        problems.append(f"{label}: a missing figure needs a reason in words")
    return problems


def check_rows(label: str, rows, columns: list) -> list:
    if not isinstance(rows, list):
        return [f"{label} must be a list"]
    for n, row in enumerate(rows):
        if not isinstance(row, dict) or set(row) != set(columns):
            return [f"{label}[{n}] must hold exactly the columns {', '.join(columns)}"]
        if not all(v is None or isinstance(v, str) or is_number(v) for v in row.values()):
            return [f"{label}[{n}] holds a value that is neither text, a number nor null"]
    return []


STATES = ("judged", "due", "open", "not-shipped")
HYPOTHESIS_KEYS = {"id", "kind", "title", "markets", "queries", "status", "verdict", "signal", "went_live", "window_days",
                   "window_end", "state", "age_days", "days_past_window", "reads_in_window", "basket", "basket_keys",
                   "prediction", "kill_criterion", "confounds"}
BASKET_KEYS = {"up", "down", "flat", "unpaired", "unmeasurable"}
KEY_KEYS = {"market", "keyword", "group", "brand", "positions", "movement", "priority"}


def check_top(obj: dict, keys: set) -> list:
    extra = sorted(set(obj) ^ ({"schema", "as_of"} | keys))
    return [f"top-level keys must be schema, as_of, {', '.join(sorted(keys))}; differs by {', '.join(extra)}"] if extra else []


def check_hypotheses(obj: dict) -> list:
    problems = check_top(obj, {"hypotheses"})
    for n, h in enumerate(obj.get("hypotheses") if isinstance(obj.get("hypotheses"), list) else []):
        label = f"hypotheses[{n}]"
        if not isinstance(h, dict) or set(h) != HYPOTHESIS_KEYS:
            problems.append(f"{label} must hold exactly: {', '.join(sorted(HYPOTHESIS_KEYS))}")
            continue
        if h["kind"] not in ("H", "C") or h["state"] not in STATES:
            problems.append(f"{label}: kind must be H or C and state one of {', '.join(STATES)}")
        if h["basket"] is not None and (not isinstance(h["basket"], dict) or set(h["basket"]) != BASKET_KEYS):
            problems.append(f"{label}: basket must be null or hold {', '.join(sorted(BASKET_KEYS))}")
        if any(h[k] is not None and as_date(h[k]) is None for k in ("went_live", "window_end")):
            problems.append(f"{label}: went_live and window_end must be dates or null")
        if not all(isinstance(h[k], list) for k in ("markets", "queries", "confounds", "basket_keys")):
            problems.append(f"{label}: markets, queries, confounds and basket_keys must be lists")
        elif not all(isinstance(k, list) and len(k) == 2 for k in h["basket_keys"]):
            problems.append(f"{label}: a basket key is a market and a keyword")
    return problems


def check_keys(obj: dict) -> list:
    problems = check_top(obj, {"dates", "keys"})
    dates = obj.get("dates") if isinstance(obj.get("dates"), list) else []
    if any(as_date(d) is None for d in dates) or dates != sorted(set(dates)):
        problems.append("dates must be distinct dates in order")
    for n, k in enumerate(obj.get("keys") if isinstance(obj.get("keys"), list) else []):
        label = f"keys[{n}]"
        if not isinstance(k, dict) or set(k) != KEY_KEYS:
            problems.append(f"{label} must hold exactly: {', '.join(sorted(KEY_KEYS))}")
            continue
        positions = k["positions"]
        if not isinstance(positions, list) or len(positions) != len(dates):
            problems.append(f"{label}: positions must line up with dates, one entry per date")
        elif not all(p is None or p in ("b", "e", "z") or (isinstance(p, int) and not isinstance(p, bool) and p >= 1)
                     for p in positions):
            problems.append(f"{label}: a position is a rank, b (beyond depth), e (error), z (no results) or null")
        if not isinstance(k["brand"], bool):
            problems.append(f"{label}: brand must be true or false")
    return problems


def check_events(obj: dict) -> list:
    problems = check_top(obj, {"releases", "queue"})
    for name, keys in (("releases", {"version", "date"}), ("queue", {"id", "date", "title"})):
        for n, item in enumerate(obj.get(name) if isinstance(obj.get(name), list) else []):
            if not isinstance(item, dict) or set(item) != keys or as_date(item.get("date")) is None:
                problems.append(f"{name}[{n}] must hold {', '.join(sorted(keys))}, with a real date")
    return problems


ENTITY_CHECKS = {"hypotheses.json": check_hypotheses, "keys.json": check_keys, "events.json": check_events}
