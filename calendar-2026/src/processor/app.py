"""Triggered by every object created under raw/: re-encode, store under media/, mark done, email once."""
import time
import urllib.parse

import boto3

from shared import config, imaging, mail, store

_s3 = None


def s3():
    global _s3
    if _s3 is None:
        _s3 = boto3.client("s3", region_name=config.REGION)
    return _s3


def process(bucket, key):
    post_id = key.split("/", 1)[1]
    post = store.get_post(post_id)
    if not post:
        s3().delete_object(Bucket=bucket, Key=key)
        return "orphan"
    # Repeat events (a reused upload URL, a retry) never run twice: the transition is conditional.
    if not store.transition(post_id, "awaiting_upload", "processing"):
        s3().delete_object(Bucket=bucket, Key=key)
        return "ignored"
    try:
        head = s3().head_object(Bucket=bucket, Key=key)
        size = int(head.get("ContentLength", 0))
        if size < 1 or size > config.LIMITS["max_upload_bytes"]:
            raise imaging.BadImage(f"size {size}")
        data = s3().get_object(Bucket=bucket, Key=key)["Body"].read()
        full, thumb, (w, h) = imaging.reencode(data)
        s3().put_object(Bucket=bucket, Key=f"media/{post_id}/full.webp", Body=full, ContentType="image/webp", CacheControl="private, max-age=600")
        s3().put_object(Bucket=bucket, Key=f"media/{post_id}/thumb.webp", Body=thumb, ContentType="image/webp", CacheControl="private, max-age=600")
        store.update_post(post_id, status="done", width=w, height=h, bytes=size, processed=store.now_iso(), pipeline=imaging.PIPELINE_VERSION)
        store.table().update_item(Key={"pk": f"POST#{post_id}", "sk": "POST"}, UpdateExpression="REMOVE #t", ExpressionAttributeNames={"#t": "ttl"})
        post.update(status="done")
        try:
            mail.notify(post)
        except Exception as e:
            print("MAIL ERROR", repr(e))
        return "done"
    except imaging.BadImage as e:
        store.update_post(post_id, status="failed", failure=str(e)[:200], processed=store.now_iso())
        return "failed"
    finally:
        s3().delete_object(Bucket=bucket, Key=key)


def handler(event, context):
    results = []
    for rec in event.get("Records", []):
        bucket = rec["s3"]["bucket"]["name"]
        key = urllib.parse.unquote_plus(rec["s3"]["object"]["key"])
        if not key.startswith("raw/"):
            continue
        started = time.time()
        results.append((key, process(bucket, key), round(time.time() - started, 2)))
    print("PROCESSED", results)
    return {"results": results}
