#!/usr/bin/env python3
"""Publish the outtake photos to the month pages.

    python3 calendar-2026/tools/months.py /path/to/photos [--profile personal] [--dry-run]

The folder holds twelve subfolders named january … december (missing ones are empty months).
Each image is resized to a 1600 px WebP and a 400 px thumbnail, named by content hash, uploaded only
if missing, and stale files are removed. Writes months/<month>/index.json and invalidates what changed.
"""
import argparse
import hashlib
import json
import pathlib
import sys

import boto3

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))
from shared import imaging  # noqa: E402

MONTHS = ["january", "february", "march", "april", "may", "june",
          "july", "august", "september", "october", "november", "december"]
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif", ".gif"}


def plan(src):
    """{month: {hash: (path, order)}} for every image, hash covering bytes and pipeline settings."""
    out = {m: {} for m in MONTHS}
    for m in MONTHS:
        folder = src / m
        if not folder.is_dir():
            continue
        files = sorted(p for p in folder.iterdir() if p.is_file() and not p.name.startswith(".") and p.suffix.lower() in IMAGE_SUFFIXES)
        for i, path in enumerate(files):
            h = hashlib.sha1(path.read_bytes() + f"|{imaging.PIPELINE_VERSION}|{imaging.FULL_PX}|{imaging.THUMB_PX}".encode()).hexdigest()[:12]
            out[m][h] = (path, i)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src", type=pathlib.Path)
    ap.add_argument("--profile", default="personal")
    ap.add_argument("--region", default="us-east-1")
    ap.add_argument("--stack", default="calendar-2026")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    cfn = session.client("cloudformation")
    outputs = {o["OutputKey"]: o["OutputValue"] for o in cfn.describe_stacks(StackName=args.stack)["Stacks"][0]["Outputs"]}
    bucket, dist = outputs["WebBucketName"], outputs["DistributionId"]
    s3 = session.client("s3")
    cf = session.client("cloudfront")

    wanted = plan(args.src)
    invalidate = []
    for m in MONTHS:
        prefix = f"months/{m}/p/"
        existing = set()
        pages = s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix)
        for page in pages:
            for obj in page.get("Contents", []):
                existing.add(obj["Key"][len(prefix):])
        photos = []
        for h, (path, order) in sorted(wanted[m].items(), key=lambda kv: kv[1][1]):
            full_key, thumb_key = f"{h}.webp", f"{h}_t.webp"
            full, thumb, (w, hgt) = imaging.reencode(path.read_bytes())  # local, also gives the dimensions
            if full_key not in existing or thumb_key not in existing:
                print(f"  upload {m}/{path.name} -> {h} ({w}x{hgt})")
                if not args.dry_run:
                    for key, body in ((full_key, full), (thumb_key, thumb)):
                        s3.put_object(Bucket=bucket, Key=prefix + key, Body=body, ContentType="image/webp",
                                      CacheControl="public, max-age=31536000, immutable")
            photos.append({"id": h, "w": w, "h": hgt})
        keep = {f"{h}.webp" for h in wanted[m]} | {f"{h}_t.webp" for h in wanted[m]}
        for stale in sorted(existing - keep):
            print(f"  delete {m}/{stale}")
            if not args.dry_run:
                s3.delete_object(Bucket=bucket, Key=prefix + stale)
            invalidate.append(f"/{prefix}{stale}")
        manifest = json.dumps({"month": m, "photos": photos}, separators=(",", ":"))
        print(f"{m}: {len(photos)} photos")
        if not args.dry_run:
            s3.put_object(Bucket=bucket, Key=f"months/{m}/index.json", Body=manifest.encode(), ContentType="application/json",
                          CacheControl="public, max-age=60")
        invalidate.append(f"/months/{m}/index.json")
    if invalidate and not args.dry_run:
        cf.create_invalidation(DistributionId=dist, InvalidationBatch={"Paths": {"Quantity": len(invalidate), "Items": invalidate[:3000]}, "CallerReference": hashlib.sha1("".join(invalidate).encode()).hexdigest()})
        print(f"invalidated {len(invalidate)} paths")


if __name__ == "__main__":
    main()
