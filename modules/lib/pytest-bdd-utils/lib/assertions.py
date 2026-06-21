import json
import time

# ── HTTP response assertions ───────────────────────────────────────────────────


def assert_status(response, expected: int) -> None:
    assert response.status_code == expected, (
        f"expected HTTP {expected}, got {response.status_code}: {response.data}"
    )


def assert_field(response, field: str, value) -> None:
    """Assert a single top-level field in the JSON response body."""
    body = json.loads(response.data)
    assert body.get(field) == value, (
        f"expected {field}={value!r}, got {body.get(field)!r}"
    )


def assert_json_body(response, **expected) -> dict:
    """Assert multiple key=value pairs in the JSON response body.

    Returns the full parsed body so callers can make additional checks.

        assert_json_body(resp, name="Alice", role="SENIOR", active=True)
    """
    body = json.loads(response.data)
    for key, value in expected.items():
        assert body.get(key) == value, (
            f"expected {key}={value!r}, got {body.get(key)!r}"
        )
    return body


def assert_error_contains(response, fragment: str) -> None:
    body = json.loads(response.data)
    error = body.get("error", "")
    assert fragment.lower() in error.lower(), (
        f"expected error containing {fragment!r}, got {error!r}"
    )


# ── SQS assertions ─────────────────────────────────────────────────────────────


def assert_sqs_message(
    sqs_client,
    queue_url: str,
    event_type: str,
    timeout: float = 5.0,
) -> dict:
    """Poll *queue_url* until a message with ``event == event_type`` appears.

    Uses long-polling (WaitTimeSeconds=1) so it is efficient in both local
    Docker and CI environments. Raises AssertionError if *timeout* seconds
    pass without a matching message.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        wait = min(1, max(0, int(remaining)))
        msgs = sqs_client.receive_message(
            QueueUrl=queue_url,
            MaxNumberOfMessages=10,
            WaitTimeSeconds=wait,
        ).get("Messages", [])
        for msg in msgs:
            body = json.loads(msg["Body"])
            sqs_client.delete_message(
                QueueUrl=queue_url, ReceiptHandle=msg["ReceiptHandle"]
            )
            if body.get("event") == event_type:
                return body
    raise AssertionError(
        f"event '{event_type}' not found in SQS queue after {timeout}s"
    )


def assert_no_sqs_message(
    sqs_client,
    queue_url: str,
    event_type: str,
    wait: float = 1.0,
) -> None:
    """Assert that no message with ``event == event_type`` appears within *wait* seconds.

    Uses short-polls (WaitTimeSeconds=0) to drain quickly, then returns.
    Raises AssertionError immediately if a matching message is found.
    """
    deadline = time.monotonic() + wait
    while time.monotonic() < deadline:
        msgs = sqs_client.receive_message(
            QueueUrl=queue_url,
            MaxNumberOfMessages=10,
            WaitTimeSeconds=0,
        ).get("Messages", [])
        if not msgs:
            break
        for msg in msgs:
            body = json.loads(msg["Body"])
            sqs_client.delete_message(
                QueueUrl=queue_url, ReceiptHandle=msg["ReceiptHandle"]
            )
            if body.get("event") == event_type:
                raise AssertionError(
                    f"expected no event '{event_type}' but one was found: {body}"
                )


# ── SNS assertions ─────────────────────────────────────────────────────────────


def assert_sns_message(
    sqs_client,
    capture_url: str,
    subject: str,
    timeout: float = 5.0,
) -> dict:
    """Assert an SNS notification with *subject* was published.

    *capture_url* is the per-topic SQS capture queue auto-created by BDDInfra.
    Access it via ``infra.sns_capture_urls["topic-name"]``.

    SNS wraps each publish in a JSON envelope; this function matches on the
    ``Subject`` field of that envelope and returns the full envelope dict.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        wait = min(1, max(0, int(remaining)))
        msgs = sqs_client.receive_message(
            QueueUrl=capture_url,
            MaxNumberOfMessages=10,
            WaitTimeSeconds=wait,
        ).get("Messages", [])
        for msg in msgs:
            body = json.loads(msg["Body"])
            sqs_client.delete_message(
                QueueUrl=capture_url, ReceiptHandle=msg["ReceiptHandle"]
            )
            if body.get("Subject") == subject:
                return body
    raise AssertionError(
        f"SNS notification with subject '{subject}' not found after {timeout}s"
    )


def assert_no_sns_message(
    sqs_client,
    capture_url: str,
    subject: str,
    wait: float = 1.0,
) -> None:
    """Assert that no SNS notification with *subject* appears within *wait* seconds."""
    deadline = time.monotonic() + wait
    while time.monotonic() < deadline:
        msgs = sqs_client.receive_message(
            QueueUrl=capture_url,
            MaxNumberOfMessages=10,
            WaitTimeSeconds=0,
        ).get("Messages", [])
        if not msgs:
            break
        for msg in msgs:
            body = json.loads(msg["Body"])
            sqs_client.delete_message(
                QueueUrl=capture_url, ReceiptHandle=msg["ReceiptHandle"]
            )
            if body.get("Subject") == subject:
                raise AssertionError(
                    f"expected no SNS notification '{subject}' but one was found: {body}"
                )


# ── S3 assertions ──────────────────────────────────────────────────────────────


def assert_s3_object_exists(s3_client, bucket: str, key: str) -> None:
    try:
        s3_client.head_object(Bucket=bucket, Key=key)
    except Exception as exc:
        raise AssertionError(f"S3 object s3://{bucket}/{key} does not exist") from exc


def assert_s3_object_contains(s3_client, bucket: str, key: str, fragment: str) -> None:
    """Assert that the content of s3://*bucket*/*key* contains *fragment*."""
    try:
        content = s3_client.get_object(Bucket=bucket, Key=key)["Body"].read().decode()
    except Exception as exc:
        raise AssertionError(f"S3 object s3://{bucket}/{key} does not exist") from exc
    assert fragment in content, (
        f"expected s3://{bucket}/{key} to contain {fragment!r}\ngot: {content[:300]}"
    )
