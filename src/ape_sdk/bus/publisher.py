import json
import logging
from collections.abc import Callable
from contextlib import AbstractContextManager

import pika
from pika.exceptions import AMQPError, ChannelWrongStateError, StreamLostError

from ape_sdk.messages.envelope import MessageEnvelope
from ape_sdk.worker.errors import MessagePublishError
from ape_sdk.worker.settings import RabbitMqSettings

logger = logging.getLogger(__name__)
ConnectionFactory = Callable[[], pika.BlockingConnection]


class RabbitMQPublisher(AbstractContextManager["RabbitMQPublisher"]):
    def __init__(
        self,
        connection: pika.BlockingConnection | None = None,
        *,
        connection_factory: ConnectionFactory | None = None,
    ) -> None:
        if connection is None and connection_factory is None:
            raise ValueError("RabbitMQPublisher requires a connection or connection_factory")
        self.connection = connection
        self.connection_factory = connection_factory
        self.channel = connection.channel() if connection is not None else None

    def _ensure_channel(self) -> pika.channel.Channel:
        if self.connection is None or self.connection.is_closed:
            if self.connection_factory is None:
                raise RuntimeError("RabbitMQ publisher connection is closed")
            self.connection = self.connection_factory()
            self.channel = None
        if self.channel is None or self.channel.is_closed:
            self.channel = self.connection.channel()
        return self.channel

    def _reconnect(self) -> None:
        if self.connection_factory is None:
            return
        try:
            if self.connection is not None and self.connection.is_open:
                self.connection.close()
        except AMQPError:
            logger.debug("Failed to close stale RabbitMQ publisher connection")
        self.connection = self.connection_factory()
        self.channel = self.connection.channel()

    def declare_exchange(self, exchange: str) -> None:
        self._ensure_channel().exchange_declare(
            exchange=exchange,
            exchange_type="topic",
            durable=True,
        )

    def publish(self, exchange: str, routing_key: str, envelope: MessageEnvelope) -> None:
        if self.connection_factory is not None:
            self._reconnect()
        try:
            self._publish_once(exchange, routing_key, envelope)
        except (AMQPError, ChannelWrongStateError, StreamLostError):
            if self.connection_factory is None:
                raise
            logger.warning(
                "RabbitMQ publisher channel closed; reconnecting and retrying publish "
                "routing_key=%s",
                routing_key,
            )
            self._reconnect()
            self._publish_once(exchange, routing_key, envelope)

    def _publish_once(self, exchange: str, routing_key: str, envelope: MessageEnvelope) -> None:
        self.declare_exchange(exchange)
        self._ensure_channel().basic_publish(
            exchange=exchange,
            routing_key=routing_key,
            body=envelope.to_json_bytes(),
            properties=pika.BasicProperties(
                content_type="application/json",
                delivery_mode=pika.DeliveryMode.Persistent,
                message_id=envelope.message_id,
                correlation_id=envelope.correlation_id,
            ),
        )
        logger.info("published message_type=%s routing_key=%s", envelope.message_type, routing_key)

    def __exit__(self, exc_type, exc_value, traceback) -> None:  # type: ignore[no-untyped-def]
        if self.channel is not None and self.channel.is_open:
            self.channel.close()


def decode_envelope(body: bytes) -> MessageEnvelope:
    return MessageEnvelope.model_validate(json.loads(body.decode("utf-8")))


class RabbitMqEventPublisher:
    def __init__(
        self,
        *,
        rabbitmq_settings: RabbitMqSettings,
        connection_factory: ConnectionFactory,
    ) -> None:
        self.rabbitmq_settings = rabbitmq_settings
        self.connection_factory = connection_factory
        self.connection: pika.BlockingConnection | None = None
        self.channel: pika.channel.Channel | None = None

    def publish(self, envelope: MessageEnvelope) -> None:
        routing_key = f"event.{envelope.message_type}"
        try:
            channel = self._ensure_channel()
            channel.exchange_declare(
                exchange=self.rabbitmq_settings.event_exchange,
                exchange_type="topic",
                durable=True,
            )
            channel.basic_publish(
                exchange=self.rabbitmq_settings.event_exchange,
                routing_key=routing_key,
                body=envelope.to_json_bytes(),
                properties=pika.BasicProperties(
                    content_type="application/json",
                    delivery_mode=pika.DeliveryMode.Persistent,
                    message_id=envelope.message_id,
                    correlation_id=envelope.correlation_id,
                ),
            )
        except Exception as exc:
            raise MessagePublishError(
                f"Failed to publish event message_type={envelope.message_type}"
            ) from exc

        logger.info(
            "published event tenant_key=%s message_id=%s correlation_id=%s message_type=%s "
            "routing_key=%s",
            envelope.tenant_key,
            envelope.message_id,
            envelope.correlation_id,
            envelope.message_type,
            routing_key,
        )

    def _ensure_channel(self) -> pika.channel.Channel:
        if self.connection is None or self.connection.is_closed:
            self.connection = self.connection_factory()
            self.channel = None
        if self.channel is None or self.channel.is_closed:
            self.channel = self.connection.channel()
        return self.channel
