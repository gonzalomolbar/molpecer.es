"""Alarm handler. Every alarm already emailed the owner through the topic; the two cost alarms
also cut the backend here by setting the functions' concurrency to zero. Reopen with tools/switch.sh open."""
import json
import os

import boto3

CUT_ON = ("calendar-2026-egress", "calendar-2026-requests")
FUNCTIONS = ("calendar-2026-api", "calendar-2026-processor")
_lambda = None


def handler(event, context):
    global _lambda
    acted = []
    for rec in event.get("Records", []):
        try:
            msg = json.loads(rec["Sns"]["Message"])
        except (KeyError, ValueError):
            continue
        name = msg.get("AlarmName", "")
        state = msg.get("NewStateValue", "")
        if name in CUT_ON and state == "ALARM":
            if _lambda is None:
                _lambda = boto3.client("lambda", region_name=os.environ.get("AWS_REGION", "us-east-1"))
            for fn in FUNCTIONS:
                _lambda.put_function_concurrency(FunctionName=fn, ReservedConcurrentExecutions=0)
            acted.append(name)
    print("BREAKER", {"cut": acted})
    return {"cut": acted}
