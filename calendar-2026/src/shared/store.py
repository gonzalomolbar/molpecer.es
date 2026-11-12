"""The one table: posts, codes, daily counters, bans."""
import datetime as dt
import secrets
import time
import unicodedata

import boto3
from boto3.dynamodb.conditions import Attr
from botocore.exceptions import ClientError

from . import config

CODE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
_table = None
_client = None


def table():
    global _table
    if _table is None:
        _table = boto3.resource("dynamodb", region_name=config.REGION).Table(config.TABLE)
    return _table


def client():
    global _client
    if _client is None:
        _client = boto3.client("dynamodb", region_name=config.REGION)
    return _client


def now_iso():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def today():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")


def hour():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H")


def ulid():
    """Time-ordered, unguessable id: 10 chars of ms timestamp + 16 random, Crockford base32."""
    alphabet = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
    ms = int(time.time() * 1000)
    head = ""
    for _ in range(10):
        head = alphabet[ms & 31] + head
        ms >>= 5
    return head + "".join(secrets.choice(alphabet) for _ in range(16))


# ---------- codes ----------
def code_prefix(name):
    letters = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode().upper()
    letters = "".join(ch for ch in letters if ch.isalpha())[:6]
    return letters or "CAL"


def new_code(name, length=4):
    return f"{code_prefix(name)}-{''.join(secrets.choice(CODE_ALPHABET) for _ in range(length))}"


def normalise_code(code):
    return "".join(ch for ch in (code or "").upper() if ch.isalnum() or ch == "-").strip("-")[:40]


# ---------- counters (atomic, with TTL) ----------
def bump(scope, amount=1, ttl_seconds=2 * 86400):
    """Increments the counter for `scope` (e.g. posts#<net>#<day>) and returns the new value."""
    out = table().update_item(
        Key={"pk": f"RL#{scope}", "sk": "RL"},
        UpdateExpression="ADD n :a SET #t = if_not_exists(#t, :ttl)",
        ExpressionAttributeNames={"#t": "ttl"},
        ExpressionAttributeValues={":a": amount, ":ttl": int(time.time()) + ttl_seconds},
        ReturnValues="UPDATED_NEW",
    )
    return int(out["Attributes"]["n"])


def count(scope):
    item = table().get_item(Key={"pk": f"RL#{scope}", "sk": "RL"}).get("Item")
    return int(item["n"]) if item else 0


# ---------- bans ----------
def is_banned(net):
    if not net:
        return False
    item = table().get_item(Key={"pk": f"BAN#{net}", "sk": "BAN"}).get("Item")
    return bool(item)


def ban(net, who, post_id=None):
    table().put_item(Item={"pk": f"BAN#{net}", "sk": "BAN", "net": net, "by": who, "at": now_iso(), "post": post_id or ""})


def unban(net):
    table().delete_item(Key={"pk": f"BAN#{net}", "sk": "BAN"})


def bans():
    items = []
    kwargs = {"FilterExpression": Attr("sk").eq("BAN")}
    while True:
        page = table().scan(**kwargs)
        items.extend(page.get("Items", []))
        if "LastEvaluatedKey" not in page:
            break
        kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]
    return sorted(items, key=lambda i: i.get("at", ""), reverse=True)


# ---------- posts ----------
def create_post(post, name):
    """Writes the post and its unique code in one transaction; retries the code suffix on collision."""
    for attempt in range(6):
        code = new_code(name, 4 if attempt < 4 else 5)
        post["code"] = code
        try:
            client().transact_write_items(TransactItems=[
                {"Put": {"TableName": config.TABLE, "Item": _ser(post), "ConditionExpression": "attribute_not_exists(pk)"}},
                {"Put": {"TableName": config.TABLE, "Item": _ser({"pk": f"CODE#{code}", "sk": "CODE", "post": post["pk"], "created": post["created"]}),
                         "ConditionExpression": "attribute_not_exists(pk)"}},
            ])
            return code
        except ClientError as e:
            if e.response["Error"]["Code"] != "TransactionCanceledException":
                raise
    raise RuntimeError("could not allocate a unique code")


def _ser(item):
    from boto3.dynamodb.types import TypeSerializer
    ser = TypeSerializer()
    return {k: ser.serialize(v) for k, v in item.items()}


def get_post(post_id):
    return table().get_item(Key={"pk": f"POST#{post_id}", "sk": "POST"}).get("Item")


def post_for_code(code):
    ref = table().get_item(Key={"pk": f"CODE#{code}", "sk": "CODE"}).get("Item")
    if not ref:
        return None
    return table().get_item(Key={"pk": ref["post"], "sk": "POST"}).get("Item")


def update_post(post_id, **fields):
    names = {f"#{i}": k for i, k in enumerate(fields)}
    values = {f":{i}": v for i, v in enumerate(fields.values())}
    expr = "SET " + ", ".join(f"#{i} = :{i}" for i in range(len(fields)))
    table().update_item(Key={"pk": f"POST#{post_id}", "sk": "POST"}, UpdateExpression=expr,
                        ExpressionAttributeNames=names, ExpressionAttributeValues=values)


def transition(post_id, from_status, to_status, **fields):
    """Conditional status change; returns False if the post is not in from_status."""
    fields["status"] = to_status
    names = {f"#{i}": k for i, k in enumerate(fields)}
    names["#s"] = "status"
    values = {f":{i}": v for i, v in enumerate(fields.values())}
    values[":from"] = from_status
    expr = "SET " + ", ".join(f"#{i} = :{i}" for i in range(len(fields)))
    try:
        table().update_item(Key={"pk": f"POST#{post_id}", "sk": "POST"}, UpdateExpression=expr,
                            ConditionExpression="#s = :from", ExpressionAttributeNames=names,
                            ExpressionAttributeValues=values)
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return False
        raise


def list_posts(month=None, kind=None, status=None, limit=50, cursor=None):
    """Newest first. A scan is fine at a few thousand items; the wall is admin-only."""
    f = Attr("sk").eq("POST")
    if month:
        f = f & Attr("month").eq(month)
    if kind:
        f = f & Attr("kind").eq(kind)
    if status:
        f = f & Attr("status").eq(status)
    items = []
    kwargs = {"FilterExpression": f}
    while True:
        page = table().scan(**kwargs)
        items.extend(page.get("Items", []))
        if "LastEvaluatedKey" not in page:
            break
        kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]
    items.sort(key=lambda i: i.get("id", ""), reverse=True)  # ids are time-ordered to the millisecond
    if cursor:
        items = [i for i in items if i.get("id", "") < cursor]
    page_items = items[:limit]
    next_cursor = page_items[-1]["id"] if len(items) > limit else None
    return page_items, next_cursor
