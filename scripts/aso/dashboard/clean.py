"""The clean check: what must not be in `data/` before it is published. It reads; it changes nothing."""
from __future__ import annotations

import re
from pathlib import Path

# What must never leave the repository beyond identifiers: regular expressions, each tried against the text of
# every file in data/. A file that matches one is a problem. Nothing is listed until the owner decides.
# TODO(human): list what you will not publish, e.g. r'"proceeds_usd"' for revenue or r'"keyword"' for the basket.
NEVER_PUBLISH = []

# config.md lines whose values identify the app's accounts. A value is looked for as a whole word.
IDENTIFIERS = ("App ID", "Bundle ID", "Provider Token", "Apple Ads account", "GA4 Property ID", "GA4 Stream ID", "GA4 Credentials",
               "Firebase Project ID", "Firebase Project Number", "Firebase App ID", "Firebase Bundle ID", "BigQuery Project ID",
               "BigQuery Dataset", "RevenueCat Project ID")

SHAPES = (
    ("an e-mail address", re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")),
    ("a private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("a key or token (a signed token)", re.compile(r"eyJ[\w-]{8,}\.[\w-]{8,}\.[\w-]{8,}")),
    ("a key or token (a provider prefix)", re.compile(r"\b(AIza[\w-]{30,}|(sk|pk|rk|appl|goog)_[A-Za-z0-9]{16,}|gh[pousr]_[A-Za-z0-9]{20,})")),
    # 32 or more letters and digits in a row holding both: a hash, an API key. A long word holds no digit.
    ("a key or token (a long opaque string)", re.compile(r"(?<![A-Za-z0-9])(?=[A-Za-z]*\d)(?=\d*[A-Za-z])[A-Za-z0-9]{32,}(?![A-Za-z0-9])")),
)


def identifiers(store: Path) -> dict:
    """label -> the value config.md gives it, for the labels that identify an account. A value of fewer than five
    characters is left out: as a whole word it would match ordinary numbers."""
    found = {}
    path = store / "config.md"
    for line in path.read_text(encoding="utf-8").splitlines() if path.is_file() else []:
        match = re.match(r"\*\*([^*]+)\*\*:\s*[`\"']?([^\s`\"']+)", line.strip())      # a value may sit in backticks or quotes
        if match and match.group(1).strip() in IDENTIFIERS and len(match.group(2)) >= 5 and not match.group(2).upper().startswith("TODO"):
            found[match.group(1).strip()] = match.group(2)
    return found


def whole(value: str):
    """A pattern for the value standing alone: not inside a longer run of letters and digits."""
    return re.compile(rf"(?<![A-Za-z0-9]){re.escape(value)}(?![A-Za-z0-9])")


def mask(obj, wanted: list, found: set):
    """`obj` with every account identifier that stands in a text replaced by `[redacted]`; `found` gains the labels
    met. Numbers are left alone: a figure is not prose, and an identifier is never a figure."""
    if isinstance(obj, str):
        for label, pattern in wanted:
            if pattern.search(obj):
                found.add(label)
                obj = pattern.sub("[redacted]", obj)
        return obj
    if isinstance(obj, list):
        return [mask(item, wanted, found) for item in obj]
    if isinstance(obj, dict):
        return {key: mask(value, wanted, found) for key, value in obj.items()}
    return obj


def check(data_dir: Path, store: Path) -> list:
    """Problems found in `data/`, one line each: the file and what kind of thing it holds, never the value."""
    if not data_dir.is_dir():
        return [f"{data_dir}: there is no data folder to check; run the export first"]
    wanted = [(f"the store's {label}", whole(value)) for label, value in identifiers(store).items()]
    wanted += list(SHAPES) + [(f"what NEVER_PUBLISH lists ({pattern})", re.compile(pattern)) for pattern in NEVER_PUBLISH]
    problems = []
    for path in sorted(p for p in data_dir.rglob("*") if p.is_file()):
        text = path.read_text(encoding="utf-8", errors="replace")
        for what, pattern in wanted:
            if pattern.search(text):
                problems.append(f"{path.relative_to(data_dir).as_posix()}: holds {what}")
    return problems
