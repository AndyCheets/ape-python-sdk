import json
import logging
from typing import Any

import pytest

from ape_sdk.bus.consumer import RabbitMqCommandConsumer
from ape_sdk.bus.publisher import RabbitMqEventPublisher
from ape_sdk.control import client as control_client_module
from ape_sdk.control.client import ControlApiClient
from ape_sdk.messages.envelope import MessageEnvelope
from ape_sdk.tenant.context import TenantWorkerContext
from ape_sdk.worker.errors import ConfigurationError
from ape_sdk.worker.processing import (
    MessageDecision,
    MessageProcessingResult,
    WorkerCommandProcessor,
)
from ape_sdk.worker.result import WorkerTaskResult
from ape_sdk.worker.settings import Settings, load_worker_settings


BASE_ENV = {
    "APE_ENVIRONMENT": "Development",
    "APE_SERVICE_NAME": "ape-worker-template",
    "APE_CONTROL_API_BASE_URL": "http://control-api",
    "APE_CONTROL_API_TOKEN": "control-token-secret",
    "RABBITMQ_HOST": "rabbitmq",
    "RABBITMQ_PORT": "5672",
    "RABBITMQ_USERNAME": "ape",
    "RABBITMQ_PASSWORD": "rabbit-secret",
    "RABBITMQ_VHOST": "ape_dev",
    "RABBITMQ_COMMAND_EXCHANGE": "ape.commands",
    "RABBITMQ_EVENT_EXCHANGE": "ape.events",
    "RABBITMQ_QUEUE_NAME": "ape.example-worker.dev",
    "RABBITMQ_BINDING_KEYS": "command.ExampleCommand",
    "WORKER_COMMAND_MESSAGE_TYPE": "ExampleCommand",
    "WORKER_COMPLETED_EVENT_MESSAGE_TYPE": "ExampleTaskCompleted",
    "WORKER_FAILED_EVENT_MESSAGE_TYPE": "ExampleTaskFailed",
}


def test_valid_command_envelope_parses_correctly() -> None:
    envelope = MessageEnvelope.model_validate(command_payload())

    assert envelope.message_id == "command-message-id"
    assert envelope.correlation_id == "correlation-id"
    assert envelope.tenant_key == "tenant-a"
    assert envelope.message_type == "ExampleCommand"
    assert envelope.payload == {"value": 123}


def test_invalid_json_is_acked_after_logging(processor: WorkerCommandProcessor, caplog) -> None:
    caplog.set_level(logging.ERROR)

    result = processor.process(b"{not-json")

    assert result.decision == MessageDecision.ACK
    assert "invalid command JSON" in caplog.text


def test_missing_tenant_key_is_acked_after_logging(
    processor: WorkerCommandProcessor,
    caplog,
) -> None:
    caplog.set_level(logging.ERROR)
    payload = command_payload()
    del payload["tenantKey"]

    result = processor.process(json_body(payload))

    assert result.decision == MessageDecision.ACK
    assert "invalid command envelope" in caplog.text


def test_missing_message_type_is_acked_after_logging(
    processor: WorkerCommandProcessor,
    caplog,
) -> None:
    caplog.set_level(logging.ERROR)
    payload = command_payload()
    del payload["messageType"]

    result = processor.process(json_body(payload))

    assert result.decision == MessageDecision.ACK
    assert "invalid command envelope" in caplog.text


def test_unsupported_message_type_is_acked_and_ignored(
    settings: Settings,
    caplog,
) -> None:
    control_api = FakeControlApiClient()
    task_handler = FakeTaskHandler()
    publisher = FakePublisher()
    processor = WorkerCommandProcessor(
        settings=settings,
        control_api_client=control_api,
        task_handler=task_handler,
        event_publisher=publisher,
    )

    caplog.set_level(logging.WARNING)
    result = processor.process(json_body(command_payload(messageType="OtherCommand")))

    assert result.decision == MessageDecision.ACK
    assert "unsupported command message type" in caplog.text
    assert control_api.tenant_keys == []
    assert task_handler.calls == []
    assert publisher.envelopes == []


