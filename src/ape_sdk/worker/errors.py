class ConfigurationError(RuntimeError):
    """Raised when required startup configuration is missing or invalid."""


class ControlApiError(RuntimeError):
    """Raised when tenant worker context cannot be resolved."""


class MessagePublishError(RuntimeError):
    """Raised when an event cannot be published to RabbitMQ."""
