"""Signed cookies. The visitor cookie is verified by the edge (secret shared through the KVS);
the admin cookie only by the API (separate secret)."""
import hashlib
import hmac
import re
import time

from . import config

SUBJECT = re.compile(r"^[A-Z0-9-]{1,40}$")


def _sign(kind, subject, exp, secret):
    payload = f"{kind}.{subject}.{exp}"
    sig = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{payload}.{sig}"


def visitor_cookie(subject, now=None):
    """Kind v: opens arrived months. Fixed expiry so every visitor cookie dies together."""
    exp = config.VISITOR_COOKIE_EXPIRY
    return _sign("v", subject, exp, config.params()["session_secret"]), max(exp - int(now or time.time()), 1)


def preview_cookie(name, now=None):
    """Kind p: an admin's edge cookie, bypasses the time lock."""
    exp = int(now or time.time()) + config.ADMIN_COOKIE_SECONDS
    return _sign("p", name.upper(), exp, config.params()["session_secret"]), config.ADMIN_COOKIE_SECONDS


def admin_cookie(name, now=None):
    exp = int(now or time.time()) + config.ADMIN_COOKIE_SECONDS
    return _sign("a", name.upper(), exp, config.params()["admin_secret"]), config.ADMIN_COOKIE_SECONDS


def verify_admin(value, now=None):
    """Returns the admin name (lowercase) or None."""
    parts = (value or "").split(".")
    if len(parts) != 4:
        return None
    kind, subject, exp, sig = parts
    if kind != "a" or not SUBJECT.match(subject) or not exp.isdigit() or int(exp) <= int(now or time.time()):
        return None
    secret = config.params().get("admin_secret")
    if not secret:
        return None
    expected = _sign("a", subject, exp, secret).rsplit(".", 1)[1]
    if not hmac.compare_digest(expected, sig):
        return None
    name = subject.lower()
    return name if name in config.ADMINS else None


PBKDF2_ROUNDS = 200_000


def hash_admin_code(code, salt=None):
    """pbkdf2$<salt hex>$<hash hex>; salted and slow because the codes are chosen by people."""
    import os
    salt = salt if salt is not None else os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", code.encode(), salt, PBKDF2_ROUNDS)
    return f"pbkdf2${salt.hex()}${digest.hex()}"


def check_admin_code(name, code):
    stored = config.admins().get(name.lower(), "")
    parts = stored.split("$")
    if len(parts) != 3 or parts[0] != "pbkdf2":
        return False
    try:
        salt = bytes.fromhex(parts[1])
    except ValueError:
        return False
    return hmac.compare_digest(hash_admin_code(code, salt), stored)
