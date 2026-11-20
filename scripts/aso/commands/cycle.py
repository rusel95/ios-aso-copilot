"""The consolidated collection pass (`cycle`, also `collect`) and the digests it prints."""

import datetime as dt
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from aso.commands.base import SKILL_DIR, compact_asc_output, resolve_app_identity, run_cmd
from aso.commands.charts import fetch_category_chart, genre_ids, read_charts
from aso.commands.collect import fetch_lookup, funnel_script, prepare_funnel_pull
from aso.commands.parallel import run_stages
from aso.pull_revenuecat_series import ADS_COLS, ADS_KEEP
from aso.store import append_changed, read_ranks
from aso.store_state import first_release_day, store_charts, store_ratings, store_release
from pull_bigquery_telemetry import parse_config, store_weeks


DEFAULT_JOBS = 8       # the stages wait on different services; side by side, a pass takes as long as its slowest one


class _Tee:
    """Pass stdout through unchanged while keeping a copy for the closing stage table."""
    def __init__(self, real):
        self.real, self.parts = real, []

    def write(self, s):
        self.parts.append(s)
        return self.real.write(s)

    def flush(self):
        self.real.flush()

    def __getattr__(self, name):
        return getattr(self.real, name)


def cycle_stage_table(text):
    """Stage | status | reason, read back from the cycle's own `▶ [n/N]` sections.

    The long output scrolls and a caller that tails it loses the warnings; this is the part that
    must still be on screen. ok = no warning; partial = a warning line; failed = a source error or
    a non-zero child; skipped = the stage was switched off by a flag.
    """
    sections = re.split(r"(?m)^▶ \[(\d)/\d\] (.*)$", text)
    rows = []
    for i in range(1, len(sections), 3):
        num, name, body = sections[i], sections[i + 1].rstrip("."), sections[i + 2]
        # the cycle flags trouble with "⚠️", except one 📝 line (unresponded reviews) that says "unknown"
        warn = [l.strip() for l in body.splitlines()
                if "⚠️" in l or ("📝" in l and re.search(r"unknown|no output", l))]
        if "explicitly skipped" in body and not warn:
            rows.append((num, name, "skipped", "flag"))
        elif not warn:
            rows.append((num, name, "ok", ""))
        else:
            hard = re.search(r"Could not|failed|unavailable|exited with code|not found|missing", warn[0])
            rows.append((num, name, "failed" if hard else "partial", warn[0].replace("⚠️", "").replace("📝", "").strip()[:150]))
    return rows