def test_worker_resolves_tenant_context_using_tenant_key(settings: Settings) -> None:
    control_api = FakeControlApiClient()
    processor = make_processor(settings=settings, control_api_client=control_api)

    processor.process(json_body(command_payload(tenantKey="tenant-b")))

    assert control_api.tenant_keys == ["tenant-b"]


def test_control_api_token_is_sent_and_not_logged(monkeypatch, caplog) -> None:
    seen_headers: dict[str, str] = {}

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback) -> None:
            return None

        def read(self) -> bytes:
            return json_body(worker_context_payload())

    def fake_urlopen(request, timeout):  # type: ignore[no-untyped-def]
        seen_headers.update(dict(request.header_items()))
        return Response()

    monkeypatch.setattr(control_client_module, "urlopen", fake_urlopen)
    caplog.set_level(logging.INFO)

    client = ControlApiClient(
        base_url="http://control-api",
        token="control-token-secret",
        timeout_seconds=3,
    )
    context = client.get_worker_context("tenant-a")

    assert context.tenant_key == "tenant-a"
    assert seen_headers["Authorization"] == "Bearer control-token-secret"
    assert "control-token-secret" not in caplog.text


def test_task_handler_is_called_for_configured_command_message_type(settings: Settings) -> None:
    task_handler = FakeTaskHandler()
    processor = make_processor(settings=settings, task_handler=task_handler)

    processor.process(json_body(command_payload()))

    assert len(task_handler.calls) == 1
    assert task_handler.calls[0].envelope.message_type == "ExampleCommand"


def test_successful_task_publishes_completed_event(settings: Settings) -> None:
    publisher = FakePublisher()
    processor = make_processor(settings=settings, event_publisher=publisher)

    processor.process(json_body(command_payload()))

    assert publisher.envelopes[0].message_type == "ExampleTaskCompleted"
    assert publisher.envelopes[0].payload == {"ok": True}


def test_completed_event_preserves_correlation_id(settings: Settings) -> None:
    publisher = FakePublisher()
    processor = make_processor(settings=settings, event_publisher=publisher)

    processor.process(json_body(command_payload(correlationId="corr-123")))

    assert publisher.envelopes[0].correlation_id == "corr-123"


def test_completed_event_sets_causation_id_to_command_message_id(settings: Settings) -> None:
    publisher = FakePublisher()
    processor = make_processor(settings=settings, event_publisher=publisher)

    processor.process(json_body(command_payload(messageId="cmd-123")))

    assert publisher.envelopes[0].causation_id == "cmd-123"


def test_completed_event_uses_configured_completed_event_message_type(settings: Settings) -> None:
    publisher = FakePublisher()
    processor = make_processor(settings=settings, event_publisher=publisher)

    processor.process(json_body(command_payload()))

    assert publisher.envelopes[0].message_type == settings.worker.completed_event_message_type


def test_failed_task_publishes_failed_event(settings: Settings) -> None:
    publisher = FakePublisher()
    processor = make_processor(
        settings=settings,
        task_handler=FakeTaskHandler(error=RuntimeError("task failed")),
        event_publisher=publisher,
    )

    processor.process(json_body(command_payload()))

    assert publisher.envelopes[0].message_type == "ExampleTaskFailed"


def test_failed_event_preserves_correlation_id(settings: Settings) -> None:
    publisher = FakePublisher()
    processor = make_processor(
        settings=settings,
        task_handler=FakeTaskHandler(error=RuntimeError("task failed")),
        event_publisher=publisher,
    )

    processor.process(json_body(command_payload(correlationId="corr-456")))

    assert publisher.envelopes[0].correlation_id == "corr-456"


def test_failed_event_sets_causation_id_to_command_message_id(settings: Settings) -> None:
    publisher = FakePublisher()
    processor = make_processor(
        settings=settings,
        task_handler=FakeTaskHandler(error=RuntimeError("task failed")),
        event_publisher=publisher,
    )

    processor.process(json_body(command_payload(messageId="cmd-456")))

    assert publisher.envelopes[0].causation_id == "cmd-456"


