import logging
import threading
from contextlib import contextmanager

class ContextLogger:
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialize()
            return cls._instance
    
    def _initialize(self):
        self.logger = logging.getLogger('ContextLogger')
        self.logger.setLevel(logging.DEBUG)
        
        # Create console handler with formatting
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(context)s - %(message)s'
        )
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)
        
        # Thread-local storage for context
        self._context = threading.local()
        self._context.data = {}

    def set_context(self, **kwargs):
        """Add key-value pairs to the current context"""
        self._context.data.update(kwargs)
    
    def clear_context(self):
        """Clear all context data"""
        self._context.data = {}
    
    @contextmanager
    def context(self, **kwargs):
        """Temporary context manager that automatically cleans up"""
        old_context = self._context.data.copy()
        self.set_context(**kwargs)
        try:
            yield
        finally:
            self._context.data = old_context
    
    def _log(self, level: int, message: str, **kwargs):
        try:
            context = self._context.data.copy()
        except AttributeError:
            # Initialize data if it doesn't exist
            self._context.data = {}
            context = {}
        context.update(kwargs)
        context_str = ' '.join(f'{k}={v}' for k, v in context.items())
        extra = {'context': context_str if context_str else 'no_context'}
        self.logger.log(level, message, extra=extra)
    
    def debug(self, message: str, **kwargs):
        self._log(logging.DEBUG, message, **kwargs)
    
    def info(self, message: str, **kwargs):
        self._log(logging.INFO, message, **kwargs)
    
    def warning(self, message: str, **kwargs):
        self._log(logging.WARNING, message, **kwargs)
    
    def error(self, message: str, **kwargs):
        self._log(logging.ERROR, message, **kwargs)
    
    def critical(self, message: str, **kwargs):
        self._log(logging.CRITICAL, message, **kwargs)

# Create a singleton instance
logger = ContextLogger()