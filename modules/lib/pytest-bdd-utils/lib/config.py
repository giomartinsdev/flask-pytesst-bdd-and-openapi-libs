import os
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Images:
    POSTGRES = "postgres:16-alpine"
    LOCALSTACK = "localstack/localstack:3"
    SQLSERVER = "flask-bdd-mssql:latest"


class BDDConfig(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    db_type: str = "postgres"
    sqs_queues: list[str] = Field(default_factory=list)
    sns_topics: list[str] = Field(default_factory=list)
    s3_buckets: list[str] = Field(default_factory=list)
    aws_region: str = "us-east-1"
    db_base: Any | None = None
    db_url: str | None = None
    aws_endpoint: str | None = None
    postgres_image: str = Images.POSTGRES
    sqlserver_image: str = Images.SQLSERVER
    localstack_image: str = Images.LOCALSTACK

    @classmethod
    def from_env(
        cls,
        db_base: Any = None,
        db_type: str = "postgres",
        sqs_queues: list[str] | None = None,
        sns_topics: list[str] | None = None,
        s3_buckets: list[str] | None = None,
    ) -> "BDDConfig":
        """Always starts fresh containers on random host ports.

        Does NOT read DATABASE_URL or AWS_ENDPOINT_URL from the environment —
        those are app-server variables that would pin tests to fixed ports and
        cause conflicts when multiple test sessions run concurrently.
        Use from_ci_env() if pre-provisioned services must be reused.
        """
        return cls(
            db_type=db_type,
            db_base=db_base,
            db_url=None,
            aws_endpoint=None,
            aws_region=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
            sqs_queues=sqs_queues or [],
            sns_topics=sns_topics or [],
            s3_buckets=s3_buckets or [],
        )

    @classmethod
    def from_ci_env(
        cls,
        db_base: Any = None,
        db_type: str = "postgres",
        sqs_queues: list[str] | None = None,
        sns_topics: list[str] | None = None,
        s3_buckets: list[str] | None = None,
    ) -> "BDDConfig":
        """Reads DATABASE_URL and AWS_ENDPOINT_URL from the environment.

        Use this only in CI pipelines where the database and LocalStack are
        provisioned externally (e.g. as Docker Compose services with fixed
        service-network hostnames). In local development, use from_env() so
        that testcontainers assigns random host ports automatically.
        """
        return cls(
            db_type=db_type,
            db_base=db_base,
            db_url=os.environ.get("DATABASE_URL"),
            aws_endpoint=os.environ.get("AWS_ENDPOINT_URL"),
            aws_region=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
            sqs_queues=sqs_queues or [],
            sns_topics=sns_topics or [],
            s3_buckets=s3_buckets or [],
        )
