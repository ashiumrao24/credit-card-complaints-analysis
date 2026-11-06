"""Shared AWS names, derived from the signed-in account so nothing is hardcoded."""
import os

import boto3

STACK_NAME = "complaints-pipeline"
DEFAULT_REGION = "ap-south-1"


def session() -> boto3.Session:
    return boto3.Session(region_name=os.getenv("AWS_REGION", DEFAULT_REGION))


def account_id(aws: boto3.Session) -> str:
    return aws.client("sts").get_caller_identity()["Account"]


def data_bucket(aws: boto3.Session) -> str:
    return f"complaints-data-{account_id(aws)}-{aws.region_name}"


def artifact_bucket(aws: boto3.Session) -> str:
    return f"complaints-artifacts-{account_id(aws)}-{aws.region_name}"
