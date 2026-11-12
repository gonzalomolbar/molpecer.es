"""The calendar-2026 API: one Lambda behind CloudFront, a small router."""
import hashlib
import re
import time

import boto3
from botocore.config import Config

from shared import config, sessions, store
from shared.http import Request, cookie, error, respond

POST_ID = re.compile(r"^[0-9A-Z]{26}$")
_s3 = None


def s3():
    global _s3
    if _s3 is None:
        _s3 = boto3.client("s3", region_name=config.REGION,
                           config=Config(signature_version="s3v4", s3={"addressing_style": "virtual", "us_east_1_regional_endpoint": "regional"}))
    return _s3


# ---------- bot checks: proof of work and honeypot, no third party ----------
POW_BITS = 13           # leading zero bits; about 8k hashes on average, a second or so in a browser
POW_MIN_AGE = 3         # seconds between page load and submit
POW_MAX_AGE = 3600


def pow_ok(token, now=None):
    """token = "<load_ts>.<nonce>", valid when sha256("ts.nonce.domain") has POW_BITS leading zeros
    and ts is between POW_MIN_AGE and POW_MAX_AGE seconds ago."""
    if not isinstance(token, str) or len(token) > 64:
        return False
    ts, _, nonce = token.partition(".")
    if not ts.isdigit() or not nonce.isdigit():
        return False
    age = int(now or time.time()) - int(ts)
    if age < POW_MIN_AGE or age > POW_MAX_AGE:
        return False
    digest = hashlib.sha256(f"{ts}.{nonce}.{config.DOMAIN}".encode()).digest()
    return int.from_bytes(digest[:4], "big") >> (32 - POW_BITS) == 0


def honeypot_hit(body):
    return bool(str(body.get("website") or "").strip())


# ---------- handlers ----------
def health(req):
    return respond(200, {"ok": True})


def create_post(req):
    if not req.same_origin():
        return error(403, "csrf")
    body = req.json()
    if body is None:
        return error(400, "bad_json")
    kind = body.get("kind")
    name = str(body.get("name") or "").strip()[: config.LIMITS["max_name_chars"]]
    text = str(body.get("text") or "").strip()[: config.LIMITS["max_text_chars"]]
    if kind not in config.KINDS:
        return error(400, "bad_fields")
    upload = body.get("upload")
    if not isinstance(upload, dict):
        return error(400, "missing_upload")
    try:
        size = int(upload.get("size", 0))
    except (TypeError, ValueError):
        return error(400, "bad_size")
    ctype = str(upload.get("type") or "")
    if size < 1 or size > config.LIMITS["max_upload_bytes"]:
        return error(413, "too_big", limit=config.LIMITS["max_upload_bytes"])
    if not ctype.startswith("image/") or len(ctype) > 60:
        return error(400, "bad_type")

    net = req.net()
    if store.is_banned(net):
        return error(403, "banned")
    if not pow_ok(body.get("pow")):
        return error(400, "bot_check")
    if honeypot_hit(body) or not req.header("user-agent"):
        # Looks like a bot: answer as if it worked, store nothing, set no cookie.
        return respond(201, {"id": store.ulid(), "code": store.new_code(name)})

    day = store.today()
    if store.count(f"posts#GLOBAL#{day}") >= config.LIMITS["global_posts_day"]:
        return error(429, "full_today")
    if store.bump(f"posts#{net}#{day}") > config.LIMITS["per_net_posts_day"]:
        return error(429, "limit_posts")
    if store.bump(f"bytes#{net}#{day}", size) > config.LIMITS["per_net_bytes_day"]:
        return error(429, "limit_bytes")
    store.bump(f"posts#GLOBAL#{day}")

    post_id = store.ulid()
    now = store.now_iso()
    post = {
        "pk": f"POST#{post_id}", "sk": "POST", "id": post_id, "kind": kind,
        "name": name, "text": text, "created": now, "status": "awaiting_upload",
        "visitor": req.visitor(), "actions": [],
        "ttl": int(time.time()) + 2 * 86400,  # expires if never uploaded; the processor removes it
        "declared_size": size,
    }
    code = store.create_post(post, name)

    out = {
        "id": post_id, "code": code,
        "upload": s3().generate_presigned_post(
            Bucket=config.DATA_BUCKET, Key=f"raw/{post_id}",
            Fields={"Content-Type": ctype, "x-amz-meta-post": post_id},
            Conditions=[{"Content-Type": ctype}, {"x-amz-meta-post": post_id}, ["content-length-range", 1, size]],
            ExpiresIn=config.UPLOAD_URL_SECONDS,
        ),
    }
    value, max_age = sessions.visitor_cookie(code)
    return respond(201, out, cookies=[cookie("calendar2026_s", value, max_age)])


def unlock(req):
    if not req.same_origin():
        return error(403, "csrf")
    body = req.json() or {}
    code = store.normalise_code(str(body.get("code") or ""))
    if not code or "-" not in code:
        return error(400, "bad_code")
    net = req.net()
    day = store.today()
    if store.count(f"unlocks#GLOBAL#{day}") >= config.LIMITS["global_unlocks_day"]:
        return error(429, "full_today")
    if store.bump(f"unlocks#{net}#{day}") > config.LIMITS["per_net_unlocks_day"]:
        return error(429, "limit_unlocks")
    store.bump(f"unlocks#GLOBAL#{day}")
    post = store.post_for_code(code)
    if not post or post.get("status") == "deleted":
        return error(401, "unknown_code")
    value, max_age = sessions.visitor_cookie(code)
    return respond(200, {"ok": True}, cookies=[cookie("calendar2026_s", value, max_age)])