def funnel_digest(store, today=None):
    """The store funnel and install lifecycle the cycle already holds, as a table with its conversions.

    Reads metrics/weekly.csv and metrics/lifecycle.csv (the newest week of each, as last recorded) so the numbers a
    reader needs are on screen without opening a file. A read older than 3 days is called STALE: this store's
    weekly.csv once sat 11 days behind its source and nobody could tell from the output.
    """
    import csv
    today = today or dt.date.today()

    def newest(name):
        path = store / "metrics" / name
        if not path.is_file():
            return None, []
        with path.open(encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        if not rows:
            return None, []
        # one week: a history pull records every week it holds on one day, and a table of all of them is not a digest
        week = max(r.get("week_start", "") for r in rows)
        rows = [r for r in rows if r.get("week_start", "") == week]
        rec = max(r.get("recorded", "") for r in rows)
        return rec, [r for r in rows if r.get("recorded") == rec]

    def pct(a, b):
        try:
            return f"{100 * float(a) / float(b):.1f}%" if float(b) else "—"
        except (TypeError, ValueError):
            return "—"

    def age(rec):
        try:
            days = (today - dt.date.fromisoformat(rec)).days
        except ValueError:
            return ""
        return f" — STALE: {days} days old" if days > 3 else ""

    print("\nFUNNEL DIGEST (store → install; the newest week each file holds)")
    rec, rows = newest("weekly.csv")
    if not rows:
        print("  store funnel: no metrics/weekly.csv rows — run `copilot.py funnel --pull`")
    else:
        print(f"  App Store funnel, week of {rows[0].get('week_start')}, recorded {rec}{age(rec)}  [store:metrics/weekly.csv]")
        print(f"  {'segment':<8}{'impr':>8}{'page views':>11}{'1st dl':>8}{'PV/impr':>9}{'dl/impr':>9}{'dl/PV':>8}{'trials':>8}")
        for r in rows:
            print(f"  {r.get('segment', ''):<8}{r.get('impressions', ''):>8}{r.get('product_page_views', ''):>11}"
                  f"{r.get('downloads', ''):>8}{pct(r.get('product_page_views'), r.get('impressions')):>9}"
                  f"{pct(r.get('downloads'), r.get('impressions')):>9}{pct(r.get('downloads'), r.get('product_page_views')):>8}"
                  f"{(r.get('trial_starts') or 'n/a'):>8}")
        print("  (dl/PV can exceed 100%: Apple counts downloads from the search card without a page view)")
    rec, rows = newest("lifecycle.csv")
    if not rows:
        print("  lifecycle: no metrics/lifecycle.csv rows")
    else:
        print(f"  Opt-in install lifecycle, week of {rows[0].get('week_start')}, recorded {rec}{age(rec)}  [store:metrics/lifecycle.csv]")
        print(f"  {'segment':<8}{'installs':>9}{'deleted':>9}{'deleted %':>10}{'≤1 day':>8}")
        for r in rows:
            print(f"  {r.get('segment', ''):<8}{r.get('first_installs_optin', ''):>9}{r.get('deletions_optin', ''):>9}"
                  f"{pct(r.get('deletions_optin'), r.get('first_installs_optin')):>10}{r.get('deleted_within_1d', ''):>8}")


def cashflow_digest(store: Path):
    """Print the stored RevenueCat & Apple Ads cashflow summary (Gross, Net Tax, Proceeds vs Ad Spend)."""
    store = Path(store).resolve()
    try:
        app = resolve_app_identity(store)
    except SystemExit:
        return
    rc_project_id = app.get("rc_project_id")
    rc_json_path = store / "metrics" / "revenuecat_latest.json"

    if rc_json_path.is_file():
        try:
            data = json.loads(rc_json_path.read_text(encoding="utf-8"))
            ov = data.get("overview", {})
            w14 = data.get("windows", {}).get("last_14d_global", {})
            w28 = data.get("windows", {}).get("last_28d_global", {})
            wall = data.get("windows", {}).get("all_time_global", {})
            print(f"\nCASHFLOW DIGEST (RevenueCat Proceeds vs Apple Ads Spend · snapshot {data.get('captured_at', '')[:10]})  [store:metrics/revenuecat_latest.json]")
            print(f"  Active Subs: {ov.get('active_subscriptions', {}).get('value', 0)} · Active Trials: {ov.get('active_trials', {}).get('value', 0)} · MRR: ${ov.get('mrr', {}).get('value', 0)}")
            for label, w in (("Last 14d", w14), ("Last 28d", w28), ("All-Time", wall)):
                if w:
                    cf = w.get("net_cashflow", 0.0)
                    cf_s = f"+${cf:.2f}" if cf >= 0 else f"-${abs(cf):.2f}"
                    roas = f"{w['net_roas_pct']:.0f}%" if w.get("net_roas_pct") is not None else "—"
                    print(f"  {label:<10}: Gross ${w.get('gross_revenue', 0):.2f} · NetTax ${w.get('net_of_taxes', 0):.2f} · "
                          f"Proceeds ${w.get('proceeds', 0):.2f} vs Spend ${w.get('ad_spend', 0):.2f} → Cashflow {cf_s} (ROAS {roas})")
            for f in data.get("flight_evaluations", []):
                cf = f.get("net_cashflow", 0.0)
                cf_s = f"+${cf:.2f}" if cf >= 0 else f"-${abs(cf):.2f}"
                roas = f"{f['net_roas_pct']:.0f}%" if f.get("net_roas_pct") is not None else "—"
                print(f"  Flight [{f['country']}] {f['name'][:28]} ({f['status']}): Spend ${f['ad_spend']:.2f} → "
                      f"Gross ${f['gross_revenue']:.2f} / Proceeds ${f['proceeds']:.2f} → Cashflow {cf_s} (ROAS {roas})")
        except Exception as exc:          # a digest that stops half way and says nothing reads as a complete one
            print(f"  ⚠️ cashflow digest: metrics/revenuecat_latest.json could not be shown ({type(exc).__name__}: {exc})")
    elif rc_project_id:
        print(f"\nCASHFLOW DIGEST: no metrics/revenuecat_latest.json — run `copilot.py rc --export`")


TELEMETRY_WEEKS_PER_PASS = 8


def chart_storefronts(store: Path, config: dict) -> list:
    """The storefronts to read the category charts in: the ones config.md names, else every storefront the store
    tracks a key in, the one with most keys first (the feeds are public, so nothing is needed to ask)."""
    named = [c.strip().lower() for c in config.get("Charts storefronts", "").split(",") if c.strip()]
    if named:
        return named
    keys = {}
    for r in read_ranks(store):
        if r.get("market"):
            keys.setdefault(r["market"], set()).add(r["keyword"])
    return sorted(keys, key=lambda market: (-len(keys[market]), market))


def collect_extras(store: Path, app: dict) -> bool:
    """Store the two series nothing else in the pass writes: the app's own telemetry by closed week, and where the
    app stands in the category charts. A store not set up for one says so and reads nothing; a step that fails
    says why and the next still runs. Returns False when a step failed."""
    config, clean, today = parse_config(store), True, dt.date.today()

    def named(*labels):
        """The first of these config.md lines that holds a value; a `TODO` placeholder is not one."""
        return next((v for v in ((config.get(label) or "").strip() for label in labels) if v and not v.upper().startswith("TODO")), None)

    project = named("Firebase Project ID", "BigQuery Project ID")
    prop = named("GA4 Property ID", "Firebase Property ID") or app.get("ga4_property_id")
    dataset = named("BigQuery Dataset") or (f"analytics_{prop.split()[0]}" if prop else None)
    if not project or not dataset:
        print("  in-app weeks: not set up (config.md names no Firebase Project ID with a GA4 Property ID)")
    else:
        try:
            # a first pass over a store with a long history is many BigQuery queries; each pass takes the newest few
            stored = store_weeks(store, project, dataset, today, limit=TELEMETRY_WEEKS_PER_PASS)
            print(f"  in-app weeks: {len(stored)} stored"
                  + (" (older weeks, if any, are read on the next pass)" if len(stored) == TELEMETRY_WEEKS_PER_PASS else ""))
        except Exception as exc:          # one source down must not cost the pass its other steps
            print(f"  ⚠️ in-app weeks: failed ({str(exc).splitlines()[0] if str(exc) else type(exc).__name__})")
            clean = False

    storefronts = chart_storefronts(store, config)
    if not storefronts:
        print("  chart positions: not set up (the store tracks no key yet, and config.md names no Charts storefronts)")
    else:
        try:
            results = read_charts(app, storefronts, genre_ids(config.get("Charts genres"), app), fetch=fetch_category_chart)
            failed = [r for r in results if r.get("error")]
            print(f"  chart positions: charts.csv +{store_charts(store, results, today.isoformat())}"
                  + (f" ({len(failed)} of {len(results)} charts could not be read)" if failed else ""))
            if failed:
                print(f"  ⚠️ chart positions: {failed[0]['country']} {failed[0]['genre']} failed ({failed[0]['error']})")
                clean = False
        except Exception as exc:
            print(f"  ⚠️ chart positions: failed ({str(exc).splitlines()[0] if str(exc) else type(exc).__name__})")
            clean = False
    return clean


def cmd_cycle(args):
    """Run the cycle, then print the funnel digest, cashflow digest, and a stage → status → reason table LAST."""
    tee = _Tee(sys.stdout)
    sys.stdout = tee
    try:
        code = _cycle_run(args)
    finally:
        sys.stdout = tee.real
    rows = cycle_stage_table("".join(tee.parts))
    store = Path(args.store).resolve()
    funnel_digest(store)
    cashflow_digest(store)
    print("\nSTAGE SUMMARY (a footer above is not a completeness certificate)")
    print(f"{'#':<2} {'stage':<46} {'status':<8} reason")
    for num, name, status, reason in rows:
        print(f"{num:<2} {name[:46]:<46} {status:<8} {reason}")
    return code


def print_step_funnel_summary(store):
    """Print a clear, prominent ASC Impressions & Funnel Summary directly in cycle Step 3."""
    weekly_csv = store / "metrics" / "weekly.csv"
    if not weekly_csv.is_file():
        print("  ⚠️ No weekly.csv found; ASC impressions snapshot unavailable.")
        return
    import csv
    with weekly_csv.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        print("  ⚠️ weekly.csv is empty; ASC impressions snapshot unavailable.")
        return

    weeks = sorted(set(r.get("week_start") for r in rows if r.get("week_start")))
    if not weeks:
        return
    latest_week = weeks[-1]
    latest_rows = [r for r in rows if r.get("week_start") == latest_week]
    rec = max((r.get("recorded", "") for r in latest_rows), default="")

    all_row = next((r for r in latest_rows if r.get("segment") == "all"), None)
    search_row = next((r for r in latest_rows if r.get("segment") == "search"), None)
    browse_row = next((r for r in latest_rows if r.get("segment") == "browse"), None)

    channel_segs = {"search", "browse", "web_referrer", "app_referrer"}
    channel_rows = [r for r in latest_rows if r.get("segment") in channel_segs or (r.get("segment") or "").startswith("other_")]

    if all_row:
        total_imp = int(all_row.get("impressions") or 0)
        total_pv = int(all_row.get("product_page_views") or 0)
        total_dl = int(all_row.get("downloads") or 0)
    else:
        total_imp = sum(int(r.get("impressions") or 0) for r in channel_rows)
        total_pv = sum(int(r.get("product_page_views") or 0) for r in channel_rows)
        total_dl = sum(int(r.get("downloads") or 0) for r in channel_rows)

    search_imp = int(search_row.get("impressions") or 0) if search_row else 0
    browse_imp = int(browse_row.get("impressions") or 0) if browse_row else 0
    search_dl = int(search_row.get("downloads") or 0) if search_row else 0

    pv_imp_cvr = f"{100.0 * total_pv / total_imp:.1f}%" if total_imp else "—"
    dl_pv_cvr = f"{100.0 * total_dl / total_pv:.1f}%" if total_pv else "—"
    dl_imp_cvr = f"{100.0 * total_dl / total_imp:.2f}%" if total_imp else "—"

    print(f"\n  📊 App Store Impressions & Funnel Summary (ASC Analytics):")
    print(f"     Latest Week:           {latest_week} (recorded: {rec})")
    print(f"     Total Impressions:     {total_imp:,} (Search: {search_imp:,}, Browse: {browse_imp:,}, Other: {total_imp - search_imp - browse_imp:,})")
    print(f"     Product Page Views:    {total_pv:,} (PV/Imp: {pv_imp_cvr})")
    print(f"     First-time Downloads:  {total_dl:,} (Dl/Imp: {dl_imp_cvr}, Dl/PV: {dl_pv_cvr})")
    if search_row:
        s_pv = int(search_row.get("product_page_views") or 0)
        s_cvr = f"{100.0 * search_dl / s_pv:.1f}%" if s_pv else "—"
        print(f"     Search Channel:        {search_imp:,} impr · {search_dl} dl (Search CVR: {s_cvr})")

    territory_rows = [r for r in latest_rows if len(r.get("segment") or "") == 2]
    if territory_rows:
        print("     Top Storefronts:")
        sorted_terr = sorted(territory_rows, key=lambda r: int(r.get("impressions") or 0), reverse=True)
        for r in sorted_terr[:5]:
            t_imp = int(r.get("impressions") or 0)
            t_dl = int(r.get("downloads") or 0)
            print(f"       {r['segment'].upper()}: {t_imp:,} imp, {t_dl} dl")

    if len(weeks) > 1:
        print("     Weekly Trajectory (Last 4 Weeks):")
        for w in weeks[-4:]:
            w_rows = [r for r in rows if r.get("week_start") == w]
            w_all = next((r for r in w_rows if r.get("segment") == "all"), None)
            w_search = next((r for r in w_rows if r.get("segment") == "search"), None)
            if w_all:
                w_imp = int(w_all.get("impressions") or 0)
                w_dl = int(w_all.get("downloads") or 0)
            else:
                w_ch = [r for r in w_rows if r.get("segment") in channel_segs or (r.get("segment") or "").startswith("other_")]
                w_imp = sum(int(r.get("impressions") or 0) for r in w_ch)
                w_dl = sum(int(r.get("downloads") or 0) for r in w_ch)
            w_s_imp = int(w_search.get("impressions") or 0) if w_search else 0
            print(f"       {w}: {w_imp:>7,} impr (Search: {w_s_imp:>6,}) · {w_dl:>3} first-dl")


def stage_versions(app_id: str) -> bool:
    rc, out, err = run_cmd(["asc", "versions", "list", "--app", app_id, "--platform", "IOS"])
    if rc != 0:
        print(f"  ⚠️ Could not query ASC versions: {err.strip() or f'exit {rc}'}")
        return False
    if not out.strip():
        print("  ⚠️ ASC version query returned no output.")
        return False
    summary = compact_asc_output(out, "versions")
    print(f"  {summary}" if summary else "  ⚠️ ASC version output format is unknown; payload omitted.")
    return bool(summary)


def stage_ratings(store: Path, app_id: str) -> bool:
    clean = True
    rc, out, err = run_cmd(["asc", "reviews", "ratings", "--app", app_id, "--all"])
    ratings_out = out if rc == 0 else ""
    if rc == 0 and out.strip():
        summary = compact_asc_output(out, "ratings")
        if summary:
            print(f"  {summary}")
        else:
            print("  ⚠️ ASC ratings output format is unknown; payload omitted.")
            clean = False
    elif rc == 0:
        print("  ⚠️ ASC ratings query returned no output.")
        clean = False
    else:
        print(f"  ⚠️ Could not query ASC ratings: {err.strip() or f'exit {rc}'}")
        clean = False
    rc, out, err = run_cmd(["asc", "reviews", "--app", app_id, "--only-unresponded"])
    # the history: what this pass read of the store's own state is appended to the store, never rewritten
    seen = dt.date.today().isoformat()
    rc_all, listing, _ = run_cmd(["asc", "reviews", "--app", app_id, "--limit", "1"])     # for its total only
    gained = store_ratings(store, ratings_out, out if rc == 0 else None, seen, listing if rc_all == 0 else None)
    lookup = fetch_lookup(app_id)
    print(f"  stored: ratings.csv +{gained}, releases.csv +{store_release(store, lookup, seen) if lookup else 0}"
          + ("" if lookup else " (the store lookup could not be read)"))
    if rc == 0 and out.strip():
        summary = compact_asc_output(out, "unreplied")
        if summary:
            print(f"  📝 {summary}")
        else:
            print("  📝 Unresponded review output format is unknown; payload omitted.")
            clean = False
    elif rc == 0:
        print("  📝 Unresponded review query returned no output; whether there are zero rows is unknown.")
        clean = False
    else:
        print(f"  ⚠️ Could not query unresponded reviews: {err.strip() or f'exit {rc}'}")
        clean = False
    return clean


def stream(command: list, env=None) -> tuple:
    """Run a long child and pass its lines on as they come -> (exit code, lines)."""
    proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, env=env)
    lines = []
    for line in proc.stdout:
        lines.append(line.strip())
        print("  " + line.rstrip("\n"), flush=True)
    return proc.wait(), lines


