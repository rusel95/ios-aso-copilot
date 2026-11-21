"""Google search intelligence: trends, suggestions, the anchored batch."""

import json
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

from aso.commands.base import ENTRY, SKILL_DIR, log_error, log_info, log_warn
from aso.commands.keywords import record_found


def cmd_google(args):
    """Google Search Intelligence: Trends, Autocomplete suggestions, and Batch volume profiling."""
    action = getattr(args, "google_action", None)
    if not action:
        log_error("Specify a google action: 'trends', 'suggest', or 'batch'")
        return 1
    if action == "trends":
        return cmd_google_trends(args)
    elif action == "suggest":
        return cmd_google_suggest(args)
    elif action == "batch":
        return cmd_google_batch(args)
    else:
        log_error(f"Unknown google action: {action}")
        return 1


def _trend_req():
    """(TrendReq, None), or (None, exit code) after re-running this command inside the skill's .venv.

    pytrends is an unofficial scraper of Google Trends and is not a dependency of the rest of the skill, so it lives in
    `<skill>/.venv`. Nothing here may name a user's home directory: the repo is public and shared across apps.
    """
    try:
        from pytrends.request import TrendReq
        return TrendReq, None
    except ImportError:
        venv_py = SKILL_DIR / ".venv" / "bin" / "python3"
        if venv_py.exists() and str(sys.executable) != str(venv_py):
            return None, subprocess.run([str(venv_py), str(ENTRY)] + sys.argv[1:]).returncode
        log_error(f"pytrends is not installed. Install it with: python3 -m venv {SKILL_DIR}/.venv && "
                  f"{SKILL_DIR}/.venv/bin/pip install pytrends")
        return None, 1


def cmd_google_trends(args):
    """Compare search interest via Google Trends."""
    terms = getattr(args, "terms", [])
    if not terms:
        log_error("Specify at least one keyword term to compare.")
        return 1

    country = getattr(args, "country", "US")
    timeframe = getattr(args, "timeframe", "today 12-m")
    as_json = getattr(args, "json", False)
    do_related = getattr(args, "related", False)
    do_geo = getattr(args, "geo", False)

    TrendReq, code = _trend_req()
    if TrendReq is None:
        return code

    pytrend = TrendReq(hl="en-US", tz=180, timeout=(10, 30))

    # 1. Related queries mode
    if do_related:
        target = terms[0]
        log_info(f"Querying Google Trends related queries for '{target}' in {country} ({timeframe})...")
        try:
            pytrend.build_payload([target], cat=0, timeframe=timeframe, geo=country)
            rq = pytrend.related_queries()
        except Exception as exc:
            log_error(f"Google Trends query failed: {exc}")
            return 1

        top_df = rq.get(target, {}).get("top") if rq else None
        rising_df = rq.get(target, {}).get("rising") if rq else None

        top_list = top_df.to_dict(orient="records") if top_df is not None and not top_df.empty else []
        rising_list = rising_df.to_dict(orient="records") if rising_df is not None and not rising_df.empty else []

        if as_json:
            print(json.dumps({"target": target, "country": country, "timeframe": timeframe, "top": top_list, "rising": rising_list}, ensure_ascii=False, indent=2))
            return 0

        print(f"\n📡 Google Trends Related Queries for '{target}' in {country.upper()} ({timeframe}):")
        print("\n🔥 RISING QUERIES (Breakouts & Emerging Trends):")
        if rising_list:
            for item in rising_list[:10]:
                q = item.get("query", "")
                val = item.get("value", "")
                val_str = f"+{val}%" if isinstance(val, (int, float)) and val < 5000 else "Breakout (Explosive)"
                print(f"  • {q:<35} {val_str}")
        else:
            print("  (No rising queries detected for this period/country)")

        print("\n🔝 TOP RELATED QUERIES (Highest Search Volume):")
        if top_list:
            for item in top_list[:10]:
                q = item.get("query", "")
                val = item.get("value", "")
                print(f"  • {q:<35} (Score: {val})")
        else:
            print("  (No top related queries returned)")
        print()
        return 0

    # 2. Subregion Geo breakdown mode
    if do_geo:
        log_info(f"Querying Google Trends subregion breakdown for {terms[:5]} in {country} ({timeframe})...")
        try:
            pytrend.build_payload(terms[:5], cat=0, timeframe=timeframe, geo=country)
            geo_df = pytrend.interest_by_region(resolution="REGION", inc_low_vol=True, inc_geo_code=True)
        except Exception as exc:
            log_error(f"Google Trends geo query failed: {exc}")
            return 1

        if geo_df.empty:
            log_warn("No subregion data available.")
            return 0

        active_regions = geo_df[(geo_df[terms[:5]] > 0).any(axis=1)]
        if as_json:
            print(active_regions.to_json(orient="index", force_ascii=False, indent=2))
            return 0

        print(f"\n🗺️ Google Trends Subregion Interest Breakdown in {country.upper()} ({timeframe}):")
        for region_name, row in active_regions.head(15).iterrows():
            scores_str = ", ".join(f"{kw}: {row[kw]}" for kw in terms[:5] if kw in row)
            print(f"  • {region_name:<30} [{scores_str}]")
        print()
        return 0

    # 3. Standard comparison mode
    log_info(f"Querying Google Trends for {terms[:5]} in {country} ({timeframe})...")
    try:
        pytrend.build_payload(terms[:5], cat=0, timeframe=timeframe, geo=country)
        df = pytrend.interest_over_time()
    except Exception as exc:
        log_error(f"Google Trends query failed: {exc}")
        return 1

    if df.empty:
        log_warn("No direct trend data returned (queries may have low volume or Google rate-limited).")
        if as_json:
            print(json.dumps({"terms": terms, "country": country, "timeframe": timeframe, "scores": {}}))
        return 0

    means = {kw: float(df[kw].mean()) for kw in terms if kw in df}
    max_val = max(means.values()) if means else 1.0

    if as_json:
        res = {
            "country": country,
            "timeframe": timeframe,
            "scores": means,
            "relative_ratios": {kw: round(v / max_val, 3) for kw, v in means.items()} if max_val > 0 else {}
        }
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0

    print(f"\n📡 Google Trends Search Interest in {country.upper()} ({timeframe}):")
    print(f"   (Relative score 0-100 scale, normalized against peak)\n")
    first_val = list(means.values())[0] if means else 1.0
    for kw, val in sorted(means.items(), key=lambda x: x[1], reverse=True):
        bar = "█" * int((val / max_val) * 25) if max_val > 0 else ""
        ratio = (val / first_val) if first_val > 0 else 0
        print(f"  {kw:<30} {val:5.1f}  {bar:<25} ({ratio:.2f}x)")
    print()
    return 0


