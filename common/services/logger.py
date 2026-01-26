import logging
import threading
import traceback
from typing import Any, Optional

from pythonjsonlogger import jsonlogger
from settings import settings

# Disable FastAPI's default error logging
if settings.LOG_STYLE == "json":
    uvicorn_access = logging.getLogger("uvicorn.access")
    uvicorn_access.disabled = True
    uvicorn_error = logging.getLogger("uvicorn.error")
    uvicorn_error.disabled = True


class ContextLogger:
    _instance = None
    _lock = threading.Lock()
    _context = {}

    def __new__(cls) -> "ContextLogger":
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialize()
            return cls._instance

    def _initialize(self) -> None:
        self.logger = logging.getLogger("ContextLogger")
        self.logger.setLevel(logging.DEBUG)

        # Create JSON handler with formatting
        handler = logging.StreamHandler()
        formatter = (
            jsonlogger.JsonFormatter(
                fmt="%(asctime)s %(levelname)s %(message)s %(stack_trace)s"
            )
            if settings.LOG_STYLE == "json"
            else logging.Formatter(fmt="%(asctime)s %(levelname)s %(message)s")
        )
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)

    def set_context(self, **kwargs: Any) -> None:
        """Add key-value pairs to the current context"""
        self._context.update(kwargs)

    def clear_context(self) -> None:
        """Clear all context data"""
        self._context = {}

    def _log(
        self,
        level: int,
        message: str,
        exc_info: Optional[Exception] = None,
        **kwargs: Any,
    ) -> None:
        context = self._context.copy()

        context.update(kwargs)

        # Convert context to a JSON-friendly format
        extra = {k: str(v) for k, v in context.items()}

        # Add stack trace if exception info is provided
        if exc_info and settings.LOG_STYLE == "json":
            extra["stack_trace"] = "".join(
                traceback.format_exception(
                    type(exc_info), exc_info, exc_info.__traceback__
                )
            )
        if settings.LOG_STYLE != "json":
            message = f"{message} {','.join(f'{k}: {v}' for k, v in extra.items())}"
            if exc_info:
                print(
                    "".join(
                        traceback.format_exception(
                            type(exc_info), exc_info, exc_info.__traceback__
                        )
                    )
                )
        self.logger.log(level, message, extra=extra)

    def debug(
        self, message: str, exc_info: Optional[Exception] = None, **kwargs: Any
    ) -> None:
        self._log(logging.DEBUG, message, exc_info, **kwargs)

    def info(
        self, message: str, exc_info: Optional[Exception] = None, **kwargs: Any
    ) -> None:
        self._log(logging.INFO, message, exc_info, **kwargs)

    def warning(
        self, message: str, exc_info: Optional[Exception] = None, **kwargs: Any
    ) -> None:
        self._log(logging.WARNING, message, exc_info, **kwargs)

    def error(
        self, message: str, exc_info: Optional[Exception] = None, **kwargs: Any
    ) -> None:
        self._log(logging.ERROR, message, exc_info, **kwargs)

    def critical(
        self, message: str, exc_info: Optional[Exception] = None, **kwargs: Any
    ) -> None:
        self._log(logging.CRITICAL, message, exc_info, **kwargs)


# Create a singleton instance
logger = ContextLogger()
