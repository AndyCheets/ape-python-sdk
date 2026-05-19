import json
import logging
from collections.abc import Protocol
from dataclasses import dataclass
from enum import Enum

from pydantic import ValidationError

from ape_sdk.common.logging import sanitise_error_message
from ape_sdk.control.client import ControlApiClient
from ape_sdk.messages.envelope import MessageEnvelope
from ape_sdk.tenant.database import TenantDatabase
from ape_sdk.worker.context import WorkerCommandContext
from ape_sdk.worker.result import WorkerTaskResult
from ape_sdk.worker.settings import Settings

logger = logging.getLogger(__name__)


class EventPublisher(Protocol):
    def publish(self, envelope: MessageEnvelope) -> None:
        ...


class TaskHandler(Protocol):
    def handle(self, command: WorkerCommandContext) -> WorkerTaskResult:
        ...


class MessageDecision(Enum):
    ACK = "ack"
    NACK_WITHOUT_REQUEUE = "nack_without_requeue"


@dataclass(frozen=True)
class MessageProcessingResult:
    decision: MessageDecision


class WorkerCommandProcessor:
    def __init__(
        self,
        *,
        settings: Settings,
        control_api_client: ControlApiClient,
        task_handler: TaskHandler,
        event_publisher: EventPublisher,
    ) -> None:
        self.settings = settings
        self.control_api_client = control_api_client
        self.task_handler = task_handler
        self.event_publisher = event_publisher

    def process(self, body: bytes) -> MessageProcessingResult:
        envelope = self._parse_envelope(body)
        if envelope is None:
            return MessageProcessingResult(MessageDecision.ACK)

        if envelope.message_type != self.settings.worker.command_message_type:
            logger.warning(
                "unsupported command message type tenant_key=%s message_id=%s correlation_id=%s "
                "message_type=%s expected_message_type=%s",
                envelope.tenant_key,
                envelope.message_id,
                envelope.correlation_id,
                envelope.message_type,
                self.settings.worker.command_message_type,
            )
            return MessageProcessingResult(MessageDecision.ACK)

        try:
            tenant_context = self.control_api_client.get_worker_context(envelope.tenant_key)
            command = WorkerCommandContext(
                envelope=envelope,
                tenant_context=tenant_context,
                tenant_database=TenantDatabase(tenant_context),
            )
            result = self.task_handler.handle(command)
        except Exception as exc:
            logger.error(
                "command processing failed tenant_key=%s message_id=%s correlation_id=%s "
                "message_type=%s error_type=%s error_message=%s",
                envelope.tenant_key,
                envelope.message_id,
                envelope.correlation_id,
                envelope.message_type,
                type(exc).__name__,
                sanitise_error_message(str(exc)),
            )
            self._try_publish_failed_event(envelope, exc)
            return MessageProcessingResult(MessageDecision.NACK_WITHOUT_REQUEUE)

        try:
            self._publish_completed_event(envelope, result)
        except Exception as exc:
            logger.error(
                "completed event publish failed tenant_key=%s message_id=%s correlation_id=%s "
                "message_type=%s error_type=%s error_message=%s",
                envelope.tenant_key,
                envelope.message_id,
                envelope.correlation_id,
                envelope.message_type,
                type(exc).__name__,
                sanitise_error_message(str(exc)),
            )
            return MessageProcessingResult(MessageDecision.NACK_WITHOUT_REQUEUE)

        logger.info(
            "command processed tenant_key=%s message_id=%s correlation_id=%s message_type=%s",
            envelope.tenant_key,
            envelope.message_id,
            envelope.correlation_id,
            envelope.message_type,
        )
        return MessageProcessingResult(MessageDecision.ACK)

    def _parse_envelope(self, body: bytes) -> MessageEnvelope | None:
        try:
            payload = json.loads(body.decode("utf-8"))
            return MessageEnvelope.model_validate(payload)
        except json.JSONDecodeError:
            logger.error("invalid command JSON")
            return None
        except ValidationError:
            logger.error("invalid command envelope")
            return None

    def _publish_completed_event(
        self,
        source_command: MessageEnvelope,
        result: WorkerTaskResult,
    ) -> None:
        envelope = MessageEnvelope.new_event(
            source_command=source_command,
            source=self.settings.app.service_name,
            message_type=self.settings.worker.completed_event_message_type,
            payload=result.payload,
        )
        self.event_publisher.publish(envelope)

    def _try_publish_failed_event(self, source_command: MessageEnvelope, exc: Exception) -> None:
        envelope = MessageEnvelope.new_event(
            source_command=source_command,
            source=self.settings.app.service_name,
            message_type=self.settings.worker.failed_event_message_type,
            payload={
                "errorType": type(exc).__name__,
                "errorMessage": sanitise_error_message(str(exc)),
            },
        )
        try:
            self.event_publisher.publish(envelope)
        except Exception as publish_exc:
            logger.error(
                "failed event publish failed tenant_key=%s message_id=%s correlation_id=%s "
                "message_type=%s error_type=%s error_message=%s",
                source_command.tenant_key,
                source_command.message_id,
                source_command.correlation_id,
                source_command.message_type,
                type(publish_exc).__name__,
                sanitise_error_message(str(publish_exc)),
            )
