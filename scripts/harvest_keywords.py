#!/usr/bin/env python3
"""Keyword candidate discovery: App Store autocomplete hints + competitor discovery.

Both sources are free, public, and need no API key (research.md §4, §6; verified again against the
live endpoints on 2026-08-19 while this script was written). Every candidate is emitted with a
`live:` provenance tag (references/provenance.md) — this script never guesses.

Usage:
    harvest_keywords.py hints --storefront us --term compress
    harvest_keywords.py competitors --country us --seeds "compress photos,compress videos"
    harvest_keywords.py --self-check
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import timezone, datetime

# US/GB/DE/UA — the four markets this skill tracks weekly (marketing/README.md).
# Values are the storefront header Apple expects; confirmed live 2026-08-19.
STOREFRONTS = {
    "us": "143441-1,29",
    "gb": "143444-1,29",
    "de": "143443-1,29",
    "ua": "143492-1,29",
}

HINTS_URL = "https://search.itunes.apple.com/WebObjects/MZSearchHints.woa/wa/hints"
SEARCH_URL = "https://itunes.apple.com/search"
USER_AGENT = "iTunes/12.0 (Macintosh)"


class ShapeChanged(RuntimeError):
    """Apple's response didn't look like what we expect. Fail loudly, never return []."""


def _get(url: str, headers: dict[str, str] | None = None, timeout: float = 10.0) -> bytes:
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — fixed Apple hosts only
        return resp.read()


def fetch_hints(term: str, storefront: str) -> list[str]:
    """Popularity-ordered autocomplete suggestions for `term` in `storefront` (a market code)."""
    if storefront not in STOREFRONTS:
        raise ValueError(f"unknown storefront {storefront!r}; known: {sorted(STOREFRONTS)}")
    url = f"{HINTS_URL}?clientApplication=Software&term={urllib.parse.quote(term)}"
    headers = {
        "X-Apple-Store-Front": STOREFRONTS[storefront],
        "User-Agent": USER_AGENT,
    }
    try:
        body = _get(url, headers)
    except urllib.error.URLError as exc:
        raise ShapeChanged(f"MZSearchHints request failed for {term!r}/{storefront!r}: {exc}") from exc
    return parse_hints(body)


def parse_hints(body: bytes) -> list[str]:
    """Parse the plist XML `hints` response into an ordered list of suggestion strings.

    Raises ShapeChanged rather than returning [] if the document doesn't have the <hints><dict>
    <key>term</key><string>...</string> shape we've verified — an empty *parsed* result is a
    legitimate "no suggestions for this prefix", but a document that doesn't parse into that shape
    at all means Apple changed the response format, and silently returning [] would look identical
    to "no suggestions" while actually meaning "this script is broken".
    """
    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        raise ShapeChanged(f"MZSearchHints did not return parseable XML: {exc}") from exc

    hints_array = root.find("./dict/array")
    if hints_array is None:
        raise ShapeChanged("MZSearchHints XML has no dict/array — response shape changed")

    terms: list[str] = []
    for hint_dict in hints_array.findall("dict"):
        keys = [k.text for k in hint_dict.findall("key")]
        strings = [s.text for s in hint_dict.findall("string")]
        try:
            term_index = keys.index("term")
        except ValueError:
            raise ShapeChanged(f"hint entry has no <key>term</key>: keys={keys}") from None
        terms.append(strings[term_index])
    return terms


def fetch_competitors(seed_terms: list[str], country: str, limit: int = 25) -> list[tuple[str, int]]:
    """Rank apps by how many distinct seed terms surface them (research.md §6).

    Returns (app_name, seed_hit_count) sorted by hit count descending. This index is NOT the real
    App Store search index (research.md §4) — use it for competitor *discovery*, never as a rank
    claim.
    """
    hits: dict[str, int] = {}
    for term in seed_terms:
        url = (
            f"{SEARCH_URL}?term={urllib.parse.quote(term)}&country={country}"
            f"&entity=software&limit={limit}"
        )
        try:
            body = _get(url)
        except urllib.error.URLError as exc:
            raise ShapeChanged(f"iTunes Search API request failed for {term!r}: {exc}") from exc
        try:
            data = json.loads(body)
        except json.JSONDecodeError as exc:
            raise ShapeChanged(f"iTunes Search API did not return JSON: {exc}") from exc
        if "results" not in data:
            raise ShapeChanged(f"iTunes Search API response has no 'results' key: {list(data)}")
        seen_this_term: set[str] = set()
        for result in data["results"]:
            name = result.get("trackName")
            if name and name not in seen_this_term:
                hits[name] = hits.get(name, 0) + 1
                seen_this_term.add(name)
    return sorted(hits.items(), key=lambda kv: kv[1], reverse=True)


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def cmd_hints(args: argparse.Namespace) -> None:
    terms = fetch_hints(args.term, args.storefront)
    tag = f"live:MZSearchHints@{_today()}"
    for rank, term in enumerate(terms, start=1):
        print(f"{rank}\t{term}\t[{tag}]")


def cmd_competitors(args: argparse.Namespace) -> None:
    seeds = [s.strip() for s in args.seeds.split(",") if s.strip()]
    ranked = fetch_competitors(seeds, args.country)
    tag = f"live:itunes-search-api@{_today()}"
    for name, count in ranked:
        print(f"{count}\t{name}\t[{tag}]")


def self_check() -> None:
    # 1. Live call against a known-populated storefront/term returns popularity-ordered suggestions.
    terms = fetch_hints("phot", "us")
    assert terms, "expected non-empty hints for a known-good term/storefront"
    assert all(isinstance(t, str) and t for t in terms), "every hint must be a non-empty string"

    # 2. A malformed/unexpected document fails loudly rather than degrading to [].
    for bad_body in (b"not xml at all", b"<plist><dict></dict></plist>"):
        try:
            parse_hints(bad_body)
        except ShapeChanged:
            pass
        else:
            raise AssertionError(f"expected ShapeChanged for malformed body: {bad_body!r}")

    # 3. Unknown storefront is rejected before any network call.
    try:
        fetch_hints("x", "fr")
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for an untracked storefront code")

    print(f"OK — {len(terms)} hints for 'phot'/us; shape-change and bad-storefront guards hold")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--self-check", action="store_true", help="run the built-in self-check and exit")
    sub = parser.add_subparsers(dest="command")

    hints_p = sub.add_parser("hints", help="autocomplete suggestions for one term/storefront")
    hints_p.add_argument("--term", required=True)
    hints_p.add_argument("--storefront", required=True, choices=sorted(STOREFRONTS))
    hints_p.set_defaults(func=cmd_hints)

    comp_p = sub.add_parser("competitors", help="rank apps by seed-term overlap")
    comp_p.add_argument("--seeds", required=True, help="comma-separated seed terms")
    comp_p.add_argument("--country", required=True, choices=sorted(STOREFRONTS))
    comp_p.set_defaults(func=cmd_competitors)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.self_check:
        self_check()
        return 0

    if not getattr(args, "func", None):
        parser.print_help()
        return 1

    try:
        args.func(args)
    except ShapeChanged as exc:
        print(f"ERROR — Apple's response shape changed: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
