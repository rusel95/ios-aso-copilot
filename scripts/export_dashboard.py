#!/usr/bin/env python3
"""Derive the dashboard data files from the marketing store. Offline; the store and --as-of decide every byte.

    export_dashboard.py --store PATH --as-of 2026-11-14            write PATH/data/
    export_dashboard.py --store PATH --as-of 2026-11-14 --check    write nothing; fail if PATH/data/ differs

It prints one line per file (WROTE, SAME, REMOVED), then a NOTE for everything the store could not show, then
PASS or FAIL. The page is built from these files by build_site.py and from nothing else.
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from aso.dashboard.export import run  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--store", type=Path, required=True, help="the app repository's marketing/ directory")
    parser.add_argument("--as-of", type=dt.date.fromisoformat, required=True, metavar="YYYY-MM-DD",
                        help="the day the export is made for; the only date it uses")
    parser.add_argument("--check", action="store_true", help="compare with the data folder instead of writing it")
    parser.add_argument("--rewind", action="store_true",
                        help="allow a day before the one data/ holds (it removes the files of the days after it)")
    args = parser.parse_args(argv)
    if not args.store.is_dir():
        parser.error(f"--store {args.store} is not a directory")
    return run(args.store.resolve(), args.as_of, check_only=args.check, rewind=args.rewind)


if __name__ == "__main__":
    sys.exit(main())
