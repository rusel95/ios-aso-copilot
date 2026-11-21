"""Prose the store holds, carried to the page as written: the reasoning behind a hypothesis's verdict, the newest
decisions, and the latest cycle report. Nothing here judges or counts. A file is read, cut where it must be, and
copied; the same store and day give the same bytes.
"""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

from aso.store import parse_date, problem

DAY = re.compile(r"\d{4}-\d{2}-\d{2}")
SECTION_END = re.compile(r"^#{1,2}\s")                     # a level-1 or level-2 heading ends a section; `###` stays inside
REASONING_HEADING = re.compile(r"^##\s+.*\bverdict reasoning\b(.*)$", re.IGNORECASE)
DECISION_HEADING = re.compile(r"^##\s+(\d{4}-\d{2}-\d{2})\s+[—–-]+\s+(.+?)\s*$")
DECISIONS_SHOWN = 8
DECISION_CAP = 6000          # characters; a longer entry is cut and says so
REPORT_CAP = 30000


def clip(text: str, cap: int) -> tuple:
    """(the text, or its first `cap` characters cut at a line end; whether it was cut)."""
    if len(text) <= cap:
        return text, False
    return text[:cap].rsplit("\n", 1)[0].rstrip(), True


def section(lines: list, start: int) -> str:
    """The text under the heading at `lines[start]`, up to the next heading of its level or above."""
    end = next((n for n in range(start + 1, len(lines)) if SECTION_END.match(lines[n])), len(lines))
    return "\n".join(lines[start + 1:end]).strip()


def verdict_reasoning(path: Path):
    """The latest `## Verdict reasoning` section of a hypothesis file: `{date, text}`, or None when it has none. The
    heading may carry a day, `## Verdict reasoning (2026-10-25)`, or a lead-in, `## Original verdict reasoning`. The
    newest day wins, an undated section loses to a dated one, and of two equal the later in the file stands (a verdict
    is written below the one it revises)."""
    lines = path.read_text(encoding="utf-8").splitlines()
    found = []
    for n, line in enumerate(lines):
        heading = REASONING_HEADING.match(line)
        text = section(lines, n) if heading else ""
        if text:
            day = DAY.search(heading.group(1))
            found.append((day.group(0) if day else "", n, text))
    if not found:
        return None
    day, _, text = max(found)
    return {"date": day or None, "text": text}


def decisions(store: Path, as_of: dt.date) -> list:
    """The newest entries of `decisions.md` dated on or before `as_of`, newest first. An entry is a `## <day> — <title>`
    heading and what follows it."""
    path = store / "decisions.md"
    if not path.is_file():
        return []
    lines, entries = path.read_text(encoding="utf-8").splitlines(), []
    for n, line in enumerate(lines):
        if not line.startswith("## "):
            continue
        heading = DECISION_HEADING.match(line)
        if not heading or parse_date(heading.group(1)) is None:
            problem(f"decisions.md:{n + 1}", f"heading `{line.strip()}` is not `## <date> — <title>`; left out")
        elif heading.group(1) <= as_of.isoformat():
            text, cut = clip(section(lines, n), DECISION_CAP)
            entries.append((heading.group(1), n, {"date": heading.group(1), "title": heading.group(2), "text": text,
                                                  "truncated": cut}))
    return [entry for _, _, entry in sorted(entries, key=lambda e: e[:2], reverse=True)[:DECISIONS_SHOWN]]


def cycle_report(store: Path, as_of: dt.date):
    """The newest `reports/*cycle*.md` whose file name carries a day on or before `as_of`, or None."""
    found = []
    for path in (store / "reports").glob("*cycle*.md"):
        days = DAY.findall(path.name)
        if path.is_file() and days and days[-1] <= as_of.isoformat() and parse_date(days[-1]) is not None:
            found.append((days[-1], path.name, path))
    if not found:
        return None
    day, name, path = max(found)
    text, cut = clip(path.read_text(encoding="utf-8").strip(), REPORT_CAP)
    return {"name": name, "date": day, "text": text, "truncated": cut}


def notes(store: Path, as_of: dt.date) -> dict:
    return {"decisions": decisions(store, as_of), "report": cycle_report(store, as_of)}
