import json
from collections.abc import Callable

import pytest
from email_sync_worker.control_api_client import ControlApiError, TenantWorkerContext
from email_sync_worker.message_envelope import MessageEnvelope
from email_sync_worker.scheduled_processor import (
    MessageDecision,
    ScheduledEmailCampaignProcessor,
)
from pydantic import ValidationError


class FakeControlApiClient:
    def __init__(
        self,
        context: TenantWorkerContext | None = None,
        error: Exception | None = None,
    ) -> None:
        self.context = context
        self.error = error
        self.requested_tenant_keys: list[str] = []

    def get_worker_context(self, tenant_key: str) -> TenantWorkerContext:
        self.requested_tenant_keys.append(tenant_key)
        if self.error is not None:
            raise self.error
        assert self.context is not None
        return self.context


class RecordingSyncHandler:
    def __init__(self) -> None:
        self.envelopes = []
        self.raise_on_handle = False

    def handle(self, envelope) -> None:
        self.envelopes.append(envelope)
        if self.raise_on_handle:
            raise RuntimeError("sync failed")


def _context(
    *,
    modules: list[str] | None = None,
    connection_string: str = (
        "Server=mysql;Port=3306;Database=tenant;User Id=ape;Password=secret;"
    ),
) -> TenantWorkerContext:
    return TenantWorkerContext.model_validate(
        {
            "tenantKey": "bite-demo",
            "displayName": "Bite Demo",
            "databaseName": "ape_tenant_bite_demo_dev",
            "enabledModules": modules if modules is not None else ["email-campaigns"],
            "tenantDatabaseConnectionString": connection_string,
        }
    )


def _body(**overrides) -> bytes:
    payload = {
        "messageId": "message-1",
        "correlationId": "correlation-1",
        "causationId": None,
        "tenantKey": "bite-demo",
        "source": "ape-scheduler-service",
        "messageType": "SyncEmailCampaigns",
        "schemaVersion": 1,
        "createdAtUtc": "2026-05-16T11:30:00Z",
        "metadata": {"scheduleKey": "sync-email-campaigns-nightly"},
        "payload": {"lookbackDays": 28, "triggeredBy": "scheduler"},
    }
    payload.update(overrides)
    return json.dumps(payload).encode("utf-8")


def _processor(
    control_api_client: FakeControlApiClient,
    handler: RecordingSyncHandler | None = None,
    verifier: Callable[[Callable], None] | None = None,
):
    created_connection_strings: list[str] = []

    def session_factory_builder(connection_string: str):
        created_connection_strings.append(connection_string)
        return lambda: None

    actual_handler = handler or RecordingSyncHandler()
    processor = ScheduledEmailCampaignProcessor(
        control_api_client=control_api_client,  # type: ignore[arg-type]
        sync_handler_factory=lambda session_factory: actual_handler,  # type: ignore[return-value]
        session_factory_builder=session_factory_builder,
        database_connection_verifier=verifier or (lambda session_factory: None),
    )
    return processor, actual_handler, created_connection_strings


def test_valid_sync_email_campaigns_envelope_parses_camel_case_fields() -> None:
    envelope = MessageEnvelope.model_validate(json.loads(_body()))

    assert envelope.message_id == "message-1"
    assert envelope.correlation_id == "correlation-1"
    assert envelope.tenant_key == "bite-demo"
    assert envelope.metadata["scheduleKey"] == "sync-email-campaigns-nightly"
    assert envelope.payload["lookbackDays"] == 28


@pytest.mark.parametrize("missing_field", ["tenantKey", "messageType"])
def test_missing_required_envelope_fields_are_rejected(missing_field: str) -> None:
    payload = json.loads(_body())
    payload.pop(missing_field)

    with pytest.raises(ValidationError):
        MessageEnvelope.model_validate(payload)


def test_unsupported_message_type_is_acked_and_ignored() -> None:
    control = FakeControlApiClient(_context())
    processor, handler, connections = _processor(control)

    result = processor.process(_body(messageType="OtherMessage"))

    assert result.decision == MessageDecision.ACK
    assert control.requested_tenant_keys == []
    assert handler.envelopes == []
    assert connections == []


def test_invalid_json_is_acked_after_logging(caplog) -> None:
    control = FakeControlApiClient(_context())
    processor, _handler, _connections = _processor(control)

    result = processor.process(b"{")

    assert result.decision == MessageDecision.ACK
    assert "invalid scheduled message JSON" in caplog.text


def test_worker_context_is_requested_using_tenant_key_and_connection_is_used() -> None:
    context = _context(
        connection_string="Server=mysql;Database=tenant;User Id=ape;Password=secret;"
    )
    control = FakeControlApiClient(context)
    processor, handler, connections = _processor(control)

    result = processor.process(_body())

    assert result.decision == MessageDecision.ACK
    assert control.requested_tenant_keys == ["bite-demo"]
    assert connections == [context.tenant_database_connection_string]
    assert handler.envelopes[0].payload["lookback_days"] == 28


def test_tenant_without_email_campaigns_module_is_skipped_and_acked() -> None:
    control = FakeControlApiClient(_context(modules=["sample"]))
    processor, handler, connections = _processor(control)

    result = processor.process(_body())

    assert result.decision == MessageDecision.ACK
    assert handler.envelopes == []
    assert connections == []


def test_control_api_failure_nacks_without_requeue() -> None:
    control = FakeControlApiClient(error=ControlApiError("boom token-value"))
    processor, _handler, _connections = _processor(control)

    result = processor.process(_body())

    assert result.decision == MessageDecision.NACK_WITHOUT_REQUEUE


def test_database_connection_failure_nacks_without_requeue() -> None:
    control = FakeControlApiClient(_context())
    processor, _handler, _connections = _processor(
        control,
        verifier=lambda session_factory: (_ for _ in ()).throw(RuntimeError("db failed")),
    )

    result = processor.process(_body())

    assert result.decision == MessageDecision.NACK_WITHOUT_REQUEUE


def test_invalid_lookback_days_falls_back_to_default() -> None:
    control = FakeControlApiClient(_context())
    processor, handler, _connections = _processor(control)

    result = processor.process(_body(payload={"lookbackDays": "bad"}))

    assert result.decision == MessageDecision.ACK
    assert handler.envelopes[0].payload["lookback_days"] is None


def test_sync_failure_nacks_without_requeue() -> None:
    control = FakeControlApiClient(_context())
    handler = RecordingSyncHandler()
    handler.raise_on_handle = True
    processor, _handler, _connections = _processor(control, handler)

    result = processor.process(_body())

    assert result.decision == MessageDecision.NACK_WITHOUT_REQUEUE


def test_connection_string_is_not_logged(caplog) -> None:
    connection_string = "Server=mysql;Database=tenant;User Id=ape;Password=super-secret;"
    control = FakeControlApiClient(_context(connection_string=connection_string))
    processor, _handler, _connections = _processor(
        control,
        verifier=lambda session_factory: (_ for _ in ()).throw(RuntimeError("db failed")),
    )

    processor.process(_body())

    assert connection_string not in caplog.text
    assert "super-secret" not in caplog.text
