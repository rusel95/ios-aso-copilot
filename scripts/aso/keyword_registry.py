"""The keyword registry: every keyword the store knows, once, with where it came from.

One logical row per (market, query) in `keywords/registry.csv`. The file is append-only like every series: a row is added
when a key is new or a value of it changed, and a reader takes the latest row of each key. It is built from the store's
own files and from what the network commands record with `add`. Nothing here asks the network or the clock: the caller
passes the day.

A brand key is never tracked: `Pool.see`, the one door every source goes through, turns it away, and `build` drops
a brand row an older file still holds (the one time the file is rewritten). A term a network command found that starts
with `=`, `+`, `-` or `@` is turned away too: a spreadsheet would run it as a formula.
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
# What `add` takes: only what a network command finds. The other kinds mean "read from a file", and `sources` only grows.
NETWORK_SOURCES = ("autocomplete-hints", "google-suggest", "competitor-harvest")
FORMULA_START = ("=", "+", "-", "@")   # a cell that starts so is a formula to Excel, Numbers and Sheets
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
    is not a hit for `tidepool`. Both sides are NFC, as `Pool.see` reads a key."""
    keyword = unicodedata.normalize("NFC", keyword or "")
    return any(brand_hit(unicodedata.normalize("NFC", t), keyword) for t in tokens)


def _formula(text) -> bool:
    """A term a spreadsheet would run as a formula: it starts with `=`, `+`, `-` or `@`."""
    return " ".join((text or "").split()).startswith(FORMULA_START)


def _names(items) -> str:
    """The first eight terms of (market, keyword) pairs, for a line a person reads."""
    names = [k for _, k in items]
    return ", ".join(names[:8]) + (" ..." if len(names) > 8 else "")


def record_note(done: dict, count: int, source: str, market: str) -> str:
    """The line `--record` reports: what was recorded, and every term turned away, by name."""
    parts = [f"Recorded {count} {source} keyword(s) for {market} in {REGISTRY}: appended {done['appended']} rows"]
    if done["refused"]:
        parts.append(f"refused {len(done['refused'])} brand keyword(s), never tracked: {_names(done['refused'])}")
    if done["unsafe"]:
        parts.append(f"refused {len(done['unsafe'])} term(s) starting with = + - or @ (a spreadsheet would run them as a "
                     f"formula): {_names(done['unsafe'])}")
    if not done["brand_tokens"]:
        parts.append("NOTE config.md names no **Brand tokens**, so no brand keyword was refused")
    return "; ".join(parts)


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
        with path.open(encoding="utf-8-sig", newline="") as fh:        # a spreadsheet's "CSV UTF-8" starts with a BOM
            return list(csv.DictReader(fh, delimiter="\t" if path.suffix == ".tsv" else ","))
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        problem(rel, f"cannot be read as a table ({exc}); its keywords are NOT in the registry")
        return []


def _lines(path: Path, rel: str) -> list:
    try:
        return path.read_text(encoding="utf-8-sig").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        problem(rel, f"cannot be read as text ({exc}); its keywords are NOT in the registry")
        return []


def _tracking(pool: Pool, store: Path, skipped: list) -> None:
    """keywords/tracking-<market>[-flat].txt: one query a line, `##` heads name the group, `#` lines are comments."""
    for path in sorted((store / "keywords").glob("tracking-*.txt")):
        found = TRACKING.match(path.name)
        if not found or found.group(1) not in STOREFRONTS:
            skipped.append((f"keywords/{path.name}", "its name does not give a storefront"))
            continue
        group = ""
        for line in _lines(path, f"keywords/{path.name}"):
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
            rows = [{"text": s} for s in (line.strip() for line in _lines(path, rel)) if s and not s.startswith("#")]
        else:
            rows = _table(path, rel)
        if rows and not {"text", "suggestion"} & set(rows[0]):
            skipped.append((rel, "has no `text` or `suggestion` column; its keywords are NOT in the registry"))
            continue
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
    and the days only grow. A brand key is refused, and an older file's brand keys are dropped; a found term that starts
    with `=`, `+`, `-` or `@` is refused. Returns {appended, keys, new, read, skipped, dropped, refused, unsafe,
    brand_tokens}."""
    store, as_of = Path(store), str(as_of)
    if not store.is_dir():
        raise ValueError(f"store not found: {store}")                  # never create a store by recording into it
    brand = read_brand_tokens(store)
    if not brand:
        problem("config.md", "names no **Brand tokens**, so no brand key is refused and the registry may hold brand keys")
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
        for market in hyp_markets(h):
            if market not in STOREFRONTS:
                if queries:
                    skipped.append((f"hypotheses/{h['id']}", f"market {market!r} is not a storefront, {len(queries)} queries not placed"))
                continue
            for query in queries:
                pool.see(market, query, "hypothesis-basket", hypothesis=h["id"])
    unsafe = []
    for market, keyword, source in found:
        if _formula(keyword):
            unsafe.append((market, keyword))
        else:
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
            "dropped": dropped, "refused": sorted(pool.refused), "unsafe": unsafe, "brand_tokens": len(brand)}


def add(store: Path, market: str, keywords, source: str, as_of) -> dict:
    """Record what a network command found: `keywords` for `market`, from `source`, seen on `as_of`."""
    if source not in NETWORK_SOURCES:
        raise ValueError(f"{source!r} is not something a network command finds; add records {', '.join(NETWORK_SOURCES)}")
    market = (market or "").strip().lower()
    if market not in STOREFRONTS:
        raise ValueError(f"{market!r} is not an App Store storefront code")
    done = build(store, as_of, [(market, k, source) for k in keywords])
    brand = read_brand_tokens(Path(store))
    return {**done, "refused": [(market, k) for k in keywords if not _formula(k) and is_brand(brand, k)]}   # the terms handed in, not the store's own brand keys


def twins(rows: list) -> list:
    """[(market, [spellings])] of keys that are one query to a person and two to Apple: same loose form (the rank
    ledger's `key_of`: U+2019 read as U+0027), different exact form. Never merged in the file."""
    groups = {}
    for r in rows:
        groups.setdefault(key_of(r["market"], r["keyword"]), {})[r["key_norm"]] = r["keyword"]
    return sorted((market, [by[k] for k in sorted(by)]) for (market, _), by in groups.items() if len(by) > 1)


def summary(rows: list, limit: int = 10) -> dict:
    """What `show` prints. Counts are an inventory and keep the excluded rows (shown apart); the candidates and the
    overlaps, which feed decisions, leave them out; a candidate is also not on a tracking list already."""
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
        if r["tracked"] != "yes" and "tracking-file" not in sources:      # a key on a tracking list is chosen, only unswept
            m["candidates"] += 1
            candidates.append((len(sources), r))
    candidates.sort(key=lambda c: (-c[0], c[1]["market"], c[1]["key_norm"]))
    return {"keys": len(rows), "excluded": dict(excluded), "by_market": dict(sorted(by_market.items())),
            "by_source": dict(sorted(by_source.items())),
            "candidates": [{"market": r["market"], "keyword": r["keyword"], "sources": r["sources"].split(";"),
                            "popularity": r["popularity"]} for _, r in candidates[:limit]],
            "overlaps": [{"sources": list(p), "keys": n} for p, n in sorted(pairs.items(), key=lambda x: (-x[1], x[0]))[:limit]],
            "twins": [{"market": m, "keywords": k} for m, k in twins(rows)]}
