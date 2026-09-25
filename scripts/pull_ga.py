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


# MARK: - Known Event Catalog & Semantic Descriptions

KNOWN_EVENTS = {
    # App Lifecycle
    "first_open": ("Перше відкриття", "lifecycle"),
    "session_start": ("Старт сесії", "lifecycle"),
    "app_launched": ("Запуск додатку", "lifecycle"),
    "app_foregrounded": ("Повернення на передній план", "lifecycle"),
    "app_backgrounded": ("Перехід у фоновий режим", "lifecycle"),
    "app_update": ("Оновлення додатку", "lifecycle"),

    # Core Features & Activation (WhiteNoise / Hush)
    "first_playback": ("Перше успішне відтворення", "core"),
    "playback_requested": ("Спроба запустити звук", "core"),
    "playback_started": ("Старт відтворення звуків", "core"),
    "playback_paused": ("Пауза відтворення", "core"),
    "playback_failed": ("Звук не запустився", "core"),
    "playback_blocked": ("Запуск заблоковано лімітом", "core"),
    "sound_toggled": ("Увімкнення / вимкнення звуку", "core"),
    "sound_volume_changed": ("Регулювання гучності звуку", "core"),
    "sound_variant_changed": ("Зміна варіації звуку", "core"),
    "category_filter_selected": ("Вибір категорії звуків (чіп)", "core"),
    "timer_started": ("Запуск таймера сну", "core"),
    "timer_completed": ("Завершення таймера сну", "core"),
    "timer_cancelled": ("Скасування таймера сну", "core"),
    "listening_time_accumulated": ("Підтверджений час прослуховування", "core"),
    "free_listening_limit_reached": ("Досягнуто ліміту пробного прослуховування", "core"),
    "listening_session_started": ("Перша реальна гра у сесії застосунку", "core"),

    # Core Features & Activation (MediaCleaner / Compresso)
    "media_swiped": ("Свайп / рішення по фото/відео", "core"),
    "cleanup_screen_shown": ("Показ екрану очищення", "core"),
    "cleanup_completed": ("Успішне завершення очищення", "core"),

    # Ratings & Review Prompts
    "rating_prompt_requested": ("Запит оцінки в App Store", "rating"),
    "app_store_review_prompt": ("Показ діалогу оцінки", "rating"),

    # Monetization & Paywall Funnel
    "paywall_shown": ("Показ пейволу", "paywall"),
    "paywall_dismissed": ("Закриття пейволу", "paywall"),
    "purchase_started": ("Початок покупки", "checkout"),
    "purchase_completed": ("Покупка / entitlement отримано", "purchase"),
    "purchase_failed": ("Помилка покупки", "purchase"),
    "purchase_cancelled": ("Скасування покупки", "purchase"),
    "checkout_started": ("Початок оформлення (checkout)", "checkout"),
    "begin_checkout": ("Старт чекауту", "checkout"),
    "subscription_purchased": ("Успішна покупка підписки", "purchase"),
    "purchase": ("Покупка", "purchase"),
    "in_app_purchase": ("Внутрішньоігрова/внутрішньопрограмна покупка", "purchase"),
    "purchase_restored": ("Відновлення покупок", "purchase"),
}

# MARK: - Table Formatting

def format_table(headers, rows):
    """Format headers and rows into an aligned ASCII table."""
    if not rows:
        return "  (немає даних)"
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, val in enumerate(row):
            col_widths[i] = max(col_widths[i], len(str(val)))

    header_line = "  " + "  ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers))
    separator = "  " + "  ".join("-" * col_widths[i] for i in range(len(headers)))
    data_lines = [
        "  " + "  ".join(str(val).ljust(col_widths[i]) for i, val in enumerate(row))
        for row in rows
    ]
    return "\n".join([header_line, separator] + data_lines)


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
    local_path = store.parent / "WhiteNoise" / "GoogleService-Info.plist"
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