def funnel_failure(lines: list) -> str:
    """The line of a failed pull that says why: the last one naming a report that could not be read, a refusal or a
    rate limit; else its last line."""
    said = [line for line in lines if line]
    return next((l for l in reversed(said) if re.search(r"Partial funnel stage|refus|rate limit|429|Error:", l)),
                said[-1] if said else "no output")


def stage_funnel(store: Path, app_id: str, skip: bool) -> bool:
    pull_script, clean = funnel_script(store), True
    if skip:
        print("  (Funnel pull explicitly skipped)")
    elif pull_script.exists():
        command, raw_dir, reason = prepare_funnel_pull(pull_script, store, app_id)
        if command is None:
            print(f"  ⚠️ {reason}")
            clean = False
        else:
            print("  Running pull_funnel.py (ASC analytics is not real-time, and a first pull downloads every daily "
                  "report: half an hour is normal; later pulls ask only for new days)...")
            print(f"  Keeping source CSVs under {raw_dir}")
            rc, lines = stream(command, dict(os.environ, ASC_TIMEOUT="120s"))
            if rc == 0:
                print("  ✓ Funnel metrics & impressions updated.")
            else:
                print(f"  ⚠️ pull_funnel.py exited with code {rc}; funnel metrics may be stale. "
                      f"Cause: {funnel_failure(lines)[:200]}")
                clean = False
    else:
        print("  ⚠️ Funnel pull unavailable — pull_funnel.py not found in store or skill scripts/.")
        clean = False
    print_step_funnel_summary(store)
    return clean