def test_failed_event_uses_configured_failed_event_message_type(settings: Settings) -> None:
    publisher = FakePublisher()
    processor = make_processor(
        settings=settings,
        task_handler=FakeTaskHandler(error=RuntimeError("task failed")),
        event_publisher=publisher,
    )

    processor.process(json_body(command_payload()))

    assert publisher.envelopes[0].message_type == settings.worker.failed_event_message_type


def test_failed_event_payload_includes_safe_error_type_and_message(settings: Settings) -> None:
    publisher = FakePublisher()
    processor = make_processor(
        settings=settings,
        task_handler=FakeTaskHandler(error=RuntimeError("token=secret-value")),
        event_publisher=publisher,
    )

    processor.process(json_body(command_payload()))

    assert publisher.envelopes[0].payload == {
        "errorType": "RuntimeError",
        "errorMessage": "token=<redacted>",
    }


def test_completed_event_is_published_to_configured_event_exchange(settings: Settings) -> None:
    channel = FakeRabbitMqChannel()
    publisher = RabbitMqEventPublisher(
        rabbitmq_settings=settings.rabbitmq,
        connection_factory=lambda: FakeRabbitMqConnection(channel),
    )

    publisher.publish(completed_event_envelope(settings))

    assert channel.published[0]["exchange"] == "ape.events"


def test_completed_event_routing_key_uses_completed_event_message_type(settings: Settings) -> None:
    channel = FakeRabbitMqChannel()
    publisher = RabbitMqEventPublisher(
        rabbitmq_settings=settings.rabbitmq,
        connection_factory=lambda: FakeRabbitMqConnection(channel),
    )

    publisher.publish(completed_event_envelope(settings))

    assert channel.published[0]["routing_key"] == "event.ExampleTaskCompleted"


def test_failed_event_routing_key_uses_failed_event_message_type(settings: Settings) -> None:
    channel = FakeRabbitMqChannel()
    publisher = RabbitMqEventPublisher(
        rabbitmq_settings=settings.rabbitmq,
        connection_factory=lambda: FakeRabbitMqConnection(channel),
    )

    publisher.publish(failed_event_envelope(settings))

    assert channel.published[0]["routing_key"] == "event.ExampleTaskFailed"


def test_successful_processing_acks_original_command(settings: Settings) -> None:
    channel = FakeAckChannel()
    consumer = RabbitMqCommandConsumer(
        rabbitmq_settings=settings.rabbitmq,
        processor=FakeProcessor(MessageDecision.ACK),
        connection_factory=lambda: None,
    )

    consumer._handle_delivery(channel, 10, b"{}")

    assert channel.acks == [10]
    assert channel.nacks == []


def test_task_failure_nacks_without_requeue(settings: Settings) -> None:
    channel = FakeAckChannel()
    consumer = RabbitMqCommandConsumer(
        rabbitmq_settings=settings.rabbitmq,
        processor=FakeProcessor(MessageDecision.NACK_WITHOUT_REQUEUE),
        connection_factory=lambda: None,
    )

    consumer._handle_delivery(channel, 11, b"{}")

    assert channel.acks == []
    assert channel.nacks == [(11, False)]


def test_secrets_are_not_logged(settings: Settings, caplog) -> None:
    caplog.set_level(logging.ERROR)
    processor = make_processor(
        settings=settings,
        task_handler=FakeTaskHandler(
            error=RuntimeError(
                "token=task-secret Password=db-secret Bearer provider-secret"
            )
        ),
    )

    processor.process(json_body(command_payload()))

    assert "task-secret" not in caplog.text
    assert "db-secret" not in caplog.text
    assert "provider-secret" not in caplog.text


def test_startup_validation_fails_clearly_when_required_settings_are_missing() -> None:
    env = dict(BASE_ENV)
    del env["RABBITMQ_HOST"]

    with pytest.raises(ConfigurationError, match="RABBITMQ_HOST"):
        load_worker_settings(env)


@pytest.fixture
def settings() -> Settings:
    return load_worker_settings(BASE_ENV)


@pytest.fixture
def processor(settings: Settings) -> WorkerCommandProcessor:
    return make_processor(settings=settings)