def admin_login(req):
    if not req.same_origin():
        return error(403, "csrf")
    body = req.json() or {}
    name = str(body.get("name") or "").lower()
    code = str(body.get("code") or "")
    if name not in config.ADMINS or not code or len(code) > 200:
        return error(400, "bad_fields")
    hour = store.hour()
    if store.count(f"loginfail#GLOBAL#{hour}") >= config.LIMITS["global_login_fails_hour"]:
        return error(429, "login_disabled")
    if not pow_ok(body.get("pow")):
        return error(400, "bot_check")
    if not sessions.check_admin_code(name, code):
        store.bump(f"loginfail#GLOBAL#{hour}", ttl_seconds=7200)
        return error(401, "wrong_code")
    a_value, a_age = sessions.admin_cookie(name)
    p_value, p_age = sessions.preview_cookie(name)
    return respond(200, {"ok": True, "name": name},
                   cookies=[cookie("calendar2026_a", a_value, a_age, "Strict"), cookie("calendar2026_s", p_value, p_age)])


def admin_logout(req):
    return respond(200, {"ok": True}, cookies=[cookie("calendar2026_a", "", 0, "Strict"), cookie("calendar2026_s", "", 0)])


def require_admin(req):
    return sessions.verify_admin(req.cookies.get("calendar2026_a"))


def wall_me(req, who):
    return respond(200, {"name": who})


def wall_posts(req, who):
    q = req.query
    kind = q.get("kind") if q.get("kind") in config.KINDS else None
    status = q.get("status") if q.get("status") in ("awaiting_upload", "processing", "done", "failed", "deleted") else None
    items, cursor = store.list_posts(kind=kind, status=status, cursor=q.get("cursor"))
    return respond(200, {"posts": [_wall_item(p) for p in items], "cursor": cursor})


def _wall_item(p):
    item = {k: p.get(k) for k in ("id", "kind", "name", "text", "created", "status", "code", "visitor", "actions", "width", "height")}
    if p.get("status") == "done":
        item["full"] = _signed_get(f"media/{p['id']}/full.webp")
        item["thumb"] = _signed_get(f"media/{p['id']}/thumb.webp")
    return item


def wall_post(req, who, post_id):
    post = store.get_post(post_id)
    if not post:
        return error(410, "gone")
    return respond(200, {"post": _wall_item(post)})


def _signed_get(key):
    return s3().generate_presigned_url("get_object", Params={"Bucket": config.DATA_BUCKET, "Key": key}, ExpiresIn=600)


def wall_delete(req, who, post_id):
    if not req.same_origin():
        return error(403, "csrf")
    post = store.get_post(post_id)
    if not post:
        return error(410, "gone")
    for key in (f"media/{post_id}/full.webp", f"media/{post_id}/thumb.webp", f"raw/{post_id}"):
        try:
            s3().delete_object(Bucket=config.DATA_BUCKET, Key=key)
        except Exception:
            pass
    actions = list(post.get("actions") or []) + [{"who": who, "what": "delete", "at": store.now_iso()}]
    store.update_post(post_id, status="deleted", text="", actions=actions)
    return respond(200, {"ok": True})


def wall_ban(req, who):
    if not req.same_origin():
        return error(403, "csrf")
    body = req.json() or {}
    post_id = str(body.get("post") or "")
    if not POST_ID.match(post_id):
        return error(400, "bad_fields")
    post = store.get_post(post_id)
    if not post:
        return error(410, "gone")
    net = (post.get("visitor") or {}).get("net") or ""
    if not net:
        return error(400, "no_net")
    store.ban(net, who, post_id)
    actions = list(post.get("actions") or []) + [{"who": who, "what": "ban", "at": store.now_iso()}]
    store.update_post(post_id, actions=actions)
    return respond(200, {"ok": True, "net": net})


def wall_unban(req, who):
    if not req.same_origin():
        return error(403, "csrf")
    net = str((req.json() or {}).get("net") or "")[:64]
    if not net:
        return error(400, "bad_fields")
    store.unban(net)
    return respond(200, {"ok": True})


def wall_bans(req, who):
    return respond(200, {"bans": [{"net": b.get("net"), "by": b.get("by"), "at": b.get("at"), "post": b.get("post")} for b in store.bans()]})


# ---------- router ----------
def route(req):
    m, p = req.method, req.path
    if p == "/api/health" and m == "GET":
        return health(req)
    if p == "/api/posts" and m == "POST":
        return create_post(req)
    if p == "/api/unlock" and m == "POST":
        return unlock(req)
    if p == "/api/admin/login" and m == "POST":
        return admin_login(req)
    if p == "/api/admin/logout" and m == "POST":
        return admin_logout(req)
    if p.startswith("/api/wall/"):
        who = require_admin(req)
        if not who:
            return error(401, "locked")
        if p == "/api/wall/me" and m == "GET":
            return wall_me(req, who)
        if p == "/api/wall/posts" and m == "GET":
            return wall_posts(req, who)
        mm = re.match(r"^/api/wall/posts/([0-9A-Z]{26})$", p)
        if mm and m == "GET":
            return wall_post(req, who, mm.group(1))
        if mm and m == "DELETE":
            return wall_delete(req, who, mm.group(1))
        if p == "/api/wall/bans" and m == "GET":
            return wall_bans(req, who)
        if p == "/api/wall/bans" and m == "POST":
            return wall_ban(req, who)
        if p == "/api/wall/unban" and m == "POST":
            return wall_unban(req, who)
    return error(400, "no_such_route")


def handler(event, context):
    try:
        return route(Request(event))
    except Exception as e:  # never leak internals; the log has the trace
        print("ERROR", repr(e))
        return error(500, "internal")
