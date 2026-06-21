import json


def assert_status(response, expected: int) -> None:
    assert response.status_code == expected, (
        f"expected HTTP {expected}, got {response.status_code}: {response.data}"
    )


def assert_field(response, field: str, value) -> None:
    body = json.loads(response.data)
    assert body.get(field) == value, f"expected {field}={value!r}, got {body.get(field)!r}"


def assert_error_contains(response, fragment: str) -> None:
    body = json.loads(response.data)
    error = body.get("error", "")
    assert fragment.lower() in error.lower(), f"expected error containing {fragment!r}, got {error!r}"


def assert_sqs_message(sqs_client, queue_url: str, event_type: str, retries: int = 10) -> dict:
    for _ in range(retries):
        for msg in sqs_client.receive_message(
            QueueUrl=queue_url, MaxNumberOfMessages=10, WaitTimeSeconds=0
        ).get("Messages", []):
            body = json.loads(msg["Body"])
            sqs_client.delete_message(QueueUrl=queue_url, ReceiptHandle=msg["ReceiptHandle"])
            if body.get("event") == event_type:
                return body
    raise AssertionError(f"event '{event_type}' not found in SQS queue after {retries} polls")


def assert_s3_object_exists(s3_client, bucket: str, key: str) -> None:
    try:
        s3_client.head_object(Bucket=bucket, Key=key)
    except Exception:
        raise AssertionError(f"S3 object s3://{bucket}/{key} does not exist")