def stage_ga(store: Path, app: dict, skip: bool) -> bool:
    ga_script = SKILL_DIR / "scripts" / "pull_ga.py"
    if not ga_script.exists():
        ga_script = store / "scripts" / "pull_ga.py"
    venv_py = Path.cwd() / ".venv" / "bin" / "python"
    py_exec = str(venv_py) if venv_py.exists() else sys.executable
    if skip:
        print("  (GA4 pull explicitly skipped)")
        return True
    if not app["ga4_property_id"]:
        print(f"  ⚠️ GA4 Property ID missing from {store / 'config.md'}; skipping rather than using a fallback.")
        return False
    if not ga_script.exists():
        print("  ⚠️ GA4 pull unavailable — pull_ga.py not found in skill or store scripts/.")
        return False
    rc, out, err = run_cmd([py_exec, str(ga_script), "--store", str(store), "--days", "14",
                            "--property-id", app["ga4_property_id"]])
    lines = out.splitlines()
    if rc in (0, 2) and out.strip():
        for l in lines[:250]:
            print(f"  {l}")
        if len(lines) > 250:
            print(f"  … {len(lines) - 250} additional GA4 output lines omitted.")
    if rc == 0 and out.strip():
        return True
    if rc == 0:
        print("  ⚠️ GA4 returned no output; whether the result is empty or unavailable is unknown.")
    elif rc == 2 and out.strip():
        # pull_ga.py uses exit 2 for "partial" and prints everything it did get, with the reason
        why = next((l.strip(" ⚠️") for l in reversed(lines) if "⚠️" in l), "see the GA4 output above")
        print(f"  ⚠️ GA4 pull partial (exit 2): {why[:160]}")
    else:
        # a traceback is fifty lines; its last line names the error, and that is the line a reader needs
        why = next((l.strip() for l in reversed(err.splitlines()) if l.strip()), f"exit {rc}")
        print(f"  ⚠️ GA4 pull failed: {why[:200]}")
    return False


