import base64
import json
import time

import boto3
import pytest

from conftest import ADMIN_CODE


def event(method, path, body=None, cookies=None, headers=None, origin=True):
    h = {"cloudfront-viewer-address": "203.0.113.9:4455", "cloudfront-viewer-country": "ES", "cloudfront-viewer-city": "Madrid",
         "cloudfront-is-mobile-viewer": "true", "user-agent": "test"}
    if origin:
        h["origin"] = "https://calendar-2026.toribios.molpecer.es"
    h.update(headers or {})
    return {"rawPath": path, "requestContext": {"http": {"method": method}}, "headers": h,
            "cookies": [f"{k}={v}" for k, v in (cookies or {}).items()],
            "body": json.dumps(body) if body is not None else "", "queryStringParameters": {}}


@pytest.fixture
def app(aws, monkeypatch):
    from api import app as api_app
    monkeypatch.setattr(api_app, "pow_ok", lambda token, now=None: token == "good")
    return api_app


def call(app, *a, **k):
    r = app.handler(event(*a, **k), None)
    return r["statusCode"], json.loads(r["body"]), r.get("cookies", [])


def test_health(app):
    assert call(app, "GET", "/api/health")[0] == 200


UP = {"size": 1234, "type": "image/jpeg"}


def test_photo_creates_code_and_cookie(app):
    status, body, cookies = call(app, "POST", "/api/posts", {"kind": "photo", "month": "march", "name": "Luis García", "text": "hola", "pow": "good", "upload": UP})
    assert status == 201
    assert body["code"].startswith("LUISGA-") and len(body["code"]) == 11
    assert cookies and cookies[0].startswith("calendar2026_s=v.") and "HttpOnly" in cookies[0]
    from shared import store
    post = store.post_for_code(body["code"])
    assert post["status"] == "awaiting_upload" and post["visitor"]["city"] == "Madrid" and post["visitor"]["device"] == "mobile" and post["text"] == "hola"


def test_photo_returns_presigned_post(app):
    status, body, _ = call(app, "POST", "/api/posts", {"kind": "photo", "month": "may", "pow": "good", "upload": {"size": 1234, "type": "image/jpeg"}})
    assert status == 201
    assert body["code"].startswith("CAL-")
    up = body["upload"]
    assert up["fields"]["key"] == f"raw/{body['id']}" and up["fields"]["Content-Type"] == "image/jpeg"
    policy = json.loads(base64.b64decode(up["fields"]["policy"]))
    assert ["content-length-range", 1, 1234] in policy["conditions"]


def test_validation(app):
    assert call(app, "POST", "/api/posts", {"kind": "note", "month": "march", "text": "x", "pow": "good", "upload": UP})[1]["error"] == "bad_fields"
    assert call(app, "POST", "/api/posts", {"kind": "doodle", "month": "march", "pow": "good"})[1]["error"] == "missing_upload"
    assert call(app, "POST", "/api/posts", {"kind": "photo", "month": "nope", "pow": "good"})[1]["error"] == "bad_fields"
    assert call(app, "POST", "/api/posts", {"kind": "photo", "month": "march", "pow": "good", "upload": {"size": 99999999, "type": "image/jpeg"}})[0] == 413
    assert call(app, "POST", "/api/posts", {"kind": "photo", "month": "march", "pow": "good", "upload": {"size": 10, "type": "text/html"}})[1]["error"] == "bad_type"
    assert call(app, "POST", "/api/posts", {"kind": "photo", "month": "march", "text": "x", "pow": "bad", "upload": UP})[1]["error"] == "bot_check"
    assert call(app, "POST", "/api/posts", {"kind": "photo", "month": "march", "text": "x", "pow": "good", "upload": UP}, origin=False)[1]["error"] == "csrf"
    assert call(app, "POST", "/api/posts", {"kind": "photo", "month": "march", "text": "x", "pow": "good", "upload": UP}, origin=False, headers={"sec-fetch-site": "same-origin"})[0] == 201
    assert call(app, "POST", "/api/posts", {"kind": "photo", "month": "march", "text": "x", "pow": "good", "upload": UP}, headers={"origin": "https://evil.example"})[1]["error"] == "csrf"


