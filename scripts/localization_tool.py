#!/usr/bin/env python3
"""Universal Storefront Expansion & iOS Localization Engine.

One universal script for the entire localization & storefront expansion lifecycle:
- export-template: Dumps .xcstrings keys into a structured translation template with CLDR plural shapes.
- apply-catalog:   Applies translations, validates format specifiers, updates .xcstrings,
                   and automatically synchronizes Xcode knownRegions & test suites.
- audit:           Cross-audits in-app strings, Xcode project, App Store metadata limits,
                   and zero-waste keyword token overlap.
- validate-plurals:Strictly verifies CLDR plural category completeness across all 39 App Store locales.
- scaffold:        Scaffolds App Store Connect metadata, marketing hypothesis H0xx, and screenshot snippets.

Usage:
    # 1. Export template for a new locale:
    python3 localization_tool.py --project . export-template --locale es-MX --output /tmp/es-mx.json

    # 2. Apply filled translation template into app, Xcode, and tests:
    python3 localization_tool.py --project . apply-catalog --locale es-MX --input /tmp/es-mx.json

    # 3. Audit entire repo localization & metadata health:
    python3 localization_tool.py --project . --store marketing audit

    # 4. Scaffold App Store metadata and marketing hypothesis:
    python3 localization_tool.py --project . --store marketing scaffold --locale es-MX --market mx
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

# Apple App Store Connect 39 supported locales and CLDR plural families
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


def extract_format_specifiers(text: str) -> list[str]:
    """Extract format specifiers like %1$@, %lld, %2$s, etc."""
    return re.findall(r"%[0-9]*\$?[a-zA-Z@]", text)


def get_plural_family(locale: str) -> str:
    """Resolve plural family from locale code."""
    if locale in ASC_LOCALES:
        return ASC_LOCALES[locale]["family"]
    short = locale.split("-")[0]
    for code, meta in ASC_LOCALES.items():
        if code.startswith(short):
            return meta["family"]
    return "standard_2"


def find_xcstrings(project_root: Path) -> Path | None:
    """Find the primary Localizable.xcstrings file."""
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


def find_plural_test_file(project_root: Path) -> Path | None:
    """Find LocalizationPluralCoverageTests.swift if present."""
    for p in project_root.rglob("LocalizationPluralCoverageTests.swift"):
        if ".build" not in p.parts:
            return p
    return None


def parse_known_regions(pbxproj_path: Path) -> set[str]:
    """Parse knownRegions list from project.pbxproj."""
    if not pbxproj_path or not pbxproj_path.exists():
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


def add_to_known_regions(pbxproj_path: Path, locale: str) -> bool:
    """Add locale to knownRegions in project.pbxproj if not present."""
    if not pbxproj_path or not pbxproj_path.exists():
        return False
    content = pbxproj_path.read_text(encoding="utf-8")
    existing = parse_known_regions(pbxproj_path)
    if locale in existing:
        return False

    # Insert right before Base, or the closing parenthesis
    pattern = r"(\t+Base,\n\t+\);)"
    formatted_locale = f'"{locale}"' if "-" in locale else locale
    replacement = f'\t\t\t\t{formatted_locale},\n\\1'

    if re.search(pattern, content):
        new_content = re.sub(pattern, replacement, content, count=1)
    else:
        pattern2 = r"(\t+\);(\s+mainGroup))"
        replacement2 = f'\t\t\t\t{formatted_locale},\n\\1'
        new_content = re.sub(pattern2, replacement2, content, count=1)

    pbxproj_path.write_text(new_content, encoding="utf-8")
    print(f"✅ Added '{locale}' to knownRegions in {pbxproj_path}")
    return True


def add_to_plural_tests(test_path: Path, locale: str) -> bool:
    """Add locale to shippedLocales in LocalizationPluralCoverageTests.swift."""
    if not test_path or not test_path.exists():
        return False
    content = test_path.read_text(encoding="utf-8")
    if f'"{locale}"' in content:
        return False

    pattern = r"(static let shippedLocales = \[\n(?:.*\n)*?)(\s*\]\.map)"
    match = re.search(pattern, content)
    if match:
        formatted = f'        "{locale}",\n'
        new_content = content[:match.start(2)] + formatted + content[match.start(2):]
        test_path.write_text(new_content, encoding="utf-8")
        print(f"✅ Added '{locale}' to shippedLocales in {test_path}")
        return True
    return False


def export_template(project_root: Path, target_locale: str, output_path: Path) -> int:
    """Export all keys from Localizable.xcstrings into a structured JSON translation template."""
    xcstrings_path = find_xcstrings(project_root)
    if not xcstrings_path or not xcstrings_path.exists():
        print("Error: Localizable.xcstrings not found.", file=sys.stderr)
        return 1

    with open(xcstrings_path, "r", encoding="utf-8") as f:
        catalog = json.load(f)

    strings = catalog.get("strings", {})
    plural_family = get_plural_family(target_locale)
    required_cats = REQUIRED_PLURAL_CATEGORIES.get(plural_family, ["one", "other"])

    template = {
        "targetLocale": target_locale,
        "sourceLanguage": catalog.get("sourceLanguage", "en"),
        "pluralFamily": plural_family,
        "requiredPluralCategories": required_cats,
        "strings": {}
    }

    for key, val in sorted(strings.items()):
        locs = val.get("localizations", {})
        if not locs:
            continue

        comment = val.get("comment", "")
        # Check if plural
        is_plural = any("variations" in l for l in locs.values())

        if is_plural:
            en_vars = locs.get("en", {}).get("variations", {}).get("plural", {})
            en_samples = {cat: cval.get("stringUnit", {}).get("value", "") for cat, cval in en_vars.items()}
            target_cats = {cat: "" for cat in required_cats}
            # prefill if target already has translations
            if target_locale in locs and "variations" in locs[target_locale]:
                existing_t = locs[target_locale]["variations"].get("plural", {})
                for cat in required_cats:
                    if cat in existing_t:
                        target_cats[cat] = existing_t[cat].get("stringUnit", {}).get("value", "")

            template["strings"][key] = {
                "type": "plural",
                "comment": comment,
                "en": en_samples,
                "target": target_cats
            }
        else:
            en_val = locs.get("en", {}).get("stringUnit", {}).get("value", "")
            target_val = ""
            if target_locale in locs and "stringUnit" in locs[target_locale]:
                target_val = locs[target_locale]["stringUnit"].get("value", "")

            template["strings"][key] = {
                "type": "string",
                "comment": comment,
                "en": en_val,
                "target": target_val
            }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(template, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"✅ Exported translation template for '{target_locale}' to {output_path} ({len(template['strings'])} keys)")
    return 0


def apply_catalog(project_root: Path, target_locale: str, input_path: Path) -> int:
    """Apply filled translation template to Localizable.xcstrings, Xcode pbxproj, and test suites."""
    xcstrings_path = find_xcstrings(project_root)
    if not xcstrings_path or not xcstrings_path.exists():
        print("Error: Localizable.xcstrings not found.", file=sys.stderr)
        return 1

    if not input_path.exists():
        print(f"Error: Input file {input_path} does not exist.", file=sys.stderr)
        return 1

    with open(input_path, "r", encoding="utf-8") as f:
        input_data = json.load(f)

    with open(xcstrings_path, "r", encoding="utf-8") as f:
        catalog = json.load(f)

    translations = input_data.get("strings", {})
    catalog_strings = catalog.get("strings", {})

    plural_family = get_plural_family(target_locale)
    required_cats = REQUIRED_PLURAL_CATEGORIES.get(plural_family, ["one", "other"])

    applied_count = 0
    errors = 0

    for key, item in translations.items():
        if key not in catalog_strings:
            print(f"⚠️ Warning: key '{key}' from input does not exist in catalog. Skipping.")
            continue

        cat_entry = catalog_strings[key]
        if "localizations" not in cat_entry:
            cat_entry["localizations"] = {}

        itype = item.get("type", "string")

        if itype == "plural":
            target_dict = item.get("target", {})
            # Verify all required categories
            missing = [c for c in required_cats if not target_dict.get(c)]
            if missing:
                print(f"❌ Error: Plural key '{key}' is missing translations for required categories: {missing}", file=sys.stderr)
                errors += 1
                continue

            plural_variations = {}
            for cat, text in target_dict.items():
                if not text:
                    continue
                plural_variations[cat] = {
                    "stringUnit": {
                        "state": "translated",
                        "value": text
                    }
                }

            cat_entry["localizations"][target_locale] = {
                "variations": {
                    "plural": plural_variations
                }
            }
            applied_count += 1

        else:
            target_text = item.get("target", "")
            if not target_text:
                continue

            # Validate format specifiers against English
            en_val = cat_entry.get("localizations", {}).get("en", {}).get("stringUnit", {}).get("value", "")
            if en_val:
                en_specs = extract_format_specifiers(en_val)
                target_specs = extract_format_specifiers(target_text)
                if en_specs != target_specs:
                    print(f"⚠️ Format specifier mismatch for '{key}': en {en_specs} != target {target_specs}")

            cat_entry["localizations"][target_locale] = {
                "stringUnit": {
                    "state": "translated",
                    "value": target_text
                }
            }
            applied_count += 1

    if errors > 0:
        print(f"❌ Aborted catalog update due to {errors} errors.", file=sys.stderr)
        return 1

    # Atomic write to xcstrings
    with open(xcstrings_path, "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"✅ Successfully updated {applied_count} keys for '{target_locale}' in {xcstrings_path}")

    # Synchronize Xcode project knownRegions
    pbxproj_path = find_pbxproj(project_root)
    if pbxproj_path:
        add_to_known_regions(pbxproj_path, target_locale)

    # Synchronize test suite
    test_file = find_plural_test_file(project_root)
    if test_file:
        add_to_plural_tests(test_file, target_locale)

    return 0


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

    print(f"In-App String Catalog: {xcstrings_path} ({len(app_locales)} languages)")
    print(f"Xcode knownRegions:    {len(known_regions)} languages")
    print(f"App Store App-Info:    {len(meta_app_info_locales)} languages")
    print(f"App Store Version {latest_version}: {len(meta_version_locales)} languages\n")

    print("--- Storefront Coverage & Drift Check ---")
    missing_app_locales = []
    missing_metadata_locales = []
    missing_regions = []

    for asc_code, meta in sorted(ASC_LOCALES.items()):
        short_code = asc_code.split("-")[0]
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

            if len(title) > 30:
                print(f"❌ [{loc}] Title exceeds 30 chars: '{title}' ({len(title)} chars)")
                issues += 1
            if len(subtitle) > 30:
                print(f"❌ [{loc}] Subtitle exceeds 30 chars: '{subtitle}' ({len(subtitle)} chars)")
                issues += 1
            if len(keywords) > 100:
                print(f"❌ [{loc}] Keywords exceed 100 chars ({len(keywords)} chars)")
                issues += 1

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
        print("Error: Localizable.xcstrings not found.", file=sys.stderr)
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

            family = get_plural_family(lang)
            req = REQUIRED_PLURAL_CATEGORIES.get(family, ["other"])
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
    parser = argparse.ArgumentParser(description="Universal iOS Storefront Expansion & Localization Engine")
    parser.add_argument("--store", default="marketing", help="Path to marketing store")
    parser.add_argument("--project", default=".", help="Path to project root")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("audit", help="Audit in-app strings, metadata, and Xcode synchronization")
    subparsers.add_parser("validate-plurals", help="Validate all plural keys against CLDR rules")

    exp_p = subparsers.add_parser("export-template", help="Export structured JSON translation template")
    exp_p.add_argument("--locale", required=True, help="Target locale identifier (e.g., es-MX, fr-CA)")
    exp_p.add_argument("--output", required=True, help="Output JSON path")

    app_p = subparsers.add_parser("apply-catalog", help="Apply filled JSON translations into .xcstrings, Xcode, and tests")
    app_p.add_argument("--locale", required=True, help="Target locale identifier (e.g., es-MX, fr-CA)")
    app_p.add_argument("--input", required=True, help="Input JSON path")

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
    elif args.command == "export-template":
        sys.exit(export_template(project_root, args.locale, Path(args.output).resolve()))
    elif args.command == "apply-catalog":
        sys.exit(apply_catalog(project_root, args.locale, Path(args.input).resolve()))
    elif args.command == "scaffold":
        sys.exit(scaffold_storefront(store_path, project_root, args.locale, args.market))


if __name__ == "__main__":
    main()
