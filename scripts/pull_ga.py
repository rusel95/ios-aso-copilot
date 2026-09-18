#!/usr/bin/env python3
"""Universal Google Analytics 4 / Firebase In-App Telemetry & Funnel Puller.

Part of the global ios-marketing-ops / ios-aso-copilot skill.
Works universally across any iOS project (WhiteNoise/Hush, MediaCleaner/Compresso, etc.)
to pull engagement metrics, user event counts, and monetization funnel conversions.

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
import glob
import json
import os
import sys
from datetime import datetime
from pathlib import Path

try:
    from google.analytics.data_v1beta import BetaAnalyticsDataClient
    from google.analytics.data_v1beta.types import (
        DateRange,
        Dimension,
        Filter,
        FilterExpression,
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
    "playback_started": ("Старт відтворення звуків", "core"),
    "playback_paused": ("Пауза відтворення", "core"),
    "sound_toggled": ("Увімкнення / вимкнення звуку", "core"),
    "sound_volume_changed": ("Регулювання гучності звуку", "core"),
    "sound_variant_changed": ("Зміна варіації звуку", "core"),
    "category_filter_selected": ("Вибір категорії звуків (чіп)", "core"),
    "timer_started": ("Запуск таймера сну", "core"),
    "timer_completed": ("Завершення таймера сну", "core"),
    "timer_cancelled": ("Скасування таймера сну", "core"),

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
    "checkout_started": ("Початок оформлення (checkout)", "checkout"),
    "begin_checkout": ("Старт чекауту", "checkout"),
    "subscription_purchased": ("Успішна покупка підписки", "purchase"),
    "purchase": ("Покупка", "purchase"),
    "in_app_purchase": ("Внутрішньоігрова/внутрішньопрограмна покупка", "purchase"),
    "purchase_restored": ("Відновлення покупок", "purchase"),
}

# Known App ID -> Default GA4 Property ID mappings
KNOWN_APP_PROPERTIES = {
    "6790447224": "552518102",   # MediaCleaner / Compresso
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
    """Read App ID, version, brand and GA4 configuration from store/config.md or STATE.md."""
    app_id = ""
    brand = ""
    ga4_property_id = ""
    ga4_creds = ""

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
                if val and val != "TODO":
                    ga4_property_id = val.split()[0]
            elif line.startswith("**GA4 Credentials**:"):
                val = line.split(":", 1)[1].strip()
                if val and val != "TODO":
                    ga4_creds = val

    state_file = store / "STATE.md"
    if state_file.exists() and not ga4_property_id:
        for line in state_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("ga4_property_id:"):
                val = line.split(":", 1)[1].strip().strip('"\'')
                if val:
                    ga4_property_id = val

    return {
        "app_id": app_id,
        "brand": brand,
        "ga4_property_id": ga4_property_id,
        "ga4_creds": ga4_creds,
    }


def find_default_credentials(app_info: dict, store: Path):
    """Search for GA4 / Google Application Credentials in standard paths."""
    env_creds = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if env_creds and os.path.exists(env_creds):
        return env_creds

    if app_info.get("ga4_creds") and os.path.exists(os.path.expanduser(app_info["ga4_creds"])):
        return os.path.expanduser(app_info["ga4_creds"])

    brand = app_info.get("brand", "")
    candidates = []
    if brand:
        candidates.append(os.path.expanduser(f"~/.config/{brand}-analytics-key.json"))
    candidates.extend([
        os.path.expanduser("~/.config/analytics-key.json"),
        os.path.expanduser("~/.config/mediacleaner-analytics-key.json"),
        os.path.expanduser("~/.config/whitenoise-analytics-key.json"),
        os.path.expanduser("~/.config/firebase-analytics-key.json"),
    ])

    repo_root = store.parent
    candidates.extend(glob.glob(str(repo_root / "*analytics*.json")))
    candidates.extend(glob.glob(str(repo_root / "*firebase*adminsdk*.json")))

    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate

    return None


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
    print(f"\n📊 [Загальні метрики за останні {days} днів ({label})]")
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
        date_ranges=[DateRange(start_date=f"{days}daysAgo", end_date="today")],
    )
    response = client.run_report(request)
    if not response.rows:
        print("  Дані ще не з'явилися або немає подій за цей період.")
        return None

    row = response.rows[0]
    headers = ["Active Users", "New Users", "Sessions", "Screen Views", "Avg Engagement (s)"]
    active_users = int(row.metric_values[0].value or 0)
    new_users = int(row.metric_values[1].value or 0)
    sessions = int(row.metric_values[2].value or 0)
    views = int(row.metric_values[3].value or 0)
    total_duration = float(row.metric_values[4].value or 0.0)
    avg_duration = round(total_duration / active_users, 1) if active_users else 0.0

    print(format_table(headers, [[active_users, new_users, sessions, views, avg_duration]]))
    return {
        "active_users": active_users,
        "new_users": new_users,
        "sessions": sessions,
        "views": views,
        "avg_duration": avg_duration,
    }


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
        date_ranges=[DateRange(start_date=f"{days}daysAgo", end_date="today")],
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

    # Funnel Stages Conversion Calculation
    print("\n📈 [Конверсійна вирва користувачів]")
    users_open = max(
        events_map.get("first_open", {}).get("users", 0),
        events_map.get("session_start", {}).get("users", 0),
        events_map.get("app_launched", {}).get("users", 0),
        1
    )

    core_users = max(
        events_map.get("playback_started", {}).get("users", 0),
        events_map.get("cleanup_screen_shown", {}).get("users", 0),
        events_map.get("media_swiped", {}).get("users", 0),
        0
    )

    paywall_users = events_map.get("paywall_shown", {}).get("users", 0)
    checkout_users = max(
        events_map.get("checkout_started", {}).get("users", 0),
        events_map.get("begin_checkout", {}).get("users", 0),
        0
    )
    purchase_users = max(
        events_map.get("subscription_purchased", {}).get("users", 0),
        events_map.get("purchase", {}).get("users", 0),
        events_map.get("in_app_purchase", {}).get("users", 0),
        0
    )

    funnel_summary = [
        ["1. Відкриття додатку", users_open, "100.0%"],
        ["2. Основна дія (Core Action)", core_users, f"{round(core_users / users_open * 100, 1)}%"],
        ["3. Показ пейволу", paywall_users, f"{round(paywall_users / users_open * 100, 1)}%"],
        ["4. Старт чекауту", checkout_users, f"{round(checkout_users / max(paywall_users, 1) * 100, 1)}% від пейволу" if paywall_users else "0.0%"],
        ["5. Покупка / Тріал", purchase_users, f"{round(purchase_users / max(paywall_users, 1) * 100, 1)}% від пейволу" if paywall_users else "0.0%"],
    ]
    print(format_table(["Етап вирви", "Користувачі", "Конверсія"], funnel_summary))

    if export_path:
        export_path.parent.mkdir(parents=True, exist_ok=True)
        with open(export_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["event_name", "event_count", "total_users", "category", "description"])
            for item in sorted(all_rows, key=lambda x: -x["count"]):
                writer.writerow([item["name"], item["count"], item["users"], item["category"], item["desc"]])
        print(f"\n  ✓ Вирву експортовано у: {export_path}")


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
        date_ranges=[DateRange(start_date=f"{days}daysAgo", end_date="today")],
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
    property_id = args.property_id or os.environ.get("GA4_PROPERTY_ID") or app_info.get("ga4_property_id")
    if not property_id and app_info.get("app_id") in KNOWN_APP_PROPERTIES:
        property_id = KNOWN_APP_PROPERTIES[app_info["app_id"]]

    if not property_id:
        sys.exit(
            "⚠️  GA4 Property ID не знайдено.\n"
            "Вкажіть його одним із способів:\n"
            "  1. Через прапорець: --property-id <ID>\n"
            "  2. Через змінну оточення: export GA4_PROPERTY_ID='<ID>'\n"
            "  3. Додайте у marketing/config.md рядок:\n"
            "     **GA4 Property ID**: <ID>\n"
            "  (Знайти Property ID можна в Google Analytics Console → Admin → Property Settings → Property ID)."
        )

    # 2. Resolve Credentials
    credentials_path = args.credentials or find_default_credentials(app_info, store)
    if credentials_path:
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path

    try:
        client = BetaAnalyticsDataClient()
    except Exception as e:
        sys.exit(
            f"❌ Не вдалося ініціалізувати Google Analytics клієнт: {e}\n"
            "Переконайтеся, що файл сервісного акаунта існує і доступний:\n"
            f"  Поточний шлях: {credentials_path or '(не вказано)'}\n"
            "Вкажіть через --credentials або export GOOGLE_APPLICATION_CREDENTIALS='...'"
        )

    exclude_debug = not args.include_debug

    print("=================================================================")
    print(f"📡 Google Analytics 4 / Firebase Telemetry · Property {property_id}")
    if app_info.get("brand"):
        print(f"App: {app_info['brand'].capitalize()} · Store: {store}")
    print("=================================================================")

    if args.realtime:
        run_realtime_report(client, property_id, exclude_debug=exclude_debug)
        return

    # Full Reports
    run_summary_report(client, property_id, args.days, exclude_debug=exclude_debug)

    export_file = (store / "metrics" / "ga4_funnel.csv") if args.export_csv else None
    run_funnel_report(client, property_id, args.days, exclude_debug=exclude_debug, export_path=export_file)

    run_country_report(client, property_id, args.days, exclude_debug=exclude_debug)

    print("\n=================================================================")
    print("✅ Збір аналітики успішно завершено.")
    print("=================================================================")


if __name__ == "__main__":
    main()
