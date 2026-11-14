"""The dashboard commands of the copilot CLI. The only place the clock is read for them: `--as-of` defaults to today."""
import datetime as dt
from pathlib import Path

from aso.commands.base import DEFAULT_STORE
from aso.dashboard import export


def cmd_export(args):
    """Derive the dashboard data files from the store. Prints the day it used, so a run can be repeated."""
    as_of = dt.date.fromisoformat(args.as_of) if args.as_of else dt.date.today()
    print(f"as of {as_of}")
    store = Path(getattr(args, "store", DEFAULT_STORE)).resolve()
    if not store.is_dir():
        print(f"Store not found: {store}")
        return 2
    return export.run(store, as_of, check_only=args.check)
