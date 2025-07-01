"""
Comprehensive Logging Configuration System for AST-Grep MCP Server.

This module provides enterprise-grade logging capabilities including:
- Centralized logging configuration management
- Structured logging with consistent formatting
- Environment-based configuration
- Sensitive data filtering and protection
- Error context enrichment and correlation
- Log rotation and file management
- Performance-aware logging with conditional verbosity
"""

import logging
import logging.handlers
import os
import sys
import json
import time
import traceback
import threading
import re
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Set, Union, Callable
from pathlib import Path
from dataclasses import dataclass, field
from contextlib import contextmanager
from functools import wraps
import uuid


@dataclass
class LoggingConfig:
    """Comprehensive logging configuration."""
    
    # Basic settings
    level: str = "INFO"
    format_type: str = "structured"  # "structured", "standard", "json"
    
    # File logging
    enable_file_logging: bool = True
    log_file: Optional[str] = None
    log_dir: str = "logs"
    max_file_size: int = 10 * 1024 * 1024  # 10MB
    backup_count: int = 5
    
    # Console logging
    enable_console_logging: bool = True
    console_level: Optional[str] = None  # Uses main level if None
    
    # Advanced features
    enable_correlation_ids: bool = True
    enable_sensitive_filtering: bool = True
    enable_performance_logging: bool = True
    enable_context_enrichment: bool = True
    
    # Performance settings
    async_logging: bool = True
    buffer_size: int = 1000
    flush_interval: float = 1.0  # seconds
    
    # Filtering and security
    sensitive_patterns: Set[str] = field(default_factory=lambda: {
        r'\b[A-Za-z0-9]{20,}\b',  # API keys (generic long alphanumeric)
        r'password["\s]*[:=]["\s]*[^"\s]+',  # Password fields
        r'token["\s]*[:=]["\s]*[^"\s]+',  # Token fields
        r'secret["\s]*[:=]["\s]*[^"\s]+',  # Secret fields
        r'key["\s]*[:=]["\s]*[^"\s]+',  # Key fields
        r'\b\d{4}-\d{4}-\d{4}-\d{4}\b',  # Credit card patterns
        r'\b\d{3}-\d{2}-\d{4}\b',  # SSN patterns
    })
    
    # Module-specific logging levels
    module_levels: Dict[str, str] = field(default_factory=lambda: {
        "mcp": "WARNING",
        "asyncio": "WARNING",
        "urllib3": "WARNING",
        "requests": "WARNING"
    })
    
    @classmethod
    def from_environment(cls) -> 'LoggingConfig':
        """Create configuration from environment variables."""
        return cls(
            level=os.getenv("AST_GREP_LOG_LEVEL", "INFO").upper(),
            format_type=os.getenv("AST_GREP_LOG_FORMAT", "structured").lower(),
            enable_file_logging=os.getenv("AST_GREP_LOG_FILE_ENABLED", "true").lower() == "true",
            log_file=os.getenv("AST_GREP_LOG_FILE"),
            log_dir=os.getenv("AST_GREP_LOG_DIR", "logs"),
            max_file_size=int(os.getenv("AST_GREP_LOG_MAX_SIZE", str(10 * 1024 * 1024))),
            backup_count=int(os.getenv("AST_GREP_LOG_BACKUP_COUNT", "5")),
            enable_console_logging=os.getenv("AST_GREP_LOG_CONSOLE_ENABLED", "true").lower() == "true",
            console_level=os.getenv("AST_GREP_LOG_CONSOLE_LEVEL"),
            enable_correlation_ids=os.getenv("AST_GREP_LOG_CORRELATION_IDS", "true").lower() == "true",
            enable_sensitive_filtering=os.getenv("AST_GREP_LOG_FILTER_SENSITIVE", "true").lower() == "true",
            enable_performance_logging=os.getenv("AST_GREP_LOG_PERFORMANCE", "true").lower() == "true",
            enable_context_enrichment=os.getenv("AST_GREP_LOG_CONTEXT_ENRICHMENT", "true").lower() == "true",
            async_logging=os.getenv("AST_GREP_LOG_ASYNC", "true").lower() == "true",
            buffer_size=int(os.getenv("AST_GREP_LOG_BUFFER_SIZE", "1000")),
            flush_interval=float(os.getenv("AST_GREP_LOG_FLUSH_INTERVAL", "1.0"))
        )


