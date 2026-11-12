"""Lambda Function URL (payload v2) request parsing and JSON responses."""
import base64
import decimal
import json

from . import config


class Request:
    def __init__(self, event):
        ctx = event.get("requestContext", {}).get("http", {})
        self.method = ctx.get("method", "GET").upper()
        self.path = event.get("rawPath", "/")
        self.headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
        self.query = event.get("queryStringParameters") or {}
        self.cookies = {}
        for c in event.get("cookies") or []:
            name, _, value = c.partition("=")
            self.cookies[name.strip()] = value.strip()
        body = event.get("body") or ""
        if event.get("isBase64Encoded"):
            body = base64.b64decode(body).decode("utf-8", "replace")
        self.raw_body = body

    def json(self):
        if not self.raw_body:
            return {}
        try:
            data = json.loads(self.raw_body)
        except ValueError:
            return None
        return data if isinstance(data, dict) else None

    def header(self, name, default=""):
        return self.headers.get(name.lower(), default)

    def same_origin(self):
        """CSRF check for state-changing calls: a same-origin fetch or a top-level navigation."""
        site = self.header("sec-fetch-site")
        origin = self.header("origin")
        if origin:
            return origin == config.ORIGIN
        return site == "same-origin"

    # --- viewer facts from CloudFront ---
    def ip(self):
        addr = self.header("cloudfront-viewer-address")
        if not addr:
            return ""
        return addr.rsplit(":", 1)[0] if ":" in addr else addr

    def net(self):
        ip = self.ip()
        if ":" in ip:  # IPv6: /64
            parts = ip.split(":")
            return ":".join(parts[:4]) + "::/64"
        return ip

    def visitor(self):
        h = self.header
        device = "mobile" if h("cloudfront-is-mobile-viewer") == "true" else "tablet" if h("cloudfront-is-tablet-viewer") == "true" else "desktop" if h("cloudfront-is-desktop-viewer") == "true" else ""
        return {
            "ip": self.ip(), "net": self.net(),
            "country": h("cloudfront-viewer-country"), "region": h("cloudfront-viewer-country-region"),
            "city": h("cloudfront-viewer-city"), "postal": h("cloudfront-viewer-postal-code"),
            "lat": h("cloudfront-viewer-latitude"), "lon": h("cloudfront-viewer-longitude"),
            "tz": h("cloudfront-viewer-time-zone"), "device": device,
            "ua": h("user-agent")[:300], "lang": h("accept-language")[:100], "referer": h("referer")[:300],
        }


def _plain(value):
    """DynamoDB hands numbers back as Decimal, which json refuses."""
    if isinstance(value, decimal.Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    raise TypeError(f"not serialisable: {type(value).__name__}")


def respond(status, body, cookies=None):
    out = {
        "statusCode": status,
        "headers": {"content-type": "application/json; charset=utf-8", "cache-control": "no-store"},
        "body": json.dumps(body, ensure_ascii=False, default=_plain),
    }
    if cookies:
        out["cookies"] = cookies
    return out


def error(status, code, **extra):
    body = {"error": code}
    body.update(extra)
    return respond(status, body)


def cookie(name, value, max_age, same_site="Lax"):
    return f"{name}={value}; Max-Age={max_age}; Path=/; Secure; HttpOnly; SameSite={same_site}"
