import logging
import re
from typing import Final

_LOG_FORMAT: Final = "%(asctime)s %(levelname)s [%(service_name)s] %(name)s - %(message)s"
_NOISY_LOGGERS: Final = ("pika", "httpx", "urllib3")
_HANDLER_ATTR: Final = "_ape_stream_handler"
_SECRET_PATTERNS: Final = (
    re.compile(r"(?i)(api[_-]?key|access[_-]?token|token|password|authorization)=([^\s&;]+)"),
    re.compile(r"(?i)(Bearer|Basic)\s+[^\s]+"),
    re.compile(r"(?i)(Server|Host|Database|User Id|Uid|User|Password|Pwd)=([^;]+)"),
)


class ServiceNameFilter(logging.Filter):
    def __init__(self, service_name: str) -> None:
        super().__init__()
        self.service_name = service_name

    def filter(self, record: logging.LogRecord) -> bool:
        record.service_name = self.service_name
        return True


def _log_level(level: str) -> int:
    resolved = logging.getLevelName(level.upper())
    if isinstance(resolved, int):
        return resolved
    return logging.INFO


def sanitise_error_message(message: str) -> str:
    safe_message = message
    for pattern in _SECRET_PATTERNS:
        safe_message = pattern.sub(_redact_match, safe_message)
    return safe_message[:500]


def _redact_match(match: re.Match[str]) -> str:
    if match.lastindex and match.lastindex >= 2:
        return f"{match.group(1)}=<redacted>"
    return "<redacted>"


def _ape_handler(root_logger: logging.Logger) -> logging.Handler | None:
    for handler in root_logger.handlers:
        if getattr(handler, _HANDLER_ATTR, False):
            return handler
    return None


def configure_logging(service_name: str, log_level: str = "INFO") -> None:
    level = _log_level(log_level)
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    handler = _ape_handler(root_logger)
    if handler is None:
        handler = logging.StreamHandler()
        setattr(handler, _HANDLER_ATTR, True)
        root_logger.addHandler(handler)

    handler.setLevel(logging.NOTSET)
    handler.setFormatter(logging.Formatter(_LOG_FORMAT))
    handler.filters.clear()
    handler.addFilter(ServiceNameFilter(service_name))

    for logger_name in _NOISY_LOGGERS:
        logging.getLogger(logger_name).setLevel(logging.WARNING)
