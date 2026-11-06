"""Delete everything this project created in AWS, so nothing keeps costing money."""
import argparse

from botocore.exceptions import ClientError

from scripts.common import STACK_NAME, artifact_bucket, data_bucket, session


def empty_bucket(aws, bucket: str) -> None:
    resource = aws.resource("s3").Bucket(bucket)
    try:
        resource.objects.all().delete()
    except ClientError as error:
        if error.response["Error"]["Code"] != "NoSuchBucket":
            raise


def teardown(aws) -> None:
    empty_bucket(aws, data_bucket(aws))
    cloudformation = aws.client("cloudformation")
    cloudformation.delete_stack(StackName=STACK_NAME)
    cloudformation.get_waiter("stack_delete_complete").wait(StackName=STACK_NAME)

    bucket = artifact_bucket(aws)
    empty_bucket(aws, bucket)
    try:
        aws.client("s3").delete_bucket(Bucket=bucket)
    except ClientError as error:
        if error.response["Error"]["Code"] != "NoSuchBucket":
            raise
    print("Everything is deleted.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--yes", action="store_true", help="confirm deleting all project data")
    if not parser.parse_args().yes:
        parser.error("This deletes all project data in AWS. Rerun with --yes to confirm.")
    teardown(session())
