"""Apple Ads, reading only: campaigns, ad groups, keywords. Changes are in ads_actions."""

import json
from pathlib import Path

from aso.commands.ads_actions import cmd_ads_add_keywords, cmd_ads_set_campaign_status
from aso.commands.base import log_error, log_info, resolve_app_identity, run_cmd


def cmd_ads(args):
    """Manage Apple Ads campaigns, ad groups, and targeting keywords."""
    store = Path(args.store).resolve()
    app = resolve_app_identity(store)
    account = app.get("ads_account")
    profile = app.get("ads_profile")

    if not account:
        print(f"Error: Missing Apple Ads account ID. Set **Apple Ads account**: in {store / 'config.md'}")
        return 2

    action = getattr(args, "ads_action", None)
    if action in ("campaigns", "list"):
        return cmd_ads_campaigns(args, account, profile)
    elif action == "adgroups":
        return cmd_ads_adgroups(args, account, profile)
    elif action == "keywords":
        return cmd_ads_keywords(args, account, profile)
    elif action == "add-keywords":
        return cmd_ads_add_keywords(args, account, profile)
    elif action == "pause":
        return cmd_ads_set_campaign_status(args, account, profile, "PAUSED")
    elif action == "resume":
        return cmd_ads_set_campaign_status(args, account, profile, "ENABLED")
    else:
        print("Unknown ads subcommand. Use: campaigns, adgroups, keywords, add-keywords, pause, resume")
        return 1


def cmd_ads_campaigns(args, account, profile):
    log_info(f"Fetching Apple Ads campaigns for account {account}...")
    payload = {"pagination": {"offset": 0, "pageSize": 1000}}
    cmd = ["asc", "ads", "campaigns", "find", "--ad-account", str(account), "--file", "-"]
    if profile:
        cmd.extend(["--ads-profile", str(profile)])
    rc, out, err = run_cmd(cmd, input_text=json.dumps(payload))
    if rc != 0:
        log_error(f"asc ads campaigns find failed: {err}")
        print(f"Error querying campaigns: {err.strip() or f'exit {rc}'}")
        return rc
    try:
        data = json.loads(out)
        campaigns = data.get("result", [])
    except Exception as exc:
        log_error(f"Failed to parse campaigns output: {exc}")
        print(f"Failed to parse campaigns JSON: {exc}")
        return 1

    status_filter = getattr(args, "status", None)
    country_filter = getattr(args, "country", None)

    filtered = []
    for c in campaigns:
        st = c.get("status") or c.get("displayStatus") or ""
        if status_filter and status_filter.upper() != "ALL" and st.upper() != status_filter.upper():
            continue
        countries = (c.get("targeting") or {}).get("countryOrRegion", {}).get("include", [])
        if country_filter and country_filter.upper() not in [ct.upper() for ct in countries]:
            continue
        filtered.append(c)

    if getattr(args, "json", False):
        print(json.dumps(filtered, indent=2))
        return 0

    print(f"\n📢 Apple Ads Campaigns (Account: {account}) — {len(filtered)} campaigns:")
    print(f"{'ID':<12} {'Status':<9} {'Budget':<8} {'Country':<8} {'Name'}")
    print("-" * 75)
    for c in sorted(filtered, key=lambda x: x.get("name", "")):
        cid = str(c.get("id"))
        status = c.get("displayStatus") or c.get("status") or "UNKNOWN"
        budget_val = (c.get("dailyBudget") or {}).get("value", {})
        budget_str = f"${budget_val.get('amount', '?')}/d"
        countries = (c.get("targeting") or {}).get("countryOrRegion", {}).get("include", [])
        country_str = ",".join(countries) if countries else "—"
        name = c.get("name", "")
        print(f"{cid:<12} {status:<9} {budget_str:<8} {country_str:<8} {name}")
    return 0


def cmd_ads_adgroups(args, account, profile):
    campaign_id = getattr(args, "campaign_id", None)
    payload = {"pagination": {"offset": 0, "pageSize": 1000}}
    if campaign_id:
        payload["filters"] = [{"field": "campaignId", "operator": "EQUALS", "value": [int(campaign_id)]}]
    cmd = ["asc", "ads", "ad-groups", "find", "--ad-account", str(account), "--file", "-"]
    if profile:
        cmd.extend(["--ads-profile", str(profile)])
    rc, out, err = run_cmd(cmd, input_text=json.dumps(payload))
    if rc != 0:
        print(f"Error querying ad groups: {err.strip() or f'exit {rc}'}")
        return rc
    try:
        data = json.loads(out)
        groups = data.get("result", [])
    except Exception as exc:
        print(f"Failed to parse ad groups: {exc}")
        return 1

    if getattr(args, "json", False):
        print(json.dumps(groups, indent=2))
        return 0
    print(f"\n📦 Apple Ads Ad Groups — {len(groups)} groups:")
    print(f"{'ID':<12} {'Campaign ID':<13} {'Status':<9} {'Bid':<7} {'Name'}")
    print("-" * 75)
    for g in groups:
        gid = str(g.get("id"))
        cid = str(g.get("campaignId"))
        st = g.get("displayStatus") or g.get("status") or "UNKNOWN"
        bid_amount = ((g.get("bidStrategy") or {}).get("bid") or {}).get("amount", "?")
        bid_str = f"${bid_amount}"
        name = g.get("name", "")
        print(f"{gid:<12} {cid:<13} {st:<9} {bid_str:<7} {name}")
    return 0


def cmd_ads_keywords(args, account, profile):
    adgroup_id = getattr(args, "adgroup_id", None)
    campaign_id = getattr(args, "campaign_id", None)
    payload = {"pagination": {"offset": 0, "pageSize": 1000}}
    filters = []
    if adgroup_id:
        filters.append({"field": "adGroupId", "operator": "EQUALS", "value": [int(adgroup_id)]})
    if campaign_id:
        filters.append({"field": "campaignId", "operator": "EQUALS", "value": [int(campaign_id)]})
    if filters:
        payload["filters"] = filters

    cmd = ["asc", "ads", "targeting-keywords", "find", "--ad-account", str(account), "--file", "-"]
    if profile:
        cmd.extend(["--ads-profile", str(profile)])
    rc, out, err = run_cmd(cmd, input_text=json.dumps(payload))
    if rc != 0:
        print(f"Error querying keywords: {err.strip() or f'exit {rc}'}")
        return rc
    try:
        data = json.loads(out)
        keywords = data.get("result", [])
    except Exception as exc:
        print(f"Failed to parse keywords: {exc}")
        return 1

    if getattr(args, "json", False):
        print(json.dumps(keywords, indent=2))
        return 0
    print(f"\n🎯 Apple Ads Targeting Keywords — {len(keywords)} keywords:")
    print(f"{'ID':<12} {'Match':<7} {'Bid':<7} {'Status':<9} {'Keyword Text'}")
    print("-" * 75)
    for kw in keywords[:100]:
        kid = str(kw.get("id"))
        match = kw.get("matchType", "EXACT")
        bid_amount = (kw.get("bid") or {}).get("amount", "?")
        bid_str = f"${bid_amount}"
        st = kw.get("displayStatus") or kw.get("status") or "UNKNOWN"
        text = kw.get("text", "")
        print(f"{kid:<12} {match:<7} {bid_str:<7} {st:<9} {text}")
    if len(keywords) > 100:
        print(f"... and {len(keywords) - 100} more keywords.")
    return 0
