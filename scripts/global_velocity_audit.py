#!/usr/bin/env python3
"""
global_velocity_audit.py — Global Audit of Competitor Review Velocity, Recency & Vulnerability across all 649 queries.

Reads:
  marketing/reports/global_audit.json (query-market pairs)

Audits:
  - Top 1, Top 2, Top 3 competitors per query via live iTunes Search API
  - Competitor review velocity (30d/90d) & recency via Apple Customer Reviews RSS
  - App update recency (days since currentVersionReleaseDate)
  - Classification: 🎯 Soft Target (<50 reviews), 💤 Sleeping Giant (dormant reviews), 🪦 Outdated (>180d no update), 🔥 Active Defender
  - Identifies the exact "Sweet Spot" queries across all 25 markets

Outputs:
  - marketing/reports/global_velocity_audit_2026-09-08.json
  - marketing/reports/global_velocity_audit_2026-09-08.md
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# Thread-safe caches to avoid re-fetching reviews for the same app in the same country
_REVIEWS_CACHE: dict[tuple[str, int], dict] = {}
_CACHE_LOCK = threading.Lock()

MARKET_WEIGHT: dict[str, float] = {
    "us": 100, "jp": 22,  "cn": 30,  "gb": 14,  "de": 13,
    "fr": 10,  "kr": 8,   "in": 8,   "au": 7,   "ca": 7,
    "es": 7,   "it": 7,   "br": 7,   "ru": 5,   "tw": 5,
    "mx": 5,   "nl": 4,   "tr": 4,   "pl": 4,   "sa": 4,
    "se": 3,   "hk": 3,   "sg": 3,   "ua": 2,   "il": 2,
}

def fetch_json(url: str, timeout: float = 8.0, retries: int = 2) -> dict | None:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode())
        except Exception:
            if attempt < retries - 1:
                time.sleep(0.5)
    return None

def get_app_recent_reviews(country: str, app_id: int) -> dict:
    key = (country, app_id)
    with _CACHE_LOCK:
        if key in _REVIEWS_CACHE:
            return _REVIEWS_CACHE[key]
            
    url = f"https://itunes.apple.com/{country}/rss/customerreviews/id={app_id}/sortBy=mostRecent/json"
    data = fetch_json(url)
    
    res = {
        "has_rss_feed": False,
        "feed_review_count": 0,
        "days_since_last_review": None,
        "velocity_30d": 0,
        "velocity_90d": 0,
        "recent_rating": None,
        "last_review_date": None
    }
    
    if data:
        entries = data.get("feed", {}).get("entry", [])
        review_entries = [e for e in entries if isinstance(e, dict) and "updated" in e and "im:rating" in e]
        if review_entries:
            now = datetime.now(timezone.utc)
            dates = []
            ratings = []
            for r in review_entries:
                try:
                    dt = datetime.fromisoformat(r["updated"]["label"])
                    dates.append(dt)
                    ratings.append(int(r["im:rating"]["label"]))
                except Exception:
                    continue
            if dates:
                days_since = (now - dates[0]).days
                v_30d = sum(1 for d in dates if (now - d).days <= 30)
                v_90d = sum(1 for d in dates if (now - d).days <= 90)
                recent_avg = sum(ratings[:10]) / len(ratings[:10]) if ratings else None
                res = {
                    "has_rss_feed": True,
                    "feed_review_count": len(dates),
                    "days_since_last_review": days_since,
                    "velocity_30d": v_30d,
                    "velocity_90d": v_90d,
                    "recent_rating": round(recent_avg, 2) if recent_avg else None,
                    "last_review_date": dates[0].strftime("%Y-%m-%d")
                }
                
    with _CACHE_LOCK:
        _REVIEWS_CACHE[key] = res
    return res

def analyze_app(country: str, app: dict, rank: int) -> dict:
    app_id = app.get("trackId")
    name = app.get("trackName", "Unknown")
    total_ratings = app.get("userRatingCount", 0)
    avg_rating = round(app.get("averageUserRating", 0.0), 2)
    current_ver_date = app.get("currentVersionReleaseDate", "")
    seller = app.get("sellerName", "")
    
    now = datetime.now(timezone.utc)
    days_since_update = None
    if current_ver_date:
        try:
            up_dt = datetime.fromisoformat(current_ver_date.replace("Z", "+00:00"))
            days_since_update = (now - up_dt).days
        except Exception:
            pass
            
    reviews = get_app_recent_reviews(country, app_id)
    days_last_rev = reviews["days_since_last_review"]
    v_30d = reviews["velocity_30d"]
    
    # Classification
    if total_ratings < 50:
        classification = "🎯 Soft Target"
        vuln = 9.0
    elif days_last_rev is not None and days_last_rev > 90:
        classification = "💤 Sleeping Giant"
        vuln = 8.5
    elif days_since_update is not None and days_since_update > 180:
        classification = "🪦 Outdated Incumbent"
        vuln = 8.0
    elif v_30d >= 8:
        classification = "🔥 Active Defender"
        vuln = 3.0
    else:
        classification = "⚡ Moderate Defender"
        vuln = 5.0
        
    if avg_rating < 4.2:
        vuln = min(10.0, vuln + 1.0)
    if total_ratings > 10000 and v_30d > 4:
        vuln = max(1.0, vuln - 3.0)
        
    return {
        "rank": rank,
        "app_id": app_id,
        "name": name,
        "seller": seller,
        "total_ratings": total_ratings,
        "avg_rating": avg_rating,
        "days_since_update": days_since_update,
        "days_since_last_review": days_last_rev,
        "velocity_30d": v_30d,
        "velocity_90d": reviews["velocity_90d"],
        "classification": classification,
        "vulnerability": round(vuln, 1)
    }

def audit_query(country: str, term: str, base_meta: dict) -> dict:
    url = f"https://itunes.apple.com/search?term={urllib.parse.quote(term)}&country={country}&entity=software&limit=5"
    data = fetch_json(url)
    results = data.get("results", []) if data else []
    
    our_rank = None
    competitors = []
    for idx, app in enumerate(results, 1):
        bundle = app.get("bundleId", "")
        track_id = app.get("trackId")
        target_bundle = os.environ.get("TARGET_BUNDLE", "")
        if target_bundle and (bundle == target_bundle or target_bundle.lower() in name.lower()):
            if our_rank is None:
                our_rank = idx
        comp = analyze_app(country, app, idx)
        competitors.append(comp)
        
    top1 = competitors[0] if competitors else None
    top2 = competitors[1] if len(competitors) > 1 else None
    top3 = competitors[2] if len(competitors) > 2 else None
    
    # Calculate query vulnerability (average of Top 3)
    top3_comps = [c for c in competitors[:3] if c]
    avg_vuln = sum(c["vulnerability"] for c in top3_comps) / len(top3_comps) if top3_comps else 0.0
    
    # Sweet spot determination:
    # 1. Top 1 has 15-50 reviews (proven searches, beatable), OR
    # 2. Top 1 has <15 reviews, but Top 2/3 has 15-50 reviews, OR
    # 3. Top 1 is Sleeping Giant (0 recent reviews in >90d)
    is_sweet_spot = False
    sweet_spot_reason = "Standard"
    
    if top1:
        t1_ratings = top1["total_ratings"]
        t1_class = top1["classification"]
        t1_vel = top1["velocity_30d"]
        
        if 15 <= t1_ratings <= 60 and t1_vel <= 2:
            is_sweet_spot = True
            sweet_spot_reason = "🎯 15-60 Reviews Sweet Spot (Active Search, Beatable)"
        elif t1_class == "💤 Sleeping Giant":
            is_sweet_spot = True
            sweet_spot_reason = "💤 Sleeping Giant at #1 (Dormant >90d)"
        elif t1_class == "🎯 Soft Target" and (top2 and 15 <= top2["total_ratings"] <= 100):
            is_sweet_spot = True
            sweet_spot_reason = "🎯 Top 1 Soft (<50) + Top 2 Validated Traffic"
        elif t1_class == "🪦 Outdated Incumbent":
            is_sweet_spot = True
            sweet_spot_reason = "🪦 Outdated #1 (>180d without app update)"
            
    # Market weight & overall priority score
    mkt_w = MARKET_WEIGHT.get(country, 2.0)
    # Opportunity score: combines Market Size × Query Vulnerability × Sweet Spot Bonus
    sweet_mult = 1.4 if is_sweet_spot else 1.0
    opp_score = round(mkt_w * (avg_vuln / 10.0) * sweet_mult, 1)
    
    priority = "P3 - Defended"
    if is_sweet_spot and avg_vuln >= 7.5:
        priority = "P0 - Prime Attack Target"
    elif avg_vuln >= 7.0 or is_sweet_spot:
        priority = "P1 - High Opportunity"
    elif avg_vuln >= 5.5:
        priority = "P2 - Secondary"
        
    return {
        "country": country.upper(),
        "country_code": country,
        "term": term,
        "total_results": len(results),
        "our_rank": our_rank if our_rank is not None else base_meta.get("our_rank"),
        "market_weight": mkt_w,
        "query_vulnerability": round(avg_vuln, 1),
        "is_sweet_spot": is_sweet_spot,
        "sweet_spot_reason": sweet_spot_reason,
        "opportunity_score": opp_score,
        "priority": priority,
        "top1": top1,
        "top2": top2,
        "top3": top3,
        "all_competitors": competitors
    }

def _self_check() -> int:
    # Test market weights
    assert MARKET_WEIGHT["us"] == 100
    assert MARKET_WEIGHT["ua"] == 2
    
    # Test app classification logic
    # 1. Soft target
    soft = analyze_app("us", {"trackId": 1, "trackName": "Soft App", "userRatingCount": 20, "averageUserRating": 4.5}, 1)
    assert soft["classification"] == "🎯 Soft Target"
    assert soft["vulnerability"] >= 9.0
    
    # 2. Low rating bonus
    low_rated = analyze_app("us", {"trackId": 2, "trackName": "Buggy App", "userRatingCount": 20, "averageUserRating": 3.8}, 1)
    assert low_rated["vulnerability"] == 10.0
    
    # 3. Active defender
    # Mock cache
    with _CACHE_LOCK:
        _REVIEWS_CACHE[("us", 3)] = {
            "has_rss_feed": True,
            "feed_review_count": 20,
            "days_since_last_review": 2,
            "velocity_30d": 15,
            "velocity_90d": 40,
            "recent_rating": 4.8,
            "last_review_date": "2026-09-01"
        }
    defender = analyze_app("us", {"trackId": 3, "trackName": "Big App", "userRatingCount": 50000, "averageUserRating": 4.8}, 1)
    assert defender["classification"] == "🔥 Active Defender"
    assert defender["vulnerability"] <= 3.0
    
    print("OK — market weights, classifications, and vulnerability scoring verified.")
    print("Self-check passed successfully.")
    return 0

def main():
    parser = argparse.ArgumentParser(description="Global velocity and vulnerability audit across all queries")
    parser.add_argument("--self-check", action="store_true", help="Run self-tests and exit")
    parser.add_argument("--input", default="marketing/reports/global_audit.json")
    parser.add_argument("--output-json", default="marketing/reports/global_velocity_audit_2026-09-08.json")
    parser.add_argument("--output-md", default="marketing/reports/global_velocity_audit_2026-09-08.md")
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    
    if args.self_check:
        sys.exit(_self_check())
    
    if not os.path.exists(args.input):
        print(f"Error: input file {args.input} not found!")
        sys.exit(1)
        
    with open(args.input, "r", encoding="utf-8") as f:
        global_audit_data = json.load(f)
        
    tasks = []
    for country, items in global_audit_data.items():
        for item in items:
            tasks.append((country, item["term"], item))
            
    total_tasks = len(tasks)
    print(f"Starting Global Velocity & Vulnerability Audit for {total_tasks} queries across {len(global_audit_data)} markets...")
    print(f"Using ThreadPoolExecutor with {args.workers} workers and deduplicating review feeds.\n")
    
    start_t = time.time()
    results = []
    completed = 0
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(audit_query, cc, term, meta): (cc, term) for cc, term, meta in tasks}
        for fut in concurrent.futures.as_completed(futures):
            cc, term = futures[fut]
            completed += 1
            try:
                res = fut.result()
                results.append(res)
                if completed % 50 == 0 or completed == total_tasks:
                    elapsed = time.time() - start_t
                    print(f"  [{completed}/{total_tasks}] ({(completed/total_tasks)*100:.1f}%) in {elapsed:.1f}s — Cached {len(_REVIEWS_CACHE)} unique apps")
            except Exception as e:
                print(f"  ✗ Error on {cc} '{term}': {e}")
                
    # Sort results by opportunity_score descending
    results.sort(key=lambda x: x["opportunity_score"], reverse=True)
    
    # Save full JSON
    Path(args.output_json).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output_json, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\nSaved complete JSON audit to {args.output_json}")
    
    # Aggregate Stats
    sweet_spots = [r for r in results if r.get("is_sweet_spot")]
    sleeping_giants = [r for r in results if (r.get("top1") or {}).get("classification") == "💤 Sleeping Giant"]
    soft_targets = [r for r in results if (r.get("top1") or {}).get("classification") == "🎯 Soft Target"]
    active_defenders = [r for r in results if (r.get("top1") or {}).get("classification") == "🔥 Active Defender"]
    p0_targets = [r for r in results if r.get("priority") == "P0 - Prime Attack Target"]
    
    # Build Markdown Summary
    lines = [
        "# Global App Store Velocity, Recency & Vulnerability Audit (649 Queries)",
        f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M UTC')} | **Total Queries Analyzed:** {len(results)} across 25 markets",
        "",
        "## 📊 Executive Summary & Market Intelligence",
        "",
        f"- **Total Queries Audited:** {len(results)}",
        f"- **Unique Top Competitors Analyzed via Apple RSS:** {len(_REVIEWS_CACHE)}",
        f"- **🎯 Sweet Spot Opportunities (Traffic Confirmed + Highly Beatable):** **{len(sweet_spots)} queries ({len(sweet_spots)/len(results)*100:.1f}%)**",
        f"- **💤 Sleeping Giants at #1 (Dormant >90 days, Zero Recent Velocity):** **{len(sleeping_giants)} queries**",
        f"- **🎯 Soft Targets at #1 (<50 ratings, Minimal Defense):** **{len(soft_targets)} queries**",
        f"- **🔥 Heavily Defended at #1 (Active daily reviews / ASA defenders):** **{len(active_defenders)} queries** (DO NOT ATTACK)",
        f"- **🚀 P0 Immediate Attack Targets:** **{len(p0_targets)} queries**",
        "",
        "---",
        "",
        "## 🏆 Top 35 Global Attack Targets (Highest Opportunity Score)",
        "_Opportunity Score = Market Weight × Query Vulnerability × Sweet Spot Multiplier. Sorted by easiest takeover of high-value traffic._",
        "",
        "| # | Mkt | Query | Opp Score | Query Vuln | Top 1 Competitor | Top 1 Ratings | Last Review | 30d Vel | Last Update | Sweet Spot Reason |",
        "|---|---|---|---|---|---|---|---|---|---|---|"
    ]
    
    for idx, r in enumerate(results[:35], 1):
        t1 = r.get("top1") or {}
        name = t1.get("name", "N/A")[:18]
        ratings = f"{t1.get('total_ratings', 0)}★"
        last_rev = f"{t1.get('days_since_last_review')}d ago" if t1.get('days_since_last_review') is not None else "No RSS"
        v30 = f"{t1.get('velocity_30d', 0)}/mo"
        last_up = f"{t1.get('days_since_update')}d ago" if t1.get('days_since_update') is not None else "N/A"
        reason = r["sweet_spot_reason"]
        
        lines.append(f"| {idx} | {r['country']} | `{r['term']}` | **{r['opportunity_score']}** | {r['query_vulnerability']}/10 | {name} | {ratings} | {last_rev} | {v30} | {last_up} | {reason} |")
        
    lines.append("\n---\n")
    lines.append("## 🌍 Key Market Breakdowns (P0 & P1 Opportunities)\n")
    
    focus_markets = ["US", "DE", "GB", "FR", "PL", "UA", "NL", "ES", "IT", "JP", "KR"]
    for m in focus_markets:
        m_results = [r for r in results if r["country"] == m and r["priority"] in ["P0 - Prime Attack Target", "P1 - High Opportunity"]]
        if not m_results:
            continue
        lines.append(f"### {m} (Top Opportunities: {len(m_results)})")
        lines.append("| Query | Opp Score | Top 1 Competitor | Total Ratings | 30d Velocity | Last Update | Strategy |")
        lines.append("|---|---|---|---|---|---|---|")
        for r in m_results[:8]:
            t1 = r.get("top1") or {}
            name = t1.get("name", "N/A")[:20]
            ratings = f"{t1.get('total_ratings', 0)}★ ({t1.get('avg_rating', 0)})"
            v30 = f"{t1.get('velocity_30d', 0)} rev/mo"
            last_up = f"{t1.get('days_since_update')}d ago" if t1.get('days_since_update') is not None else "N/A"
            strat = r["sweet_spot_reason"]
            lines.append(f"| `{r['term']}` | **{r['opportunity_score']}** | {name} | {ratings} | {v30} | {last_up} | {strat} |")
        lines.append("")
        
    Path(args.output_md).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output_md, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
        
    print(f"Saved Markdown report to {args.output_md}")
    print(f"Total time: {time.time() - start_t:.1f}s")

if __name__ == "__main__":
    main()
