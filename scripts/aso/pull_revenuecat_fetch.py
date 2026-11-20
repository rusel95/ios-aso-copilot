"""What pull_revenuecat reads from outside: the RevenueCat CLI and the Apple Ads reports."""

import datetime as dt
import json
import shutil
import subprocess
import urllib.parse
from pathlib import Path


COUNTRY_NAME_TO_CODE = {
    "Ukraine": "UA",
    "Spain": "ES",
    "Portugal": "PT",
    "Italy": "IT",
    "United States": "US",
    "Poland": "PL",
    "Indonesia": "ID",
    "Vietnam": "VN",
    "Thailand": "TH",
    "Romania": "RO",
    "Israel": "IL",
    "Hungary": "HU",
    "Slovakia": "SK",
    "Japan": "JP",
    "Singapore": "SG",
    "South Korea": "KR",
    "Korea": "KR",
    "Norway": "NO",
    "Sweden": "SE",
    "Finland": "FI",
    "Denmark": "DK",
    "Brazil": "BR",
    "China": "CN",
    "Germany": "DE",
    "France": "FR",
    "United Kingdom": "GB",
}


CODE_TO_COUNTRY_NAME = {v: k for k, v in COUNTRY_NAME_TO_CODE.items()}


def find_bin(name: str) -> str:
    found = shutil.which(name)
    if found:
        return found
    for candidate in (Path.home() / ".local" / "bin" / name, Path("/opt/homebrew/bin") / name):
        if candidate.is_file():
            return str(candidate)
    return name


def run_json_cmd(cmd, input_text=None):
    try:
        res = subprocess.run(cmd, input=input_text, capture_output=True, text=True, timeout=45)
    except Exception as exc:
        return None, str(exc)
    if res.returncode != 0:
        err = (res.stderr or res.stdout or f"exit {res.returncode}").strip()
        return None, err
    out = res.stdout.strip()
    if not out:
        return {}, ""
    try:
        idx = out.find("{")
        if idx >= 0:
            out = out[idx:]
        return json.loads(out), ""
    except Exception as exc:
        return None, f"Invalid JSON: {exc}"


def rc_api_get(rc_bin: str, project_id: str, path: str):
    cmd = [rc_bin, "api", "GET", path, "--project-id", project_id, "--json"]
    data, err = run_json_cmd(cmd)
    if err or data is None:
        return None, err
    if isinstance(data, dict) and "error" in data:
        return None, data["error"].get("message", str(data["error"]))
    return data.get("data", data) if isinstance(data, dict) else data, ""


def fetch_rc_overview(rc_bin: str, project_id: str):
    cmd = [rc_bin, "metrics", "--project-id", project_id, "--json"]
    data, err = run_json_cmd(cmd)
    if err or not data:
        return {}, err
    metrics_list = data.get("data", {}).get("metrics", [])
    overview = {}
    for m in metrics_list:
        mid = m.get("id")
        if mid:
            overview[mid] = {
                "name": m.get("name", mid),
                "value": m.get("value", 0),
                "unit": m.get("unit", ""),
                "period": m.get("period", ""),
                "description": m.get("description", ""),
            }
    return overview, ""