def test_limits_per_net_and_global(app):
    body = {"kind": "photo", "month": "march", "text": "x", "pow": "good", "upload": UP}
    for _ in range(3):
        assert call(app, "POST", "/api/posts", body)[0] == 201
    assert call(app, "POST", "/api/posts", body)[1]["error"] == "limit_posts"
    for suffix in ("3:4:5:6", "aaaa::1", "bbbb::2"):
        assert call(app, "POST", "/api/posts", body, headers={"cloudfront-viewer-address": f"2001:db8:1:2:{suffix}:9000"})[0] == 201
    assert call(app, "POST", "/api/posts", body, headers={"cloudfront-viewer-address": "2001:db8:1:2:ffff::1:9000"})[1]["error"] == "limit_posts", "same /64"
    assert call(app, "POST", "/api/posts", body, headers={"cloudfront-viewer-address": "2001:db8:1:3::1:9000"})[0] == 201, "other /64"
    assert call(app, "POST", "/api/posts", body, headers={"cloudfront-viewer-address": "198.51.100.7:1"})[0] == 201
    assert call(app, "POST", "/api/posts", body, headers={"cloudfront-viewer-address": "198.51.100.8:1"})[1]["error"] == "full_today"


def test_ban_blocks(app):
    from shared import store
    store.ban("203.0.113.9", "toribios")
    assert call(app, "POST", "/api/posts", {"kind": "photo", "month": "march", "text": "x", "pow": "good", "upload": UP})[1]["error"] == "banned"


def test_unlock(app):
    _, body, _ = call(app, "POST", "/api/posts", {"kind": "photo", "month": "march", "name": "Ana", "text": "x", "pow": "good", "upload": UP})
    status, _, cookies = call(app, "POST", "/api/unlock", {"code": body["code"].lower().replace("-", " - ")})
    assert status == 200 and cookies[0].startswith(f"calendar2026_s=v.{body['code']}.")
    assert call(app, "POST", "/api/unlock", {"code": "ANA-ZZZZ"})[1]["error"] == "unknown_code"
    assert call(app, "POST", "/api/unlock", {"code": "nodash"})[1]["error"] == "bad_code"
    for _ in range(2):
        call(app, "POST", "/api/unlock", {"code": "ANA-ZZZZ"})
    assert call(app, "POST", "/api/unlock", {"code": body["code"]})[1]["error"] == "limit_unlocks"


def test_visitor_cookie_matches_edge_format(app):
    from shared import sessions, config
    import hashlib, hmac
    value, max_age = sessions.visitor_cookie("ANA-7K2P", now=1700000000)
    kind, subject, exp, sig = value.split(".")
    assert (kind, subject, exp) == ("v", "ANA-7K2P", str(config.VISITOR_COOKIE_EXPIRY))
    assert sig == hmac.new(b"edge-secret", f"v.ANA-7K2P.{exp}".encode(), hashlib.sha256).hexdigest()[:32]
    assert max_age == config.VISITOR_COOKIE_EXPIRY - 1700000000


def login(app):
    status, body, cookies = call(app, "POST", "/api/admin/login", {"name": "toribios", "code": ADMIN_CODE, "pow": "good"})
    assert status == 200 and body["name"] == "toribios"
    jar = {}
    for c in cookies:
        k, v = c.split(";")[0].split("=", 1)
        jar[k] = v
    assert jar["calendar2026_a"].startswith("a.TORIBIOS.") and jar["calendar2026_s"].startswith("p.TORIBIOS.")
    return jar


