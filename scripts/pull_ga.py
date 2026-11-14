#!/usr/bin/env python3
"""Universal Google Analytics 4 / Firebase In-App Telemetry & Funnel Puller.

Part of the global ios-marketing-ops / ios-aso-copilot skill.
Reads only the selected app store's configured GA4 property and credentials, and reports
engagement metrics, event counts, and monetization funnel observations.

Usage:
    # 1. Install dependency:
    #    pip3 install google-analytics-data
    #
    # 2. Run directly:
    #    python3 scripts/pull_ga.py
    #    python3 scripts/pull_ga.py --days 14 --export-csv
    #    python3 scripts/pull_ga.py --realtime
    #
    # 3. Via unified copilot CLI:
    #    python3 scripts/copilot.py ga --days 14
"""

import argparse
import csv
import json
import os
import plistlib
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

try:
    from google.analytics.data_v1beta import BetaAnalyticsDataClient
    from google.analytics.data_v1beta.types import (
        DateRange,
        Dimension,
        Filter,
        FilterExpression,
        FilterExpressionList,
        Metric,
        RunRealtimeReportRequest,
        RunReportRequest,
    )
except ImportError:
    sys.exit(
        "Помилка: бібліотека 'google-analytics-data' не встановлена.\n"
        "Встановіть її командою:\n"
        "    pip3 install google-analytics-data\n"
        "або використовуйте віртуальне оточення проекту (.venv)."
    )
from aso.pull_ga_reports import (  # noqa: E402,F401
    KNOWN_EVENTS,
    event_name_filter,
    format_table,
    get_version_filter,
    run_country_report,
    run_custom_dimension_report,
    run_funnel_report,
    run_listening_report,
    run_realtime_report,
    run_retention_report,
    run_returning_play_report,
    run_sequential_funnel_report,
    run_summary_report,
    run_version_report,
)


# MARK: - Known Event Catalog & Semantic Descriptions


# MARK: - Table Formatting


# MARK: - Config & Discovery Helpers

def resolve_app_info(store: Path):
    """Read app identity and GA4 configuration from the selected store only."""
    app_id = ""
    brand = ""
    ga4_property_id = ""
    ga4_stream_id = ""
    ga4_creds = ""
    firebase_project_id = ""
    firebase_app_id = ""
    firebase_bundle_id = ""
    ga4_custom_dimensions = []
    ga4_funnel_steps = []

    config_file = store / "config.md"
    if config_file.exists():
        for line in config_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("**App ID**:"):
                val = line.split(":", 1)[1].strip()
                if val and val != "TODO":
                    app_id = val.split()[0]
            elif line.startswith("**Brand tokens**:") or line.startswith("**Brand**:"):
                val = line.split(":", 1)[1].strip()
                if val:
                    brand = val.split(",")[0].strip().lower()
            elif line.startswith("**GA4 Property ID**:") or line.startswith("**Firebase Property ID**:"):
                val = line.split(":", 1)[1].strip()
                if val and val.split(maxsplit=1)[0].upper() != "TODO":
                    ga4_property_id = val.split()[0]
            elif line.startswith("**GA4 Stream ID**:"):
                val = line.split(":", 1)[1].strip()
                if val and val.upper() != "TODO":
                    ga4_stream_id = val.split()[0]
            elif line.startswith("**Firebase Project ID**:"):
                firebase_project_id = line.split(":", 1)[1].strip().split()[0]
            elif line.startswith("**Firebase App ID**:"):
                firebase_app_id = line.split(":", 1)[1].strip().split()[0]
            elif line.startswith("**Firebase Bundle ID**:"):
                firebase_bundle_id = line.split(":", 1)[1].strip().split()[0]
            elif line.startswith("**GA4 Credentials**:"):
                val = line.split(":", 1)[1].strip()
                if val and val.split(maxsplit=1)[0].upper() != "TODO":
                    ga4_creds = val.strip("\"'")
            elif line.startswith("**GA4 Funnel Steps**:"):
                val = line.split(":", 1)[1].strip()
                ga4_funnel_steps = [
                    step.strip() for step in val.replace("→", ",").split(",") if step.strip()
                ]
            elif line.startswith("**GA4 Custom Event Dimensions**:"):
                ga4_custom_dimensions = [
                    name.strip() for name in line.split(":", 1)[1].split(",") if name.strip()
                ]

    return {
        "app_id": app_id,
        "brand": brand,
        "ga4_property_id": ga4_property_id,
        "ga4_stream_id": ga4_stream_id,
        "ga4_custom_dimensions": ga4_custom_dimensions,
        "ga4_creds": ga4_creds,
        "ga4_funnel_steps": ga4_funnel_steps,
        "firebase_project_id": firebase_project_id,
        "firebase_app_id": firebase_app_id,
        "firebase_bundle_id": firebase_bundle_id,
    }


def find_default_credentials(app_info: dict):
    """Prefer this app's explicit credential path, then a configured runtime credential."""
    if app_info.get("ga4_creds"):
        return os.path.expanduser(app_info["ga4_creds"])
    return os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")