def fetch_rc_revenue_series(rc_bin: str, project_id: str, start_date: str, end_date: str):
    """Fetch daily revenue series across all 3 revenue types segmented by country and product_id."""
    revenue_types = ["revenue", "revenue_net_of_taxes", "proceeds"]
    by_country_daily = {}  # (date, country_code, country_name) -> {revenue, net_tax, proceeds, tx}
    by_product_daily = {}  # (date, product_name) -> {revenue, net_tax, proceeds, tx}

    for rtype in revenue_types:
        sel = urllib.parse.quote(json.dumps({"revenue_type": rtype}))
        # 1. By country
        path_c = f"/projects/{project_id}/charts/revenue?segment=country&selectors={sel}&start_date={start_date}&end_date={end_date}"
        d_c, err_c = rc_api_get(rc_bin, project_id, path_c)
        if not err_c and isinstance(d_c, dict):
            segs = d_c.get("segments") or []
            for v in d_c.get("values") or []:
                val = float(v.get("value") or 0.0)
                if val <= 0:
                    continue
                s_idx = v.get("segment")
                s_name = segs[s_idx]["display_name"] if s_idx is not None and isinstance(s_idx, int) and s_idx < len(segs) else str(s_idx)
                s_id = segs[s_idx].get("id", "") if s_idx is not None and isinstance(s_idx, int) and s_idx < len(segs) else ""
                if s_name == "Total" or s_id == "total":
                    continue
                code = (s_id.upper() if len(s_id) == 2 else COUNTRY_NAME_TO_CODE.get(s_name, s_name[:2].upper()))
                dt_str = dt.datetime.fromtimestamp(v["cohort"], dt.timezone.utc).strftime("%Y-%m-%d")
                key = (dt_str, code, s_name)
                entry = by_country_daily.setdefault(key, {"gross": 0.0, "net_tax": 0.0, "proceeds": 0.0, "tx": 0})
                measure = v.get("measure")
                if measure == 0:
                    if rtype == "revenue":
                        entry["gross"] = val
                    elif rtype == "revenue_net_of_taxes":
                        entry["net_tax"] = val
                    elif rtype == "proceeds":
                        entry["proceeds"] = val
                elif measure == 1 and rtype == "revenue":
                    entry["tx"] = int(round(val))

        # 2. By product_id
        path_p = f"/projects/{project_id}/charts/revenue?segment=product_id&selectors={sel}&start_date={start_date}&end_date={end_date}"
        d_p, err_p = rc_api_get(rc_bin, project_id, path_p)
        if not err_p and isinstance(d_p, dict):
            segs = d_p.get("segments") or []
            for v in d_p.get("values") or []:
                val = float(v.get("value") or 0.0)
                if val <= 0:
                    continue
                s_idx = v.get("segment")
                s_name = segs[s_idx]["display_name"] if s_idx is not None and isinstance(s_idx, int) and s_idx < len(segs) else str(s_idx)
                if s_name == "Total":
                    continue
                dt_str = dt.datetime.fromtimestamp(v["cohort"], dt.timezone.utc).strftime("%Y-%m-%d")
                key = (dt_str, s_name)
                entry = by_product_daily.setdefault(key, {"gross": 0.0, "net_tax": 0.0, "proceeds": 0.0, "tx": 0})
                measure = v.get("measure")
                if measure == 0:
                    if rtype == "revenue":
                        entry["gross"] = val
                    elif rtype == "revenue_net_of_taxes":
                        entry["net_tax"] = val
                    elif rtype == "proceeds":
                        entry["proceeds"] = val
                elif measure == 1 and rtype == "revenue":
                    entry["tx"] = int(round(val))

    return by_country_daily, by_product_daily


def fetch_rc_trials_and_mrr(rc_bin: str, project_id: str, start_date: str, end_date: str):
    """Fetch new trials by country, trial conversions (actives_new), and latest MRR by country."""
    trials_by_country = {}  # (date, code, name) -> count
    d_t, err_t = rc_api_get(rc_bin, project_id, f"/projects/{project_id}/charts/trials_new?segment=country&start_date={start_date}&end_date={end_date}")
    if not err_t and isinstance(d_t, dict):
        segs = d_t.get("segments") or []
        for v in d_t.get("values") or []:
            val = int(round(float(v.get("value") or 0)))
            if val <= 0 or v.get("measure") != 0:
                continue
            s_idx = v.get("segment")
            if s_idx is None or not isinstance(s_idx, int) or s_idx >= len(segs):
                continue
            s_name = segs[s_idx].get("display_name", "")
            s_id = segs[s_idx].get("id", "")
            if s_name == "Total" or s_id == "total":
                continue
            code = s_id.upper() if len(s_id) == 2 else COUNTRY_NAME_TO_CODE.get(s_name, s_name[:2].upper())
            dt_str = dt.datetime.fromtimestamp(v["cohort"], dt.timezone.utc).strftime("%Y-%m-%d")
            trials_by_country[(dt_str, code, s_name)] = val

    mrr_by_country = {}
    d_m, err_m = rc_api_get(rc_bin, project_id, f"/projects/{project_id}/charts/mrr?segment=first_country&start_date={start_date}&end_date={end_date}")
    if not err_m and isinstance(d_m, dict):
        segs = d_m.get("segments") or []
        for v in d_m.get("values") or []:
            if v.get("measure") != 0:
                continue
            s_idx = v.get("segment")
            if s_idx is None or not isinstance(s_idx, int) or s_idx >= len(segs):
                continue
            s_name = segs[s_idx].get("display_name", "")
            if s_name and s_name != "Total":
                mrr_by_country[s_name] = float(v.get("value") or 0.0)

    # Check attribution_campaign status
    d_a, _ = rc_api_get(rc_bin, project_id, f"/projects/{project_id}/charts/revenue?segment=attribution_campaign&start_date={start_date}&end_date={end_date}")
    attr_campaigns = []
    if isinstance(d_a, dict):
        for s in d_a.get("segments") or []:
            name = s.get("display_name", "")
            if name not in ("Total", "No campaign"):
                attr_campaigns.append(name)

    return trials_by_country, mrr_by_country, attr_campaigns


