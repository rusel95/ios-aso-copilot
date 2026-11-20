#!/usr/bin/env python3
"""Deterministic hypothesis + keyword ledger. Same store, same output, every run.

Three questions, in this order, before anything new is proposed:

  A. What happened to the hypotheses that are already live? (close them, or say why not)
  B. Which tracked keys moved, which regressed, which are still unobserved?
  C. Given per-market net proceeds, which untaken action is worth doing first?

What this does NOT do: invent a verdict, invent a rank, or print a revenue forecast.
Section C is a priority ORDER built from declared inputs, all printed inline — not a
cash projection (references/provenance.md, references/aso-loop.md).

    ledger.py --store PATH report
    ledger.py --store PATH ingest SNAPSHOT.json --date 2026-09-08 --depth 200
    ledger.py --self-check
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
# The logic lives in scripts/aso/. The names below stay importable from here for the scripts that always
# imported them from this file.
from aso.ledger_ingest import DEFAULT_DELAY, draft, ingest, refresh  # noqa: E402
from aso.ledger_report import bands, report  # noqa: E402,F401
from aso.ranks import brand_hit  # noqa: E402,F401
from aso.store import PROBLEMS, print_problems  # noqa: E402


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", nargs="?", choices=["report", "ingest", "draft", "refresh", "bands"], default="report")
    p.add_argument("snapshot", nargs="?")
    p.add_argument("--store", type=Path)
    p.add_argument("--as-of", type=dt.date.fromisoformat,
                   help="evaluation date for report/draft (YYYY-MM-DD); fixes time-dependent ledger state")
    p.add_argument("--date", default=str(dt.date.today()))
    p.add_argument("--delay", type=float,
                   help="seconds between Search API requests (minimum 3.0; default 3.0)")
    p.add_argument("--source", default="itunes-search-api")
    p.add_argument("--depth", type=int)
    p.add_argument("--group", default="target")
    p.add_argument("--limit", type=int, default=25)
    p.add_argument("--market")
    p.add_argument("--queries", default="")
    p.add_argument("--window", type=int, default=21)
    p.add_argument("--out", type=Path)
    p.add_argument("--bundle")
    p.add_argument("--markets")
    p.add_argument("--failed-only", action="store_true")
    p.add_argument("--out-dir", type=Path)
    p.add_argument("--self-check", action="store_true")
    args = p.parse_args()
    if args.self_check:
        from aso.ledger_selfcheck import self_check
        return self_check()
    if args.as_of:
        if args.command not in ("report", "draft"):
            p.error("--as-of applies only to report and draft; ingest/refresh record observation dates")
    as_of = args.as_of or dt.date.today()
    if not args.store or not args.store.exists():
        p.error("--store must point at the app repo's marketing/ directory")
    PROBLEMS.clear()
    if args.command == "ingest":
        if not args.snapshot:
            p.error("ingest needs a snapshot JSON path")
        done = ingest(args.store, Path(args.snapshot), args.date, args.source, args.depth, args.group)
        print_problems(sys.stderr)
        return done
    if args.command == "refresh":
        if not args.bundle:
            p.error("refresh needs --bundle (the app's exact bundle id)")
        done = refresh(args.store, args.bundle,
                       [m.strip().lower() for m in (args.markets or "").split(",") if m.strip()],
                       args.failed_only, DEFAULT_DELAY if args.delay is None else args.delay,
                       args.out_dir or args.store / "reports" / "snapshots")
        print_problems(sys.stderr)
        return done
    if args.command == "bands":
        bands(args.store)
        print_problems(sys.stderr)
        return 0
    if args.command == "draft":
        if not args.market:
            p.error("draft needs --market and --queries")
        done = draft(args.store, args.market, args.queries.split(";"), args.window, args.out, as_of)
        print_problems(sys.stderr)
        return done
    report(args.store, args.limit, as_of)


if __name__ == "__main__":
    main()