def make_processor(
    *,
    settings: Settings,
    control_api_client: Any | None = None,
    task_handler: Any | None = None,
    event_publisher: Any | None = None,
) -> WorkerCommandProcessor:
    return WorkerCommandProcessor(
        settings=settings,
        control_api_client=control_api_client or FakeControlApiClient(),
        task_handler=task_handler or FakeTaskHandler(),
        event_publisher=event_publisher or FakePublisher(),
    )


def command_payload(**overrides) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    payload = {
        "messageId": "command-message-id",
        "correlationId": "correlation-id",
        "causationId": None,
        "tenantKey": "tenant-a",
        "source": "test",
        "messageType": "ExampleCommand",
        "schemaVersion": 1,
        "createdAtUtc": "2026-05-17T08:00:00Z",
        "metadata": {"trace": "yes"},
        "payload": {"value": 123},
    }
    payload.update(overrides)
    return payload


def worker_context_payload() -> dict[str, Any]:
    return {
        "tenantKey": "tenant-a",
        "displayName": "Tenant A",
        "databaseName": "tenant_a",
        "enabledModules": ["example"],
        "tenantDatabaseConnectionString": (
            "Server=mysql;Port=3306;Database=tenant_a;User Id=ape;Password=db-secret;"
        ),
    }


def json_body(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload).encode("utf-8")


def completed_event_envelope(settings: Settings) -> MessageEnvelope:
    return MessageEnvelope.new_event(
        source_command=MessageEnvelope.model_validate(command_payload()),
        source=settings.app.service_name,
        message_type=settings.worker.completed_event_message_type,
        payload={"ok": True},
    )


def failed_event_envelope(settings: Settings) -> MessageEnvelope:
    return MessageEnvelope.new_event(
        source_command=MessageEnvelope.model_validate(command_payload()),
        source=settings.app.service_name,
        message_type=settings.worker.failed_event_message_type,
        payload={"errorType": "RuntimeError", "errorMessage": "failed"},
    )


class FakeControlApiClient:
    def __init__(self) -> None:
        self.tenant_keys: list[str] = []

    def get_worker_context(self, tenant_key: str) -> TenantWorkerContext:
        self.tenant_keys.append(tenant_key)
        return TenantWorkerContext.model_validate(
            worker_context_payload() | {"tenantKey": tenant_key}
        )


class FakeTaskHandler:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[Any] = []

    def handle(self, command) -> WorkerTaskResult:  # type: ignore[no-untyped-def]
        self.calls.append(command)
        if self.error is not None:
            raise self.error
        return WorkerTaskResult(payload={"ok": True})


class FakePublisher:
    def __init__(self) -> None:
        self.envelopes: list[MessageEnvelope] = []

    def publish(self, envelope: MessageEnvelope) -> None:
        self.envelopes.append(envelope)


class FakeProcessor:
    def __init__(self, decision: MessageDecision) -> None:
        self.decision = decision

    def process(self, body: bytes) -> MessageProcessingResult:
        return MessageProcessingResult(self.decision)


class FakeAckChannel:
    def __init__(self) -> None:
        self.acks: list[int] = []
        self.nacks: list[tuple[int, bool]] = []

    def basic_ack(self, *, delivery_tag: int) -> None:
        self.acks.append(delivery_tag)

    def basic_nack(self, *, delivery_tag: int, requeue: bool) -> None:
        self.nacks.append((delivery_tag, requeue))


class FakeRabbitMqConnection:
    is_closed = False

    def __init__(self, channel: "FakeRabbitMqChannel") -> None:
        self._channel = channel

    def channel(self) -> "FakeRabbitMqChannel":
        return self._channel


class FakeRabbitMqChannel:
    is_closed = False

    def __init__(self) -> None:
        self.exchanges: list[dict[str, Any]] = []
        self.published: list[dict[str, Any]] = []

    def exchange_declare(self, **kwargs) -> None:  # type: ignore[no-untyped-def]
        self.exchanges.append(kwargs)

    def basic_publish(self, **kwargs) -> None:  # type: ignore[no-untyped-def]
        kwargs["body_json"] = json.loads(kwargs["body"].decode("utf-8"))
        self.published.append(kwargs)
