from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class WorkerTaskResult:
    payload: dict[str, Any] = field(default_factory=dict)
