"""Environment and parameters, read once per container."""
import json
import os
import time

import boto3

REGION = os.environ.get("AWS_REGION", "us-east-1")
TABLE = os.environ.get("TABLE", "calendar-2026")
DATA_BUCKET = os.environ.get("DATA_BUCKET", "calendar-2026-data")
DOMAIN = os.environ.get("DOMAIN", "calendar-2026.toribios.molpecer.es")
ORIGIN = f"https://{DOMAIN}"
NOTIFY_EMAIL = os.environ.get("NOTIFY_EMAIL", "")
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "")
PARAM_PREFIX = os.environ.get("PARAM_PREFIX", "/calendar-2026")

MONTHS = ["january", "february", "march", "april", "may", "june",
          "july", "august", "september", "october", "november", "december"]
ADMINS = ("toribios", "molpeceres")
KINDS = ("photo", "doodle")

# The visitor cookie must outlive the calendar year; the edge also checks this.
VISITOR_COOKIE_EXPIRY = 1832889600  # 2028-01-31T00:00:00Z
ADMIN_COOKIE_SECONDS = 30 * 24 * 3600
UPLOAD_URL_SECONDS = 300


def _int(name, default):
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return int(default)


LIMITS = {
    "per_net_posts_day": _int("PER_NET_POSTS_DAY", 50),
    "per_net_bytes_day": _int("PER_NET_BYTES_DAY", 500 * 1024 * 1024),
    "per_net_unlocks_day": _int("PER_NET_UNLOCKS_DAY", 50),
    "global_posts_day": _int("GLOBAL_POSTS_DAY", 150),
    "global_unlocks_day": _int("GLOBAL_UNLOCKS_DAY", 2000),
    "global_login_fails_hour": _int("GLOBAL_LOGIN_FAILS_HOUR", 100),
    "max_upload_bytes": _int("MAX_UPLOAD_BYTES", 10 * 1024 * 1024),
    "max_text_chars": _int("MAX_TEXT_CHARS", 1000),
    "max_name_chars": _int("MAX_NAME_CHARS", 60),
}

_params = {}
_params_at = 0.0
_ssm = None


PARAM_NAMES = ("session_secret", "admin_secret", "admins")


def params():
    """The /calendar-2026/* secrets as a dict keyed by name, fetched by name and cached 5 minutes."""
    global _params, _params_at, _ssm
    if _params and time.time() - _params_at < 300:
        return _params
    if _ssm is None:
        _ssm = boto3.client("ssm", region_name=REGION)
    page = _ssm.get_parameters(Names=[f"{PARAM_PREFIX}/{n}" for n in PARAM_NAMES], WithDecryption=True)
    out = {p["Name"].rsplit("/", 1)[-1]: p["Value"] for p in page.get("Parameters", [])}
    _params, _params_at = out, time.time()
    return out


def admins():
    """{name: sha256 hex of the admin code}; missing or malformed means nobody can log in."""
    try:
        data = json.loads(params().get("admins", "{}"))
    except ValueError:
        return {}
    return {k.lower(): v for k, v in data.items() if isinstance(v, str)}