def daily_rows(report, country_by_cid: dict, campaigns_meta: dict) -> dict:
    """(day, campaign id, storefront) -> spend, impressions, taps and installs, from one daily campaign report.
    `installs` is None when the report gave no count for that day: unknown, not zero. A day with nothing is no row."""
    rows = {}
    if not isinstance(report, dict):
        return rows
    for r in (report.get("result") or {}).get("rows") or []:
        cid = int((r.get("metadata") or {}).get("id") or 0)
        meta = campaigns_meta.get(cid, {})
        # without an all-time row the campaign's own targeting says where it ran, when it names exactly one storefront
        country = country_by_cid.get(cid) or (meta["country"] if len(meta.get("countries") or []) == 1 else UNATTRIBUTED)
        for g in r.get("granularMetrics") or []:
            day = g.get("date")
            if not day:
                continue
            spend = float((g.get("localSpend") or {}).get("amount") or 0.0)
            impressions, taps = int(g.get("impressions") or 0), int(g.get("taps") or 0)
            if spend > 0 or impressions > 0 or taps > 0:
                installs = g.get("tapInstalls")
                rows[(day, cid, country)] = {"spend": spend, "impressions": impressions, "taps": taps,
                                             "installs": int(installs) if installs is not None else None}
    return rows


def day_chunks(start: str, end: str, days: int) -> list:
    """[(start, end), ...]: the range cut into pieces of at most `days` days, in order, each day in one piece."""
    first, last, pieces = dt.date.fromisoformat(start), dt.date.fromisoformat(end), []
    while first <= last:
        until = min(first + dt.timedelta(days=days - 1), last)
        pieces.append((first.isoformat(), until.isoformat()))
        first = until + dt.timedelta(days=1)
    return pieces


DAILY_REPORT_DAYS = 90        # Apple Ads gives day-by-day results for at most this many days a request
UNATTRIBUTED = "??"           # the storefront of spend that cannot be tied to one: unknown, not a guess


