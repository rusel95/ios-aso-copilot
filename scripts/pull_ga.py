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
    "first_playback": ("Перше успішне відтворення", "core"),
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
    ga4_creds = ""
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
            elif line.startswith("**GA4 Credentials**:"):
                val = line.split(":", 1)[1].strip()
                if val and val.split(maxsplit=1)[0].upper() != "TODO":
                    ga4_creds = val.strip("\"'")
            elif line.startswith("**GA4 Funnel Steps**:"):
                val = line.split(":", 1)[1].strip()
                ga4_funnel_steps = [
                    step.strip() for step in val.replace("→", ",").split(",") if step.strip()
                ]

    return {
        "app_id": app_id,
        "brand": brand,
        "ga4_property_id": ga4_property_id,
        "ga4_creds": ga4_creds,
        "ga4_funnel_steps": ga4_funnel_steps,
    }


def find_default_credentials(app_info: dict):
    """Prefer this app's explicit credential path, then a configured runtime credential."""
    if app_info.get("ga4_creds"):
        return os.path.expanduser(app_info["ga4_creds"])
    return os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")


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
        date_ranges=[DateRange(start_date=f"{days}daysAgo", end_date="yesterday")],
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

    sequential_funnel_ok = run_sequential_funnel_report(
        property_id,
        app_info.get("ga4_funnel_steps", []),
        args.days,
        exclude_debug=exclude_debug,
    )

    if not sequential_funnel_ok:
        print("\n⚠️ Збір частковий: послідовну вирву GA4 не підтверджено.")
        sys.exit(2)

    print("\n=================================================================")
    print("✅ Збір аналітики успішно завершено.")
    print("=================================================================")


if __name__ == "__main__":
    main()
