import logging
from collections.abc import Callable
from dataclasses import dataclass
from threading import Thread

import pika

from ape_sdk.bus.publisher import decode_envelope
from ape_sdk.messages.envelope import MessageEnvelope

logger = logging.getLogger(__name__)
MessageHandler = Callable[[MessageEnvelope], None]
HEARTBEAT_POLL_SECONDS = 1.0


@dataclass(frozen=True)
class QueueBinding:
    queue_name: str
    routing_key: str
    handler: MessageHandler


class RabbitMQConsumer:
    def __init__(self, connection: pika.BlockingConnection) -> None:
        self.connection = connection
        self.channel = connection.channel()

    def consume(
        self,
        *,
        exchange: str,
        queue_name: str,
        routing_key: str,
        handler: MessageHandler,
    ) -> None:
        self.consume_many(
            exchange=exchange,
            bindings=[
                QueueBinding(
                    queue_name=queue_name,
                    routing_key=routing_key,
                    handler=handler,
                )
            ],
        )

    def consume_many(self, *, exchange: str, bindings: list[QueueBinding]) -> None:
        self.channel.exchange_declare(exchange=exchange, exchange_type="topic", durable=True)
        self.channel.basic_qos(prefetch_count=1)

        for binding in bindings:
            self.channel.queue_declare(queue=binding.queue_name, durable=True)
            self.channel.queue_bind(
                exchange=exchange,
                queue=binding.queue_name,
                routing_key=binding.routing_key,
            )

            def callback(channel, method, properties, body, binding=binding) -> None:  # type: ignore[no-untyped-def]
                error: list[BaseException] = []

                def run_handler() -> None:
                    try:
                        binding.handler(decode_envelope(body))
                    except BaseException as exc:
                        error.append(exc)

                worker = Thread(target=run_handler, name=f"{binding.queue_name}-handler")
                worker.start()
                while worker.is_alive():
                    self.connection.process_data_events(time_limit=0)
                    worker.join(HEARTBEAT_POLL_SECONDS)

                try:
                    if error:
                        raise error[0]
                    if channel.is_open:
                        channel.basic_ack(delivery_tag=method.delivery_tag)
                    else:
                        logger.error(
                            "Channel closed before ack queue=%s delivery_tag=%s",
                            binding.queue_name,
                            method.delivery_tag,
                        )
                except Exception:
                    logger.exception("failed to handle message on queue=%s", binding.queue_name)
                    if channel.is_open:
                        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
                    else:
                        logger.error(
                            "Channel closed before nack queue=%s delivery_tag=%s",
                            binding.queue_name,
                            method.delivery_tag,
                        )

            self.channel.basic_consume(
                queue=binding.queue_name,
                on_message_callback=callback,
            )
            logger.info(
                "consuming queue=%s routing_key=%s",
                binding.queue_name,
                binding.routing_key,
            )

        self.channel.start_consuming()

    def stop(self) -> None:
        if self.channel.is_open:
            self.channel.stop_consuming()
            self.channel.close()
