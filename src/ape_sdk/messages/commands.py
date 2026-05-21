from typing import Any

from pydantic import BaseModel, Field


class ExampleCommand(BaseModel):
    """Example command payload for services generated from the worker template."""

    requested_by: str | None = Field(default=None, alias="requestedBy")
    parameters: dict[str, Any] = Field(default_factory=dict)
