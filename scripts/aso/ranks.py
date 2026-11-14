"""Pure rank logic: what one observation means, how two compare, and the bands of one sweep."""
from __future__ import annotations

import unicodedata

from aso.store import norm

# Section C model. Two declared factors, both printed with every row, neither measured by this
# toolkit: `gain` is how much of the top-3 position is still unclaimed, `reach` is how close the
# current position is to being moved at all. A key we already rank #8 for is a far cheaper target
# than one we are nowhere for, even though the second has more theoretical headroom — without the
# second factor this section degenerates into "every keyword you don't rank for, sorted by price".
BANDS = [(3, "top3", 0.00, 1.00), (10, "top10", 0.45, 1.00), (30, "top30", 0.80, 0.70),
         (200, "deep", 0.95, 0.35)]
BEYOND = ("beyond-depth", 1.00, 0.10)


def band(pos):
    """-> (name, gain, reach)"""
    if pos is None:
        return BEYOND
    for limit, name, gain, reach in BANDS:
        if pos <= limit:
            return name, gain, reach
    return BEYOND


def brand_hit(token: str, keyword: str) -> bool:
    """A brand token is a whole word. `pixel` is the app's name; `pixelator` is a generic query that merely
    contains it, and a substring test once dropped hundreds of tracked pairs from section C."""
    token, keyword = token.casefold(), keyword.casefold()
    at = keyword.find(token)
    while at != -1:
        before, after = keyword[at - 1:at], keyword[at + len(token):at + len(token) + 1]
        if not (before.isascii() and before.isalnum()) and not (after.isascii() and after.isalnum()):
            return True
        at = keyword.find(token, at + 1)
    return False


def key_of(market: str, keyword: str) -> tuple:
    """A key's loose form: storefront and text compared without case, spacing, the form of a composed letter, or
    which apostrophe a keyboard typed. Two tracked keys can share one loose form and still be two queries to the
    store, which ranks U+2019 and U+0027 apart; so this is never the join itself. `resolve_key` is."""
    text = norm(unicodedata.normalize("NFC", keyword or "")).replace("\u2019", "'")
    return (market or "").strip().lower(), text


def loose_index(keys) -> dict:
    """loose form -> the tracked keys that share it."""
    index = {}
    for key in keys:
        index.setdefault(key_of(*key), set()).add(key)
    return index


def resolve_key(keys, index: dict, market: str, query: str):
    """The tracked key a hypothesis query names, or None. The exact spelling when it is tracked; otherwise the one
    key with the same loose form. When two keys share that form the query names neither: guessing would put one
    query's movement under another's name."""
    if (market, query) in keys:
        return market, query
    same = index.get(key_of(market, query), ())
    return next(iter(same)) if len(same) == 1 else None


def zero_result_keys(rows):
    """Keys whose LATEST non-error reading is an empty result list: unmeasurable right now, including the
    older rows that recorded the same empty answer as "beyond-depth" before `no-results` existed. A key
    that later starts returning results (and so a real beyond-depth or a position) is measurable again;
    one transient empty answer does not erase its history."""
    last = {}
    for i, r in sorted(enumerate(rows), key=lambda ir: (ir[1]["date"], ir[0])):
        if r["status"] != "error":
            last[(r["market"], r["keyword"])] = r["status"]
    return {key for key, status in last.items() if status == "no-results"}


def series(rows):
    """(market, keyword) -> observations sorted by date, failed requests dropped.

    A failed request is kept in the CSV as a record of what was attempted, but it is not an
    observation: leaving it in the series would let one outage block a key's delta forever.
    """
    out = {}
    empty = zero_result_keys(rows)
    for r in rows:
        if r["status"] in ("error", "no-results") or (r["market"], r["keyword"]) in empty:
            continue
        out.setdefault((r["market"], r["keyword"]), []).append(r)
    for key in out:
        out[key].sort(key=lambda r: r["date"])
    return {k: v for k, v in out.items() if v}


def movement(first, last):
    """Return (label, delta) — a censored pair never becomes a numeric delta.

    A key seen once is not "flat": comparing a row with itself yields delta 0, which reads as
    "measured twice, did not move" when the truth is "measured once". That is the same substitution
    of absence-of-evidence for evidence-of-absence the rest of this file exists to refuse.
    """
    if first["date"] == last["date"]:
        return "only one observation date", None
    if first["provider"] != last["provider"]:
        return f"incomparable provider ({first['provider']} vs {last['provider']})", None
    if not (first["legacy"] or last["legacy"]) and first["depth"] != last["depth"]:
        return f"incomparable depth ({first['depth']} vs {last['depth']})", None

    a, b = first["position"], last["position"]
    if a is None and b is None:
        return "never observed within depth", None
    if a is None:
        return "ENTERED (was beyond depth)", None
    if b is None:
        return "EXITED (now beyond depth)", None
    label = "improved" if b < a else "regressed" if b > a else "flat"
    # Rows predating the depth/status columns pair with each other, but the pair cannot be verified
    # comparable — it carries that caveat rather than being silently promoted or silently dropped.
    return (label + (" · legacy, depth not recorded" if first["legacy"] else "")), a - b


