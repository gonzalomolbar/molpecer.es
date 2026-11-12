import io
import json

import boto3
import pytest
from PIL import Image


def jpeg(w=3000, h=2000, exif_orientation=None):
    img = Image.new("RGB", (w, h), (200, 30, 30))
    buf = io.BytesIO()
    kwargs = {}
    if exif_orientation:
        exif = Image.Exif(); exif[0x0112] = exif_orientation; kwargs["exif"] = exif
    img.save(buf, "JPEG", **kwargs)
    return buf.getvalue()


def test_reencode_sizes_and_rotation():
    from shared import imaging
    full, thumb, size = imaging.reencode(jpeg())
    assert size == (1600, 1067)
    assert Image.open(io.BytesIO(full)).format == "WEBP" and Image.open(io.BytesIO(thumb)).size == (400, 267)
    _, _, rotated = imaging.reencode(jpeg(3000, 2000, exif_orientation=6))
    assert rotated == (1067, 1600), "EXIF orientation applied"


def test_reencode_rejects_bad_input():
    from shared import imaging
    with pytest.raises(imaging.BadImage):
        imaging.reencode(b"not an image")
    buf = io.BytesIO(); Image.new("RGB", (10, 10)).save(buf, "BMP")
    with pytest.raises(imaging.BadImage):
        imaging.reencode(buf.getvalue())
    with pytest.raises(imaging.BadImage):
        imaging.reencode(jpeg(4, 4))


@pytest.fixture
def pipeline(aws, monkeypatch):
    from processor import app as proc
    from shared import mail, store
    sent = []
    monkeypatch.setattr(mail, "notify", lambda post: sent.append(post["pk"]))
    post_id = store.ulid()
    post = {"pk": f"POST#{post_id}", "sk": "POST", "id": post_id, "kind": "photo", "month": "march", "name": "Ana",
            "created": store.now_iso(), "status": "awaiting_upload", "visitor": {}, "ttl": 1}
    store.create_post(post, "Ana")
    s3 = boto3.client("s3", region_name="us-east-1")
    return proc, store, s3, post_id, sent


def s3_event(key):
    return {"Records": [{"s3": {"bucket": {"name": "calendar-2026-data-test"}, "object": {"key": key}}}]}


def test_processor_happy_path_runs_once(pipeline):
    proc, store, s3, post_id, sent = pipeline
    s3.put_object(Bucket="calendar-2026-data-test", Key=f"raw/{post_id}", Body=jpeg())
    out = proc.handler(s3_event(f"raw/{post_id}"), None)
    assert out["results"][0][1] == "done"
    post = store.get_post(post_id)
    assert post["status"] == "done" and post["width"] == 1600 and "ttl" not in post
    assert s3.head_object(Bucket="calendar-2026-data-test", Key=f"media/{post_id}/thumb.webp")["ContentType"] == "image/webp"
    with pytest.raises(Exception):
        s3.head_object(Bucket="calendar-2026-data-test", Key=f"raw/{post_id}")
    assert sent == [f"POST#{post_id}"]
    # a second upload with the same presigned URL is ignored and never emails again
    s3.put_object(Bucket="calendar-2026-data-test", Key=f"raw/{post_id}", Body=jpeg())
    assert proc.handler(s3_event(f"raw/{post_id}"), None)["results"][0][1] == "ignored"
    assert sent == [f"POST#{post_id}"]


def test_processor_marks_failed(pipeline):
    proc, store, s3, post_id, sent = pipeline
    s3.put_object(Bucket="calendar-2026-data-test", Key=f"raw/{post_id}", Body=b"garbage")
    assert proc.handler(s3_event(f"raw/{post_id}"), None)["results"][0][1] == "failed"
    assert store.get_post(post_id)["status"] == "failed" and sent == []


def test_processor_orphan(pipeline):
    proc, store, s3, post_id, sent = pipeline
    s3.put_object(Bucket="calendar-2026-data-test", Key="raw/NOPE", Body=jpeg())
    assert proc.handler(s3_event("raw/NOPE"), None)["results"][0][1] == "orphan"


def test_breaker_cuts_only_on_cost_alarms(monkeypatch):
    from breaker import app as breaker
    calls = []
    class Fake:
        def put_function_concurrency(self, FunctionName, ReservedConcurrentExecutions):
            calls.append((FunctionName, ReservedConcurrentExecutions))
    monkeypatch.setattr(breaker, "_lambda", Fake())
    msg = lambda name, state: {"Records": [{"Sns": {"Message": json.dumps({"AlarmName": name, "NewStateValue": state})}}]}
    assert breaker.handler(msg("calendar-2026-api-flood", "ALARM"), None)["cut"] == []
    assert breaker.handler(msg("calendar-2026-egress", "OK"), None)["cut"] == []
    assert breaker.handler(msg("calendar-2026-egress", "ALARM"), None)["cut"] == ["calendar-2026-egress"]
    assert calls == [("calendar-2026-api", 0), ("calendar-2026-processor", 0)]


def test_mail_subject_strips_newlines(aws, monkeypatch):
    from shared import mail
    captured = {}
    class Fake:
        def send_email(self, **kw): captured.update(kw)
    monkeypatch.setattr(mail, "_ses", Fake())
    mail.notify({"pk": "POST#01ABC", "month": "march", "kind": "photo", "name": "Eve\r\nBcc: x@y", "text": "hi", "code": "EVE-1234", "visitor": {"city": "Madrid", "country": "ES", "device": "mobile", "ip": "1.2.3.4"}})
    assert "\n" not in captured["Content"]["Simple"]["Subject"]["Data"]
    assert captured["FromEmailAddress"] == "Calendar 2026 <calendar+2026@molpecer.es>"
