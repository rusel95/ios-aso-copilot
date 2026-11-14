#!/usr/bin/env python3
"""Build the dashboard page from the data files. Offline; the same data gives the same bytes.

    build_site.py --data PATH/data --out public [--name "App name"]

Every file is checked against the data contract first. One file that breaks it prints INVALID lines and
FAIL data, and nothing is written. The page is one index.html that loads nothing from outside.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from aso.dashboard.site import build  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data", type=Path, required=True, help="the data folder the export wrote")
    parser.add_argument("--out", type=Path, required=True, help="the folder index.html is written into")
    parser.add_argument("--name", default="App", help="the app's name as the page shows it")
    args = parser.parse_args(argv)
    return build(args.data, args.out, args.name)


if __name__ == "__main__":
    sys.exit(main())