# A market counts as genuinely dominant only at true top-3 for a small storefront or true top-5 for
# a large one — not merely "an open hypothesis exists there." Before this fix, "covered by an open
# hypothesis" meant only that the market appeared in some hypothesis's `markets:` field, so a
# position like #11 (no), #26 (se), or #6 in a market too small to call top-3 (il) all read as
# "covered" even though none of them are anywhere near dominant. An open hypothesis in progress does
# not mean the position is defended; only the position itself does. `LARGE_MARKET_DOMINANCE_THRESHOLD`
# markets get the more forgiving top-5 bar because a large storefront's result page shows more
# competing apps before the fold; every other market uses top-3.
LARGE_MARKETS = {"us", "gb", "de", "fr", "jp", "cn"}


def is_dominant(market: str, pos) -> bool:
    """True only if `pos` is a real top-3 (small market) or top-5 (large market) position.
    `None` (beyond depth) is never dominant."""
    if pos is None:
        return False
    threshold = 5 if market in LARGE_MARKETS else 3
    return pos <= threshold


def band_of(pos):
    """top10 / top30 / top100 / top200 / out (None = not found within the queried depth)."""
    if pos is None:
        return "out"
    return "t10" if pos <= 10 else "t30" if pos <= 30 else "t100" if pos <= 100 else "t200"


def demand_label(demand, market: str, keyword: str) -> str:
    """One cell for a tracked key: `head 55`, `below 44` (unlisted: unknown, not zero), `no data`, or `—` (never pulled)."""
    heads, cuts = demand
    market = market.lower()
    if (market, norm(keyword)) in heads:
        return f"head {heads[(market, norm(keyword))][0]}"
    if market not in cuts:
        return "—"
    return f"below {cuts[market][0]}" if cuts[market][0] is not None else "no data"


BAND_NAMES = {"t10": "top10", "t30": "top30", "t100": "top100", "t200": "top200"}
COUNTS = ("keys_read", "top10", "top30", "top100", "top200", "beyond", "no_results", "errors")


def sweep_bands(rows: list, brand: list, date: str) -> dict:
    """How the tracked non-brand keys stood on one sweep date. The bands do not overlap: top30 is 11 to 30.

    `keys_read` counts the keys that got an answer that day (a position or "beyond depth"); `tracked_keys`
    counts every key the store had asked about by then, so the two together say how much of the basket a
    sweep covered. A retry on the same date is a later row for the same key, and the later row is the answer.
    """
    def tracked_here(r):
        return not any(brand_hit(token, r["keyword"]) for token in brand)

    latest, tracked = {}, {}
    for r in rows:
        if not tracked_here(r):
            continue
        if r["date"] <= date:
            tracked.setdefault(r["market"], set()).add(r["keyword"])
        if r["date"] == date:
            latest[(r["market"], r["keyword"])] = r
    total = dict.fromkeys(COUNTS, 0)
    by_market = {m: {"tracked_keys": len(keys), **dict.fromkeys(COUNTS, 0)} for m, keys in sorted(tracked.items())}
    for (market, _), r in latest.items():
        if r["status"] == "ok" and r["position"] is not None:
            names = ("keys_read", BAND_NAMES[band_of(r["position"])])
        elif r["status"] == "beyond-depth":
            names = ("keys_read", "beyond")
        elif r["status"] == "no-results":
            names = ("no_results",)
        elif r["status"] == "error":
            names = ("errors",)
        else:
            continue                       # a legacy row with no status and no position observed nothing
        for name in names:
            total[name] += 1
            by_market[market][name] += 1
    return {"tracked_keys": sum(len(keys) for keys in tracked.values()), **total, "by_market": by_market}


def movers(pairs: dict, brand: list) -> list:
    """First observation against the latest, per non-brand key: numeric moves first, largest gain on top, then the
    pairs that cannot be a number (entered, exited, never seen, incomparable) in the store's order."""
    numeric, censored = [], []
    for (market, keyword), obs in pairs.items():
        if any(brand_hit(token, keyword) for token in brand):
            continue
        label, delta = movement(obs[0], obs[-1])
        row = {"market": market, "keyword": keyword, "first_date": obs[0]["date"], "first": obs[0]["position"],
               "last_date": obs[-1]["date"], "last": obs[-1]["position"], "delta": delta, "label": label}
        (numeric if delta is not None else censored).append(row)
    numeric.sort(key=lambda r: (-r["delta"], r["market"]))
    return numeric + censored


def coverage(rows: list) -> dict:
    """How much of the ledger can be compared at all. A thin report is thin because of these numbers."""
    pairs, attempted = series(rows), {(r["market"], r["keyword"]) for r in rows}
    return {"tracked": len(attempted),
            "paired": sum(movement(obs[0], obs[-1])[1] is not None for obs in pairs.values()),
            "unobserved": len(attempted) - len(pairs),
            "failed": sum(r["status"] == "error" for r in rows),
            "unmeasurable": len(zero_result_keys(rows)),
            "observations": len(rows)}