def stage_radar(store: Path, app_id: str) -> bool:
    """Apple's search popularity and impression share: the newest week, and every earlier week since the app's
    first release that the store does not hold yet (Apple answers for past weeks; a week already held costs nothing)."""
    since = first_release_day(fetch_lookup(app_id))
    rc, out, err = run_cmd([sys.executable, str(SKILL_DIR / "scripts" / "radar.py"), "--store", str(store), "pull", "--if-configured"]
                           + (["--since", since] if since else []))
    if rc == 0:
        for l in out.splitlines():
            print(f"  {l}")
        return True
    print(f"  ⚠️ Radar pull incomplete (exit {rc}); stored weeks are unchanged for the markets that failed:")
    for l in (out + err).splitlines()[:20]:
        print(f"    {l}")
    return False


def stage_revenue(store: Path, app: dict, skip: bool) -> bool:
    """RevenueCat and Apple Ads: the snapshot, and the closed weeks of cashflow and of ads results."""
    if skip:
        print("  (RevenueCat pull explicitly skipped)")
        return True
    import pull_revenuecat
    if not app.get("rc_project_id"):
        print("  revenue: not set up (config.md names no RevenueCat Project ID)")
        if not app.get("ads_account"):
            return True
        rows, err = pull_revenuecat.collect_ads(store)       # Apple Ads needs no subscription provider
        if err or rows is None:
            print(f"  ⚠️ Apple Ads results could not be read: {err or 'nothing came back'}")
            return False
        gained = append_changed(store / "metrics" / "ads.csv", ADS_COLS, rows, ("week_start", "campaign_id"), keep=ADS_KEEP)
        print(f"  stored: ads.csv +{gained} (Apple Ads results by closed week, {len(rows)} read)")
        return True
    data, err = pull_revenuecat.collect_revenuecat_and_cashflow(store, project_id_override=app["rc_project_id"])
    if err or not data:
        print(f"  ⚠️ RevenueCat & Cashflow live pull failed: {err or 'nothing came back'}")
        return False
    pull_revenuecat.export_snapshots(store, data)
    pull_revenuecat.print_cashflow_report(data)
    return True


