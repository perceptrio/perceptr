import logging
import json
from datetime import datetime
from typing import Any, Dict, Union

class StructuredLogger(logging.Logger):
    def log_json(self, level: int, message: str, extra: Dict[str, Any] = None, *args, **kwargs):
        log_entry = {
            "level": logging.getLevelName(level).lower(),
            "time": datetime.utcnow().isoformat() + 'Z',
            "message": message
        }
        if extra and isinstance(extra, dict):
            if extra and isinstance(extra, dict) and "data" in extra:
                log_entry.update(extra.get("data"))
            else:
                log_entry.update(extra)

        formatted_message = json.dumps(log_entry, indent=2)
        super().log(level, formatted_message, *args, **kwargs)

    def info(self, message: str, extra: Dict[str, Any] = None, *args, **kwargs):
        self.log_json(logging.INFO, message, extra, *args, **kwargs)

    def error(self, message: str, extra: Dict[str, Any] = None, *args, **kwargs):
        self.log_json(logging.ERROR, message, extra, *args, **kwargs)

    def warning(self, message: str, extra: Dict[str, Any] = None, *args, **kwargs):
        self.log_json(logging.WARNING, message, extra, *args, **kwargs)

class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        # The record is already in JSON format, so just return it
        return record.getMessage()

def get_module_logger(mod_name: str) -> logging.Logger:
    """Configure and return a structured logger instance"""
    logging.setLoggerClass(StructuredLogger)
    logger = logging.getLogger(mod_name)
    
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
        logger.propagate = False
    
    return logger