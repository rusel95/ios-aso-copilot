"""The keyword registry: every keyword the store knows, once, with where it came from.

One logical row per (market, query) in `keywords/registry.csv`. The file is append-only like every series: a row is added
when a key is new or a value of it changed, and a reader takes the latest row of each key. It is built from the store's
own files and from what the network commands record with `add`. Nothing here asks the network or the clock: the caller
passes the day.

A brand key is never tracked: `Pool.see`, the one door every source goes through, turns it away, and `build` drops
a brand row an older file still holds (the one time the file is rewritten).
"""
from __future__ import annotations

import csv
import itertools
import os
import re
import unicodedata
from collections import Counter
from pathlib import Path

from storefronts import STOREFRONTS

from aso.ranks import brand_hit, demand_label, key_of
from aso.store import (append_changed, demand_lookup, hyp_markets, norm, problem, read_brand_tokens, read_csv,
                       read_hypotheses, read_ranks)

REGISTRY = "keywords/registry.csv"
COLUMNS = ["market", "keyword", "key_norm", "first_seen", "last_seen", "sources", "tracked", "popularity",
           "position", "status", "rank_date", "hypotheses", "excluded", "captured"]
KEY = ("market", "key_norm")
# Where a keyword was found. Closed, like references/provenance.md: a new kind is added here and in state-store.md.
SOURCES = ("ranks", "tracking-file", "ads-keyword", "ads-search-term", "autocomplete-hints", "google-suggest",
           "competitor-harvest", "hypothesis-basket", "popularity-head")
OWN_GROUPS = ("own", "title")          # the store's own tags for the app's metadata words (ranks `group`, tracking `##`)
# What `keywords filter` and the Apple Ads work leave under ads/: only reviewed or live keywords, and Apple's own hints.
ADS_FILES = {"accepted.csv", "keywords.txt", "reviewed_live.csv", "market_specific_observed.csv", "native_seeds.tsv"}
ADS_EVIDENCE = {"search_term": "ads-search-term", "suggestion": "autocomplete-hints"}
TRACKING = re.compile(r"^tracking-([a-z]{2})(?:-flat)?\.txt$")
FOLDER = re.compile(r"^([a-z]{2})(?:_|$)")           # `de_reviewed`, `il_h076`, `se`; not `nordic_h077`


def key_norm(text) -> str:
    """The identity of a query: NFC, case-folded, one space between words. The apostrophe stays as typed, because Apple
    ranks U+0027 and U+2019 apart; `twins` compares them, at read time, with the rank ledger's loose form."""
    return norm(unicodedata.normalize("NFC", text or ""))


def is_brand(tokens, keyword) -> bool:
    """A brand key: a whole-word hit of any `**Brand tokens**` token (`aso.ranks.brand_hit`), so `tidepoolish`
    is not a hit for `tidepool`."""
    return any(brand_hit(t, keyword or "") for t in tokens)


class Pool:
    """Everything one run saw, by key: the first spelling, the sources, the days it was dated, the hypotheses, own-ness.
    A brand key is refused here and listed in `refused`, whichever source brought it."""

    def __init__(self, brand=()):
        self.keys, self.brand, self.refused = {}, brand, set()

    def see(self, market, keyword, source, day="", hypothesis="", own=False):
        market = (market or "").strip().lower()
        spelling = " ".join(unicodedata.normalize("NFC", keyword or "").split())
        if not market or not spelling:
            return
        if is_brand(self.brand, spelling):
            self.refused.add((market, norm(spelling)))
            return
        seen = self.keys.setdefault((market, norm(spelling)), {"keyword": spelling, "sources": set(), "days": set(),
                                                               "hypotheses": set(), "own": False})
        seen["sources"].add(source)
        if day:
            seen["days"].add(day)
        if hypothesis:
            seen["hypotheses"].add(hypothesis)
        seen["own"] = seen["own"] or own


def _table(path: Path, rel: str) -> list:
    try:
        with path.open(encoding="utf-8", newline="") as fh:
            return list(csv.DictReader(fh, delimiter="\t" if path.suffix == ".tsv" else ","))
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        problem(rel, f"cannot be read as a table ({exc}); its keywords are NOT in the registry")
        return []


def _tracking(pool: Pool, store: Path, skipped: list) -> None:
    """keywords/tracking-<market>[-flat].txt: one query a line, `##` heads name the group, `#` lines are comments."""
    for path in sorted((store / "keywords").glob("tracking-*.txt")):
        found = TRACKING.match(path.name)
        if not found or found.group(1) not in STOREFRONTS:
            skipped.append((f"keywords/{path.name}", "its name does not give a storefront"))
            continue
        group = ""
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("##"):
                group = line.lstrip("#").split("(")[0].strip().lower()
            elif line and not line.startswith("#"):
                pool.see(found.group(1), line, "tracking-file", own=group in OWN_GROUPS)


