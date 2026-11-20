"""What the localization tool knows about an Xcode project: locales, plural rules, where its files are."""

from __future__ import annotations

import re
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
    "sl-SI": {"family": "slovenian_4", "name": "Slovenian"},
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
    "slovenian_4": ["one", "two", "few", "other"],
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