class SensitiveDataFilter:
    """Filters sensitive data from log messages."""
    
    def __init__(self, patterns: Set[str]):
        self.patterns = [re.compile(pattern, re.IGNORECASE) for pattern in patterns]
        self.replacement = "[REDACTED]"
    
    def filter_message(self, message: str) -> str:
        """Filter sensitive data from a log message."""
        filtered = message
        for pattern in self.patterns:
            filtered = pattern.sub(self.replacement, filtered)
        return filtered
    
    def filter_record(self, record: logging.LogRecord) -> logging.LogRecord:
        """Filter sensitive data from a log record."""
        if hasattr(record, 'msg') and isinstance(record.msg, str):
            record.msg = self.filter_message(record.msg)
        
        # Filter arguments
        if hasattr(record, 'args') and record.args:
            filtered_args = []
            for arg in record.args:
                if isinstance(arg, str):
                    filtered_args.append(self.filter_message(arg))
                else:
                    filtered_args.append(arg)
            record.args = tuple(filtered_args)
        
        return record


class CorrelationContextManager:
    """Manages correlation IDs for request tracing."""
    
    def __init__(self):
        self._local = threading.local()
    
    def get_correlation_id(self) -> Optional[str]:
        """Get current correlation ID."""
        return getattr(self._local, 'correlation_id', None)
    
    def set_correlation_id(self, correlation_id: str) -> None:
        """Set correlation ID for current context."""
        self._local.correlation_id = correlation_id
    
    def generate_correlation_id(self) -> str:
        """Generate a new correlation ID."""
        return str(uuid.uuid4())
    
    @contextmanager
    def correlation_context(self, correlation_id: Optional[str] = None):
        """Context manager for correlation ID scope."""
        if correlation_id is None:
            correlation_id = self.generate_correlation_id()
        
        old_id = self.get_correlation_id()
        self.set_correlation_id(correlation_id)
        try:
            yield correlation_id
        finally:
            if old_id is not None:
                self.set_correlation_id(old_id)
            else:
                delattr(self._local, 'correlation_id')


class ContextEnrichmentFilter(logging.Filter):
    """Enriches log records with additional context."""
    
    def __init__(self, correlation_manager: CorrelationContextManager):
        super().__init__()
        self.correlation_manager = correlation_manager
    
    def filter(self, record: logging.LogRecord) -> bool:
        """Enrich the log record with context information."""
        # Add correlation ID
        record.correlation_id = self.correlation_manager.get_correlation_id() or "none"
        
        # Add process information
        record.process_id = os.getpid()
        record.thread_id = threading.get_ident()
        
        # Add timestamp in ISO format
        record.iso_timestamp = datetime.fromtimestamp(record.created).isoformat()
        
        # Add module path for better organization
        record.module_path = getattr(record, 'pathname', 'unknown')
        
        return True


