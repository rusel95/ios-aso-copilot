"""What every command shares: paths, logging, the app identity, and the one way a subprocess is run."""

import json
import subprocess
import sys
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = SKILL_DIR / "scripts"
ENTRY = SCRIPTS_DIR / "copilot.py"
DEFAULT_STORE = Path.cwd() / "marketing"

# Logging configuration
LOG_LEVEL = 1  # 0=DEBUG, 1=INFO, 2=WARN, 3=ERROR


def set_log_level(debug=False, info=False, quiet=False):
    global LOG_LEVEL
    if debug:
        LOG_LEVEL = 0
    elif quiet:
        LOG_LEVEL = 2
    elif info:
        LOG_LEVEL = 1
    else:
        LOG_LEVEL = 1


def log_debug(msg):
    if LOG_LEVEL <= 0:
        print(f"[DEBUG] {msg}", file=sys.stderr)


def log_info(msg):
    if LOG_LEVEL <= 1:
        print(f"[INFO] {msg}", file=sys.stderr)


def log_warn(msg):
    if LOG_LEVEL <= 2:
        print(f"[WARN] ⚠️ {msg}", file=sys.stderr)


def log_error(msg):
    if LOG_LEVEL <= 3:
        print(f"[ERROR] 🛑 {msg}", file=sys.stderr)


def resolve_app_identity(store: Path):
    """Read App ID, version, brand tokens, and Apple Ads settings from config.md."""
    config_file = store / "config.md"
    if not config_file.is_file():
        raise SystemExit(f"Missing app identity: create {config_file} from assets/store-template/config.md.")

    values = {}
    for line in config_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        for label, key in (("**App ID**:", "app_id"), ("**Version**:", "version"),
                           ("**Brand tokens**:", "brand"), ("**GA4 Property ID**:", "ga4_property_id"),
                           ("**Firebase Property ID**:", "ga4_property_id"),
                           ("**Firebase Project ID**:", "firebase_project_id"),
                           ("**BigQuery Project ID**:", "bigquery_project_id"),
                           ("**RevenueCat Project ID**:", "rc_project_id"),
                           ("**Apple Ads profile**:", "ads_profile"),
                           ("**Apple Ads account**:", "ads_account"),
                           ("**Apple Ads genres**:", "ads_genres"),
                           ("**Apple Ads topic words**:", "ads_topics")):
            if line.startswith(label):
                values[key] = line.split(":", 1)[1].strip()

    app_id = (values.get("app_id") or "").split(maxsplit=1)[0] if values.get("app_id") else ""
    version = (values.get("version") or "").split(maxsplit=1)[0] if values.get("version") else ""
    if not app_id.isdigit() or not version or version.upper() == "TODO":
        raise SystemExit(f"Set a numeric **App ID** and working **Version** in {config_file}; refusing to guess.")
    property_parts = (values.get("ga4_property_id") or "").split(maxsplit=1)
    property_value = property_parts[0] if property_parts else ""
    if property_value and property_value.upper() != "TODO" and not property_value.isdigit():
        raise SystemExit(f"Set a numeric **GA4 Property ID** in {config_file}; refusing to guess.")

    rc_project_id = (values.get("rc_project_id") or "").split(maxsplit=1)[0] if values.get("rc_project_id") else None
    if rc_project_id and rc_project_id.upper().startswith("TODO"):
        rc_project_id = None

    ads_profile = values.get("ads_profile")
    if ads_profile and (ads_profile.upper() == "TODO" or ads_profile.upper().startswith("TODO")):
        ads_profile = None
    ads_account = values.get("ads_account")
    if ads_account and (ads_account.upper() == "TODO" or ads_account.upper().startswith("TODO")):
        ads_account = None

    genres = [g.strip().upper() for g in (values.get("ads_genres") or "").split(",") if g.strip() and not g.strip().upper().startswith("TODO")]
    topics = [t.strip().casefold() for t in (values.get("ads_topics") or "").split(",") if t.strip() and not t.strip().upper().startswith("TODO")]

    return {
        "app_id": app_id,
        "version": version,
        "brand": values.get("brand") or store.parent.name,
        "ga4_property_id": property_value if property_value.isdigit() else None,
        "rc_project_id": rc_project_id,
        "ads_profile": ads_profile,
        "ads_account": ads_account,
        "ads_genres": genres,
        "ads_topics": topics,
    }


def run_cmd(args, capture=True, check=False, input_text=None):
    """Run shell command with clean output capture and logging."""
    log_debug(f"run_cmd: {' '.join(str(a) for a in args)}")
    try:
        res = subprocess.run(args, capture_output=capture, text=True, check=check, input=input_text)
        log_debug(f"run_cmd [{args[0]}] exit code: {res.returncode}")
        return res.returncode, res.stdout, res.stderr
    except FileNotFoundError:
        log_error(f"Command not found: {args[0]}")
        return -1, "", f"Command not found: {args[0]}"
    except Exception as e:
        log_error(f"Command execution error: {e}")
        return -1, "", str(e)


def compact_asc_output(output, kind):
    """Return a bounded summary of structured ASC data without review bodies or raw links."""
    try:
        payload = json.loads(output)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(payload, dict):
        return None
    if kind == "versions" and isinstance(payload.get("data"), list):
        rows = payload["data"]
        if not rows:
            return "ASC reports no versions."
        labels = []
        for row in rows[:5]:
            attributes = (row.get("attributes") or {}) if isinstance(row, dict) else {}
            if not isinstance(attributes, dict):
                attributes = {}
            labels.append(f"{attributes.get('versionString', 'version unknown')}: "
                          f"{attributes.get('appStoreState', 'state unknown')} / "
                          f"{attributes.get('appVersionState', 'build state unknown')}")
        suffix = f"; {len(rows) - 5} more omitted" if len(rows) > 5 else ""
        return f"{len(rows)} versions; " + "; ".join(labels) + suffix
    if kind == "ratings" and "averageRating" in payload and "totalCount" in payload:
        countries = payload.get("byCountry")
        histogram = payload.get("histogram")
        if isinstance(histogram, dict):
            counts = ", ".join(f"{star}:{histogram.get(str(star), histogram.get(star, '?'))}"
                                for star in range(1, 6))
            stars = f"stars {counts}"
        else:
            stars = "star histogram unavailable from ASC response"
        country_summary = ""
        if isinstance(countries, list):
            entries = [f"{row.get('country', '?')}:{row.get('ratingCount', '?')} @"
                       f"{row.get('averageRating', '?')}/5" for row in countries if isinstance(row, dict)]
            country_summary = "; " + ", ".join(entries) if entries else ""
        country_count = payload.get("countryCount")
        if country_count is None:
            country_count = len(countries) if isinstance(countries, list) else "unknown"
        return (f"Average {payload['averageRating']}/5; {payload['totalCount']} ratings; "
                f"{country_count} storefronts{country_summary}; {stars}")
    if kind == "unreplied" and isinstance(payload.get("data"), list):
        meta = payload.get("meta")
        paging = meta.get("paging") if isinstance(meta, dict) else None
        total = paging.get("total") if isinstance(paging, dict) else None
        if isinstance(total, int):
            return f"{total} unresponded reviews (ASC total; review text omitted)."
        return f"{len(payload['data'])} unresponded reviews returned; total unknown; review text omitted."
    return None
