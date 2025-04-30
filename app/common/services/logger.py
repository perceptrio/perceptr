import logging
import threading
import traceback
from contextlib import contextmanager
from typing import Any, Iterator, Optional

from pythonjsonlogger import jsonlogger


class ContextLogger:
    _instance = None
    _lock = threading.Lock()

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
        formatter = jsonlogger.JsonFormatter(
            fmt="%(asctime)s %(levelname)s %(name)s %(context)s %(message)s %(stack_trace)s"
        )
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)

        # Thread-local storage for context
        self._context = threading.local()
        self._context.data = {}

    def set_context(self, **kwargs: Any) -> None:
        """Add key-value pairs to the current context"""
        self._context.data.update(kwargs)

    def clear_context(self) -> None:
        """Clear all context data"""
        self._context.data = {}

    @contextmanager
    def context(self, **kwargs: Any) -> Iterator[None]:
        """Temporary context manager that automatically cleans up"""
        old_context = self._context.data.copy()
        self.set_context(**kwargs)
        try:
            yield
        finally:
            self._context.data = old_context

    def _log(
        self,
        level: int,
        message: str,
        exc_info: Optional[Exception] = None,
        **kwargs: Any,
    ) -> None:
        try:
            context = self._context.data.copy()
        except AttributeError:
            # Initialize data if it doesn't exist
            self._context.data = {}
            context = {}

        context.update(kwargs)

        # Convert context to a JSON-friendly format
        context_dict = {k: str(v) for k, v in context.items()}

        # Add stack trace if exception info is provided
        extra = {
            "context": context_dict,
        }

        if exc_info:
            extra["stack_trace"] = "".join(
                traceback.format_exception(
                    type(exc_info), exc_info, exc_info.__traceback__
                )
            )

        self.logger.log(
            level, message, extra=extra, exc_info=exc_info if exc_info else None
        )

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
