#!/usr/bin/env python3
"""Generate and store the calendar-2026 secrets. Run once after the first deploy, by hand.

    python3 calendar-2026/tools/setup-secrets.py init     --profile personal   # signing secrets, asks for both admin codes
    python3 calendar-2026/tools/setup-secrets.py admin toribios --profile personal   # asks for a new code for one admin

Writes SSM SecureStrings under /calendar-2026/ and the visitor-cookie secret into the edge key-value store.
Admin codes are chosen by the admins, typed at a prompt, and stored only as a salted slow hash.
"""
import argparse
import getpass
import json
import pathlib
import secrets as rnd
import sys

import boto3

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))
from shared.sessions import hash_admin_code  # noqa: E402

PREFIX = "/calendar-2026"
ADMINS = ("toribios", "molpeceres")


def put(ssm, name, value):
    ssm.put_parameter(Name=f"{PREFIX}/{name}", Value=value, Type="SecureString", Overwrite=True)


def ask_code(name):
    while True:
        code = getpass.getpass(f"admin code for {name} (8+ characters, not shown): ")
        if len(code) < 8:
            print("  too short"); continue
        if getpass.getpass("repeat it: ") != code:
            print("  they differ"); continue
        return code


def kvs_put(session, stack, key, value):
    """The key-value store API is signed with SigV4A, which plain boto3 lacks; the AWS CLI bundles it."""
    import subprocess
    cfn = session.client("cloudformation")
    outputs = {o["OutputKey"]: o["OutputValue"] for o in cfn.describe_stacks(StackName=stack)["Stacks"][0]["Outputs"]}
    arn = outputs["KeyValueStoreArn"]
    base = ["aws", "cloudfront-keyvaluestore", "--profile", session.profile_name or "default"]
    etag = subprocess.run(base + ["describe-key-value-store", "--kvs-arn", arn, "--query", "ETag", "--output", "text"],
                          check=True, capture_output=True, text=True).stdout.strip()
    subprocess.run(base + ["put-key", "--kvs-arn", arn, "--key", key, "--value", value, "--if-match", etag],
                   check=True, capture_output=True, text=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["init", "admin"])
    ap.add_argument("name", nargs="?")
    ap.add_argument("--profile", default="personal")
    ap.add_argument("--region", default="us-east-1")
    ap.add_argument("--stack", default="calendar-2026")
    args = ap.parse_args()
    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    ssm = session.client("ssm")

    if args.action == "init":
        session_secret = rnd.token_urlsafe(32)
        put(ssm, "session_secret", session_secret)
        put(ssm, "admin_secret", rnd.token_urlsafe(32))
        hashes = {name: hash_admin_code(ask_code(name)) for name in ADMINS}
        put(ssm, "admins", json.dumps(hashes))
        kvs_put(session, args.stack, "secret", session_secret)
        kvs_put(session, args.stack, "mode", "open")
        print("stored: session_secret (SSM + KVS), admin_secret, both admin codes (hashed); mode=open")
    elif args.action == "admin":
        if args.name not in ADMINS:
            raise SystemExit(f"name must be one of {ADMINS}")
        current = json.loads(ssm.get_parameter(Name=f"{PREFIX}/admins", WithDecryption=True)["Parameter"]["Value"])
        current[args.name] = hash_admin_code(ask_code(args.name))
        put(ssm, "admins", json.dumps(current))
        print(f"stored a new code for {args.name}")


if __name__ == "__main__":
    main()
