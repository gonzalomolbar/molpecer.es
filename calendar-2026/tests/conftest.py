import json
import os
import pathlib
import sys

import boto3
import pytest
from moto import mock_aws

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

os.environ.update({
    "AWS_REGION": "us-east-1", "AWS_DEFAULT_REGION": "us-east-1",
    "AWS_ACCESS_KEY_ID": "testing", "AWS_SECRET_ACCESS_KEY": "testing",
    "TABLE": "calendar-2026", "DATA_BUCKET": "calendar-2026-data-test",
    "DOMAIN": "calendar-2026.toribios.molpecer.es", "NOTIFY_EMAIL": "owner@example.com",
    "SENDER_EMAIL": "calendar+2026@molpecer.es", "GLOBAL_POSTS_DAY": "8", "PER_NET_POSTS_DAY": "3",
    "PER_NET_UNLOCKS_DAY": "4", "GLOBAL_LOGIN_FAILS_HOUR": "3",
})

ADMIN_CODE = "tor-code-123"


@pytest.fixture
def aws():
    with mock_aws():
        ddb = boto3.client("dynamodb", region_name="us-east-1")
        ddb.create_table(TableName="calendar-2026", BillingMode="PAY_PER_REQUEST",
                         AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"}, {"AttributeName": "sk", "AttributeType": "S"}],
                         KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}, {"AttributeName": "sk", "KeyType": "RANGE"}])
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="calendar-2026-data-test")
        ssm = boto3.client("ssm", region_name="us-east-1")
        from shared.sessions import hash_admin_code
        for name, value in {
            "session_secret": "edge-secret", "admin_secret": "admin-secret",
            "admins": json.dumps({"toribios": hash_admin_code(ADMIN_CODE)}),
        }.items():
            ssm.put_parameter(Name=f"/calendar-2026/{name}", Value=value, Type="SecureString")
        ses = boto3.client("sesv2", region_name="us-east-1")
        ses.create_email_identity(EmailIdentity="molpecer.es")
        from shared import config, store
        config._params, config._params_at = {}, 0.0
        store._table = store._client = None
        yield
