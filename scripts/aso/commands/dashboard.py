"""The dashboard commands of the copilot CLI. The only place the clock is read for them: `--as-of` defaults to today."""
import datetime as dt
from pathlib import Path

from aso.commands.base import DEFAULT_STORE
from aso.dashboard import clean, export, site
from aso.ledger_state import reads_due
from aso.store import read_brand_tokens, read_hypotheses, read_ranks


def cmd_export(args):
    """Derive the dashboard data files from the store. Prints the day it used, so a run can be repeated."""
    as_of = dt.date.fromisoformat(args.as_of) if args.as_of else dt.date.today()
    print(f"as of {as_of}")
    store = Path(getattr(args, "store", DEFAULT_STORE)).resolve()
    if not store.is_dir():
        print(f"Store not found: {store}")
        return 2
    return export.run(store, as_of, check_only=args.check)


def cmd_build(args):
    """Build the page from the store's data folder. The app is named by its first brand token."""
    store = Path(getattr(args, "store", DEFAULT_STORE)).resolve()
    tokens = read_brand_tokens(store)
    out = Path(args.out).resolve() if args.out else store / "public"
    return site.build(store / "data", out, tokens[0].capitalize() if tokens else "App")


def cmd_due(args):
    """The rank reads the live hypotheses need at the end of their windows: one line a storefront and day."""
    as_of = dt.date.fromisoformat(args.as_of) if args.as_of else dt.date.today()
    store = Path(getattr(args, "store", DEFAULT_STORE)).resolve()
    due = sorted(reads_due(read_hypotheses(store), read_ranks(store), as_of), key=lambda d: (d["day"], d["id"], d["market"]))
    for d in due:
        print(f"{d['day']}  {d['id']}  {d['market']}  {'; '.join(d['queries'])}" + ("  (missed)" if d["day"] < as_of.isoformat() else ""))
    if not due:
        print("Nothing due.")
    return 0


def cmd_check(args):
    """Look through the data folder for what must not be published. Exits 1 when anything is found."""
    store = Path(getattr(args, "store", DEFAULT_STORE)).resolve()
    problems = clean.check(store / "data", store)
    print("\n".join(problems) if problems else "PASS clean")
    return 1 if problems else 0
