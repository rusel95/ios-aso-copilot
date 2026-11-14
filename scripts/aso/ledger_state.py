"""The ledger as data: where every hypothesis stands on a given day, and what to do next by money at stake."""
from __future__ import annotations

import datetime as dt
import re

from aso.ranks import band, brand_hit, demand_label, is_dominant, loose_index, movement, resolve_key
from aso.store import hyp_markets, parse_date

DEFAULT_WINDOW = 21


def window_days(h: dict) -> int:
    found = re.match(r"\s*(\d+)", h.get("window_days") or "")
    return int(found.group(1)) if found else DEFAULT_WINDOW


def basket_queries(h: dict) -> list:
    return [q.strip().lower() for q in (h.get("queries") or "").split(";") if q.strip()]


def reads_due(hyps: list, rows: list, as_of) -> list:
    """The reads a live rank hypothesis needs to be judged on: one entry per storefront and day, for each of the
    last three days of its window that is on or before `as_of` and on which no sweep read a key of its basket.
    A failed request is not a read. A judged, unshipped, funnel or channel hypothesis asks for none."""
    tracked = {(r["market"], r["keyword"]) for r in rows}
    index = loose_index(tracked)
    read = {(r["date"], r["market"], r["keyword"]) for r in rows if r["status"] in ("ok", "beyond-depth")}
    out = []
    for h in hyps:
        live = parse_date(h.get("went_live"))
        if (not live or (h.get("verdict") or "").strip() or (h.get("primary_signal") or "").strip() == "funnel"
                or (h.get("id") or "").startswith("C")):
            continue
        queries, end = basket_queries(h), live + dt.timedelta(days=window_days(h))
        if not queries:                  # an incomplete record: there is nothing a sweep could read for it
            continue
        for market in hyp_markets(h):
            keys = {resolve_key(tracked, index, market, query) for query in queries} - {None}
            for back in (2, 1, 0):
                day = end - dt.timedelta(days=back)
                if day <= as_of and not any((day.isoformat(), *key) in read for key in keys):
                    out.append({"id": h["id"], "market": market, "queries": queries, "day": day.isoformat()})
    return out


def hypothesis_states(hyps: list, pairs: dict, empty, as_of) -> list:
    """One dict per hypothesis: its state on `as_of` and how its own query basket moved.

    Only the hypothesis's own declared basket is counted. Counting every key in the storefront would put a
    number next to the hypothesis that has nothing to do with it, and a number there is read as its effect.
    """
    tracked = {key for key in pairs if isinstance(key, tuple) and len(key) == 2} | set(empty)
    index = loose_index(tracked)
    out = []
    for h in hyps:
        live, verdict = parse_date(h.get("went_live")), (h.get("verdict") or "").strip()
        markets = hyp_markets(h)
        window = window_days(h)
        age = (as_of - live).days if live else None
        if verdict:
            state = "judged"
        elif not live:
            state = "not-shipped"
        else:
            state = "due" if age >= window else "open"
        signal = "funnel" if (h.get("primary_signal") or "").strip() == "funnel" else "rank"
        queries = basket_queries(h)
        basket, reason = None, None
        if signal == "funnel":
            reason = "funnel"              # a funnel hypothesis is not measured by rank; no basket is correct
        elif not markets:
            reason = "no-markets"
        elif not queries:
            reason = "no-queries"
        else:
            up = down = flat = unpaired = unmeasurable = 0
            for market in markets:
                for query in queries:
                    key = resolve_key(tracked, index, market, query)
                    obs = pairs.get(key)
                    if key in empty:
                        unmeasurable += 1
                    elif not obs:
                        unpaired += 1
                    else:
                        _, delta = movement(obs[0], obs[-1])
                        if delta is None:
                            unpaired += 1
                        else:
                            up, down, flat = up + (delta > 0), down + (delta < 0), flat + (delta == 0)
            basket = {"up": up, "down": down, "flat": flat, "unpaired": unpaired, "unmeasurable": unmeasurable}
        out.append({"id": h.get("id", "?"), "markets": markets, "signal": signal, "live": live, "window": window,
                    "verdict": verdict, "state": state, "age_days": age, "basket": basket, "basket_reason": reason})
    return out


def priority(pairs: dict, markets: dict, hyps: list, brand: list, demand) -> list:
    """Untaken keys ordered by net proceeds per subscriber x unclaimed gain x reach. An order, never a forecast.

    A key in a verified top-3 (top-5 in a large storefront) is defended, not attacked, so it is absent; so is a
    brand key, a key in a storefront with no price record, and a key whose last look was a failed request.
    """
    open_markets = {m for h in hyps if not (h.get("verdict") or "").strip() for m in hyp_markets(h)}
    shown = bool(demand and demand[1])     # a store that never ran the radar has no demand to show
    rows = []
    for (market, keyword), obs in pairs.items():
        if any(brand_hit(token, keyword) for token in brand):
            continue
        proceeds = markets.get(market)
        if proceeds is None or obs[-1]["status"] == "error":
            continue
        position = obs[-1]["position"]
        if is_dominant(market, position):
            continue
        name, gain, reach = band(position)
        if gain <= 0:
            continue
        rows.append({"score": round(proceeds * gain * reach, 2), "market": market, "keyword": keyword,
                     "position": position, "band": name, "proceeds": proceeds, "gain": gain, "reach": reach,
                     "status": "open hypothesis, not yet dominant" if market in open_markets else "UNCLAIMED",
                     "demand": demand_label(demand, market, keyword) if shown else None})
    rows.sort(key=lambda r: (r["score"], r["market"], r["keyword"]), reverse=True)
    return rows