def run_custom_dimension_report(client, property_id, days, available, exclude_debug=True):
    """Show sound and play-source segments only after GA4 has registered the dimensions."""
    reports = [
        ("sound_name", "sound_played", "Звуки, що реально стартували"),
        ("variant", "sound_played", "Варіанти звуку, що реально стартували"),
        ("source", "playback_started", "Джерело запуску відтворення"),
        ("build_channel", "playback_started", "Канал збірки для запусків відтворення"),
    ]
    for name, event_name, label in reports:
        if name not in available:
            continue
        request = RunReportRequest(
            property=f"properties/{property_id}",
            dimensions=[Dimension(name=f"customEvent:{name}")],
            metrics=[Metric(name="eventCount"), Metric(name="totalUsers")],
            dimension_filter=FilterExpression(
                and_group=FilterExpressionList(expressions=[
                    event_name_filter(event_name),
                    get_version_filter(exclude_debug),
                ])
            ) if exclude_debug else event_name_filter(event_name),
            date_ranges=[DateRange(start_date=f"{days}daysAgo", end_date="yesterday")],
        )
        try:
            response = client.run_report(request)
            rows = [[row.dimension_values[0].value or "(not set)", *(value.value for value in row.metric_values)] for row in response.rows]
            print(f"\n🔎 [{label}]")
            print(format_table([name, "Events", "Users"], rows))
        except Exception as error:
            print(f"\n⚠️ Зріз {name} недоступний: {type(error).__name__}.")


def get_version_filter(exclude_debug: bool = True):
    """Filter out internal debug / simulator traffic (e.g. appVersion == '0')."""
    if not exclude_debug:
        return None
    return FilterExpression(
        not_expression=FilterExpression(
            filter=Filter(
                field_name="appVersion",
                string_filter=Filter.StringFilter(value="0"),
            )
        )
    )


# MARK: - Report Runners

def run_summary_report(client, property_id, days, exclude_debug: bool = True):
    """Pull top-level active users, sessions, screen views, and engagement."""
    label = "тільки релізні версії" if exclude_debug else "всі версії (включно з debug)"
    print(f"\n📊 [Загальні метрики за останні {days} повних днів ({label})]")
    request = RunReportRequest(
        property=f"properties/{property_id}",
        dimensions=[],
        metrics=[
            Metric(name="activeUsers"),
            Metric(name="newUsers"),
            Metric(name="sessions"),
            Metric(name="screenPageViews"),
            Metric(name="userEngagementDuration"),
        ],
        dimension_filter=get_version_filter(exclude_debug),
        date_ranges=[DateRange(start_date=f"{days}daysAgo", end_date="yesterday")],
    )
    response = client.run_report(request)
    if not response.rows:
        print("  Дані ще не з'явилися або немає подій за цей період.")
        return None

    row = response.rows[0]
    timezone = response.metadata.time_zone or "UTC"
    local_today = datetime.now(ZoneInfo(timezone)).date()
    start = local_today - timedelta(days=days)
    end = local_today - timedelta(days=1)
    print(f"  Період: {start.isoformat()} — {end.isoformat()} · timezone: {timezone} · джерело: GA4 Data API")
    headers = ["Active Users", "New Users", "Sessions", "Sessions / user", "Screen Views", "Avg app engagement (s/user)"]
    active_users = int(row.metric_values[0].value or 0)
    new_users = int(row.metric_values[1].value or 0)
    sessions = int(row.metric_values[2].value or 0)
    views = int(row.metric_values[3].value or 0)
    total_duration = float(row.metric_values[4].value or 0.0)
    avg_duration = round(total_duration / active_users, 1) if active_users else 0.0
    sessions_per_user = round(sessions / active_users, 2) if active_users else 0

    print(format_table(headers, [[active_users, new_users, sessions, sessions_per_user, views, avg_duration]]))
    return {
        "active_users": active_users,
        "new_users": new_users,
        "sessions": sessions,
        "sessions_per_user": sessions_per_user,
        "views": views,
        "avg_duration": avg_duration,
        "timezone": timezone,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
    }


