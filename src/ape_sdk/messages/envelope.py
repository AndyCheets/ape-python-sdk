from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from ape_sdk.common.ids import new_id
from ape_sdk.common.time import utc_now


class MessageEnvelope(BaseModel):
    message_id: str = Field(default_factory=new_id)
    message_type: str
    correlation_id: str = Field(default_factory=new_id)
    causation_id: str | None = None
    occurred_at_utc: datetime = Field(default_factory=utc_now)
    payload: dict[str, Any]

    @classmethod
    def wrap(
        cls,
        message: BaseModel,
        *,
        correlation_id: str | None = None,
        causation_id: str | None = None,
    ) -> "MessageEnvelope":
        return cls(
            message_type=message.__class__.__name__,
            correlation_id=correlation_id or new_id(),
            causation_id=causation_id,
            payload=message.model_dump(mode="json"),
        )

