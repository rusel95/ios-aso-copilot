#!/usr/bin/env python3
"""Pull App Store Connect discovery (impressions) and downloads analytics for any iOS app.

Downloads daily instances from ASC Analytics:
1. App Store Discovery and Engagement Standard (impressions, product page views, taps)
2. App Downloads Standard (first-time downloads)

Deduplicates rolling-window restatements and aggregates weekly totals by:
- Global total ('all')
- Acquisition channels ('search', 'browse', 'web_referrer', 'app_referrer', etc.)
- Top storefront territories ('us', 'ua', 'de', 'no', 'pl', etc.)

Writes/updates metrics/weekly.csv.
"""

import argparse
import collections
import csv
from datetime import date, timedelta
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, str(Path(__file__).resolve().parent))
from aso.funnel_lifecycle import (  # noqa: E402,F401
    LIFECYCLE_FIELDS, count_value, fold_lifecycle, median_gap, merge_days, monday_on_or_after, reached, week_start,
    write_lifecycle_weeks)

DISCOVERY_REPORT = "App Store Discovery and Engagement Standard"
DOWNLOADS_REPORT = "App Downloads Standard"
INSTALLS_REPORT = "App Store Installation and Deletion Standard"
WEEKLY_FIELDS = [
    "week_start", "segment", "impressions", "product_page_views", "downloads",
    "cvr_pct", "trial_starts", "source", "recorded", "note"
]


def safe_stderr(value):
    value = re.sub(r"https?://\S+", "[URL]", value or "")
    value = re.sub(
        r"(?i)(authorization|access[_-]?token|refresh[_-]?token|api[_-]?key)(\s*[:=]\s*)\S+",
        r"\1\2[redacted]", value
    )
    return " ".join(value.split())[-500:]


def asc_json(command):
    env = dict(os.environ)
    env["ASC_TIMEOUT"] = "120s"
    result = subprocess.run(command, capture_output=True, text=True, env=env)
    if result.returncode:
        detail = safe_stderr(result.stderr)
        suffix = f" Detail: {detail}" if detail else ""
        raise RuntimeError(f"ASC command failed ({' '.join(command[:3])}; exit {result.returncode}).{suffix}")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"ASC returned invalid JSON for {' '.join(command[:3])}.") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"ASC returned an unexpected response for {' '.join(command[:3])}.")
    return payload


def asc_download(request_id, instance_id, segment_id, output):
    command = [
        "asc", "analytics", "download", "--request-id", request_id,
        "--instance-id", instance_id, "--segment-id", segment_id,
        "--output", str(output), "--decompress"
    ]
    env = dict(os.environ)
    env["ASC_TIMEOUT"] = "120s"
    last_err = ""
    for attempt in range(3):
        result = subprocess.run(command, capture_output=True, text=True, env=env)
        if result.returncode == 0 and output.is_file():
            return
        last_err = safe_stderr(result.stderr)
        import time
        time.sleep(2 * (attempt + 1))
    suffix = f" Detail: {last_err}" if last_err else ""
    raise RuntimeError(f"ASC download failed for instance {instance_id} after 3 attempts.{suffix}")


def segment_name(source_type):
    value = (source_type or "").strip().casefold()
    if "search" in value:
        return "search"
    if "browse" in value:
        return "browse"
    if "web" in value:
        return "web_referrer"
    if "app referrer" in value:
        return "app_referrer"
    slug = re.sub(r"[^a-z0-9]+", "_", value).strip("_")
    return f"other_{slug}" if slug else "other_unknown"


