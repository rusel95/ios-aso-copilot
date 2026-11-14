"""The dashboard commands of the copilot CLI. The only place the clock is read for them: `--as-of` defaults to today."""
import datetime as dt
from pathlib import Path

from aso.commands.base import DEFAULT_STORE
from aso.dashboard import clean, export, site
from aso.commands.base import SCRIPTS_DIR
from aso.ledger_state import hypothesis_states, priority, proposals, reads_due
from aso.ranks import series, zero_result_keys
from aso.store import demand_lookup, read_brand_tokens, read_hypotheses, read_markets, read_ranks


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


def cmd_propose(args):
    """Generate the next rank hypotheses from the store: the storefronts free to start one, by money at stake, each
    with its basket and the line that drafts it. What is due is named first: it is judged before anything new."""
    as_of = dt.date.fromisoformat(args.as_of) if args.as_of else dt.date.today()
    print(f"as of {as_of}")
    store = Path(getattr(args, "store", DEFAULT_STORE)).resolve()
    rows = [r for r in read_ranks(store) if (r.get("date") or "") <= as_of.isoformat()]
    pairs, hyps, brand = series(rows), read_hypotheses(store, kinds=("H", "C")), read_brand_tokens(store)
    states = hypothesis_states(hyps, pairs, zero_result_keys(rows), as_of)
    due = [h["id"] for h in states if h["state"] == "due"]
    if due:
        print(f"{len(due)} hypotheses are due and come first: {', '.join(due)} (see `due` and the ledger report).")
    found = proposals(priority(pairs, read_markets(store), hyps, brand, demand_lookup(store, as_of)), states, args.basket, args.limit)
    if not found:
        print("Nothing to propose: no storefront with a price record has an untaken key and no window in flight.")
        return 0
    for n, p in enumerate(found, 1):
        print(f"\n{n}. {p['market']}  net proceeds ${p['proceeds']:.2f} a paying subscriber · no window in flight there"
              + (f" · already drafted, never shipped: {', '.join(p['drafted'])} (ship or revise it before writing another)" if p["drafted"] else ""))
        for k in p["keys"]:
            where = f"#{k['position']}" if k["position"] else "beyond depth"
            print(f"   {k['keyword']}  {where} ({k['band']})  score {k['score']}" + (f"  Apple demand: {k['demand']}" if k["demand"] else ""))
        print(f"   draft: python3 {SCRIPTS_DIR / 'ledger.py'} --store {store} draft --market {p['market']} --queries "
              f"\"{'; '.join(k['keyword'] for k in p['keys'])}\"")
    print("\nThe draft fills in the baseline, the window and the kill criterion. The change and its mechanism are yours to argue.")
    return 0