def fetch_apple_ads_spend(asc_bin: str, account: str, profile: str, start_date: str, end_date: str, app_id: str = None):
    """Fetch Apple Ads campaign metadata, all-time country spend, and daily spend per campaign. One account can
    advertise several apps: with `app_id`, only the campaigns that promote that app are read, so a store never
    holds another app's results."""
    if not account:
        return {}, [], {}
    only_app = [{"field": "promotedObjectId", "operator": "IN", "value": [str(app_id)]}] if app_id else []

    # 1. Campaign metadata (active / paused / on_hold)
    cmd_find = [asc_bin, "ads", "campaigns", "find", "--ad-account", str(account), "--file", "-"]
    if profile:
        cmd_find.extend(["--ads-profile", str(profile)])
    find_data, _ = run_json_cmd(cmd_find, input_text=json.dumps({"pagination": {"offset": 0, "pageSize": 1000}}))
    campaigns_meta = {}
    if isinstance(find_data, dict):
        for c in find_data.get("result") or []:
            if app_id and str(c.get("promotedObjectId")) != str(app_id):
                continue
            cid = int(c.get("id"))
            countries = ((c.get("targeting") or {}).get("countryOrRegion") or {}).get("include") or []
            campaigns_meta[cid] = {
                "id": cid,
                "name": c.get("name", f"Campaign {cid}"),
                "status": c.get("displayStatus") or c.get("status") or "UNKNOWN",
                "countries": countries,
                "country": countries[0] if countries else "??",
                "daily_budget": float(((c.get("dailyBudget") or {}).get("value") or {}).get("amount") or 0.0),
                "start_time": (c.get("startTime") or "")[:10],
                "end_time": (c.get("endTime") or "")[:10],
            }

    # 2. All campaigns (including deleted) total spend grouped by countryOrRegion
    payload_all = {
        "timeRange": {"start": start_date, "end": end_date, "timeZone": "ORTZ"},
        "fields": ["impressions", "taps", "localSpend"],
        "groupBy": ["countryOrRegion"],
        "filters": [{"field": "deleted", "operator": "IN", "value": [True, False]}] + only_app,
        "pagination": {"offset": 0, "pageSize": 100},
    }
    cmd_rep = [asc_bin, "ads", "reports", "apps", "campaigns", "--ad-account", str(account), "--file", "-"]
    if profile:
        cmd_rep.extend(["--ads-profile", str(profile)])
    rep_all, _ = run_json_cmd(cmd_rep, input_text=json.dumps(payload_all))
    all_campaign_rows = []
    if isinstance(rep_all, dict):
        for r in (rep_all.get("result") or {}).get("rows") or []:
            meta = r.get("metadata") or {}
            tot = r.get("totalMetrics") or {}
            cid = int(meta.get("id") or 0)
            country = (meta.get("countryOrRegion") or "??").upper()
            spend = float((tot.get("localSpend") or {}).get("amount") or 0.0)
            impr = int(tot.get("impressions") or 0)
            taps = int(tot.get("taps") or 0)
            c_info = campaigns_meta.get(cid, {})
            all_campaign_rows.append({
                "campaign_id": cid,
                "name": c_info.get("name", f"Historical Campaign {cid}"),
                "status": c_info.get("status", "DELETED" if meta.get("deleted") else "UNKNOWN"),
                "deleted": bool(meta.get("deleted", cid not in campaigns_meta)),
                "country": country,
                "spend": spend,
                "impressions": impr,
                "taps": taps,
                "start_time": c_info.get("start_time", ""),
                "end_time": c_info.get("end_time", ""),
            })

    # 3. Daily granular spend for non-deleted campaigns (and overall daily spend). The install count is asked for
    # too; a CLI or an account that refuses that field is asked again without it, so spend is never lost to it.
    countries_of = {}
    for r in all_campaign_rows:
        countries_of.setdefault(r["campaign_id"], set()).add(r["country"])
    # a campaign that spent in several storefronts has no one country: its daily report is not split by storefront, so
    # its days go to "??" (unattributed) and not to whichever storefront the all-time report happened to list last
    country_by_cid = {cid: next(iter(found)) if len(found) == 1 else UNATTRIBUTED for cid, found in countries_of.items()}
    daily_spend = {}
    for piece_start, piece_end in day_chunks(start_date, end_date, DAILY_REPORT_DAYS):
        for fields in (["impressions", "taps", "tapInstalls", "localSpend"], ["impressions", "taps", "localSpend"]):
            payload_daily = {
                "timeRange": {"start": piece_start, "end": piece_end, "timeZone": "ORTZ", "granularity": "DAILY"},
                "fields": fields,
                "filters": [{"field": "deleted", "operator": "IN", "value": [True, False]}] + only_app,
                "pagination": {"offset": 0, "pageSize": 100},
            }
            rep_daily, _ = run_json_cmd(cmd_rep, input_text=json.dumps(payload_daily))
            found = daily_rows(rep_daily, country_by_cid, campaigns_meta)
            daily_spend.update(found)                   # a day sits in one piece, so nothing is overwritten
            if found or (isinstance(rep_daily, dict) and "result" in rep_daily):
                break                                   # an answer, even an empty one: do not ask again

    return campaigns_meta, all_campaign_rows, daily_spend
