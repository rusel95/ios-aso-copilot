"""Folding App Store Connect's daily reports into closed Monday weeks: the helpers every fold shares, and the
install lifecycle (opt-in installs and deletions). pull_funnel.py is the entry that fetches the reports."""
import collections
import csv
from datetime import date, timedelta

LIFECYCLE_FIELDS = ["week_start", "segment", "first_installs_optin", "deletions_optin", "deletions_per_100_installs",
                    "deleted_within_1d", "deletions_timed", "median_days_to_delete", "source", "recorded"]

def week_start(day):
    return day - timedelta(days=day.weekday())


def count_value(value):
    value = (value or "").strip().replace(",", "")
    return int(value) if value else None


def reached(*reports):
    """The newest day every one of these reports holds, as an ISO date, or None when they hold nothing.

    Apple publishes a day about two days late, so on the Monday after a week its Sunday is in no report yet. A week
    is written once, and is therefore folded only when the reports already hold a day after it."""
    newest = [max(row["Date"] for row in rows) for rows in reports if rows]
    return min(newest) if newest else None


def merge_days(newer: list, older: list) -> list:
    """Rows of two requests for one report: a day both hold is taken from the newer request, whole."""
    held = {row["Date"] for row in newer}
    return newer + [row for row in older if row["Date"] not in held]


def monday_on_or_after(day: date) -> date:
    return week_start(day + timedelta(days=6))


def fold_lifecycle(rows, today=None, whole_from=None):
    """(week start, segment) -> the opt-in installs and deletions of one closed Monday week; the segments are `all`
    and each storefront. A sample of devices that share analytics, not a cohort: a week's deletions are mostly of
    installs made earlier. `timed` counts the deletions whose install day is known, `gaps` the days between."""
    today = today or date.today()
    weeks, reach = {}, reached(rows)
    for row in rows:
        day = date.fromisoformat(row["Date"])
        start = week_start(day)
        sunday = start + timedelta(days=6)
        if sunday >= today or (whole_from and start < whole_from) or sunday.isoformat() >= reach:
            continue
        kind, count = (row.get("Event") or "").strip().casefold(), count_value(row.get("Counts"))
        if count is None or kind not in ("install", "delete"):
            continue
        if kind == "install" and (row.get("Download Type") or "").strip().casefold() != "first-time download":
            continue
        gap = None
        if kind == "delete":
            try:
                gap = (day - date.fromisoformat((row.get("App Download Date") or "").strip())).days
            except ValueError:
                gap = None
            if gap is not None and gap < 0:      # deleted before it was installed: the report's noise, not a time
                gap = None
        territory = (row.get("Territory") or "").strip().lower()
        for segment in ["all"] + ([territory] if len(territory) == 2 and territory.isalpha() else []):
            item = weeks.setdefault((start.isoformat(), segment), {
                "installs": 0, "deletions": 0, "within_1d": 0, "timed": 0, "gaps": collections.Counter()})
            if kind == "install":
                item["installs"] += count
                continue
            item["deletions"] += count
            if gap is not None:
                item["timed"] += count
                item["within_1d"] += count if gap <= 1 else 0
                item["gaps"][gap] += count
    return weeks


def median_gap(gaps):
    """The middle day of a {days: deletions} count (the lower of two middles), or "" when nothing was timed."""
    seen, half = 0, (sum(gaps.values()) + 1) // 2
    for days in sorted(gaps):
        seen += gaps[days]
        if seen >= half:
            return days
    return ""


def write_lifecycle_weeks(out_dir, metrics, today=None):
    """Append the folded weeks metrics/lifecycle.csv does not hold yet -> (rows written, keys skipped)."""
    today = today or date.today()
    path = out_dir / "lifecycle.csv"
    existing = set()
    if path.is_file():
        with path.open(encoding="utf-8") as source:
            existing = {(row["week_start"], row["segment"]) for row in csv.DictReader(source)}
    recorded = today.isoformat()
    rows, skipped = [], []
    for (week, segment), item in sorted(metrics.items()):
        if (week, segment) in existing:
            skipped.append((week, segment))
            continue
        rows.append({
            "week_start": week, "segment": segment, "first_installs_optin": item["installs"],
            "deletions_optin": item["deletions"],
            "deletions_per_100_installs": f"{100.0 * item['deletions'] / item['installs']:.1f}" if item["installs"] else "",
            "deleted_within_1d": item["within_1d"], "deletions_timed": item["timed"],
            "median_days_to_delete": median_gap(item["gaps"]),
            "source": f"live:asc analytics daily lifecycle@{recorded}", "recorded": recorded})
    if rows:
        write_header = not path.is_file()
        with path.open("a", encoding="utf-8", newline="") as target:
            writer = csv.DictWriter(target, fieldnames=LIFECYCLE_FIELDS, lineterminator="\n")
            if write_header:
                writer.writeheader()
            writer.writerows(rows)
    return len(rows), skipped
