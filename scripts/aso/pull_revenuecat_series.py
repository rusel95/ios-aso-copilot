"""What pull_revenuecat stores as series: one row per subscription read, and closed Monday weeks of cashflow per
storefront and of Apple Ads results per campaign. Rows are appended; a correction is a new row with a later
`captured`, never an edit."""
from __future__ import annotations

import datetime as dt

from aso.dashboard.weeks import closed, monday
from aso.store import append_changed  # noqa: F401 — the series files are appended through it

REVENUE_COLS = ["captured", "active_subscriptions", "active_trials", "mrr_usd", "revenue_28d_usd", "new_customers_28d",
                "active_users_28d", "source"]
CASHFLOW_COLS = ["week_start", "country", "transactions", "new_trials", "gross_revenue_usd", "proceeds_usd", "ad_spend_usd",
                 "source", "captured"]
ADS_COLS = ["week_start", "campaign_id", "market", "spend_usd", "impressions", "taps", "installs", "source", "captured"]
ADS_KEEP = ("installs",)      # a later report that gives no install count does not erase the one already stored
OVERVIEW = {"active_subscriptions": "active_subscriptions", "active_trials": "active_trials", "mrr_usd": "mrr",
            "revenue_28d_usd": "revenue", "new_customers_28d": "new_customers", "active_users_28d": "active_users"}


def week_of(day: str, as_of: dt.date, whole_from: dt.date | None = None):
    """The Monday of a day's week as text, or None when that week has not closed (or the day is not a date), or began
    before `whole_from`: a pull that starts mid-week holds only the end of that week, and a part of a week stored as a
    week would be read as a slow one."""
    try:
        week = monday(dt.date.fromisoformat(day[:10]))
    except ValueError:
        return None
    return week.isoformat() if closed(week, as_of) and (whole_from is None or week >= whole_from) else None


def revenue_row(data: dict) -> dict:
    """One read of the subscription provider's overview. The overview is what the provider says on the day of the
    read, whatever span the pull asked for, so it is dated by that day; a figure the read lacks is a blank cell,
    which the export shows as nothing to measure."""
    overview = data.get("overview") or {}
    row = {"captured": (data.get("captured_at") or "")[:10] or data["period"]["end"], "source": "revenuecat"}
    for column, theirs in OVERVIEW.items():
        found = overview.get(theirs)
        row[column] = found.get("value", "") if isinstance(found, dict) and found.get("value") is not None else ""
    return row


def cashflow_weeks(by_country_daily: dict, trials_by_country: dict, daily_spend: dict, as_of: dt.date, captured: str,
                   whole_from: dt.date | None = None) -> list:
    """Daily revenue, trials and ad spend folded into closed Monday weeks per storefront. `whole_from` is the first
    Monday whose week the pull holds from its first day: earlier weeks are partial and are not written."""
    weeks = {}

    def cell(day, country):
        week = week_of(day, as_of, whole_from)
        if week is None or not country:
            return None
        return weeks.setdefault((week, country.upper()), {"tx": 0, "trials": 0, "gross": 0.0, "proceeds": 0.0, "spend": 0.0})

    for (day, code, _), values in by_country_daily.items():
        found = cell(day, code)
        if found:
            found["tx"] += values["tx"]
            found["gross"] += values["gross"]
            found["proceeds"] += values["proceeds"]
    for (day, code, _), count in trials_by_country.items():
        found = cell(day, code)
        if found:
            found["trials"] += count
    for (day, _, country), values in daily_spend.items():
        found = cell(day, country)
        if found:
            found["spend"] += values["spend"]
    return [{"week_start": week, "country": country, "transactions": v["tx"], "new_trials": v["trials"],
             "gross_revenue_usd": f"{v['gross']:.2f}", "proceeds_usd": f"{v['proceeds']:.2f}", "ad_spend_usd": f"{v['spend']:.2f}",
             "source": "revenuecat+apple-ads", "captured": captured}
            for (week, country), v in sorted(weeks.items())]


def ads_weeks(daily_spend: dict, as_of: dt.date, captured: str, whole_from: dt.date | None = None) -> list:
    """Daily Apple Ads results folded into closed Monday weeks per campaign. When the report gave no install count
    for any day of the week, the cell is blank: unknown, not zero. `whole_from` as in `cashflow_weeks`."""
    weeks = {}
    for (day, campaign, country), values in daily_spend.items():
        week = week_of(day, as_of, whole_from)
        if week is None:
            continue
        found = weeks.setdefault((week, str(campaign)), {"market": (country or "").lower(), "spend": 0.0, "impressions": 0,
                                                         "taps": 0, "installs": None})
        found["spend"] += values["spend"]
        found["impressions"] += values["impressions"]
        found["taps"] += values["taps"]
        if values.get("installs") is not None:
            found["installs"] = (found["installs"] or 0) + values["installs"]
    return [{"week_start": week, "campaign_id": campaign, "market": v["market"], "spend_usd": f"{v['spend']:.2f}",
             "impressions": v["impressions"], "taps": v["taps"], "installs": "" if v["installs"] is None else v["installs"],
             "source": "apple-ads", "captured": captured}
            for (week, campaign), v in sorted(weeks.items())]


def store_series(store, data: dict) -> dict:
    """Append what one collection learned to the store's series. Returns the number of rows each file gained."""
    metrics = store / "metrics"
    return {"revenue.csv": append_changed(metrics / "revenue.csv", REVENUE_COLS, [revenue_row(data)], ("captured",)),
            "cashflow_weekly.csv": append_changed(metrics / "cashflow_weekly.csv", CASHFLOW_COLS,
                                                  data.get("weekly_cashflow") or [], ("week_start", "country")),
            "ads.csv": append_changed(metrics / "ads.csv", ADS_COLS, data.get("weekly_ads") or [], ("week_start", "campaign_id"),
                                      keep=ADS_KEEP)}
