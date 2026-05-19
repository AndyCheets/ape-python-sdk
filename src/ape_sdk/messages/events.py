from typing import Any

from pydantic import BaseModel


class ExampleTaskCompleted(BaseModel):
    """Example completed event payload for services generated from the worker template."""

    result: dict[str, Any]


class ExampleTaskFailed(BaseModel):
    """Example failed event payload for services generated from the worker template."""

    error_type: str
    error_message: str