class StructuredFormatter(logging.Formatter):
    """Structured JSON formatter for logs."""
    
    def __init__(self, include_extra: bool = True):
        super().__init__()
        self.include_extra = include_extra
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as structured JSON."""
        log_data = {
            "timestamp": getattr(record, 'iso_timestamp', datetime.fromtimestamp(record.created).isoformat()),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "correlation_id": getattr(record, 'correlation_id', 'none'),
            "process_id": getattr(record, 'process_id', os.getpid()),
            "thread_id": getattr(record, 'thread_id', threading.get_ident())
        }
        
        # Add exception information
        if record.exc_info:
            log_data["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else None,
                "message": str(record.exc_info[1]) if record.exc_info[1] else None,
                "traceback": self.formatException(record.exc_info) if record.exc_info else None
            }
        
        # Add extra fields if enabled
        if self.include_extra:
            for key, value in record.__dict__.items():
                if key not in log_data and not key.startswith('_') and key not in [
                    'name', 'msg', 'args', 'levelname', 'levelno', 'pathname',
                    'filename', 'module', 'exc_info', 'exc_text', 'stack_info',
                    'lineno', 'funcName', 'created', 'msecs', 'relativeCreated',
                    'thread', 'threadName', 'processName', 'process', 'message'
                ]:
                    try:
                        # Only include JSON-serializable values
                        json.dumps(value)
                        log_data[key] = value
                    except (TypeError, ValueError):
                        log_data[key] = str(value)
        
        return json.dumps(log_data, separators=(',', ':'))


class SafeFormatter(logging.Formatter):
    """Formatter that handles missing log record fields gracefully."""
    
    def format(self, record: logging.LogRecord) -> str:
        """Format with safe handling of missing fields."""
        # Ensure required fields exist with fallbacks
        if not hasattr(record, 'iso_timestamp'):
            record.iso_timestamp = datetime.fromtimestamp(record.created).isoformat()
        if not hasattr(record, 'correlation_id'):
            record.correlation_id = 'none'
        
        return super().format(record)


class PerformanceAwareFormatter(logging.Formatter):
    """Formatter that adjusts verbosity based on performance impact."""
    
    def __init__(self, detailed_format: str, simple_format: str, performance_threshold: float = 1000.0):
        super().__init__()
        self.detailed_formatter = SafeFormatter(detailed_format)
        self.simple_formatter = SafeFormatter(simple_format)
        self.performance_threshold = performance_threshold
        self.recent_log_times = []
        self.lock = threading.Lock()
    
    def format(self, record: logging.LogRecord) -> str:
        """Format with performance-aware verbosity."""
        current_time = time.time()
        
        with self.lock:
            # Clean old entries (keep last second)
            cutoff_time = current_time - 1.0
            self.recent_log_times = [t for t in self.recent_log_times if t > cutoff_time]
            
            # Add current log time
            self.recent_log_times.append(current_time)
            
            # Calculate logs per second
            logs_per_second = len(self.recent_log_times)
        
        # Use simple format if logging rate is high
        if logs_per_second > self.performance_threshold / 1000:
            return self.simple_formatter.format(record)
        else:
            return self.detailed_formatter.format(record)


class AsyncLogHandler(logging.Handler):
    """Asynchronous log handler for high-performance logging."""
    
    def __init__(self, target_handler: logging.Handler, buffer_size: int = 1000, flush_interval: float = 1.0):
        super().__init__()
        self.target_handler = target_handler
        self.buffer_size = buffer_size
        self.flush_interval = flush_interval
        self.buffer = []
        self.buffer_lock = threading.Lock()
        self.flush_thread = None
        self.shutdown_event = threading.Event()
        self.start_flush_thread()
    
    def start_flush_thread(self):
        """Start the background flush thread."""
        if self.flush_thread is None or not self.flush_thread.is_alive():
            self.shutdown_event.clear()
            self.flush_thread = threading.Thread(target=self._flush_worker, daemon=True)
            self.flush_thread.start()
    
    def _flush_worker(self):
        """Background worker to flush log buffer."""
        while not self.shutdown_event.is_set():
            try:
                if self.shutdown_event.wait(self.flush_interval):
                    break  # Shutdown requested
                self._flush_buffer()
            except Exception as e:
                # Avoid infinite recursion by using print
                print(f"Error in log flush worker: {e}", file=sys.stderr)
    
    def _flush_buffer(self):
        """Flush the current buffer to the target handler."""
        if not self.buffer:
            return
        
        with self.buffer_lock:
            records_to_flush = self.buffer[:]
            self.buffer.clear()
        
        for record in records_to_flush:
            try:
                self.target_handler.emit(record)
            except Exception as e:
                print(f"Error emitting log record: {e}", file=sys.stderr)
        
        try:
            self.target_handler.flush()
        except Exception as e:
            print(f"Error flushing log handler: {e}", file=sys.stderr)
    
    def emit(self, record: logging.LogRecord):
        """Add record to buffer."""
        with self.buffer_lock:
            self.buffer.append(record)
            
            # Force flush if buffer is full
            if len(self.buffer) >= self.buffer_size:
                self._flush_buffer()
    
    def flush(self):
        """Flush all pending records."""
        self._flush_buffer()
        self.target_handler.flush()
    
    def close(self):
        """Close the handler and cleanup resources."""
        self.shutdown_event.set()
        if self.flush_thread and self.flush_thread.is_alive():
            self.flush_thread.join(timeout=5.0)
        
        self._flush_buffer()  # Final flush
        self.target_handler.close()
        super().close()


class EnhancedLoggingManager:
    """Central manager for enhanced logging configuration."""
    
    def __init__(self, config: LoggingConfig):
        self.config = config
        self.correlation_manager = CorrelationContextManager()
        self.sensitive_filter = SensitiveDataFilter(config.sensitive_patterns) if config.enable_sensitive_filtering else None
        self.handlers: List[logging.Handler] = []
        self.is_configured = False
    
    def configure_logging(self) -> None:
        """Configure the logging system with enhanced features."""
        if self.is_configured:
            return
        
        # Get root logger
        root_logger = logging.getLogger()
        
        # Clear existing handlers
        root_logger.handlers.clear()
        
        # Set root level
        root_logger.setLevel(getattr(logging, self.config.level))
        
        # Configure file logging
        if self.config.enable_file_logging:
            self._setup_file_logging(root_logger)
        
        # Configure console logging
        if self.config.enable_console_logging:
            self._setup_console_logging(root_logger)
        
        # Set module-specific levels
        self._configure_module_levels()
        
        # Add global filters
        self._add_global_filters(root_logger)
        
        self.is_configured = True
    
    def _setup_file_logging(self, root_logger: logging.Logger) -> None:
        """Setup file logging with rotation."""
        log_dir = Path(self.config.log_dir)
        log_dir.mkdir(exist_ok=True)
        
        log_file = self.config.log_file or "ast_grep_mcp.log"
        log_path = log_dir / log_file
        
        # Use rotating file handler
        file_handler = logging.handlers.RotatingFileHandler(
            filename=str(log_path),
            maxBytes=self.config.max_file_size,
            backupCount=self.config.backup_count,
            encoding='utf-8'
        )
        
        # Configure formatter
        if self.config.format_type == "json":
            formatter = StructuredFormatter()
        elif self.config.format_type == "structured":
            formatter = StructuredFormatter()
        else:
            formatter = SafeFormatter(
                '%(iso_timestamp)s - %(name)s - %(levelname)s - %(correlation_id)s - %(message)s'
            )
        
        file_handler.setFormatter(formatter)
        
        # Wrap in async handler if enabled
        if self.config.async_logging:
            final_handler = AsyncLogHandler(
                file_handler, 
                buffer_size=self.config.buffer_size,
                flush_interval=self.config.flush_interval
            )
        else:
            final_handler = file_handler
        
        self.handlers.append(final_handler)
        root_logger.addHandler(final_handler)
    
    def _setup_console_logging(self, root_logger: logging.Logger) -> None:
        """Setup console logging."""
        console_handler = logging.StreamHandler(sys.stderr)
        
        console_level = self.config.console_level or self.config.level
        console_handler.setLevel(getattr(logging, console_level))
        
        # Use performance-aware formatter for console
        if self.config.enable_performance_logging:
            detailed_format = '%(iso_timestamp)s - %(name)s - %(levelname)s - %(correlation_id)s - %(message)s'
            simple_format = '%(levelname)s - %(name)s - %(message)s'
            formatter = PerformanceAwareFormatter(detailed_format, simple_format)
        else:
            formatter = SafeFormatter(
                '%(iso_timestamp)s - %(name)s - %(levelname)s - %(correlation_id)s - %(message)s'
            )
        
        console_handler.setFormatter(formatter)
        
        self.handlers.append(console_handler)
        root_logger.addHandler(console_handler)
    
    def _configure_module_levels(self) -> None:
        """Configure logging levels for specific modules."""
        for module_name, level in self.config.module_levels.items():
            logger = logging.getLogger(module_name)
            logger.setLevel(getattr(logging, level))
    
    def _add_global_filters(self, root_logger: logging.Logger) -> None:
        """Add global filters to the root logger."""
        # Add context enrichment filter
        if self.config.enable_context_enrichment:
            context_filter = ContextEnrichmentFilter(self.correlation_manager)
            root_logger.addFilter(context_filter)
        
        # Add sensitive data filter
        if self.sensitive_filter:
            class SensitiveFilter(logging.Filter):
                def __init__(self, sensitive_filter):
                    super().__init__()
                    self.sensitive_filter = sensitive_filter
                
                def filter(self, record):
                    self.sensitive_filter.filter_record(record)
                    return True
            
            sensitive_logging_filter = SensitiveFilter(self.sensitive_filter)
            root_logger.addFilter(sensitive_logging_filter)
    
    def get_correlation_manager(self) -> CorrelationContextManager:
        """Get the correlation context manager."""
        return self.correlation_manager
    
    def shutdown(self) -> None:
        """Shutdown the logging manager and cleanup resources."""
        for handler in self.handlers:
            try:
                handler.flush()
                handler.close()
            except Exception as e:
                print(f"Error closing log handler: {e}", file=sys.stderr)
        
        self.handlers.clear()
        self.is_configured = False


# Global logging manager instance
_logging_manager: Optional[EnhancedLoggingManager] = None


def get_logging_manager() -> Optional[EnhancedLoggingManager]:
    """Get the global logging manager instance."""
    return _logging_manager


def setup_enhanced_logging(config: Optional[LoggingConfig] = None) -> EnhancedLoggingManager:
    """Setup enhanced logging system."""
    global _logging_manager
    
    if config is None:
        config = LoggingConfig.from_environment()
    
    _logging_manager = EnhancedLoggingManager(config)
    _logging_manager.configure_logging()
    
    return _logging_manager


def shutdown_logging() -> None:
    """Shutdown the logging system."""
    global _logging_manager
    if _logging_manager:
        _logging_manager.shutdown()
        _logging_manager = None


def get_logger(name: str) -> logging.Logger:
    """Get a logger with enhanced capabilities."""
    return logging.getLogger(name)


def with_correlation_id(correlation_id: Optional[str] = None):
    """Decorator to add correlation ID to function context."""
    def decorator(func):
        try:
            import asyncio
            if asyncio.iscoroutinefunction(func):
                @wraps(func)
                async def async_wrapper(*args, **kwargs):
                    manager = get_logging_manager()
                    if manager:
                        with manager.get_correlation_manager().correlation_context(correlation_id):
                            return await func(*args, **kwargs)
                    else:
                        return await func(*args, **kwargs)
                return async_wrapper
        except ImportError:
            pass
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            manager = get_logging_manager()
            if manager:
                with manager.get_correlation_manager().correlation_context(correlation_id):
                    return func(*args, **kwargs)
            else:
                return func(*args, **kwargs)
        return sync_wrapper
    return decorator


def log_function_call(logger: Optional[logging.Logger] = None, level: int = logging.DEBUG):
    """Decorator to log function calls with arguments and execution time."""
    def decorator(func):
        func_logger = logger or logging.getLogger(func.__module__)
        
        try:
            import asyncio
            if asyncio.iscoroutinefunction(func):
                @wraps(func)
                async def async_wrapper(*args, **kwargs):
                    start_time = time.time()
                    correlation_id = None
                    
                    manager = get_logging_manager()
                    if manager:
                        correlation_id = manager.get_correlation_manager().get_correlation_id()
                    
                    func_logger.log(level, f"Calling {func.__name__} with args={args}, kwargs={kwargs}", extra={
                        "function_name": func.__name__,
                        "correlation_id": correlation_id,
                        "event_type": "function_start"
                    })
                    
                    try:
                        result = await func(*args, **kwargs)
                        duration = time.time() - start_time
                        func_logger.log(level, f"Completed {func.__name__} in {duration:.3f}s", extra={
                            "function_name": func.__name__,
                            "correlation_id": correlation_id,
                            "duration_ms": duration * 1000,
                            "event_type": "function_end",
                            "success": True
                        })
                        return result
                    except Exception as e:
                        duration = time.time() - start_time
                        func_logger.error(f"Failed {func.__name__} after {duration:.3f}s: {e}", extra={
                            "function_name": func.__name__,
                            "correlation_id": correlation_id,
                            "duration_ms": duration * 1000,
                            "event_type": "function_error",
                            "success": False,
                            "error_type": type(e).__name__,
                            "error_message": str(e)
                        })
                        raise
                return async_wrapper
        except ImportError:
            pass
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.time()
            correlation_id = None
            
            manager = get_logging_manager()
            if manager:
                correlation_id = manager.get_correlation_manager().get_correlation_id()
            
            func_logger.log(level, f"Calling {func.__name__} with args={args}, kwargs={kwargs}", extra={
                "function_name": func.__name__,
                "correlation_id": correlation_id,
                "event_type": "function_start"
            })
            
            try:
                result = func(*args, **kwargs)
                duration = time.time() - start_time
                func_logger.log(level, f"Completed {func.__name__} in {duration:.3f}s", extra={
                    "function_name": func.__name__,
                    "correlation_id": correlation_id,
                    "duration_ms": duration * 1000,
                    "event_type": "function_end",
                    "success": True
                })
                return result
            except Exception as e:
                duration = time.time() - start_time
                func_logger.error(f"Failed {func.__name__} after {duration:.3f}s: {e}", extra={
                    "function_name": func.__name__,
                    "correlation_id": correlation_id,
                    "duration_ms": duration * 1000,
                    "event_type": "function_error",
                    "success": False,
                    "error_type": type(e).__name__,
                    "error_message": str(e)
                })
                raise
        return sync_wrapper
    return decorator 