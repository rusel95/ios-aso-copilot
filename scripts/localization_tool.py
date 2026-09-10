#!/usr/bin/env python3
"""Storefront Expansion & Localization Tool for iOS apps.

Audits, validates, and scaffolds end-to-end storefront localizations:
- In-App String Catalogs (.xcstrings) and CLDR pluralization completeness.
- Xcode project knownRegions synchronization.
- App Store Connect metadata limits (Title <=30, Subtitle <=30, Keywords <=100).
- Zero-waste keyword token overlap detection.
- Marketing hypothesis generation and screenshot copy readiness.

Usage:
    python3 localization_tool.py --store marketing/ --project . audit
    python3 localization_tool.py --store marketing/ --project . scaffold --locale pt-PT --market pt
    python3 localization_tool.py --store marketing/ --project . validate-plurals
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

# Apple App Store Connect 39 supported locales
ASC_LOCALES = {
    "ar-SA": {"family": "semitic_6", "name": "Arabic (Saudi Arabia)"},
    "ca": {"family": "standard_2", "name": "Catalan"},
    "cs": {"family": "west_slavic_4", "name": "Czech"},
    "da": {"family": "standard_2", "name": "Danish"},
    "de-DE": {"family": "standard_2", "name": "German"},
    "el": {"family": "standard_2", "name": "Greek"},
    "en-AU": {"family": "standard_2", "name": "English (Australia)"},
    "en-CA": {"family": "standard_2", "name": "English (Canada)"},
    "en-GB": {"family": "standard_2", "name": "English (UK)"},
    "en-US": {"family": "standard_2", "name": "English (US)"},
    "es-ES": {"family": "standard_2", "name": "Spanish (Spain)"},
    "es-MX": {"family": "standard_2", "name": "Spanish (Mexico)"},
    "fi": {"family": "standard_2", "name": "Finnish"},
    "fr-CA": {"family": "standard_2", "name": "French (Canada)"},
    "fr-FR": {"family": "standard_2", "name": "French (France)"},
    "he": {"family": "semitic_he", "name": "Hebrew"},
    "hi": {"family": "standard_2", "name": "Hindi"},
    "hr": {"family": "slavic_4", "name": "Croatian"},
    "hu": {"family": "standard_2", "name": "Hungarian"},
    "id": {"family": "asian_1", "name": "Indonesian"},
    "it": {"family": "standard_2", "name": "Italian"},
    "ja": {"family": "asian_1", "name": "Japanese"},
    "ko": {"family": "asian_1", "name": "Korean"},
    "ms": {"family": "asian_1", "name": "Malay"},
    "nl-NL": {"family": "standard_2", "name": "Dutch"},
    "no": {"family": "standard_2", "name": "Norwegian"},
    "pl": {"family": "polish_4", "name": "Polish"},
    "pt-BR": {"family": "standard_2", "name": "Portuguese (Brazil)"},
    "pt-PT": {"family": "standard_2", "name": "Portuguese (Portugal)"},
    "ro": {"family": "standard_2", "name": "Romanian"},
    "ru": {"family": "slavic_4", "name": "Russian"},
    "sk": {"family": "west_slavic_4", "name": "Slovak"},
    "sv": {"family": "standard_2", "name": "Swedish"},
    "th": {"family": "asian_1", "name": "Thai"},
    "tr": {"family": "asian_1", "name": "Turkish"},
    "uk": {"family": "slavic_4", "name": "Ukrainian"},
    "vi": {"family": "asian_1", "name": "Vietnamese"},
    "zh-Hans": {"family": "asian_1", "name": "Chinese (Simplified)"},
    "zh-Hant": {"family": "asian_1", "name": "Chinese (Traditional)"},
}

REQUIRED_PLURAL_CATEGORIES = {
    "asian_1": ["other"],
    "standard_2": ["one", "other"],
    "slavic_4": ["one", "few", "many", "other"],
    "polish_4": ["one", "few", "many", "other"],
    "west_slavic_4": ["one", "few", "many", "other"],
    "semitic_6": ["zero", "one", "two", "few", "many", "other"],
    "semitic_he": ["one", "two", "many", "other"],
}


def find_xcstrings(project_root: Path) -> Path | None:
    """Find the main Localizable.xcstrings file."""
    for p in project_root.rglob("Localizable.xcstrings"):
        if ".build" not in p.parts and "Pods" not in p.parts:
            return p
    return None


def find_pbxproj(project_root: Path) -> Path | None:
    """Find project.pbxproj."""
    for p in project_root.rglob("project.pbxproj"):
        if ".build" not in p.parts:
            return p
    return None


def parse_known_regions(pbxproj_path: Path) -> set[str]:
    """Parse knownRegions list from project.pbxproj."""
    if not pbxproj_path.exists():
        return set()
    content = pbxproj_path.read_text(encoding="utf-8")
    m = re.search(r"knownRegions\s*=\s*\((.*?)\);", content, re.DOTALL)
    if not m:
        return set()
    raw = m.group(1)
    regions = set()
    for line in raw.split("\n"):
        cleaned = line.strip().strip(",").strip('"').strip("'")
        if cleaned and not cleaned.startswith("/*") and cleaned != "Base":
            regions.add(cleaned)
    return regions


def audit_storefronts(store_path: Path, project_root: Path) -> int:
    """Audit coverage and zero-waste quality across in-app strings, metadata, and Xcode."""
    print("=== Compresso Storefront & Localization Audit ===\n")

    xcstrings_path = find_xcstrings(project_root)
    pbxproj_path = find_pbxproj(project_root)

    app_locales = set()
    plural_keys = []
    if xcstrings_path and xcstrings_path.exists():
        try:
            with open(xcstrings_path, "r", encoding="utf-8") as f:
                cat = json.load(f)
            for k, v in cat.get("strings", {}).items():
                locs = v.get("localizations", {})
                app_locales.update(locs.keys())
                if any("variations" in l for l in locs.values()):
                    plural_keys.append(k)
        except Exception as e:
            print(f"Error reading {xcstrings_path}: {e}", file=sys.stderr)

    known_regions = parse_known_regions(pbxproj_path) if pbxproj_path else set()

    metadata_dir = project_root / "metadata"
    app_info_dir = metadata_dir / "app-info"
    version_dir = metadata_dir / "version"

    meta_app_info_locales = set()
    if app_info_dir.exists():
        meta_app_info_locales = {p.stem for p in app_info_dir.glob("*.json")}

    latest_version = None
    meta_version_locales = set()
    if version_dir.exists():
        subdirs = sorted([p for p in version_dir.iterdir() if p.is_dir()])
        if subdirs:
            latest_version = subdirs[-1].name
            meta_version_locales = {p.stem for p in (version_dir / latest_version).glob("*.json")}

    card_html_path = project_root / "appstore/screenshots/frame/card.html"
    card_locales = set()
    if card_html_path.exists():
        txt = card_html_path.read_text(encoding="utf-8")
        for match in re.finditer(r"['\"]([a-zA-Z0-9_\-]+)['\"]\s*:\s*\{", txt):
            cand = match.group(1)
            if cand in ASC_LOCALES or any(cand == loc.split("-")[0] for loc in ASC_LOCALES):
                card_locales.add(cand)

    print(f"In-App String Catalog: {xcstrings_path} ({len(app_locales)} languages)")
    print(f"Xcode knownRegions:    {len(known_regions)} languages")
    print(f"App Store App-Info:    {len(meta_app_info_locales)} languages")
    print(f"App Store Version {latest_version}: {len(meta_version_locales)} languages")
    print(f"Screenshot card.html:  {len(card_locales)} languages\n")

    # Check gaps against ASC_LOCALES
    print("--- Storefront Coverage & Drift Check ---")
    missing_app_locales = []
    missing_metadata_locales = []
    missing_regions = []

    for asc_code, meta in sorted(ASC_LOCALES.items()):
        short_code = asc_code.split("-")[0]
        # In-app matches either full or short code
        has_app = (asc_code in app_locales) or (short_code in app_locales)
        has_region = (asc_code in known_regions) or (short_code in known_regions)
        has_meta = (asc_code in meta_app_info_locales) or (short_code in meta_app_info_locales)

        if not has_app:
            missing_app_locales.append(f"{asc_code} ({meta['name']})")
        if not has_meta:
            missing_metadata_locales.append(f"{asc_code} ({meta['name']})")
        if has_app and not has_region:
            missing_regions.append(asc_code)

    if missing_regions:
        print(f"⚠️ In-app language not registered in Xcode knownRegions: {', '.join(missing_regions)}")
    else:
        print("✅ Xcode knownRegions perfectly matches in-app locales.")

    if missing_metadata_locales:
        print(f"\nMissing App Store Connect storefront metadata ({len(missing_metadata_locales)}):")
        for item in missing_metadata_locales[:10]:
            print(f"  - {item}")
        if len(missing_metadata_locales) > 10:
            print(f"  ... and {len(missing_metadata_locales) - 10} more.")

    # Validate metadata limits & zero-waste token overlap
    print("\n--- Metadata Limits & Token Overlap Audit ---")
    issues = 0
    if app_info_dir.exists() and latest_version and (version_dir / latest_version).exists():
        for info_file in sorted(app_info_dir.glob("*.json")):
            loc = info_file.stem
            ver_file = version_dir / latest_version / f"{loc}.json"
            if not ver_file.exists():
                continue

            with open(info_file, "r", encoding="utf-8") as f:
                info_data = json.load(f)
            with open(ver_file, "r", encoding="utf-8") as f:
                ver_data = json.load(f)

            title = info_data.get("name", "")
            subtitle = info_data.get("subtitle", "")
            keywords = ver_data.get("keywords", "")

            # Length check
            if len(title) > 30:
                print(f"❌ [{loc}] Title exceeds 30 chars: '{title}' ({len(title)} chars)")
                issues += 1
            if len(subtitle) > 30:
                print(f"❌ [{loc}] Subtitle exceeds 30 chars: '{subtitle}' ({len(subtitle)} chars)")
                issues += 1
            if len(keywords) > 100:
                print(f"❌ [{loc}] Keywords exceed 100 chars ({len(keywords)} chars)")
                issues += 1

            # Token overlap check
            def tokenize(text: str) -> set[str]:
                tokens = re.split(r"[\s,:;\.\-—\(\)]+", text.lower())
                return {t for t in tokens if len(t) > 2}

            title_tokens = tokenize(title)
            subtitle_tokens = tokenize(subtitle)
            kw_tokens = {t.strip() for t in keywords.lower().split(",") if len(t.strip()) > 2}

            title_sub_overlap = title_tokens & subtitle_tokens
            if title_sub_overlap:
                print(f"⚠️ [{loc}] Token overlap between Title and Subtitle: {title_sub_overlap}")

            title_kw_overlap = title_tokens & kw_tokens
            if title_kw_overlap:
                print(f"⚠️ [{loc}] Wasteful token overlap between Title and Keywords: {title_kw_overlap}")
                issues += 1

            sub_kw_overlap = subtitle_tokens & kw_tokens
            if sub_kw_overlap:
                print(f"⚠️ [{loc}] Wasteful token overlap between Subtitle and Keywords: {sub_kw_overlap}")
                issues += 1

    if issues == 0:
        print("✅ Zero-waste keyword token contract respected: 0 character limit violations, 0 duplicate tokens.")
    else:
        print(f"⚠️ Found {issues} token optimization or character limit issues.")

    return 0


def validate_plurals(project_root: Path) -> int:
    """Validate all plural keys in Localizable.xcstrings against CLDR requirements."""
    xcstrings_path = find_xcstrings(project_root)
    if not xcstrings_path or not xcstrings_path.exists():
        print("Error: Localizable.xcstrings not found", file=sys.stderr)
        return 1

    with open(xcstrings_path, "r", encoding="utf-8") as f:
        cat = json.load(f)

    strings = cat.get("strings", {})
    plural_keys = {}
    for k, v in strings.items():
        locs = v.get("localizations", {})
        for lang, lval in locs.items():
            if "variations" in lval:
                plural_keys[k] = v
                break

    print(f"Auditing {len(plural_keys)} plural keys across languages against CLDR matrices...")
    errors = 0

    for k, v in sorted(plural_keys.items()):
        locs = v.get("localizations", {})
        for lang, lval in locs.items():
            if "variations" not in lval:
                continue
            pvars = lval["variations"].get("plural", {})
            categories = set(pvars.keys())

            # Find matching family
            meta = ASC_LOCALES.get(lang)
            if not meta:
                # try short
                for asc_c, m in ASC_LOCALES.items():
                    if asc_c.startswith(lang):
                        meta = m
                        break

            if meta:
                req = REQUIRED_PLURAL_CATEGORIES.get(meta["family"], ["other"])
                missing = [r for r in req if r not in categories]
                if missing:
                    print(f"❌ Key '{k}' for locale '{lang}' is missing required CLDR categories: {missing}")
                    errors += 1

    if errors == 0:
        print(f"✅ All {len(plural_keys)} plural keys conform strictly to CLDR plural rules.")
        return 0
    else:
        print(f"❌ Found {errors} CLDR plural category violations.")
        return 1


def scaffold_storefront(store_path: Path, project_root: Path, locale: str, market: str) -> int:
    """Scaffold metadata, hypothesis, and configuration snippets for a new storefront."""
    meta = ASC_LOCALES.get(locale)
    lang_name = meta["name"] if meta else locale
    print(f"Scaffolding expansion for {locale} ({lang_name}), market '{market}'...")

    # 1. App-info metadata
    app_info_file = project_root / "metadata" / "app-info" / f"{locale}.json"
    app_info_file.parent.mkdir(parents=True, exist_ok=True)
    if not app_info_file.exists():
        content = {
            "name": f"Compresso: Title ({locale})",
            "subtitle": "Subtitle text here",
            "privacyPolicyUrl": "https://rusel95.github.io/rusel95-apps-legal/MediaCleaner/privacy-policy.html"
        }
        app_info_file.write_text(json.dumps(content, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Created: {app_info_file}")

    # 2. Version metadata
    version_dir = project_root / "metadata" / "version"
    subdirs = sorted([p for p in version_dir.iterdir() if p.is_dir()]) if version_dir.exists() else []
    if subdirs:
        latest_ver = subdirs[-1]
        ver_file = latest_ver / f"{locale}.json"
        if not ver_file.exists():
            v_content = {
                "description": f"Full localized description for {lang_name}...",
                "keywords": "token1,token2,token3,token4,token5",
                "promotionalText": "Promotional hook text (<=170 chars)",
                "supportUrl": "https://rusel95.github.io/rusel95-apps-legal/MediaCleaner/support.html",
                "whatsNew": f"Full {lang_name} localization and performance polish."
            }
            ver_file.write_text(json.dumps(v_content, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(f"Created: {ver_file}")

    # 3. Next hypothesis file
    hypo_dir = store_path / "hypotheses"
    if hypo_dir.exists():
        existing = [p.name for p in hypo_dir.glob("H*.md")]
        max_id = 0
        for name in existing:
            m = re.match(r"H(\d{3})", name)
            if m:
                max_id = max(max_id, int(m.group(1)))
        next_id = f"H{max_id + 1:03d}"
        hypo_file = hypo_dir / f"{next_id}-{market}-market-launch.md"
        if not hypo_file.exists():
            hypo_content = f"""---