def event_name_filter(event_name):
    return FilterExpression(
        filter=Filter(
            field_name="eventName",
            string_filter=Filter.StringFilter(value=event_name),
        )
    )


def run_version_report(client, property_id, days, exclude_debug=True):
    """Show which production app versions contribute to the selected window."""
    print("\n📱 [Розподіл релізного трафіку за версією застосунку]")
    request = RunReportRequest(
        property=f"properties/{property_id}",
        dimensions=[Dimension(name="appVersion")],
        metrics=[Metric(name="activeUsers"), Metric(name="sessions")],
        dimension_filter=get_version_filter(exclude_debug),
        date_ranges=[DateRange(start_date=f"{days}daysAgo", end_date="yesterday")],
    )
    try:
        response = client.run_report(request)
        rows = [[row.dimension_values[0].value or "(unknown)", *(value.value for value in row.metric_values)] for row in response.rows]
        print(format_table(["App version", "Active users", "Sessions"], rows))
        return True
    except Exception as error:
        print(f"  ⚠️ Розподіл версій недоступний: {type(error).__name__}.")
        return False


def run_listening_report(client, property_id, days, exclude_debug=True):
    """Use the event's GA4 value parameter (seconds), never foreground duration."""
    print("\n🎧 [Реальне прослуховування за listening_time_accumulated.value]")
    request = RunReportRequest(
        property=f"properties/{property_id}",
        metrics=[Metric(name="eventValue"), Metric(name="totalUsers"), Metric(name="eventCount")],
        dimension_filter=FilterExpression(
            and_group=FilterExpressionList(expressions=[
                event_name_filter("listening_time_accumulated"),
                get_version_filter(exclude_debug),
            ])
        ) if exclude_debug else event_name_filter("listening_time_accumulated"),
        date_ranges=[DateRange(start_date=f"{days}daysAgo", end_date="yesterday")],
    )
    try:
        response = client.run_report(request)
    except Exception as error:
        print(f"  ⚠️ Час прослуховування недоступний: {type(error).__name__}.")
        return False
    if not response.rows:
        print("  Даних про контрольні записи слухання ще немає.")
        return False
    row = response.rows[0]
    total_seconds = float(row.metric_values[0].value or 0)
    listeners = int(row.metric_values[1].value or 0)
    checkpoints = int(row.metric_values[2].value or 0)
    if checkpoints > 0 and total_seconds <= 0:
        print(f"  ⚠️ Є {checkpoints} listening checkpoints від {listeners} users, але GA4 eventValue порожній/0; хвилини слухання недоступні.")
        return False
    average_minutes = round(total_seconds / listeners / 60, 2) if listeners else 0
    print(format_table(
        ["Total listening (min)", "Listeners (denominator)", "Avg min / listener", "Checkpoints"],
        [[round(total_seconds / 60, 2), listeners, average_minutes, checkpoints]],
    ))
    print(f"  Період: {days} повних днів у timezone властивості · версії: {'production' if exclude_debug else 'усі, включно з debug'} · джерело: GA4 eventValue.")
    return True


