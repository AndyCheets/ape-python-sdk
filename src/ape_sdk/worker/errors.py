from ape_sdk.control.errors import ControlApiError as _ControlApiError

ControlApiError = _ControlApiError


class ConfigurationError(RuntimeError):
    """Raised when required startup configuration is missing or invalid."""


class MessagePublishError(RuntimeError):
    """Raised when an event cannot be published to RabbitMQ."""