def _ads(pool: Pool, store: Path, skipped: list) -> None:
    """The reviewed and live keywords under ads/, and Apple's autocomplete hints. The market is the row's own `market`
    column, else the first folder under ads/ that starts with a storefront code. What names none is reported."""
    root, lost = store / "ads", Counter()
    for path in sorted(p for p in root.rglob("*") if p.is_file() and (p.name in ADS_FILES or re.match(r"^hints.*\.tsv$", p.name))):
        rel = path.relative_to(store).as_posix()
        home = next((m.group(1) for part in path.relative_to(root).parts[:-1]
                     if (m := FOLDER.match(part)) and m.group(1) in STOREFRONTS), "")
        if path.suffix == ".txt":
            rows = [{"text": line.strip()} for line in path.read_text(encoding="utf-8").splitlines()
                    if line.strip() and not line.startswith("#")]
        else:
            rows = _table(path, rel)
        for row in rows:
            asked = (row.get("market") or "").strip().lower()
            market = asked or home
            if market not in STOREFRONTS:
                lost[(rel, market or "")] += 1
                continue
            text = row.get("suggestion") if "suggestion" in row else row.get("text")
            source = "autocomplete-hints" if "suggestion" in row else ADS_EVIDENCE.get((row.get("evidence") or "").strip(), "ads-keyword")
            pool.see(market, text, source)
    for (rel, market), n in sorted(lost.items()):
        skipped.append((rel, f"market {market!r} is not a storefront, {n} rows" if market
                        else f"no storefront named by its folders or a market column, {n} rows"))


def _latest_ranks(rows: list) -> dict:
    """(market, key_norm) -> the newest row that observed something, else the newest failed one. A later line wins a tie."""
    out = {}
    for r in sorted(rows, key=lambda r: r["date"]):
        key = ((r["market"] or "").strip().lower(), key_norm(r["keyword"]))
        if r["status"] != "error" or out.get(key, {"status": "error"})["status"] == "error":
            out[key] = r
    return out


def read_registry(store: Path) -> list:
    """The latest row of every key, in key order. A brand key is never one, even if an older file still holds it."""
    brand = read_brand_tokens(Path(store))
    latest = {(r["market"], r["key_norm"]): r for r in read_csv(Path(store) / REGISTRY) if not is_brand(brand, r["keyword"])}
    return [latest[k] for k in sorted(latest)]


def _drop_brand(path: Path, brand) -> int:
    """Remove the keys of an older registry that are brand keys, every row of them, and say how many keys went. The file
    is replaced whole or not at all."""
    rows = read_csv(path)
    gone = {(r["market"], r["key_norm"]) for r in rows if is_brand(brand, r["keyword"])}
    if gone:
        tmp = path.with_name(path.name + ".dropping")
        try:
            with tmp.open("w", encoding="utf-8", newline="") as fh:
                writer = csv.DictWriter(fh, fieldnames=COLUMNS, lineterminator="\n")
                writer.writeheader()
                writer.writerows(r for r in rows if (r["market"], r["key_norm"]) not in gone)
            os.replace(tmp, path)
        finally:
            tmp.unlink(missing_ok=True)
    return len(gone)