def run_retention_report(client, property_id, days, timezone, exclude_debug=True):
    """Compute D1/D7 on a cohort whose every first-open date is mature for day 7."""
    today = datetime.now(ZoneInfo(timezone or "UTC")).date()
    start = today - timedelta(days=days)
    end = today - timedelta(days=8)
    if end < start:
        print("\n⚠️ Retention недоступний: потрібно більше ніж 8 повних днів історії.")
        return False

    try:
        from google.analytics.data_v1beta.types import Cohort, CohortSpec, CohortsRange
    except ImportError:
        print("\n⚠️ Retention недоступний: версія google-analytics-data не має CohortSpec.")
        return False

    request = RunReportRequest(
        property=f"properties/{property_id}",
        dimensions=[Dimension(name="cohort"), Dimension(name="cohortNthDay")],
        metrics=[Metric(name="cohortActiveUsers"), Metric(name="cohortTotalUsers")],
        dimension_filter=get_version_filter(exclude_debug),
        cohort_spec=CohortSpec(
            cohorts=[Cohort(
                name="mature_first_open_cohorts",
                dimension="firstSessionDate",
                date_range=DateRange(start_date=start.isoformat(), end_date=end.isoformat()),
            )],
            cohorts_range=CohortsRange(granularity="DAILY", start_offset=1, end_offset=7),
        ),
    )
    print(f"\n🔁 [D1/D7 retention · first_open cohorts {start.isoformat()} — {end.isoformat()} · {timezone}]")
    try:
        response = client.run_report(request)
    except Exception as error:
        print(f"  ⚠️ Cohort report недоступний: {type(error).__name__}: {str(error)[:180]}")
        return False

    values = {}
    denominator = 0
    for row in response.rows:
        offset = row.dimension_values[1].value
        active = int(row.metric_values[0].value or 0)
        denominator = int(row.metric_values[1].value or denominator)
        values[offset] = active
    if not denominator:
        print("  Зрілих first_open cohort користувачів за цей період немає.")
        return True
    d1 = values.get("0001", 0)
    d7 = values.get("0007", 0)
    print(format_table(
        ["Когорта users (denominator)", "D1 active users", "D1 retention", "D7 active users", "D7 retention"],
        [[denominator, d1, f"{d1 / denominator:.1%}", d7, f"{d7 / denominator:.1%}"]],
    ))
    print("  Джерело: GA4 cohortActiveUsers / cohortTotalUsers; усі вибрані first_open когорти мають 7 днів дозрівання.")
    return True


def run_returning_play_report(client, property_id, days, exclude_debug=True):
    """Count new/returning users who actually started playback in this window."""
    print("\n↩️ [Нові та користувачі, що повернулися до відтворення]")
    request = RunReportRequest(
        property=f"properties/{property_id}",
        dimensions=[Dimension(name="newVsReturning")],
        metrics=[Metric(name="totalUsers"), Metric(name="eventCount")],
        dimension_filter=FilterExpression(
            and_group=FilterExpressionList(expressions=[
                event_name_filter("playback_started"),
                get_version_filter(exclude_debug),
            ])
        ) if exclude_debug else event_name_filter("playback_started"),
        date_ranges=[DateRange(start_date=f"{days}daysAgo", end_date="yesterday")],
    )
    try:
        response = client.run_report(request)
        rows = [[row.dimension_values[0].value, *(value.value for value in row.metric_values)] for row in response.rows]
        print(format_table(["GA4 new/returning", "Playback users", "playback_started events"], rows))
        print("  Це сегмент users із playback_started за період, а не когортний retention.")
        return True
    except Exception as error:
        print(f"  ⚠️ Повернення до Play недоступне: {type(error).__name__}.")
        return False


