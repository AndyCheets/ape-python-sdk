from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MessageEnvelope(BaseModel):
    """Standard APE message envelope using snake_case internally and camelCase JSON."""

    model_config = ConfigDict(populate_by_name=True)

    message_id: str = Field(alias="messageId")
    correlation_id: str = Field(alias="correlationId")
    causation_id: str | None = Field(default=None, alias="causationId")
    tenant_key: str = Field(alias="tenantKey")
    source: str | None = None
    message_type: str = Field(alias="messageType")
    schema_version: int = Field(default=1, alias="schemaVersion")
    created_at_utc: datetime = Field(alias="createdAtUtc")
    metadata: dict[str, Any] = Field(default_factory=dict)
    payload: dict[str, Any]

    @field_validator("message_id", "correlation_id", "tenant_key", "message_type")
    @classmethod
    def required_text_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("required envelope text fields must not be blank")
        return value

    @classmethod
    def new_event(
        cls,
        *,
        source_command: "MessageEnvelope",
        source: str,
        message_type: str,
        payload: dict[str, Any],
    ) -> "MessageEnvelope":
        return cls(
            messageId=str(uuid4()),
            correlationId=source_command.correlation_id,
            causationId=source_command.message_id,
            tenantKey=source_command.tenant_key,
            source=source,
            messageType=message_type,
            schemaVersion=1,
            createdAtUtc=datetime.now(timezone.utc),
            metadata={
                "sourceCommandMessageId": source_command.message_id,
                "sourceCommandMessageType": source_command.message_type,
            },
            payload=payload,
        )

    @classmethod
    def wrap_payload(
        cls,
        *,
        tenant_key: str,
        source: str,
        message_type: str,
        payload: dict[str, Any],
        correlation_id: str | None = None,
        causation_id: str | None = None,
    ) -> "MessageEnvelope":
        return cls(
            messageId=str(uuid4()),
            correlationId=correlation_id or str(uuid4()),
            causationId=causation_id,
            tenantKey=tenant_key,
            source=source,
            messageType=message_type,
            schemaVersion=1,
            createdAtUtc=datetime.now(timezone.utc),
            metadata={},
            payload=payload,
        )

    def to_json_bytes(self) -> bytes:
        return self.model_dump_json(by_alias=True).encode("utf-8")