def read_tsv(path, app_id=None):
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source, delimiter="\t")
        required = {"Date", "App Apple Identifier", "Counts"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise RuntimeError(f"ASC export has an unexpected schema: {path.name}.")
        rows = list(reader)
    for row in rows:
        if app_id and row["App Apple Identifier"].strip() != str(app_id):
            raise RuntimeError(f"ASC export contains unexpected app identity: {path.name}.")
        try:
            date.fromisoformat(row["Date"])
        except (TypeError, ValueError) as exc:
            raise RuntimeError(f"ASC export has an invalid Date value: {path.name}.") from exc
    return rows


def cached_export(path, resume, app_id=None):
    return read_tsv(path, app_id=app_id) if resume and path.is_file() else None


def load_manifest(raw_dir, request_id, app_id=None):
    path = raw_dir / "segments.json"
    if not path.exists():
        return {"app_id": app_id, "request_id": request_id, "reports": {}}
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if app_id and manifest.get("app_id") and manifest.get("app_id") != str(app_id):
        raise RuntimeError("Resume manifest does not match this app.")
    if manifest.get("request_id") != request_id or not isinstance(manifest.get("reports"), dict):
        # the folder was filled under a request that no longer runs: its instances are not this request's, start over
        return {"app_id": app_id, "request_id": request_id, "reports": {}}
    return manifest


MANIFEST_LOCK = threading.Lock()     # the three reports are read at once and share one manifest file


def save_manifest(raw_dir, manifest):
    path = raw_dir / "segments.json"
    temporary = path.with_suffix(".json.tmp")
    with MANIFEST_LOCK:
        temporary.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)


def manifest_key(processing_date, instance_id):
    return f"{processing_date}_{instance_id[:8]}"


def manifest_segments(manifest, prefix, processing_date, instance_id):
    return manifest.get("reports", {}).get(prefix, {}).get(manifest_key(processing_date, instance_id))


def request_and_reports(app_id):
    cmd = ["asc", "analytics", "requests", "--app", str(app_id), "--access-type", "ONGOING", "--paginate", "--output", "json"]
    requests = asc_json(cmd)
    active = [
        item for item in requests.get("data", [])
        if item.get("attributes", {}).get("accessType") == "ONGOING"
        and not item.get("attributes", {}).get("stoppedDueToInactivity")
    ]
    if not active:
        active = [
            item for item in requests.get("data", [])
            if item.get("attributes", {}).get("accessType") == "ONGOING"
        ]
    if not active:
        raise RuntimeError(
            f"No active ONGOING analytics request found for App ID {app_id}. "
            f"Create one with: asc analytics request --app {app_id} --access-type ONGOING --reuse-existing"
        )
    request_id = active[0].get("id")
    if not request_id:
        raise RuntimeError("ASC ongoing request has no ID.")
    payload = asc_json([
        "asc", "analytics", "view", "--request-id", request_id,
        "--granularity", "DAILY", "--paginate", "--output", "json"
    ])
    reports = {row.get("name"): row for row in payload.get("data", []) if isinstance(row, dict)}
    return request_id, reports


def snapshot_reports(app_id):
    """(request id, reports by name) of the app's one-time snapshot request, or None when it has none. A snapshot
    holds the days before the ongoing request began; Apple takes a day or two to fill one after it is asked for."""
    listed = asc_json(["asc", "analytics", "requests", "--app", str(app_id), "--paginate", "--output", "json"])
    found = next((item.get("id") for item in listed.get("data", [])
                  if item.get("attributes", {}).get("accessType") == "ONE_TIME_SNAPSHOT" and item.get("id")), None)
    if not found:
        return None
    payload = asc_json(["asc", "analytics", "view", "--request-id", found, "--granularity", "DAILY", "--paginate", "--output", "json"])
    return found, {row.get("name"): row for row in payload.get("data", []) if isinstance(row, dict)}