def run_funnel_report(client, property_id, days, exclude_debug: bool = True, export_path: Path = None):
    """Pull all events and construct the universal activation & monetization funnel."""
    print(f"\n🎯 [Події вирви (Funnel Events) за останні {days} днів]")
    request = RunReportRequest(
        property=f"properties/{property_id}",
        dimensions=[Dimension(name="eventName")],
        metrics=[
            Metric(name="eventCount"),
            Metric(name="totalUsers"),
        ],
        dimension_filter=get_version_filter(exclude_debug),
        date_ranges=[DateRange(start_date=f"{days}daysAgo", end_date="yesterday")],
    )
    response = client.run_report(request)

    events_map = {}
    all_rows = []
    for r in response.rows:
        name = r.dimension_values[0].value
        count = int(r.metric_values[0].value or 0)
        users = int(r.metric_values[1].value or 0)
        events_map[name] = {"count": count, "users": users}

        desc, category = KNOWN_EVENTS.get(name, ("", "other"))
        all_rows.append({"name": name, "count": count, "users": users, "desc": desc, "category": category})

    if not all_rows:
        print("  Подій ще немає за обраний період.")
        return

    # Categorized Tables
    lifecycle_rows = []
    core_rows = []
    monetization_rows = []
    other_rows = []

    for item in sorted(all_rows, key=lambda x: -x["count"]):
        cat = item["category"]
        row = [item["name"], item["count"], item["users"], item["desc"]]
        if cat == "lifecycle":
            lifecycle_rows.append(row)
        elif cat == "core":
            core_rows.append(row)
        elif cat in ("paywall", "checkout", "purchase"):
            monetization_rows.append(row)
        else:
            other_rows.append([item["name"], item["count"], item["users"], ""])

    headers = ["Подія", "Кількість", "Користувачі", "Призначення"]

    if core_rows:
        print("\n  ▶ Основні дії (Core Activation & Features):")
        print(format_table(headers, core_rows))

    if monetization_rows:
        print("\n  ▶ Монетизація та Пейвол:")
        print(format_table(headers, monetization_rows))

    if lifecycle_rows:
        print("\n  ▶ Життєвий цикл:")
        print(format_table(headers, lifecycle_rows))

    if other_rows:
        print("\n  ▶ Інші зафіксовані події:")
        print(format_table(headers, other_rows[:10]))

    print("\n📈 [Послідовна конверсія]")
    print("  Нижче наведено окремий user-level Funnel Report; ці eventName totals самі по собі не є послідовною конверсією.")

    if export_path:
        export_path.parent.mkdir(parents=True, exist_ok=True)
        with open(export_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["event_name", "event_count", "total_users", "category", "description"])
            for item in sorted(all_rows, key=lambda x: -x["count"]):
                writer.writerow([item["name"], item["count"], item["users"], item["category"], item["desc"]])
        print(f"\n  ✓ Вирву експортовано у: {export_path}")


def run_sequential_funnel_report(property_id, event_names, days, exclude_debug: bool = True):
    """Report ordered in-app conversion using the GA4 Data API v1alpha funnel method."""
    if not event_names:
        print("\n⚠️ Послідовна вирва недоступна: у вибраному STORE/config.md не задано GA4 Funnel Steps.")
        return False
    if len(event_names) < 2:
        print("\n⚠️ Послідовна вирва потребує щонайменше двох GA4 Funnel Steps.")
        return False

    try:
        from google.analytics.data_v1alpha import AlphaAnalyticsDataClient
        from google.analytics.data_v1alpha.types import (
            DateRange as AlphaDateRange,
            Filter as AlphaFilter,
            FilterExpression as AlphaFilterExpression,
            Funnel as AnalyticsFunnel,
            FunnelEventFilter,
            FunnelFilterExpression,
            FunnelStep,
            RunFunnelReportRequest,
            StringFilter as AlphaStringFilter,
        )
    except ImportError as error:
        print(f"\n⚠️ Послідовна вирва недоступна: бібліотека v1alpha відсутня ({error}).")
        return False

    event_steps = [(name, name) for name in event_names]
    version_filter = None
    if exclude_debug:
        version_filter = AlphaFilterExpression(
            not_expression=AlphaFilterExpression(
                filter=AlphaFilter(
                    field_name="appVersion",
                    string_filter=AlphaStringFilter(
                        match_type=AlphaStringFilter.MatchType.EXACT,
                        value="0",
                    ),
                )
            )
        )

    request = RunFunnelReportRequest(
        property=f"properties/{property_id}",
        date_ranges=[
            AlphaDateRange(start_date=f"{days}daysAgo", end_date="yesterday")
        ],
        dimension_filter=version_filter,
        funnel=AnalyticsFunnel(
            is_open_funnel=False,
            steps=[
                FunnelStep(
                    name=name,
                    filter_expression=FunnelFilterExpression(
                        funnel_event_filter=FunnelEventFilter(event_name=event_name)
                    ),
                )
                for name, event_name in event_steps
            ],
        ),
    )

    print(f"\n🧭 [Послідовна вирва GA4 · v1alpha · {days} повних днів]")
    try:
        with AlphaAnalyticsDataClient() as client:
            response = client.run_funnel_report(request=request)
    except Exception as error:
        print(f"  ⚠️ Звіт не отримано: {type(error).__name__}: {str(error)[:240]}")
        return False

    report = response.funnel_table
    rows = []
    reached_steps = set()
    for row in report.rows:
        if len(row.dimension_values) < 1 or len(row.metric_values) < 4:
            print("  ⚠️ GA4 повернув рядок із неочікуваною схемою.")
            return False
        step_label = row.dimension_values[0].value
        step_name = step_label.split(". ", 1)[-1]
        reached_steps.add(step_name)
        active_users = int(row.metric_values[0].value or 0)
        completion = float(row.metric_values[1].value or 0)
        abandonments = int(row.metric_values[2].value or 0)
        abandonment_rate = float(row.metric_values[3].value or 0)
        rows.append([
            step_label,
            active_users,
            f"{completion:.1%}",
            abandonments,
            f"{abandonment_rate:.1%}",
        ])

    if not rows:
        print("  Немає рядків послідовної вирви за цей період.")
        return False

    print(format_table(
        ["Крок", "Користувачі", "Перехід до наступного", "Відсів", "Частка відсіву"],
        rows,
    ))
    missing_steps = [name for name, _ in event_steps if name not in reached_steps]
    if missing_steps:
        print("  Наступні кроки не мають рядка у цій закритій вирві: " + ", ".join(missing_steps))
    sampling = report.metadata.sampling_metadatas
    print("  Sampling: " + ("reported" if sampling else "not reported"))
    return True