def build(store: Path, as_of, found=()) -> dict:
    """Fold every source of the store, and the sightings in `found` ((market, keyword, source) the network just
    returned, dated `as_of`), into the registry. Appends a row for a key that is new or whose values changed; `sources`
    and the days only grow. A brand key is refused, and an older file's brand keys are dropped. Returns {appended, keys,
    new, read, skipped, dropped, refused}."""
    store, as_of = Path(store), str(as_of)
    brand = read_brand_tokens(store)
    dropped = _drop_brand(store / REGISTRY, brand)
    held = {(r["market"], r["key_norm"]): r for r in read_registry(store)}
    ranks, pool, skipped = read_ranks(store), Pool(brand), []
    for r in ranks:
        pool.see(r["market"], r["keyword"], "ranks", r["date"], own=(r.get("group") or "").strip().lower() in OWN_GROUPS)
    _tracking(pool, store, skipped)
    _ads(pool, store, skipped)
    for r in read_csv(store / "metrics" / "popularity.csv"):
        pool.see(r.get("market"), r.get("term"), "popularity-head", r.get("captured") or "")
    for h in read_hypotheses(store):
        queries = [q.strip() for q in (h.get("queries") or "").split(";") if q.strip()]
        for market in (m for m in hyp_markets(h) if m in STOREFRONTS):
            for query in queries:
                pool.see(market, query, "hypothesis-basket", hypothesis=h["id"])
    for market, keyword, source in found:
        pool.see(market, keyword, source, as_of)

    latest, demand = _latest_ranks(ranks), demand_lookup(store)
    rows = []
    for key in sorted(set(pool.keys) | set(held)):
        seen, old = pool.keys.get(key, {}), held.get(key, {})
        keyword = old.get("keyword") or seen["keyword"]
        days = {d for d in (old.get("first_seen"), old.get("last_seen")) if d} | seen.get("days", set())
        first = min(days) if days else as_of                  # a key with no dated sighting is first held on the day it is added
        rank = latest.get(key)
        label = demand_label(demand, key[0], keyword)
        rows.append({
            "market": key[0], "keyword": keyword, "key_norm": key[1], "first_seen": first,
            "last_seen": max(days) if days else first,
            "sources": ";".join(sorted({s for s in old.get("sources", "").split(";") if s} | seen.get("sources", set()))),
            "tracked": "yes" if rank else "no", "popularity": "" if label == "—" else label,
            "position": str(rank["position"] or "") if rank else "", "status": rank["status"] if rank else "",
            "rank_date": rank["date"] if rank else "", "hypotheses": ";".join(sorted(seen.get("hypotheses", ()))),
            "excluded": "own-metadata" if seen.get("own") else "", "captured": as_of})
    appended = append_changed(store / REGISTRY, COLUMNS, rows, KEY)
    return {"appended": appended, "keys": len(rows), "new": len(set(pool.keys) - set(held)), "skipped": skipped,
            "read": dict(sorted(Counter(s for seen in pool.keys.values() for s in seen["sources"]).items())),
            "dropped": dropped, "refused": sorted(pool.refused)}


def add(store: Path, market: str, keywords, source: str, as_of) -> dict:
    """Record what a network command found: `keywords` for `market`, from `source`, seen on `as_of`."""
    if source not in SOURCES:
        raise ValueError(f"unknown source {source!r}; the registry knows {', '.join(SOURCES)}")
    market = (market or "").strip().lower()
    if market not in STOREFRONTS:
        raise ValueError(f"{market!r} is not an App Store storefront code")
    done = build(store, as_of, [(market, k, source) for k in keywords])
    brand = read_brand_tokens(Path(store))
    return {**done, "refused": [(market, k) for k in keywords if is_brand(brand, k)]}   # the terms handed in, not the store's own brand keys


def twins(rows: list) -> list:
    """[(market, [spellings])] of keys that are one query to a person and two to Apple: same loose form (the rank
    ledger's `key_of`: U+2019 read as U+0027), different exact form. Never merged in the file."""
    groups = {}
    for r in rows:
        groups.setdefault(key_of(r["market"], r["keyword"]), {})[r["key_norm"]] = r["keyword"]
    return sorted((market, [by[k] for k in sorted(by)]) for (market, _), by in groups.items() if len(by) > 1)


def summary(rows: list, limit: int = 10) -> dict:
    """What `show` prints. Counts are an inventory and keep the excluded rows (shown apart); the candidates and the
    overlaps, which feed decisions, leave them out."""
    by_market, by_source, excluded, pairs, candidates = {}, Counter(), Counter(), Counter(), []
    for r in rows:
        sources = [s for s in r["sources"].split(";") if s]
        m = by_market.setdefault(r["market"], {"keys": 0, "tracked": 0, "candidates": 0, "excluded": 0})
        m["keys"] += 1
        m["tracked"] += r["tracked"] == "yes"
        by_source.update(sources)
        if r["excluded"]:
            m["excluded"] += 1
            excluded[r["excluded"]] += 1
            continue
        pairs.update(itertools.combinations(sorted(sources), 2))
        if r["tracked"] != "yes":
            m["candidates"] += 1
            candidates.append((len(sources), r))
    candidates.sort(key=lambda c: (-c[0], c[1]["market"], c[1]["key_norm"]))
    return {"keys": len(rows), "excluded": dict(excluded), "by_market": dict(sorted(by_market.items())),
            "by_source": dict(sorted(by_source.items())),
            "candidates": [{"market": r["market"], "keyword": r["keyword"], "sources": r["sources"].split(";"),
                            "popularity": r["popularity"]} for _, r in candidates[:limit]],
            "overlaps": [{"sources": list(p), "keys": n} for p, n in sorted(pairs.items(), key=lambda x: (-x[1], x[0]))[:limit]],
            "twins": [{"market": m, "keywords": k} for m, k in twins(rows)]}