def fetch_report(request_id, report, raw_dir, prefix, app_id=None, resume=False, manifest=None):
    if not report:
        raise RuntimeError(f"ASC report {prefix} is missing from the existing ongoing request.")
    instances = [
        item for item in report.get("instances", [])
        if item.get("granularity", "DAILY").upper() == "DAILY"
    ]
    if not instances:
        raise RuntimeError(f"ASC report {prefix} has no daily instances yet.")
    exports = []
    manifest = manifest or {"app_id": app_id, "request_id": request_id, "reports": {}}
    with MANIFEST_LOCK:
        report_manifest = manifest.setdefault("reports", {}).setdefault(prefix, {})
    total_inst = len(instances)
    for index, instance in enumerate(instances, start=1):
        instance_id = instance.get("id")
        if not instance_id:
            continue
        processing_date = instance.get("processingDate", "unknown")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", processing_date):
            raise RuntimeError(f"ASC report {prefix} instance {instance_id} has no valid processing date.")
        cached_segments = manifest_segments(manifest, prefix, processing_date, instance_id) if resume else None
        if cached_segments and all(
            (raw_dir / f"{prefix}_{processing_date}_{instance_id[:8]}_{segment}.csv").is_file()
            for segment in cached_segments
        ):
            segments = cached_segments
            is_cached = True
        else:
            links = asc_json([
                "asc", "analytics", "instances", "links", "--instance-id", instance_id,
                "--paginate", "--output", "json"
            ])
            segments = [
                item.get("id") for item in links.get("data", [])
                if item.get("type") == "analyticsReportSegments" and item.get("id")
            ]
            is_cached = False
        if not segments:
            continue
        with MANIFEST_LOCK:
            report_manifest[manifest_key(processing_date, instance_id)] = [s[:8] for s in segments]
        for segment_id in segments:
            segment_prefix = segment_id if is_cached else segment_id[:8]
            output = raw_dir / f"{prefix}_{processing_date}_{instance_id[:8]}_{segment_prefix}.csv"
            rows = cached_export(output, resume, app_id=app_id)
            if rows is None:
                asc_download(request_id, instance_id, segment_id, output)
                rows = read_tsv(output, app_id=app_id)
            exports.append((processing_date, rows))
        if not is_cached:
            save_manifest(raw_dir, manifest)
            print(f"  ASC {prefix} daily export {index}/{total_inst} preserved.")

    latest = {}
    for processing_date, rows in exports:
        for row in rows:
            dims = tuple(row.get(k, "") for k in (
                "Date", "Source Type", "Event", "Download Type", "Device", "Platform Version",
                "Territory", "Page Type", "Page Title", "Engagement Type", "Source Info",
                "Campaign", "Pre-Order", "App Version", "App Download Date"
            ))
            prev = latest.get(dims)
            if prev is None or processing_date >= prev[0]:
                latest[dims] = (processing_date, row)
    return [item[1] for item in latest.values()], len(exports), len(instances), (instances[0].get("processingDate") if instances else None)


def fold_reports(discovery_rows, download_rows, today=None, whole_from=None):
    """(week start, segment) -> the funnel counts of closed Monday weeks. `whole_from` is the first Monday whose week
    the reports hold from its start; earlier days belong to a week that began before the reports did."""
    today = today or date.today()
    reach = reached(discovery_rows, download_rows)
    metrics = {}

    def ensure_entry(start, seg):
        key = (start.isoformat(), seg)
        if key not in metrics:
            metrics[key] = {
                "impressions": None, "product_page_views": None, "downloads": None,
                "taps": None, "source_types": set(), "territories": set()
            }
        return metrics[key]

    def record_day(day):
        start = week_start(date.fromisoformat(day))
        sunday = start + timedelta(days=6)
        if sunday >= today or (whole_from and start < whole_from) or sunday.isoformat() >= reach:
            return None
        return start

    events = {"impression": "impressions", "page view": "product_page_views", "tap": "taps"}
    for row in discovery_rows:
        day_str = row.get("Date", "")
        start = record_day(day_str)
        if start is None:
            continue
        channel = segment_name(row.get("Source Type", ""))
        territory = (row.get("Territory") or "").strip().lower()
        metric = events.get((row.get("Event") or "").strip().casefold())
        val = count_value(row.get("Counts"))
        if not metric or val is None:
            continue

        targets = [ensure_entry(start, channel), ensure_entry(start, "all")]
        if territory and len(territory) == 2:
            targets.append(ensure_entry(start, territory))

        for target in targets:
            target[metric] = (target[metric] or 0) + val
            if row.get("Source Type"):
                target["source_types"].add(row.get("Source Type"))
            if territory:
                target["territories"].add(territory)

    for row in download_rows:
        if (row.get("Download Type") or "").strip().casefold() != "first-time download":
            continue
        day_str = row.get("Date", "")
        start = record_day(day_str)
        if start is None:
            continue
        channel = segment_name(row.get("Source Type", ""))
        territory = (row.get("Territory") or "").strip().lower()
        val = count_value(row.get("Counts"))
        if val is None:
            continue

        targets = [ensure_entry(start, channel), ensure_entry(start, "all")]
        if territory and len(territory) == 2:
            targets.append(ensure_entry(start, territory))

        for target in targets:
            target["downloads"] = (target["downloads"] or 0) + val
            if row.get("Source Type"):
                target["source_types"].add(row.get("Source Type"))
            if territory:
                target["territories"].add(territory)

    return metrics


