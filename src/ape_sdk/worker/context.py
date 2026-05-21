from dataclasses import dataclass

from ape_sdk.messages.envelope import MessageEnvelope
from ape_sdk.tenant.context import TenantWorkerContext
from ape_sdk.tenant.database import TenantDatabase


@dataclass(frozen=True)
class WorkerCommandContext:
    envelope: MessageEnvelope
    tenant_context: TenantWorkerContext
    tenant_database: TenantDatabase