def stage_ranks(store: Path) -> bool:
    """Ask the App Store again for every tracked key. Apple allows about twenty searches a minute, so this is the
    long stage of a pass: it runs beside the others, and the ledger report waits for it."""
    config = parse_config(store)
    bundle = (config.get("Bundle ID") or config.get("Firebase Bundle ID") or "").split(maxsplit=1)
    if not bundle or bundle[0].upper().startswith("TODO"):
        print("  ⚠️ rank sweep: config.md names no Bundle ID (`**Bundle ID**: com.example.app`); nothing was asked")
        return False
    rc, _ = stream([sys.executable, str(SKILL_DIR / "scripts" / "ledger.py"), "--store", str(store), "refresh", "--bundle", bundle[0]])
    if rc:
        print(f"  ⚠️ rank sweep exited with code {rc}; ranks.csv holds what was read before it stopped")
    return rc == 0


def stage_ledger(store: Path) -> bool:
    ledger_py = SKILL_DIR / "scripts" / "ledger.py"
    if not ledger_py.exists():
        print(f"  ⚠️ Ledger report unavailable — {ledger_py} not found.")
        return False
    rc, out, err = run_cmd([sys.executable, str(ledger_py), "--store", str(store), "report"])
    if rc == 0 and out.strip():
        print(out)
        return True
    print("  ⚠️ Ledger report returned no output." if rc == 0 else f"  ⚠️ Ledger report failed: {err.strip() or f'exit {rc}'}")
    return False


