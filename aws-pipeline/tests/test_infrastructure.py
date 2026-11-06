import io
import re
import zipfile
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

from scripts import deploy as deploy_script
from scripts import teardown as teardown_script
from scripts.common import STACK_NAME, data_bucket

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = (ROOT / "template.yaml").read_text(encoding="utf-8")


@pytest.fixture
def aws(monkeypatch):
    for name in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"):
        monkeypatch.setenv(name, "testing")
    with mock_aws():
        yield boto3.Session(region_name="ap-south-1")


def test_zip_contains_handler_at_root_and_is_reproducible():
    first = deploy_script.build_zip()
    assert first == deploy_script.build_zip()
    assert zipfile.ZipFile(io.BytesIO(first)).namelist() == ["handler.py"]


def test_bucket_blocks_public_access_and_encrypts():
    assert "BlockPublicPolicy: true" in TEMPLATE
    assert "SSEAlgorithm: AES256" in TEMPLATE


def test_trigger_is_limited_to_landing_prefix_so_lambda_cannot_loop():
    assert re.search(r"Name: prefix\s+Value: landing/", TEMPLATE)


def test_iam_policy_has_no_wildcard_actions():
    assert not re.search(r"Action:\s*(-\s*)?['\"]?\*", TEMPLATE)
    assert "s3:*" not in TEMPLATE


def test_athena_has_scan_limit():
    assert "BytesScannedCutoffPerQuery" in TEMPLATE


def test_deploy_is_repeatable_and_teardown_removes_everything(aws):
    deploy_script.deploy(aws)
    deploy_script.deploy(aws)
    cloudformation = aws.client("cloudformation")
    stack = cloudformation.describe_stacks(StackName=STACK_NAME)["Stacks"][0]
    assert stack["StackStatus"] in ("CREATE_COMPLETE", "UPDATE_COMPLETE")
    bucket = data_bucket(aws)
    aws.client("s3").put_object(Bucket=bucket, Key="curated/x", Body=b"x")

    teardown_script.teardown(aws)

    names = [b["Name"] for b in aws.client("s3").list_buckets()["Buckets"]]
    assert names == []
