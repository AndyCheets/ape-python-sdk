import os
from collections.abc import Mapping
from dataclasses import dataclass

from ape_sdk.worker.errors import ConfigurationError


@dataclass(frozen=True)
class AppSettings:
    environment: str
    service_name: str
    log_level: str


@dataclass(frozen=True)
class ControlApiSettings:
    base_url: str
    token: str
    timeout_seconds: float


@dataclass(frozen=True)
class RabbitMqSettings:
    host: str
    port: int
    username: str
    password: str
    vhost: str
    command_exchange: str
    event_exchange: str
    queue_name: str
    binding_keys: tuple[str, ...]


@dataclass(frozen=True)
class WorkerSettings:
    command_message_type: str
    completed_event_message_type: str
    failed_event_message_type: str


@dataclass(frozen=True)
class Settings:
    app: AppSettings
    control_api: ControlApiSettings
    rabbitmq: RabbitMqSettings
    worker: WorkerSettings

    def safe_startup_log_fields(self) -> dict[str, object]:
        return {
            "service_name": self.app.service_name,
            "environment": self.app.environment,
            "rabbitmq_host": self.rabbitmq.host,
            "rabbitmq_port": self.rabbitmq.port,
            "rabbitmq_vhost": self.rabbitmq.vhost,
            "command_exchange": self.rabbitmq.command_exchange,
            "event_exchange": self.rabbitmq.event_exchange,
            "queue_name": self.rabbitmq.queue_name,
            "binding_keys": list(self.rabbitmq.binding_keys),
            "command_message_type": self.worker.command_message_type,
            "completed_event_message_type": self.worker.completed_event_message_type,
            "failed_event_message_type": self.worker.failed_event_message_type,
            "control_api_base_url": self.control_api.base_url,
        }


def load_worker_settings(environ: Mapping[str, str] | None = None) -> Settings:
    values = environ or os.environ
    return Settings(
        app=AppSettings(
            environment=_optional(values, "APE_ENVIRONMENT", "Development"),
            service_name=_optional(values, "APE_SERVICE_NAME", "ape-worker-template"),
            log_level=_optional(values, "LOG_LEVEL", "INFO"),
        ),
        control_api=ControlApiSettings(
            base_url=_required(values, "APE_CONTROL_API_BASE_URL"),
            token=_required(values, "APE_CONTROL_API_TOKEN"),
            timeout_seconds=_float(values, "APE_CONTROL_API_TIMEOUT_SECONDS", 10.0),
        ),
        rabbitmq=RabbitMqSettings(
            host=_required(values, "RABBITMQ_HOST"),
            port=_int(values, "RABBITMQ_PORT", 5672),
            username=_required(values, "RABBITMQ_USERNAME"),
            password=_required(values, "RABBITMQ_PASSWORD"),
            vhost=_required(values, "RABBITMQ_VHOST"),
            command_exchange=_required(values, "RABBITMQ_COMMAND_EXCHANGE"),
            event_exchange=_required(values, "RABBITMQ_EVENT_EXCHANGE"),
            queue_name=_required(values, "RABBITMQ_QUEUE_NAME"),
            binding_keys=_binding_keys(_required(values, "RABBITMQ_BINDING_KEYS")),
        ),
        worker=WorkerSettings(
            command_message_type=_required(values, "WORKER_COMMAND_MESSAGE_TYPE"),
            completed_event_message_type=_required(values, "WORKER_COMPLETED_EVENT_MESSAGE_TYPE"),
            failed_event_message_type=_required(values, "WORKER_FAILED_EVENT_MESSAGE_TYPE"),
        ),
    )


def _optional(values: Mapping[str, str], name: str, default: str) -> str:
    value = values.get(name, "").strip()
    return value or default


def _required(values: Mapping[str, str], name: str) -> str:
    value = values.get(name, "").strip()
    if not value:
        raise ConfigurationError(f"Missing required environment variable: {name}")
    return value


def _int(values: Mapping[str, str], name: str, default: int) -> int:
    raw_value = _optional(values, name, str(default))
    try:
        return int(raw_value)
    except ValueError as exc:
        raise ConfigurationError(f"Environment variable {name} must be an integer") from exc


def _float(values: Mapping[str, str], name: str, default: float) -> float:
    raw_value = _optional(values, name, str(default))
    try:
        return float(raw_value)
    except ValueError as exc:
        raise ConfigurationError(f"Environment variable {name} must be a number") from exc


def _binding_keys(value: str) -> tuple[str, ...]:
    keys = tuple(key.strip() for key in value.split(",") if key.strip())
    if not keys:
        raise ConfigurationError("Environment variable RABBITMQ_BINDING_KEYS must not be empty")
    return keys