def stage_plan(args, store: Path, app: dict) -> tuple:
    """(the stages that read sources independent of one another and so run side by side, the stages that read what
    those stored). The rank sweep is one of the first only when asked for: it takes about an hour."""
    app_id = app["app_id"]
    together = [
        ("Verifying App Store Connect Versions", lambda: stage_versions(app_id)),
        ("Auditing Customer Reviews & Ratings", lambda: stage_ratings(store, app_id)),
        ("Syncing Funnel Analytics & Impressions (ASC)", lambda: stage_funnel(store, app_id, args.skip_pull)),
        ("Pulling In-App Telemetry (GA4)", lambda: stage_ga(store, app, args.skip_ga)),
        ("Storing In-App Weeks & Chart Positions", lambda: collect_extras(store, app)),
        ("Apple demand radar (search popularity, impression share)", lambda: stage_radar(store, app_id)),
        ("Revenue, Cashflow & Apple Ads (RevenueCat)", lambda: stage_revenue(store, app, getattr(args, "skip_rc", False))),
    ]
    if getattr(args, "ranks", False):
        together.append(("Full Rank Sweep of the Tracked Keys", lambda: stage_ranks(store)))
    return together, [("Generating Hypothesis & Keyword Ledger Report", lambda: stage_ledger(store))]


def _cycle_run(args):
    """Run the consolidated live-read and local snapshot pass."""
    store = Path(args.store).resolve()
    app = resolve_app_identity(store)

    print("=================================================================")
    print(f"🚀 {app['brand']} Marketing CLI Cycle · {store}")
    print(f"App ID: {app['app_id']} · Version: {app['version']}")
    print("=================================================================\n")

    together, after = stage_plan(args, store, app)
    total = len(together) + len(after)
    clean = run_stages(together, getattr(args, "jobs", None) or DEFAULT_JOBS, total=total)
    clean += run_stages(after, 1, first=len(together) + 1, total=total)

    print("\n=================================================================")
    state = "finished" if all(clean) else "PARTIAL"
    print(f"Cycle command {state}. Review every warning and skipped stage; this footer does not certify data completeness.")
    print("=================================================================")
    return 0 if all(clean) else 2
