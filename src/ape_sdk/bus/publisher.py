import json
import logging
from collections.abc import Callable
from contextlib import AbstractContextManager

import pika
from pika.exceptions import AMQPError, ChannelWrongStateError, StreamLostError

from ape_sdk.messages.envelope import MessageEnvelope

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
            logger.debug("Failed to close stale RabbitMQ publisher connection", exc_info=True)
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
                exc_info=True,
            )
            self._reconnect()
            self._publish_once(exchange, routing_key, envelope)

    def _publish_once(self, exchange: str, routing_key: str, envelope: MessageEnvelope) -> None:
        self.declare_exchange(exchange)
        self._ensure_channel().basic_publish(
            exchange=exchange,
            routing_key=routing_key,
            body=envelope.model_dump_json().encode("utf-8"),
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