def cmd_google_suggest(args):
    """Live Google search autocomplete hints across storefronts and languages."""
    term = getattr(args, "term", "").strip()
    if not term:
        log_error("Specify a search term to inspect suggestions.")
        return 1

    country = getattr(args, "country", "US")
    lang = getattr(args, "lang", "uk")
    limit = getattr(args, "limit", 15)
    matrix = getattr(args, "matrix", False)
    as_json = getattr(args, "json", False)

    def fetch_suggestions(q):
        url = f"https://suggestqueries.google.com/complete/search?client=chrome&q={urllib.parse.quote(q)}&hl={lang}&gl={country}"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
        )
        try:
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data[1] if len(data) > 1 else []
        except Exception:
            return []

    # Matrix expansion mode
    if matrix:
        log_info(f"Generating Google Autocomplete Intent Matrix for '{term}' [{country.upper()}/{lang}]...")
        if lang in ("uk", "ru"):
            modifiers = [
                ("how", f"як {term}"),
                ("what_tool", f"чим {term}"),
                ("for_platform", f"{term} для"),
                ("to_size", f"{term} до"),
                ("without_friction", f"{term} без"),
                ("on_device", f"{term} на"),
                ("app_tool", f"{term} програма"),
                ("app_tool2", f"{term} додаток"),
                ("online_fast", f"{term} онлайн"),
            ]
        else:
            modifiers = [
                ("how", f"how to {term}"),
                ("best", f"best {term}"),
                ("for_platform", f"{term} for"),
                ("to_size", f"{term} to"),
                ("without_friction", f"{term} without"),
                ("on_device", f"{term} on"),
                ("app_tool", f"{term} app"),
                ("online_fast", f"{term} online"),
            ]

        discovered = {}
        for mod_key, mod_q in modifiers:
            suggs = fetch_suggestions(mod_q)
            for s in suggs:
                if s not in discovered:
                    discovered[s] = mod_key
        if getattr(args, "record", False):
            record_found(args, country.lower(), list(discovered), "google-suggest")

        categories = {
            "platforms": [],
            "size_limits": [],
            "quality_constraints": [],
            "devices": [],
            "questions": [],
            "tools_and_apps": [],
            "other": []
        }

        platform_kw = ("телеграм", "telegram", "вайбер", "viber", "інстаграм", "instagram", "фейсбук", "facebook", "whatsapp", "вотсап", "дискорд", "discord", "пошт", "mail", "gmail")
        size_kw = ("мб", "mb", "гб", "gb", "розмір", "размер", "size", "ваг")
        quality_kw = ("без втрати якості", "без потери качества", "якість", "качество", "watermark", "водяного знаку", "безкоштовно", "бесплатно", "free", "онлайн", "online")
        device_kw = ("айфон", "iphone", "ios", "телефон", "мак", "mac", "пк", "комп'ютер", "компьютер", "андроїд", "android")
        question_kw = ("як", "как", "чим", "чем", "how", "why")
        tool_kw = ("додаток", "приложение", "програма", "программа", "app", "софт", "converter", "компресор", "compressor")

        for s in discovered.keys():
            s_lower = s.lower()
            if any(k in s_lower for k in platform_kw):
                categories["platforms"].append(s)
            elif any(k in s_lower for k in size_kw):
                categories["size_limits"].append(s)
            elif any(k in s_lower for k in quality_kw):
                categories["quality_constraints"].append(s)
            elif any(k in s_lower for k in device_kw):
                categories["devices"].append(s)
            elif any(k in s_lower for k in question_kw):
                categories["questions"].append(s)
            elif any(k in s_lower for k in tool_kw):
                categories["tools_and_apps"].append(s)
            else:
                categories["other"].append(s)

        if as_json:
            print(json.dumps({"seed": term, "country": country, "lang": lang, "categories": categories}, ensure_ascii=False, indent=2))
            return 0

        print(f"\n🌐 Google Autocomplete Deep Intent Matrix for '{term}' [{country.upper()}/{lang}]:")
        print(f"   (Discovered {len(discovered)} verified high-intent long-tail search phrases)\n")

        icons = {
            "platforms": "📱 Platforms & Messengers (High Conversion)",
            "size_limits": "💾 File Size & Storage Limits",
            "quality_constraints": "⚙️ Quality & Friction Expectations",
            "devices": "🍎 Devices & Ecosystem Targets",
            "questions": "❓ Question & How-to Triggers (SEO / FAQ)",
            "tools_and_apps": "🛠️ Direct Tool & App Intent (Prime ASA)",
            "other": "🔍 Additional Discovered Terms"
        }

        for cat_key, title in icons.items():
            items = categories[cat_key]
            if items:
                print(f"[{title}]:")
                for item in items[:8]:
                    print(f"  • {item}")
                print()
        return 0

    # Standard suggestions
    suggestions = fetch_suggestions(term)[:limit]
    if getattr(args, "record", False):
        record_found(args, country.lower(), suggestions, "google-suggest")
    if as_json:
        print(json.dumps(suggestions, ensure_ascii=False, indent=2))
        return 0

    print(f"\n🔍 Live Google Autocomplete Suggestions for '{term}' [{country.upper()}/{lang}]:")
    print(f"   (Found {len(suggestions)} suggestions)\n")
    for i, s in enumerate(suggestions, 1):
        print(f"  {i:2d}. {s}")
    print()
    return 0