def write_new_weeks(out_dir, metrics, report_info, raw_dir, today=None):
    today = today or date.today()
    path = out_dir / "weekly.csv"
    existing = set()
    if path.is_file():
        with path.open(encoding="utf-8") as source:
            for row in csv.DictReader(source):
                existing.add((row["week_start"], row["segment"]))

    rows = []
    skipped = []
    recorded = today.isoformat()
    for (week, segment), item in sorted(metrics.items()):
        if (week, segment) in existing:
            skipped.append((week, segment))
            continue
        impr = item["impressions"]
        pv = item["product_page_views"]
        dl = item["downloads"]
        cvr = ""
        if pv and dl is not None:
            cvr = f"{100.0 * dl / pv:.2f}"
        elif impr and dl is not None:
            cvr = f"{100.0 * dl / impr:.2f}"

        rows.append({
            "week_start": week,
            "segment": segment,
            "impressions": "" if impr is None else impr,
            "product_page_views": "" if pv is None else pv,
            "downloads": "" if dl is None else dl,
            "cvr_pct": cvr,
            "trial_starts": "",
            "source": f"live:asc analytics daily r14+r3@{recorded}",
            "recorded": recorded,
            "note": f"ASC funnel grouped from daily exports in {raw_dir.name}; reports {report_info}."
        })

    if rows:
        write_header = not path.is_file()
        with path.open("a", encoding="utf-8", newline="") as target:
            writer = csv.DictWriter(target, fieldnames=WEEKLY_FIELDS, lineterminator="\n")
            if write_header:
                writer.writeheader()
            writer.writerows(rows)
    return len(rows), skipped