id: {next_id}
markets: {market}
queries: query1; query2; query3; query4
status: queued
phase_at_start: P2-cold
change: >
  Introduce full {lang_name} ('{locale}') in-app localization (100% string coverage,
  all CLDR plural keys, and Xcode project knownRegions inclusion),
  App Store storefront metadata (Title, Subtitle, zero-waste Keywords),
  and localized screenshot copy in card.html.
mechanism: >
  Expand into {lang_name} market with 100% native on-device localization and zero-waste
  storefront keyword allocation targeting high-intent organic search queries.
prediction: >
  Measured with itunes-search-api at depth 200, 21 days after it goes public:
  - `{market}` · query1 → Top 5
  - `{market}` · query2 → Top 5
kill_criterion: >
  Judged 21 days after it goes public. Failed if target terms beyond depth 200.
kill_criterion_written: 2026-09-10
went_live:
window_days: 21
primary_signal: rank
verdict:
confounds: []
---

## Reasoning

High-potential expansion storefront with unserved local search demand.
"""
            hypo_file.write_text(hypo_content, encoding="utf-8")
            print(f"Created: {hypo_file}")

    print("\n✅ Storefront scaffolding completed.")
    return 0


def main():
    parser = argparse.ArgumentParser(description="iOS Storefront Expansion & Localization Tool")
    parser.add_argument("--store", default="marketing", help="Path to marketing store")
    parser.add_argument("--project", default=".", help="Path to project root")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("audit", help="Audit in-app strings, metadata, and Xcode synchronization")
    subparsers.add_parser("validate-plurals", help="Validate all plural keys against CLDR rules")

    scaffold_p = subparsers.add_parser("scaffold", help="Scaffold a new storefront expansion")
    scaffold_p.add_argument("--locale", required=True, help="Locale identifier (e.g., pt-PT, de-DE)")
    scaffold_p.add_argument("--market", required=True, help="App Store market code (e.g., pt, de, sk)")

    args = parser.parse_args()

    store_path = Path(args.store).resolve()
    project_root = Path(args.project).resolve()

    if args.command == "audit":
        sys.exit(audit_storefronts(store_path, project_root))
    elif args.command == "validate-plurals":
        sys.exit(validate_plurals(project_root))
    elif args.command == "scaffold":
        sys.exit(scaffold_storefront(store_path, project_root, args.locale, args.market))


if __name__ == "__main__":
    main()
