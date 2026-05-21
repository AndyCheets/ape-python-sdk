import pika

from ape_sdk.worker.settings import RabbitMqSettings


def create_connection(settings: RabbitMqSettings) -> pika.BlockingConnection:
    credentials = pika.PlainCredentials(settings.username, settings.password)
    parameters = pika.ConnectionParameters(
        host=settings.host,
        port=settings.port,
        virtual_host=settings.vhost,
        credentials=credentials,
        heartbeat=60,
        blocked_connection_timeout=30,
    )
    return pika.BlockingConnection(parameters)
