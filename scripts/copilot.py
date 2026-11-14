#!/usr/bin/env python3
"""Unified CLI for iOS ASO Copilot (ios-marketing-ops).

Consolidates multi-step marketing operations into a single entrypoint:
  - copilot cycle: consolidated read/pull pass (versions, reviews, funnel, GA4, ledger)
  - copilot status: quick snapshot of active versions, hypotheses and ratings
  - copilot reviews: check rating histograms and unreplied customer reviews
  - copilot funnel: pull and summarize ASC analytics
  - copilot ga: pull in-app GA4 / Firebase telemetry
  - copilot ledger: delegate to ledger.py (report, refresh, draft, ingest)
  - copilot radar: delegate to radar.py (Apple search popularity, impression share, keyword report join)
"""
import argparse
import sys
from pathlib import Path

# The commands live in scripts/aso/commands/. This file is the parser and the dispatch.
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from aso.commands.ads_actions import cmd_reviews_respond  # noqa: E402
from aso.commands.ads_read import cmd_ads  # noqa: E402
from aso.commands.base import DEFAULT_STORE, set_log_level  # noqa: E402
from aso.commands.campaign import cmd_campaign  # noqa: E402
from aso.commands.charts import cmd_charts  # noqa: E402
from aso.commands.collect import cmd_funnel, cmd_ga, cmd_ledger, cmd_radar, cmd_rc, cmd_reviews, cmd_telemetry  # noqa: E402
from aso.commands.cycle import cmd_cycle  # noqa: E402
from aso.commands.google import cmd_google  # noqa: E402
from aso.commands.keywords import cmd_keywords  # noqa: E402
from aso.commands.status import cmd_brief, cmd_info, cmd_status  # noqa: E402