# Trends returns whole numbers 0-100 per week. An anchor that averages below this leaves large ratios dividing by a
# rounding error (a run on 2026-10-17 anchored on an index of ~6 and printed 13.08x, 1,307.6 and 2,694.0 for neighbouring
# spellings), so the table is then only an ORDER.
GOOGLE_ANCHOR_FLOOR = 8.0


def google_ratio(candidate_mean, anchor_mean):
    """Index with the anchor at 100, or None when the anchor cannot support a ratio (0 or missing)."""
    if anchor_mean is None or anchor_mean <= 0:
        return None
    return round(candidate_mean / anchor_mean * 100.0, 1)


def cmd_google_batch(args):
    """Relative demand of many keywords against one anchor: four candidates plus the anchor per Trends request.

    Never prints a number it cannot support: a throttled (empty) response and a zero anchor give `n/a`, and a candidate
    that Trends rounds to 0 next to the anchor is "below Trends' floor", not "no demand".
    """
    anchor = getattr(args, "anchor", None)
    terms_arg = getattr(args, "terms", None)
    file_arg = getattr(args, "file", None)
    country = getattr(args, "country", "US")
    timeframe = getattr(args, "timeframe", "today 12-m")
    delay = getattr(args, "delay", 1.5)
    as_json = getattr(args, "json", False)

    TrendReq, code = _trend_req()
    if TrendReq is None:
        return code

    candidates = []
    if file_arg:
        fpath = Path(file_arg)
        if not fpath.exists():
            log_error(f"Candidate file not found: {file_arg}")
            return 1
        with open(fpath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    parts = [p.strip() for p in line.split(",") if p.strip()]
                    candidates.extend(parts)
    elif terms_arg:
        if isinstance(terms_arg, list):
            candidates = [t.strip() for t in terms_arg if t.strip()]
        else:
            candidates = [t.strip() for t in terms_arg.split(",") if t.strip()]

    if not candidates:
        log_error("Provide candidates via --terms 'kw1,kw2' or --file path/to/file.txt")
        return 1

    if not anchor:
        anchor = candidates[0]
        candidates = candidates[1:]
    else:
        candidates = [c for c in candidates if c.lower() != anchor.lower()]

    seen = set([anchor.lower()])
    unique_cands = []
    for c in candidates:
        if c.lower() not in seen:
            seen.add(c.lower())
            unique_cands.append(c)

    if not unique_cands:
        log_error("No distinct candidates to compare against anchor.")
        return 1

    log_info(f"Starting Google Trends Batch Profiling: {len(unique_cands)} candidates against Anchor '{anchor}' in {country} ({timeframe})...")

    pytrend = TrendReq(hl="en-US", tz=180, timeout=(10, 30))

    chunk_size = 4
    chunks = [unique_cands[i:i + chunk_size] for i in range(0, len(unique_cands), chunk_size)]

    scores = {anchor: 100.0}   # term -> index; None = unavailable
    notes = {}                 # term -> why it has no number, or what 0.0 means
    anchor_means = []

    for idx, chunk in enumerate(chunks, 1):
        batch = [anchor] + chunk
        log_info(f"Processing Batch {idx}/{len(chunks)}: {batch}...")
        df = None
        try:
            pytrend.build_payload(batch, cat=0, timeframe=timeframe, geo=country)
            df = pytrend.interest_over_time()
        except Exception as exc:
            log_error(f"Batch {idx} failed: {exc}")
        if df is None or df.empty or anchor not in df:
            # Google answers a throttled request with an empty frame: that is "no data", never "no demand".
            log_warn(f"Batch {idx} returned no data; its terms are n/a, not zero.")
            for c in chunk:
                scores[c], notes[c] = None, "no data"
        else:
            anchor_mean = float(df[anchor].mean())
            anchor_means.append(anchor_mean)
            for c in chunk:
                if c not in df:
                    scores[c], notes[c] = None, "no data"
                    continue
                c_mean = float(df[c].mean())
                scores[c] = google_ratio(c_mean, anchor_mean)
                if scores[c] is None:
                    notes[c] = "anchor read 0"
                elif c_mean == 0:
                    notes[c] = "below Trends' floor"
        if idx < len(chunks):
            time.sleep(delay)

    ranked = sorted(((v, k) for k, v in scores.items() if v is not None and k != anchor))
    warnings = []
    if anchor_means and min(anchor_means) < GOOGLE_ANCHOR_FLOOR:
        pick = ranked[(len(ranked) - 1) // 2][1] if ranked else None  # lower median: a mid-volume term, not the top one
        warnings.append(
            f"Anchor '{anchor}' averaged {min(anchor_means):.1f} on Trends' 0-100 scale (below {GOOGLE_ANCHOR_FLOOR:g}): "
            "the multipliers divide by a rounding error, so read the ORDER, not the sizes."
            + (f" Re-run with a mid-volume anchor, e.g. '{pick}'." if pick else ""))

    valid_items = [(k, v) for k, v in scores.items() if v is not None]
    sorted_scores = sorted(valid_items, key=lambda x: x[1], reverse=True)
    unavailable = [k for k, v in scores.items() if v is None]

    if as_json:
        print(json.dumps({"anchor": anchor, "country": country, "timeframe": timeframe,
                          "scores": dict(sorted_scores), "notes": notes, "unavailable": unavailable,
                          "anchor_means": anchor_means, "warnings": warnings}, ensure_ascii=False, indent=2))
        return 0

    max_val = sorted_scores[0][1] if sorted_scores else 100.0
    print(f"\n📊 Google Trends Batch Profiling in {country.upper()} ({timeframe}):")
    print(f"   (Index against Anchor '{anchor}' = 100.0; Google web search, relative, languages mixed)\n")
    print(f"  {'Rank':<4} {'Keyword':<32} {'Index':>10}   {'Visual Scale':<22} {'Note'}")
    print(f"  {'-'*4} {'-'*32} {'-'*10}   {'-'*22} {'-'*20}")

    for rank, (kw, val) in enumerate(sorted_scores, 1):
        bar = "█" * (int((val / max_val) * 20) if max_val > 0 else 0)
        note = "[ANCHOR]" if kw.lower() == anchor.lower() else notes.get(kw, "")
        print(f"  {rank:<4d} {kw:<32} {val:>10.1f}   {bar:<22} {note}")
    for kw in unavailable:
        print(f"  {'-':<4} {kw:<32} {'n/a':>10}   {'':<22} {notes.get(kw, '')}")

    for w in warnings:
        print(f"\n  ⚠️ {w}")
    print()
    return 0