def run_country_report(client, property_id, days, exclude_debug: bool = True):
    """Pull top countries by active users and sessions."""
    print(f"\n🌍 [Топ країн за активними користувачами (останні {days} днів)]")
    request = RunReportRequest(
        property=f"properties/{property_id}",
        dimensions=[Dimension(name="country")],
        metrics=[
            Metric(name="activeUsers"),
            Metric(name="sessions"),
        ],
        dimension_filter=get_version_filter(exclude_debug),
        date_ranges=[DateRange(start_date=f"{days}daysAgo", end_date="yesterday")],
    )
    response = client.run_report(request)
    rows = []
    for r in response.rows:
        country = r.dimension_values[0].value
        users = int(r.metric_values[0].value or 0)
        sessions = int(r.metric_values[1].value or 0)
        rows.append([country, users, sessions])

    rows.sort(key=lambda x: -x[1])
    headers = ["Країна", "Active Users", "Sessions"]
    print(format_table(headers, rows[:10]))


def run_realtime_report(client, property_id, exclude_debug: bool = True):
    """Pull real-time events over the last 30 minutes."""
    label = "тільки релізні версії" if exclude_debug else "всі версії"
    print(f"\n⚡ [Real-time: останні 30 хвилин ({label})]")
    request = RunRealtimeReportRequest(
        property=f"properties/{property_id}",
        dimensions=[Dimension(name="eventName")],
        metrics=[Metric(name="eventCount")],
        dimension_filter=get_version_filter(exclude_debug),
    )
    try:
        response = client.run_realtime_report(request)
        rows = []
        for r in response.rows:
            name = r.dimension_values[0].value
            count = r.metric_values[0].value
            desc = KNOWN_EVENTS.get(name, ("", ""))[0]
            rows.append([name, count, desc])
        rows.sort(key=lambda x: -int(x[1]))
        headers = ["Event Name", "Count (last 30m)", "Опис"]
        print(format_table(headers, rows))
    except Exception as e:
        print(f"  Не вдалося отримати realtime звіт: {e}")


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

    firebase_ok = verify_firebase_app(app_info, store)

    # 2. Resolve Credentials
    credentials_path = args.credentials or find_default_credentials(app_info)
    if credentials_path:
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path

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
