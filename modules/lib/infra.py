import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import boto3
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from lib.config import BDDConfig


@dataclass
class BDDInfra:
    config: BDDConfig
    db_url: str
    db_engine: Engine
    sqs: Any
    sns: Any
    s3: Any
    aws_endpoint: str
    queue_urls: Dict[str, str] = field(default_factory=dict)
    topic_arns: Dict[str, str] = field(default_factory=dict)
    _containers: List[Any] = field(default_factory=list, repr=False)

    def make_session(self) -> Session:
        return sessionmaker(bind=self.db_engine)()

    def drain_all_queues(self) -> None:
        for url in self.queue_urls.values():
            _drain_queue(self.sqs, url)

    def truncate_tables(self, *table_names: str) -> None:
        with self.db_engine.connect() as conn:
            if self.config.db_type == "sqlserver":
                _sqlserver_truncate(conn, table_names)
            else:
                for table in table_names:
                    conn.execute(text(f"TRUNCATE TABLE {table} RESTART IDENTITY CASCADE"))
            conn.commit()

    def stop(self) -> None:
        self.db_engine.dispose()
        for c in self._containers:
            c.stop()

    @classmethod
    def from_config(cls, config: BDDConfig) -> "BDDInfra":
        containers: List[Any] = []

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

        boto_kwargs = dict(
            endpoint_url=aws_endpoint,
            region_name=config.aws_region,
            aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID", "test"),
            aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY", "test"),
        )
        sqs = boto3.client("sqs", **boto_kwargs)
        sns = boto3.client("sns", **boto_kwargs)
        s3 = boto3.client("s3", **boto_kwargs)

        queue_urls: Dict[str, str] = {}
        for name in config.sqs_queues:
            sqs.create_queue(QueueName=name)
            queue_urls[name] = sqs.get_queue_url(QueueName=name)["QueueUrl"]

        topic_arns: Dict[str, str] = {}
        for name in config.sns_topics:
            topic_arns[name] = sns.create_topic(Name=name)["TopicArn"]

        for name in config.s3_buckets:
            s3.create_bucket(Bucket=name)

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
            _containers=containers,
        )


def _sqlserver_truncate(conn, table_names) -> None:
    for table in table_names:
        # Disable all FK constraints (handles self-referential and cross-table FKs)
        fks = conn.execute(
            text("SELECT name FROM sys.foreign_keys WHERE OBJECT_NAME(parent_object_id) = :t"),
            {"t": table},
        ).fetchall()
        for (fk,) in fks:
            conn.execute(text(f"ALTER TABLE [{table}] NOCHECK CONSTRAINT [{fk}]"))

        conn.execute(text(f"DELETE FROM [{table}]"))

        # Reset identity seed if the table has an identity column
        has_identity = conn.execute(
            text("SELECT COUNT(1) FROM sys.identity_columns WHERE OBJECT_NAME(object_id) = :t"),
            {"t": table},
        ).scalar()
        if has_identity:
            conn.execute(text(f"DBCC CHECKIDENT ('{table}', RESEED, 0)"))

        for (fk,) in fks:
            conn.execute(text(f"ALTER TABLE [{table}] WITH CHECK CHECK CONSTRAINT [{fk}]"))


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


def _drain_queue(sqs_client: Any, queue_url: str) -> None:
    while True:
        msgs = sqs_client.receive_message(
            QueueUrl=queue_url, MaxNumberOfMessages=10, WaitTimeSeconds=0
        ).get("Messages", [])
        if not msgs:
            break
        for m in msgs:
            sqs_client.delete_message(QueueUrl=queue_url, ReceiptHandle=m["ReceiptHandle"])
