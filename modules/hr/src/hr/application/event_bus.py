import json

from hr.domain.events import DomainEvent


class EventBus:
    def __init__(
        self,
        sqs_client=None,
        sns_client=None,
        queue_url: str = "",
        topic_arn: str = "",
    ):
        self._sqs = sqs_client
        self._sns = sns_client
        self._queue_url = queue_url
        self._topic_arn = topic_arn

    def publish(self, event: DomainEvent) -> None:
        if self._sqs and self._queue_url:
            self._sqs.send_message(
                QueueUrl=self._queue_url,
                MessageBody=json.dumps(event.model_dump()),
            )

    def notify(self, subject: str, message: str) -> None:
        if self._sns and self._topic_arn:
            self._sns.publish(
                TopicArn=self._topic_arn, Subject=subject, Message=message
            )