def resolve_app_id(args):
    if args.app:
        return str(args.app).strip()
    if args.store:
        config_path = Path(args.store) / "config.md"
        if config_path.is_file():
            content = config_path.read_text(encoding="utf-8")
            m = re.search(r"^\s*app_id:\s*(\d+)", content, re.MULTILINE)
            if m:
                return m.group(1).strip()
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", help="App Apple Identifier (e.g. 1234567890)")
    parser.add_argument("--store", type=Path, help="Store directory containing config.md")
    parser.add_argument("--out", type=Path, help="Directory containing metrics/weekly.csv")
    parser.add_argument("--raw-dir", type=Path, help="Unique directory for source CSV exports")
    parser.add_argument("--resume", action="store_true", help="Reuse validated CSVs in an existing cycle directory")
    args = parser.parse_args()

    app_id = resolve_app_id(args)
    if not app_id:
        parser.error("App ID is required via --app or --store")
    if not args.out or not args.raw_dir:
        parser.error("--out and --raw-dir are required")

    raw_dir = args.raw_dir.resolve()
    raw_dir.mkdir(parents=True, exist_ok=True)

    try:
        request_id, reports = request_and_reports(app_id)
    except (RuntimeError, OSError) as exc:
        print(f"Funnel pull unavailable: {exc}", file=sys.stderr)
        return 2

    try:
        manifest = load_manifest(raw_dir, request_id, app_id=app_id)
    except RuntimeError as exc:
        print(f"Funnel pull unavailable: {exc}", file=sys.stderr)
        return 2

    wanted = ((DISCOVERY_REPORT, "r14"), (DOWNLOADS_REPORT, "r3"), (INSTALLS_REPORT, "lifecycle"))

    def read_all(request, found_reports, folder, its_manifest, label=""):
        """The three reports of one request, read side by side -> [(rows, files, instances, first processing date) or None]."""
        def read(pair):
            name, prefix = pair
            try:
                return fetch_report(request, found_reports.get(name), folder, prefix, app_id=app_id, resume=args.resume,
                                    manifest=its_manifest)
            except (RuntimeError, OSError) as exc:
                print(f"Partial funnel stage for {label}{prefix}: {exc}", file=sys.stderr)
                return None
        with ThreadPoolExecutor(max_workers=len(wanted)) as pool:
            return list(pool.map(read, wanted))

    discovery, downloads, lifecycle = read_all(request_id, reports, raw_dir, manifest)
    partial = lifecycle is None

    def floor(found):
        """The first Monday whose week an ongoing request holds whole: the week after its first daily report."""
        return week_start(date.fromisoformat(found[3])) + timedelta(days=7) if found and found[3] else None

    funnel_from = min((f for f in (floor(discovery), floor(downloads)) if f), default=None)
    lifecycle_from = floor(lifecycle)
    discovery_rows, download_rows = (discovery[0] if discovery else []), (downloads[0] if downloads else [])
    lifecycle_rows = lifecycle[0] if lifecycle else []
    summaries = [f"{prefix}: {found[2]} daily instances, {found[1]} CSVs"
                 for prefix, found in (("r14", discovery), ("r3", downloads)) if found]

    # The days before the ongoing request began, when the app has a one-time snapshot request and Apple has filled it.
    # Both funnel reports of the snapshot are needed, or its earlier weeks would be written by half.
    try:
        snapshot = snapshot_reports(app_id)
    except (RuntimeError, OSError) as exc:
        print(f"Partial funnel stage for snapshot: {exc}", file=sys.stderr)
        snapshot, partial = None, True
    if snapshot and not any((snapshot[1].get(name) or {}).get("instances") for name, _ in wanted):
        print("The one-time snapshot request holds no daily report yet (Apple fills it a day or two after it is asked for).")
    elif snapshot:
        folder = raw_dir / "snapshot"
        folder.mkdir(parents=True, exist_ok=True)
        old = read_all(snapshot[0], snapshot[1], folder, load_manifest(folder, snapshot[0], app_id=app_id), "snapshot ")
        partial = partial or any(found is None for found in old)
        if old[0] and old[1] and discovery_rows and download_rows and (old[0][0] or old[1][0]):
            earliest = min(row["Date"] for row in old[0][0] + old[1][0])
            funnel_from = min(f for f in (funnel_from, monday_on_or_after(date.fromisoformat(earliest))) if f)
            discovery_rows, download_rows = merge_days(discovery_rows, old[0][0]), merge_days(download_rows, old[1][0])
            summaries.append(f"snapshot: {old[0][2]} + {old[1][2]} daily instances")
        if old[2] and old[2][0]:
            earliest = min(row["Date"] for row in old[2][0])
            lifecycle_from = min(f for f in (lifecycle_from, monday_on_or_after(date.fromisoformat(earliest))) if f)
            lifecycle_rows = merge_days(lifecycle_rows, old[2][0])

    out_dir = args.out.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    # the install lifecycle is its own report and its own file: a funnel that could not be read does not stop it
    if lifecycle_rows:
        written, skipped = write_lifecycle_weeks(out_dir, fold_lifecycle(lifecycle_rows, whole_from=lifecycle_from))
        print(f"App ID {app_id}: lifecycle appended {written} new rows to {out_dir / 'lifecycle.csv'}; "
              f"skipped {len(skipped)} existing week/segment keys.")

    # a week is written once: a row holding one report without the other would stay half empty for good
    if not discovery_rows or not download_rows:
        print("R14 and R3 were not both read; weekly.csv was not updated.", file=sys.stderr)
        return 2

    metrics = fold_reports(discovery_rows, download_rows, whole_from=funnel_from)
    if not metrics:
        print("ASC returned no complete weekly observations; weekly.csv was not updated.", file=sys.stderr)
        return 2

    written, skipped = write_new_weeks(out_dir, metrics, "; ".join(summaries), raw_dir)
    print(f"App ID {app_id}: {len(metrics)} observed week/segment groups; appended {written} new rows to "
          f"{out_dir / 'weekly.csv'}; skipped {len(skipped)} existing week/segment keys.")
    # a report that could not be read was named above; the exit code says it too, so no caller takes the pull for whole
    return 2 if partial else 0


if __name__ == "__main__":
    sys.exit(main())
