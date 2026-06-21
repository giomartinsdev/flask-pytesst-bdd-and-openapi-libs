from collections.abc import Generator
from contextlib import contextmanager
import os
from typing import Any

import boto3
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from lib.config import BDDConfig


class BDDInfra(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    config: BDDConfig
    db_url: str
    db_engine: Any  # sqlalchemy.Engine
    sqs: Any
    sns: Any
    s3: Any
    aws_endpoint: str
    queue_urls: dict[str, str] = Field(default_factory=dict)
    topic_arns: dict[str, str] = Field(default_factory=dict)
    # Auto-created per SNS topic: {topic_name: capture_queue_url}
    # Each capture queue is subscribed to its topic so SNS publishes can be asserted via SQS.
    sns_capture_urls: dict[str, str] = Field(default_factory=dict)
    containers: list[Any] = Field(default_factory=list)

    def make_session(self) -> Session:
        return sessionmaker(bind=self.db_engine)()

    # ── Seeding ────────────────────────────────────────────────────────────────

    def seed(self, *objects: Any) -> None:
        """Insert and immediately commit one or more ORM objects.

        Use for simple, flat seed data where you don't need to inspect
        auto-generated IDs before committing:

            infra.seed(
                Category(name="Electronics"),
                Category(name="Books"),
            )
        """
        session = self.make_session()
        try:
            for obj in objects:
                session.add(obj)
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    @contextmanager
    def seed_session(self) -> Generator[Session, None, None]:
        """Context manager that yields an open session for complex seeding.

        Commits on clean exit, rolls back on exception, always closes.
        Use when you need to read back auto-generated IDs mid-seed or build
        objects that reference each other:

            with infra.seed_session() as s:
                area = Area(name="Engineering")
                s.add(area)
                s.flush()                        # populate area.id without committing
                s.add(Employee(name="Alice", area_id=area.id))
            # committed here
        """
        session = self.make_session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def drain_all_queues(self) -> None:
        for url in list(self.queue_urls.values()) + list(
            self.sns_capture_urls.values()
        ):
            _drain_queue(self.sqs, url)

    def truncate_tables(self, *table_names: str) -> None:
        with self.db_engine.connect() as conn:
            if self.config.db_type == "sqlserver":
                _sqlserver_truncate(conn, table_names)
            else:
                for table in table_names:
                    conn.execute(
                        text(f"TRUNCATE TABLE {table} RESTART IDENTITY CASCADE")
                    )
            conn.commit()

    def stop(self) -> None:
        self.db_engine.dispose()
        for c in self.containers:
            c.stop()

    @classmethod
    def from_config(cls, config: BDDConfig) -> "BDDInfra":
        containers: list[Any] = []

        if config.db_url:
            db_url = config.db_url
        elif config.db_type == "sqlserver":
            db_url = _start_sqlserver(config, containers)
        else:
            db_url = _start_postgres(config, containers)

        aws_endpoint = config.aws_endpoint or _start_localstack(config, containers)

        engine = create_engine(db_url)
        if config.db_base is not None:
            config.db_base.metadata.create_all(engine)

        boto_kwargs = {
            "endpoint_url": aws_endpoint,
            "region_name": config.aws_region,
            "aws_access_key_id": os.environ.get("AWS_ACCESS_KEY_ID", "test"),
            "aws_secret_access_key": os.environ.get("AWS_SECRET_ACCESS_KEY", "test"),
        }
        sqs = boto3.client("sqs", **boto_kwargs)
        sns = boto3.client("sns", **boto_kwargs)
        s3 = boto3.client("s3", **boto_kwargs)

        queue_urls: dict[str, str] = {}
        for name in config.sqs_queues:
            sqs.create_queue(QueueName=name)
            queue_urls[name] = sqs.get_queue_url(QueueName=name)["QueueUrl"]

        topic_arns: dict[str, str] = {}
        for name in config.sns_topics:
            topic_arns[name] = sns.create_topic(Name=name)["TopicArn"]

        for name in config.s3_buckets:
            s3.create_bucket(Bucket=name)

        # For each SNS topic, create a dedicated capture queue and subscribe it.
        # Tests can poll infra.sns_capture_urls[topic_name] via assert_sns_message().
        sns_capture_urls: dict[str, str] = {}
        for topic_name, topic_arn in topic_arns.items():
            capture_name = f"{topic_name}-capture"
            sqs.create_queue(QueueName=capture_name)
            capture_url = sqs.get_queue_url(QueueName=capture_name)["QueueUrl"]
            capture_arn = sqs.get_queue_attributes(
                QueueUrl=capture_url, AttributeNames=["QueueArn"]
            )["Attributes"]["QueueArn"]
            sns.subscribe(TopicArn=topic_arn, Protocol="sqs", Endpoint=capture_arn)
            sns_capture_urls[topic_name] = capture_url

        return cls(
            config=config,
            db_url=db_url,
            db_engine=engine,
            sqs=sqs,
            sns=sns,
            s3=s3,
            aws_endpoint=aws_endpoint,
            queue_urls=queue_urls,
            topic_arns=topic_arns,
            sns_capture_urls=sns_capture_urls,
            containers=containers,
        )


# ── Table truncation ───────────────────────────────────────────────────────────


def _sqlserver_truncate(conn, table_names) -> None:
    # Collect all FK constraints that need to be disabled upfront — including
    # cross-table incoming FKs — to handle circular references (e.g. employees ↔ areas).
    to_disable: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    for table in table_names:
        for (fk,) in conn.execute(
            text(
                "SELECT name FROM sys.foreign_keys WHERE OBJECT_NAME(parent_object_id) = :t"
            ),
            {"t": table},
        ).fetchall():
            key = (table, fk)
            if key not in seen:
                seen.add(key)
                to_disable.append(key)

        for fk, parent in conn.execute(
            text("""
                SELECT fk.name, OBJECT_NAME(fk.parent_object_id)
                FROM sys.foreign_keys fk
                WHERE OBJECT_NAME(fk.referenced_object_id) = :t
                  AND OBJECT_NAME(fk.parent_object_id) != :t
            """),
            {"t": table},
        ).fetchall():
            key = (parent, fk)
            if key not in seen:
                seen.add(key)
                to_disable.append(key)

    for tbl, fk in to_disable:
        conn.execute(text(f"ALTER TABLE [{tbl}] NOCHECK CONSTRAINT [{fk}]"))

    for table in table_names:
        conn.execute(text(f"DELETE FROM [{table}]"))
        has_identity = conn.execute(
            text(
                "SELECT COUNT(1) FROM sys.identity_columns WHERE OBJECT_NAME(object_id) = :t"
            ),
            {"t": table},
        ).scalar()
        if has_identity:
            conn.execute(text(f"DBCC CHECKIDENT ('{table}', RESEED, 0)"))

    for tbl, fk in to_disable:
        conn.execute(text(f"ALTER TABLE [{tbl}] WITH CHECK CHECK CONSTRAINT [{fk}]"))


# ── Container launchers ────────────────────────────────────────────────────────


def _start_postgres(config: BDDConfig, containers: list) -> str:
    from testcontainers.postgres import PostgresContainer

    pg = PostgresContainer(
        image=config.postgres_image,
        username="bdd",
        password="bdd",
        dbname="bdd",
    )
    pg.start()
    containers.append(pg)
    return pg.get_connection_url()


def _start_sqlserver(config: BDDConfig, containers: list) -> str:
    from testcontainers.mssql import SqlServerContainer

    mssql = SqlServerContainer(
        image=config.sqlserver_image,
        password="BddTest1!",
        dbname="tempdb",
    )
    mssql.start()
    containers.append(mssql)
    return mssql.get_connection_url()


def _start_localstack(config: BDDConfig, containers: list) -> str:
    from testcontainers.localstack import LocalStackContainer

    ls = (
        LocalStackContainer(image=config.localstack_image)
        .with_services("sqs", "sns", "s3")
        .with_env("SQS_ENDPOINT_STRATEGY", "path")
    )
    ls.start()
    containers.append(ls)
    return ls.get_url()


# ── Queue drain ────────────────────────────────────────────────────────────────


def _drain_queue(sqs_client: Any, queue_url: str) -> None:
    while True:
        msgs = sqs_client.receive_message(
            QueueUrl=queue_url, MaxNumberOfMessages=10, WaitTimeSeconds=0
        ).get("Messages", [])
        if not msgs:
            break
        for m in msgs:
            sqs_client.delete_message(
                QueueUrl=queue_url, ReceiptHandle=m["ReceiptHandle"]
            )
