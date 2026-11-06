"""Package the Lambda and create or update the CloudFormation stack."""
import hashlib
import io
import zipfile
from pathlib import Path

from botocore.exceptions import ClientError

from scripts.common import STACK_NAME, artifact_bucket, session

ROOT = Path(__file__).resolve().parent.parent


def build_zip() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        # A fixed timestamp means unchanged code hashes the same and skips an update.
        info = zipfile.ZipInfo("handler.py", date_time=(2020, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        archive.writestr(info, (ROOT / "ingest" / "handler.py").read_bytes())
    return buffer.getvalue()


def ensure_bucket(s3, bucket: str, region: str) -> None:
    try:
        s3.head_bucket(Bucket=bucket)
        return
    except ClientError:
        pass
    options = {} if region == "us-east-1" else {
        "CreateBucketConfiguration": {"LocationConstraint": region}
    }
    s3.create_bucket(Bucket=bucket, **options)
    s3.put_public_access_block(
        Bucket=bucket,
        PublicAccessBlockConfiguration={
            "BlockPublicAcls": True, "IgnorePublicAcls": True,
            "BlockPublicPolicy": True, "RestrictPublicBuckets": True,
        },
    )


def stack_exists(cloudformation) -> bool:
    try:
        cloudformation.describe_stacks(StackName=STACK_NAME)
        return True
    except ClientError:
        return False


def deploy(aws) -> None:
    s3 = aws.client("s3")
    cloudformation = aws.client("cloudformation")

    code = build_zip()
    code_key = f"lambda/{hashlib.sha256(code).hexdigest()[:16]}.zip"
    bucket = artifact_bucket(aws)
    ensure_bucket(s3, bucket, aws.region_name)
    s3.put_object(Bucket=bucket, Key=code_key, Body=code)

    arguments = {
        "StackName": STACK_NAME,
        "TemplateBody": (ROOT / "template.yaml").read_text(encoding="utf-8"),
        "Capabilities": ["CAPABILITY_IAM"],
        "Parameters": [
            {"ParameterKey": "CodeBucket", "ParameterValue": bucket},
            {"ParameterKey": "CodeKey", "ParameterValue": code_key},
        ],
    }
    if stack_exists(cloudformation):
        try:
            cloudformation.update_stack(**arguments)
        except ClientError as error:
            if "No updates are to be performed" in str(error):
                print("Stack is already up to date.")
                return
            raise
        cloudformation.get_waiter("stack_update_complete").wait(StackName=STACK_NAME)
    else:
        cloudformation.create_stack(**arguments)
        cloudformation.get_waiter("stack_create_complete").wait(StackName=STACK_NAME)
    print(f"Deployed {STACK_NAME} in {aws.region_name}.")


if __name__ == "__main__":
    deploy(session())