def test_admin_login_and_wall(app):
    assert call(app, "GET", "/api/wall/me")[0] == 401
    assert call(app, "POST", "/api/admin/login", {"name": "toribios", "code": "wrong", "pow": "good"})[1]["error"] == "wrong_code"
    assert call(app, "POST", "/api/admin/login", {"name": "molpeceres", "code": ADMIN_CODE, "pow": "good"})[1]["error"] == "wrong_code", "no code set for this admin"
    jar = login(app)
    assert call(app, "GET", "/api/wall/me", cookies=jar)[1]["name"] == "toribios"
    tampered = jar["calendar2026_a"][:-1] + ("0" if jar["calendar2026_a"][-1] != "0" else "1")
    assert call(app, "GET", "/api/wall/me", cookies={"calendar2026_a": tampered})[0] == 401
    assert call(app, "GET", "/api/wall/me", cookies={"calendar2026_a": jar["calendar2026_s"]})[0] == 401, "preview cookie is not admin"

    _, p1, _ = call(app, "POST", "/api/posts", {"kind": "photo", "month": "march", "name": "Ana", "text": "hola", "pow": "good", "upload": UP})
    _, p2, _ = call(app, "POST", "/api/posts", {"kind": "doodle", "month": "april", "name": "Bo", "text": "hey", "pow": "good", "upload": UP})
    from shared import store as st
    st.update_post(p2["id"], status="done", width=1600, height=1067, bytes=224090)  # numbers come back as Decimal
    status, body, _ = call(app, "GET", "/api/wall/posts", cookies=jar)
    assert status == 200 and [p["name"] for p in body["posts"]] == ["Bo", "Ana"]
    assert body["posts"][0]["width"] == 1600 and body["posts"][0]["thumb"].startswith("https://")
    assert body["posts"][0]["visitor"]["ip"] == "203.0.113.9"
    ev = event("GET", "/api/wall/posts", cookies=jar); ev["queryStringParameters"] = {"month": "march"}
    assert [p["name"] for p in json.loads(app.handler(ev, None)["body"])["posts"]] == ["Ana"]

    status, body, _ = call(app, "GET", f"/api/wall/posts/{p2['id']}", cookies=jar)
    assert status == 200 and body["post"]["name"] == "Bo" and body["post"]["full"].startswith("https://")
    assert call(app, "GET", "/api/wall/posts/01ARZ3NDEKTSV4RRFFQ69G5FAV", cookies=jar)[0] == 410
    assert call(app, "GET", f"/api/wall/posts/{p2['id']}")[0] == 401
    assert call(app, "DELETE", f"/api/wall/posts/{p1['id']}", cookies=jar)[0] == 200
    from shared import store
    post = store.get_post(p1["id"])
    assert post["status"] == "deleted" and post["actions"][0]["who"] == "toribios" and post["text"] == ""
    assert call(app, "POST", "/api/unlock", {"code": p1["code"]})[1]["error"] == "unknown_code", "deleted post's code no longer unlocks"

    status, body, _ = call(app, "POST", "/api/wall/bans", {"post": p2["id"]}, cookies=jar)
    assert status == 200 and body["net"] == "203.0.113.9"
    assert call(app, "GET", "/api/wall/bans", cookies=jar)[1]["bans"][0]["by"] == "toribios"
    assert call(app, "POST", "/api/wall/unban", {"net": "203.0.113.9"}, cookies=jar)[0] == 200
    assert call(app, "GET", "/api/wall/bans", cookies=jar)[1]["bans"] == []
    assert call(app, "DELETE", f"/api/wall/posts/{p2['id']}", cookies=jar, origin=False)[1]["error"] == "csrf"


def test_login_global_failure_cap(app):
    for _ in range(3):
        call(app, "POST", "/api/admin/login", {"name": "toribios", "code": "wrong", "pow": "good"})
    assert call(app, "POST", "/api/admin/login", {"name": "toribios", "code": ADMIN_CODE, "pow": "good"})[1]["error"] == "login_disabled"


def test_code_uniqueness(app, monkeypatch):
    from shared import store
    monkeypatch.setattr(store, "new_code", lambda name, length=4: "ANA-SAME" if length == 4 else "ANA-OTHER")
    seen = set()
    for i in range(2):
        post = {"pk": f"POST#{store.ulid()}", "sk": "POST", "created": store.now_iso(), "status": "done"}
        seen.add(store.create_post(post, "Ana"))
    assert seen == {"ANA-SAME", "ANA-OTHER"}


def test_unknown_route_is_400_not_404(app):
    assert call(app, "GET", "/api/whatever")[0] == 400


def test_proof_of_work_real(aws, monkeypatch):
    import hashlib
    from api import app as api_app
    ts = 1_800_000_000
    nonce = 0
    while int.from_bytes(hashlib.sha256(f"{ts}.{nonce}.calendar-2026.toribios.molpecer.es".encode()).digest()[:4], "big") >> (32 - api_app.POW_BITS):
        nonce += 1
    token = f"{ts}.{nonce}"
    assert api_app.pow_ok(token, now=ts + 10)
    assert not api_app.pow_ok(token, now=ts + 1), "too fast"
    assert not api_app.pow_ok(token, now=ts + 4000), "too old"
    assert not api_app.pow_ok(f"{ts}.{nonce + 1}", now=ts + 10), "wrong nonce"
    assert not api_app.pow_ok("junk", now=ts + 10)


def test_honeypot_fakes_success(app):
    status, body, cookies = call(app, "POST", "/api/posts", {"kind": "photo", "month": "march", "name": "Bot", "text": "buy", "pow": "good", "upload": UP, "website": "http://spam"})
    assert status == 201 and body["code"].startswith("BOT-") and cookies == [] and "upload" not in body
    from shared import store
    assert store.post_for_code(body["code"]) is None
    assert call(app, "POST", "/api/posts", {"kind": "photo", "month": "march", "text": "x", "pow": "good", "upload": UP}, headers={"user-agent": ""})[2] == []