def verify_firebase_app(app_info: dict, store: Path):
    """Verify the configured iOS app against Firebase CLI without printing SDK secrets."""
    expected = {
        "PROJECT_ID": app_info.get("firebase_project_id"),
        "GOOGLE_APP_ID": app_info.get("firebase_app_id"),
        "BUNDLE_ID": app_info.get("firebase_bundle_id"),
    }
    if not any(expected.values()):
        print("\n🔥 Firebase CLI identity check: not configured for this app.")
        return True
    if not all(expected.values()):
        print("\n⚠️ Firebase CLI identity check incomplete: configure project ID, iOS app ID, and bundle ID.")
        return False

    try:
        result = subprocess.run(
            ["firebase", "--project", expected["PROJECT_ID"], "apps:sdkconfig", "ios", expected["GOOGLE_APP_ID"], "--json"],
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
        envelope = json.loads(result.stdout)
        content = envelope["result"]["fileContents"]
        remote = plistlib.loads(content.encode("utf-8"))
    except (OSError, subprocess.SubprocessError, KeyError, ValueError, plistlib.InvalidFileException) as error:
        print(f"\n⚠️ Firebase CLI identity check failed: {type(error).__name__}.")
        return False

    mismatches = [
        key for key, value in expected.items()
        if remote.get(key) != value
    ]
    if mismatches:
        print("\n⚠️ Firebase CLI identity mismatch: " + ", ".join(mismatches) + ".")
        return False

    analytics_enabled = remote.get("IS_ANALYTICS_ENABLED")
    # the app repo keeps its GoogleService-Info.plist one folder below the repo root
    plist_candidates = sorted(store.parent.glob("*/GoogleService-Info.plist"))
    local_path = plist_candidates[0] if plist_candidates else store.parent / "GoogleService-Info.plist"
    local_analytics = None
    if local_path.exists():
        try:
            local_analytics = plistlib.loads(local_path.read_bytes()).get("IS_ANALYTICS_ENABLED")
        except (OSError, plistlib.InvalidFileException):
            pass

    print("\n🔥 Firebase CLI identity: project, iOS app ID, and bundle ID match config.md.")
    if analytics_enabled is False:
        print("  ⚠️ Firebase CLI SDK config reports Analytics disabled; checking the linked GA4 stream below.")
    elif analytics_enabled is True:
        print("  Firebase CLI SDK config reports Analytics enabled.")
    if local_analytics is not None and local_analytics != analytics_enabled:
        print(f"  ⚠️ Local GoogleService-Info.plist differs (local enabled={local_analytics}, CLI enabled={analytics_enabled}).")

    property_id = app_info.get("ga4_property_id")
    stream_id = app_info.get("ga4_stream_id")
    if not property_id or not stream_id:
        print("  ⚠️ Firebase Management API check unavailable: configure GA4 property and stream IDs.")
        return False
    try:
        import google.auth
        from google.auth.transport.requests import AuthorizedSession

        credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        url = f"https://firebase.googleapis.com/v1beta1/projects/{expected['PROJECT_ID']}/analyticsDetails"
        response = AuthorizedSession(credentials).get(url, timeout=30)
        if response.status_code != 200:
            print(f"  ⚠️ Firebase Management API analyticsDetails returned HTTP {response.status_code}.")
            return False
        details = response.json()
        property_matches = details.get("analyticsProperty", {}).get("id") == property_id
        expected_app = f"projects/{expected['PROJECT_ID']}/iosApps/{expected['GOOGLE_APP_ID']}"
        stream_matches = any(
            mapping.get("app") == expected_app and mapping.get("streamId") == stream_id
            for mapping in details.get("streamMappings", [])
        )
        if property_matches and stream_matches:
            print("  ✓ Firebase Management API confirms the configured GA4 property and iOS stream map to this app.")
            return True
        print("  ⚠️ Firebase Management API property/stream mapping does not match config.md.")
        return False
    except Exception as error:
        print(f"  ⚠️ Firebase Management API verification unavailable: {type(error).__name__}.")
        return False


def inspect_ga4_metadata(client, property_id, requested_dimensions):
    """Check whether the configured event dimensions are usable in GA4 reports."""
    partial = False
    available = set()
    try:
        metadata = client.get_metadata(name=f"properties/{property_id}/metadata")
        available = {item.api_name.removeprefix("customEvent:") for item in metadata.dimensions if item.api_name.startswith("customEvent:")}
        missing = [name for name in requested_dimensions if name not in available]
        if missing:
            print("\n⚠️ GA4 custom event dimensions unavailable (not registered or not processed): " + ", ".join(missing))
            partial = True
        else:
            print("\n✓ GA4 custom event dimensions available: " + ", ".join(requested_dimensions))
    except Exception as error:
        print(f"\n⚠️ GA4 custom dimension metadata unavailable: {type(error).__name__}.")
        partial = True

    return partial, available


# MARK: - Report Runners


# MARK: - CLI Entrypoint

def main():
    parser = argparse.ArgumentParser(description="Universal GA4 / Firebase Analytics Funnel Puller.")
    parser.add_argument("--store", default="marketing", help="Path to project marketing store directory.")
    parser.add_argument("--property-id", help="GA4 Property ID (numeric).")
    parser.add_argument("--credentials", help="Path to service-account.json.")
    parser.add_argument("--days", type=int, default=14, help="Period in days (default: 14).")
    parser.add_argument("--realtime", action="store_true", help="Show events from the last 30 minutes only.")
    parser.add_argument("--include-debug", action="store_true", help="Include debug / simulator traffic (appVersion == '0').")
    parser.add_argument("--export-csv", action="store_true", help="Export funnel metrics to <store>/metrics/ga4_funnel.csv.")

    args = parser.parse_args()
    store = Path(args.store).resolve()
    app_info = resolve_app_info(store)

    # 1. Resolve Property ID
    if not app_info.get("app_id", "").isdigit():
        sys.exit(f"Set a numeric **App ID** in {store / 'config.md'} before querying GA4.")

    property_id = args.property_id or app_info.get("ga4_property_id")
    if property_id and not property_id.isdigit():
        sys.exit("GA4 Property ID must be numeric; set it in the selected store config or pass --property-id.")

    if not property_id:
        sys.exit(
            "⚠️  GA4 Property ID не знайдено.\n"
            "Додайте у вибраний marketing/config.md рядок **GA4 Property ID**: <ID> "
            "або передайте --property-id <ID>. Значення з environment, STATE.md та інших apps не використовуються.\n"
            "  (Знайти Property ID можна в Google Analytics Console → Admin → Property Settings → Property ID)."
        )

    # 2. Resolve Credentials first: the Firebase Management check reads the same env var
    credentials_path = args.credentials or find_default_credentials(app_info)
    if credentials_path:
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path

    firebase_ok = verify_firebase_app(app_info, store)

    try:
        client = BetaAnalyticsDataClient()
    except Exception as e:
        sys.exit(
            f"❌ Не вдалося ініціалізувати Google Analytics клієнт: {e}\n"
            "Перевірте локальні Application Default Credentials або переданий файл облікових даних:\n"
            f"  Поточний шлях файлу: {credentials_path or '(не задано; використовується ADC)'}\n"
            "Файл можна передати через --credentials або GOOGLE_APPLICATION_CREDENTIALS."
        )

    exclude_debug = not args.include_debug
    partial = not firebase_ok

    print("=================================================================")
    print(f"📡 Google Analytics 4 / Firebase Telemetry · Property {property_id}")
    if app_info.get("brand"):
        print(f"App: {app_info['brand'].capitalize()} · Store: {store}")
    print("=================================================================")

    if args.realtime:
        run_realtime_report(client, property_id, exclude_debug=exclude_debug)
        if partial:
            sys.exit(2)
        return

    print(f"Period: {args.days} complete days through yesterday · property {property_id} · source: GA4 Data API")
    summary = run_summary_report(client, property_id, args.days, exclude_debug=exclude_debug)
    if not summary:
        sys.exit(2)
    print(f"Version population: appVersion != 0 · versions listed below · Firebase app: {app_info.get('firebase_app_id') or 'not configured'}")

    metadata_partial, available_dimensions = inspect_ga4_metadata(
        client,
        property_id,
        app_info.get("ga4_custom_dimensions", []),
    )
    partial = partial or metadata_partial

    export_file = (store / "metrics" / "ga4_funnel.csv") if args.export_csv else None
    run_funnel_report(client, property_id, args.days, exclude_debug=exclude_debug, export_path=export_file)
    partial = not run_version_report(client, property_id, args.days, exclude_debug=exclude_debug) or partial
    partial = not run_listening_report(client, property_id, args.days, exclude_debug=exclude_debug) or partial
    partial = not run_retention_report(client, property_id, args.days, summary["timezone"], exclude_debug=exclude_debug) or partial
    partial = not run_returning_play_report(client, property_id, args.days, exclude_debug=exclude_debug) or partial
    run_custom_dimension_report(client, property_id, args.days, available_dimensions, exclude_debug=exclude_debug)
    try:
        run_country_report(client, property_id, args.days, exclude_debug=exclude_debug)
    except Exception as error:
        print(f"\n⚠️ Country report недоступний: {type(error).__name__}.")
        partial = True

    sequential_funnel_ok = run_sequential_funnel_report(
        property_id,
        app_info.get("ga4_funnel_steps", []),
        args.days,
        exclude_debug=exclude_debug,
    )

    if not sequential_funnel_ok:
        partial = True

    if partial:
        print("\n⚠️ Збір частковий: дивись Firebase identity, GA4 mapping/dimensions або звіти, позначені вище.")
        sys.exit(2)

    print("\n=================================================================")
    print("✅ Збір аналітики успішно завершено.")
    print("=================================================================")


if __name__ == "__main__":
    main()