def build_parser():
    # Common flags inherited by all subcommands
    common_parent = argparse.ArgumentParser(add_help=False)
    common_parent.add_argument("--store", default=argparse.SUPPRESS, help="Path to marketing store directory")
    common_parent.add_argument("--debug", "-d", action="store_true", default=argparse.SUPPRESS, help="Print debug diagnostics to stderr")
    common_parent.add_argument("--info", "-v", action="store_true", default=argparse.SUPPRESS, help="Print informational logs to stderr")
    common_parent.add_argument("--quiet", "-q", action="store_true", default=argparse.SUPPRESS, help="Suppress non-essential output")
    common_parent.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="Format output as JSON where applicable")

    parser = argparse.ArgumentParser(description="Unified CLI for iOS ASO Copilot")
    parser.add_argument("--store", default=str(DEFAULT_STORE), help="Path to marketing store directory")
    parser.add_argument("--debug", "-d", action="store_true", help="Print debug diagnostics to stderr")
    parser.add_argument("--info", "-v", action="store_true", help="Print informational logs to stderr")
    parser.add_argument("--quiet", "-q", action="store_true", help="Suppress non-essential output")
    parser.add_argument("--json", action="store_true", help="Format output as JSON where applicable")
    parser.add_argument("--self-check", action="store_true", help="check app identity parsing without network access")
    subparsers = parser.add_subparsers(dest="command")

    # info
    subparsers.add_parser("info", help="Diagnostic info and environment report", parents=[common_parent])

    # status
    subparsers.add_parser("status", help="Quick status snapshot", parents=[common_parent])

    # keywords
    p_kw = subparsers.add_parser("keywords", help="Keyword discovery, hints, localization vacuums, and filtering", parents=[common_parent])
    kw_subs = p_kw.add_subparsers(dest="keywords_action")

    p_hint = kw_subs.add_parser("hints", help="Apple App Store autocomplete hints", parents=[common_parent])
    p_hint.add_argument("--term", "-t", required=True, help="Search prefix/term")
    p_hint.add_argument("--country", "-c", "--storefront", default="us", help="Storefront code (e.g. us, pl, jp)")

    p_vac = kw_subs.add_parser("vacuum", help="Audit localization vacuum in storefront", parents=[common_parent])
    p_vac.add_argument("--term", "-t", required=True, help="Keyword query")
    p_vac.add_argument("--country", "-c", required=True, help="Country code (e.g. pl, de, jp)")
    p_vac.add_argument("--limit", type=int, default=20, help="Number of apps to inspect")

    p_pop = kw_subs.add_parser("popularity", help="Apple Ads Search Term Popularity (1-100)", parents=[common_parent])
    p_pop.add_argument("--country", "-c", required=True, help="Country code (e.g. pl, us)")
    p_pop.add_argument("--terms", help="Comma-separated terms to inspect")
    p_pop.add_argument("--genre", help="Genre category (e.g. PHOTO_VIDEO)")

    p_comp = kw_subs.add_parser("competitors", help="Discover competitors from seed terms", parents=[common_parent])
    p_comp.add_argument("--seeds", "-s", required=True, help="Comma-separated seed terms")
    p_comp.add_argument("--country", "-c", default="us", help="Country code (e.g. us, pl)")
    p_comp.add_argument("--limit", type=int, default=25, help="Limit of competitors")

    p_filt = kw_subs.add_parser("filter", help="Deterministic candidate review and export", parents=[common_parent])
    p_filt.add_argument("--input", "-i", required=True, help="Input CSV path")
    p_filt.add_argument("--output", "-o", required=True, help="Output directory")
    p_filt.add_argument("--brand", action="append", default=[], help="Protected brand name(s)")
    p_filt.add_argument("--limit", type=int, default=5000, help="Max candidates ceiling")

    # ads
    p_ads = subparsers.add_parser("ads", help="Manage Apple Ads campaigns, ad groups, and keywords", parents=[common_parent])
    ads_subs = p_ads.add_subparsers(dest="ads_action")

    p_acamp = ads_subs.add_parser("campaigns", aliases=["list"], help="List Apple Ads campaigns", parents=[common_parent])
    p_acamp.add_argument("--status", default="ALL", help="Filter by status (ENABLED, PAUSED, ALL)")
    p_acamp.add_argument("--country", "-c", help="Filter by targeted country")

    p_agrp = ads_subs.add_parser("adgroups", help="List ad groups in campaign", parents=[common_parent])
    p_agrp.add_argument("--campaign-id", help="Campaign ID filter")

    p_akw = ads_subs.add_parser("keywords", help="List targeting keywords", parents=[common_parent])
    p_akw.add_argument("--adgroup-id", help="Ad Group ID filter")
    p_akw.add_argument("--campaign-id", help="Campaign ID filter")

    p_aadd = ads_subs.add_parser("add-keywords", help="Add keywords to ad group", parents=[common_parent])
    p_aadd.add_argument("--adgroup-id", required=True, help="Ad Group ID")
    p_aadd.add_argument("--terms", help="Comma-separated keyword terms")
    p_aadd.add_argument("--file", help="Path to text file with keywords (one per line)")
    p_aadd.add_argument("--bid", default="0.30", help="CPT bid amount in USD (default: 0.30)")
    p_aadd.add_argument("--match-type", default="EXACT", choices=["EXACT", "BROAD"], help="Match type")

    p_apause = ads_subs.add_parser("pause", help="Pause a campaign", parents=[common_parent])
    p_apause.add_argument("--campaign-id", required=True, help="Campaign ID")

    p_aresume = ads_subs.add_parser("resume", help="Resume a campaign", parents=[common_parent])
    p_aresume.add_argument("--campaign-id", required=True, help="Campaign ID")

    # cycle
    subparsers.add_parser("brief", help="One screen: ASC state, Top-200 bands, all hypotheses, store funnel & cashflow", parents=[common_parent])
    p_cycle = subparsers.add_parser("cycle", aliases=["collect"], help="Run the consolidated data collection pass",
                                    parents=[common_parent])
    p_cycle.add_argument("--skip-pull", action="store_true", help="Skip remote ASC funnel download")
    p_cycle.add_argument("--skip-ga", action="store_true", help="Skip GA4 pull")
    p_cycle.add_argument("--skip-rc", action="store_true", help="Skip live RevenueCat & Cashflow pull")

    # rc / cashflow
    p_rc = subparsers.add_parser("rc", aliases=["cashflow"], help="Pull RevenueCat metrics, 3-tier revenue (Gross/NetTax/Proceeds) & Apple Ads Cashflow", parents=[common_parent])
    p_rc.add_argument("--project-id", help="RevenueCat Project ID (defaults to config.md)")
    p_rc.add_argument("--start", default="2026-09-01", help="Start date YYYY-MM-DD (default: 2026-09-01)")
    p_rc.add_argument("--end", help="End date YYYY-MM-DD (default: today)")
    p_rc.add_argument("--export", action="store_true", default=True, help="Export snapshots to metrics/revenuecat_latest.json and metrics/cashflow.csv")

    # reviews
    p_rev = subparsers.add_parser("reviews", help="Audit and reply to customer reviews", parents=[common_parent])
    p_rev.add_argument("action", choices=["ratings", "unreplied", "list", "respond"], default="ratings", nargs="?")
    p_rev.add_argument("--limit", type=int, default=10, help="Limit for list")
    p_rev.add_argument("--review-id", help="Review ID for response")
    p_rev.add_argument("--response", help="Response text")

    # funnel
    p_fun = subparsers.add_parser("funnel", help="Inspect or pull ASC funnel", parents=[common_parent])
    p_fun.add_argument("--pull", action="store_true", help="Trigger remote ASC pull")

    # ga
    p_ga = subparsers.add_parser("ga", help="Inspect in-app telemetry", parents=[common_parent])
    p_ga.add_argument("--days", type=int, default=14, help="Days window")
    p_ga.add_argument("--property-id", help="GA4 Property ID (numeric)")
    p_ga.add_argument("--credentials", help="Path to service-account.json")
    p_ga.add_argument("--realtime", action="store_true", help="Show events from the last 30 minutes only")
    p_ga.add_argument("--include-debug", action="store_true", help="Include debug / simulator traffic")
    p_ga.add_argument("--export-csv", action="store_true", help="Export funnel metrics to <store>/metrics/ga4_funnel.csv")

    # telemetry
    p_tel = subparsers.add_parser("telemetry", help="Pull BigQuery raw product telemetry (funnel, retention, engine, paywall)", parents=[common_parent])
    p_tel.add_argument("--days", type=int, default=0, help="Days window (0 for all-time)")
    p_tel.add_argument("--export-md", action="store_true", help="Export markdown report to <store>/metrics/telemetry_latest.md")
    p_tel.add_argument("--export-json", action="store_true", help="Export json to <store>/metrics/telemetry_latest.json")

    # campaign
    p_camp = subparsers.add_parser("campaign", help="App Store Campaign Link & Hypothesis Anti-Collision Generator", parents=[common_parent])
    p_camp.add_argument("--list", action="store_true", help="List registered campaigns and hypotheses")
    p_camp.add_argument("--campaign", default="", help="Campaign token (e.g. threads_build_in_public)")
    p_camp.add_argument("--channel", default="threads", help="Channel (e.g. threads, reddit, x, linkedin)")
    p_camp.add_argument("--type", default="threads", choices=["reddit_reply", "reddit_showcase", "threads", "x", "ugc_video", "other"], help="Copy template type")
    p_camp.add_argument("--pt", default="", help="Provider Token (auto-detected if omitted)")
    p_camp.add_argument("--target", default="", help="Target audience / community")
    p_camp.add_argument("--scaffold-hypo", action="store_true", help="Create C<NNN> markdown hypothesis in hypotheses/")
    p_camp.add_argument("--force", action="store_true", help="Bypass anti-collision warnings")

    # ledger
    p_led = subparsers.add_parser("ledger", help="Manage hypothesis and keyword ledger", parents=[common_parent])
    p_led.add_argument("ledger_args", nargs=argparse.REMAINDER, help="Arguments passed to ledger.py")

    # radar
    p_rad = subparsers.add_parser("radar", help="Apple demand radar: popularity, impression share, keyword lens",
                                  parents=[common_parent])
    p_rad.add_argument("radar_args", nargs=argparse.REMAINDER, help="Arguments passed to radar.py (pull, report, keywords)")

    # google
    p_goog = subparsers.add_parser("google", help="Google search intelligence: trends, autocomplete hints, and batch volume profiling",
                                   parents=[common_parent])
    goog_subs = p_goog.add_subparsers(dest="google_action")

    p_gtrend = goog_subs.add_parser("trends", help="Compare search interest via Google Trends", parents=[common_parent])
    p_gtrend.add_argument("terms", nargs="+", help="Keywords to compare (up to 5)")
    p_gtrend.add_argument("--country", "-c", default="US", help="Two-letter country code (default: US)")
    p_gtrend.add_argument("--timeframe", "-t", default="today 12-m", help="Timeframe (default: today 12-m)")
    p_gtrend.add_argument("--related", action="store_true", help="Fetch top and rising related queries for first term")
    p_gtrend.add_argument("--geo", action="store_true", help="Fetch subregion / oblast interest breakdown")

    p_gsug = goog_subs.add_parser("suggest", help="Live Google search autocomplete hints", parents=[common_parent])
    p_gsug.add_argument("term", help="Root search query or seed word")
    p_gsug.add_argument("--country", "-c", default="US", help="Two-letter country code (default: US)")
    p_gsug.add_argument("--lang", "-l", default="uk", help="Language code (default: uk)")
    p_gsug.add_argument("--limit", type=int, default=15, help="Max results (default: 15)")
    p_gsug.add_argument("--matrix", action="store_true", help="Deep multi-angle intent matrix expansion")

    p_gbatch = goog_subs.add_parser("batch", help="Batch relative volume profiling normalized to an anchor keyword", parents=[common_parent])
    p_gbatch.add_argument("--anchor", "-a", required=True, help="Anchor keyword (normalized to 100.0)")
    p_gbatch.add_argument("--terms", help="Comma-separated candidate keywords")
    p_gbatch.add_argument("--file", "-f", help="Path to text or CSV file with candidate keywords")
    p_gbatch.add_argument("--country", "-c", default="US", help="Two-letter country code (default: US)")
    p_gbatch.add_argument("--timeframe", "-t", default="today 12-m", help="Timeframe (default: today 12-m)")
    p_gbatch.add_argument("--delay", type=float, default=1.5, help="Polite delay in seconds between batches (default: 1.5)")

    # charts
    p_charts = subparsers.add_parser("charts", help="Inspect App Store Category Charts (Top Free/Paid/Grossing)", parents=[common_parent])
    p_charts.add_argument("--country", "-c", default="ua", help="Country code or comma-separated codes (default: ua)")
    p_charts.add_argument("--genre", "-g", help="Genre name (utilities, photo_video, productivity) or numeric ID")
    p_charts.add_argument("--chart-type", default="top-free", choices=["top-free", "top-paid", "top-grossing"], help="Chart type (default: top-free)")
    p_charts.add_argument("--limit", type=int, default=100, help="Number of apps in chart (default: 100, max: 200)")

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    set_log_level(
        debug=getattr(args, "debug", False),
        info=getattr(args, "info", False),
        quiet=getattr(args, "quiet", False)
    )

    if args.self_check:
        from aso.commands.selfcheck import self_check
        return self_check()
    if not args.command:
        parser.print_help()
        return 0

    if args.command == "info":
        return cmd_info(args)
    elif args.command == "status":
        return cmd_status(args)
    elif args.command == "keywords":
        return cmd_keywords(args)
    elif args.command == "ads":
        return cmd_ads(args)
    elif args.command == "brief":
        return cmd_brief(args)
    elif args.command in ("cycle", "collect"):
        return cmd_cycle(args)
    elif args.command == "reviews":
        return cmd_reviews_respond(args) if args.action == "respond" else cmd_reviews(args)
    elif args.command == "funnel":
        return cmd_funnel(args)
    elif args.command == "ga":
        return cmd_ga(args)
    elif args.command == "telemetry":
        return cmd_telemetry(args)
    elif args.command in ("rc", "cashflow"):
        return cmd_rc(args)
    elif args.command == "campaign":
        return cmd_campaign(args)
    elif args.command == "ledger":
        return cmd_ledger(args)
    elif args.command == "radar":
        return cmd_radar(args)
    elif args.command == "google":
        return cmd_google(args)
    elif args.command == "charts":
        return cmd_charts(args)
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
