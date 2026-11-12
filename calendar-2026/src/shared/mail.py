"""One plain-text email per submission, from the calendar address to the owner."""
import boto3

from . import config

_ses = None


def _clean(text, limit):
    return " ".join((text or "").replace("\r", " ").replace("\n", " ").split())[:limit]


def notify(post):
    global _ses
    if not config.NOTIFY_EMAIL or not config.SENDER_EMAIL:
        return
    if _ses is None:
        _ses = boto3.client("sesv2", region_name=config.REGION)
    who = _clean(post.get("name"), 40) or post["pk"].split("#", 1)[1][-6:]
    v = post.get("visitor", {})
    where = ", ".join(x for x in (v.get("city"), v.get("country")) if x) or "unknown place"
    lines = [
        f"Kind: {post.get('kind')}",
        f"Name: {post.get('name') or '(none)'}",
        f"Code: {post.get('code')}",
        f"From: {where} · {v.get('device') or 'unknown device'} · {v.get('ip') or '?'}",
        "",
        (post.get("text") or "").strip()[:2000],
        "",
        f"Wall: {config.ORIGIN}/wall#{post['pk'].split('#', 1)[1]}",
    ]
    _ses.send_email(
        FromEmailAddress=f"Calendar 2026 <{config.SENDER_EMAIL}>",
        Destination={"ToAddresses": [config.NOTIFY_EMAIL]},
        ReplyToAddresses=[config.NOTIFY_EMAIL],
        Content={"Simple": {
            "Subject": {"Data": f"Calendar 2026: {post.get('kind')} · {who}", "Charset": "UTF-8"},
            "Body": {"Text": {"Data": "\n".join(lines), "Charset": "UTF-8"}},
        }},
    )
