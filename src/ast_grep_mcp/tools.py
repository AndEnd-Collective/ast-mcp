"""MCP Tools implementation for AST-Grep operations."""

import logging
import json
import re
import yaml
import os
import time
import asyncio
from typing import Dict, Any, List, Optional, Union, AsyncIterator, Tuple
from pathlib import Path

from mcp.server import Server
from mcp.types import Tool, TextContent
from pydantic import BaseModel, Field, field_validator, ValidationError

from .utils import (
    get_language_manager, 
    sanitize_path, 
    ASTGrepError, 
    ASTGrepValidationError,
    create_ast_grep_executor,
    ASTGrepNotFoundError,
    create_error_response,
    create_success_response,
    handle_validation_error,
    handle_configuration_error,
    handle_execution_error,
    format_tool_response,
    extract_meta_variables,
    validate_meta_variable_name,
    analyze_meta_variable_consistency,
    create_meta_variable_usage_report,
    validate_meta_variable_usage
)
from .security import (
    get_audit_logger, get_permission_manager, create_user_context,
    get_rate_limit_manager, UserRole, SecurityLevel, UserContext,
    EnhancedRateLimitError
)
from .performance import (
    PerformanceManager, CacheConfig, get_global_performance_manager,
    set_global_performance_manager, cached, EnhancedPerformanceManager,
    ConcurrencyConfig, ConcurrentRequestManager, StreamingConfig,
    StreamingManager, get_streaming_manager, set_streaming_manager,
    MemoryConfig, MemoryMonitor, get_memory_monitor, set_memory_monitor,
    MetricsConfig, PerformanceMetricsCollector, get_metrics_collector, set_metrics_collector
)

logger = logging.getLogger(__name__)


# Enhanced performance manager for caching, concurrency, streaming, memory monitoring, and metrics collection
_performance_manager: Optional[EnhancedPerformanceManager] = None


async def initialize_performance_system() -> None:
    """Initialize the enhanced performance management system with caching, concurrency control, result streaming, memory monitoring, and comprehensive metrics collection."""
    global _performance_manager
    
    if _performance_manager is None:
        # Configure caching system
        cache_config = CacheConfig(
            max_entries=2000,           # Increased for AST operations
            max_memory_mb=1024,         # 1GB cache limit
            default_ttl=600,            # 10 minutes for most operations
            max_ttl=3600,               # 1 hour max
            min_ttl=60,                 # 1 minute min
            cleanup_interval=120,       # Cleanup every 2 minutes
            statistics_interval=60,     # Log stats every minute
            enable_memory_monitoring=True,
            enable_statistics=True,
            enable_persistence=False    # Disable persistence for now
        )
        
        # Configure concurrency system
        concurrency_config = ConcurrencyConfig(
            max_concurrent_requests=50,     # Global limit
            max_concurrent_search=20,       # AST-grep search operations
            max_concurrent_scan=10,         # AST-grep scan operations
            max_concurrent_run=5,           # AST-grep run operations
            max_concurrent_call_graph=15,   # Call graph operations
            max_queue_size=200,             # Request queue size
            global_rate_limit=1000,         # 1000 RPM global
            search_rate_limit=300,          # 300 RPM for search
            scan_rate_limit=120,            # 120 RPM for scan
            run_rate_limit=60,              # 60 RPM for run
            call_graph_rate_limit=180,      # 180 RPM for call graph
            per_user_rate_limit=100,        # 100 RPM per user
            per_ip_rate_limit=200,          # 200 RPM per IP
            enable_per_user_limits=True,
            enable_priority_queue=True,
            cache_hit_priority_boost=2
        )
        
        # Configure streaming system
        streaming_config = StreamingConfig(
            default_chunk_size=1000,        # Default items per chunk
            max_chunk_size=5000,            # Max items per chunk (optimized for AST results)
            min_chunk_size=100,             # Min items per chunk
            max_buffer_size_mb=100,         # 100MB buffer for AST operations
            memory_check_interval=50,       # Check memory every 50 chunks
            chunk_processing_delay=0.001,   # 1ms delay between chunks
            backpressure_threshold=3,       # Max 3 concurrent streams
            chunk_timeout=15.0,             # 15s timeout for chunk processing
            total_stream_timeout=600.0,     # 10 minutes total streaming timeout
            enable_compression=False,       # Disable compression for now
            enable_buffering=True,          # Enable smart buffering
            enable_backpressure=True        # Enable flow control
        )
        
        # Configure memory monitoring system
        memory_config = MemoryConfig(
            enable_detailed_monitoring=True,       # Enable comprehensive monitoring
            enable_leak_detection=True,            # Enable memory leak detection
            enable_tracemalloc=True,               # Enable tracemalloc for detailed tracking
            tracemalloc_limit=25,                  # Top 25 memory allocations
            warning_threshold_mb=512,              # Warning at 512MB
            critical_threshold_mb=1024,            # Critical at 1GB
            max_memory_mb=2048,                    # Maximum 2GB
            monitoring_interval=30,                # Monitor every 30 seconds
            leak_check_interval=300,               # Check for leaks every 5 minutes
            gc_optimization_interval=60,           # Optimize GC every minute
            enable_aggressive_gc=False,            # Standard GC behavior
            gc_threshold_adjustment=True,          # Dynamic GC threshold adjustment
            enable_memory_alerts=True,             # Enable memory alerts
            alert_cooldown=300                     # 5 minute cooldown between alerts
        )
        
        # Configure performance metrics collection system
        metrics_config = MetricsConfig(
            enable_detailed_metrics=True,          # Enable comprehensive metrics collection
            enable_adaptive_timeouts=True,         # Enable adaptive timeout adjustment
            metrics_window_size=1000,              # Keep 1000 recent measurements per operation
            percentile_calculation_interval=60,    # Recalculate percentiles every minute
            # Latency tracking
            latency_buckets=[1, 5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000, 15000, 30000],  # ms buckets
            track_percentiles=[50, 90, 95, 99],    # Track P50, P90, P95, P99
            # Adaptive timeout configuration
            base_timeout_ms=15000,                 # Base timeout (15 seconds) for AST operations
            min_timeout_ms=5000,                   # Minimum timeout (5 seconds)
            max_timeout_ms=120000,                 # Maximum timeout (2 minutes) for large codebases
            timeout_percentile=95,                 # Use P95 latency for timeout calculation
            timeout_safety_factor=1.5,             # Multiply P95 by this factor for timeout
            # System load adaptation
            enable_load_aware_timeouts=True,       # Enable load-aware timeout adjustment
            cpu_threshold_high=80.0,               # High CPU usage threshold
            memory_threshold_high=85.0,            # High memory usage threshold
            load_factor_high=0.8,                  # Reduce timeout under high load
            load_factor_low=1.2,                   # Increase timeout under low load
            # Monitoring windows
            throughput_window_seconds=60,          # Calculate throughput over 1 minute
            error_rate_window_seconds=300          # Calculate error rate over 5 minutes
        )
        
        # Initialize enhanced performance manager with all subsystems
        _performance_manager = EnhancedPerformanceManager(
            cache_config, 
            concurrency_config, 
            streaming_config,
            memory_config,
            metrics_config
        )
        set_global_performance_manager(_performance_manager)
        await _performance_manager.start()
        
        logger.info("Enhanced performance management system initialized with caching, concurrency control, result streaming, comprehensive memory monitoring, and performance metrics collection with adaptive timeouts")


async def shutdown_performance_system() -> None:
    """Shutdown the performance management system."""
    global _performance_manager
    
    if _performance_manager is not None:
        await _performance_manager.shutdown()
        _performance_manager = None
        logger.info("Performance management system shutdown")


def get_performance_manager() -> Optional[EnhancedPerformanceManager]:
    """Get the current enhanced performance manager instance."""
    return _performance_manager


def get_memory_manager() -> Optional[MemoryMonitor]:
    """Get the current memory monitor instance."""
    if _performance_manager is not None:
        return _performance_manager.get_memory_monitor()
    return None


def get_metrics_manager() -> Optional[PerformanceMetricsCollector]:
    """Get the current performance metrics collector instance."""
    if _performance_manager is not None:
        return _performance_manager.get_metrics_collector()
    return None


async def force_system_cleanup() -> Dict[str, Any]:
    """Force comprehensive system cleanup across all performance subsystems."""
    perf_manager = get_performance_manager()
    if perf_manager is not None:
        return await perf_manager.force_comprehensive_cleanup()
    else:
        logger.warning("No performance manager available for system cleanup")
        return {'error': 'No performance manager available'}


async def get_comprehensive_performance_metrics() -> Dict[str, Any]:
    """Get comprehensive performance metrics from all subsystems."""
    perf_manager = get_performance_manager()
    if perf_manager is not None:
        return await perf_manager.get_comprehensive_performance_report()
    else:
        return {'error': 'No performance manager available'}


async def get_performance_dashboard_data() -> Dict[str, Any]:
    """Get performance data suitable for dashboards and monitoring."""
    perf_manager = get_performance_manager()
    if perf_manager is not None:
        return await perf_manager.get_performance_dashboard_summary()
    else:
        return {'error': 'No performance manager available'}


# Default user context for MCP operations (can be overridden)
DEFAULT_USER_CONTEXT = create_user_context(
    user_id="mcp_user",
    role=UserRole.DEVELOPER,  # MCP users get developer permissions by default
    session_id=None
)


def audit_operation(operation_name: str, security_level: SecurityLevel = SecurityLevel.RESTRICTED):
    """Decorator for auditing tool operations with comprehensive security checks.
    
    Args:
        operation_name: Name of the operation for audit logging
        security_level: Security level of the operation
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            audit_logger = get_audit_logger()
            permission_manager = get_permission_manager()
            rate_limit_manager = get_rate_limit_manager()
            
            # Extract user context if provided, otherwise use default
            user_context = kwargs.pop('user_context', DEFAULT_USER_CONTEXT)
            
            # Extract resource from input_data
            input_data = args[0] if args else None
            resource = getattr(input_data, 'path', 'unknown') if input_data else 'unknown'
            ip_address = getattr(user_context, 'ip_address', None)
            
            start_time = time.time()
            
            # Check rate limits first
            rate_allowed, rate_error = rate_limit_manager.check_rate_limit(
                user_context, operation_name, ip_address
            )
            
            if not rate_allowed:
                # Log rate limit violation
                audit_logger.log_security_violation(
                    violation_type="RateLimitExceeded",
                    operation=operation_name,
                    resource=resource,
                    user_context=user_context,
                    details={
                        "limit_type": rate_error.limit_type,
                        "retry_after": rate_error.retry_after,
                        "current_usage": rate_error.current_usage,
                        "limit": rate_error.limit
                    }
                )
                
                # Return structured error response for rate limiting
                return [TextContent(type="text", text=json.dumps({
                    "error": "RateLimitExceeded",
                    "message": str(rate_error),
                    "retry_after": rate_error.retry_after,
                    "limit_type": rate_error.limit_type,
                    "operation": operation_name,
                    "resource": resource
                }, indent=2))]
            
            # Check permissions
            has_permission, denial_reason = permission_manager.check_permission(
                user_context, operation_name, resource
            )
            
            # Log permission check
            audit_logger.log_permission_check(
                operation=operation_name,
                resource=resource,
                user_context=user_context,
                granted=has_permission,
                reason=denial_reason
            )
            
            if not has_permission:
                # Log security violation
                audit_logger.log_security_violation(
                    violation_type="permission_denied",
                    operation=operation_name,
                    resource=resource,
                    user_context=user_context,
                    details={"denial_reason": denial_reason}
                )
                
                # Return error response
                error_message = f"Permission denied: {denial_reason}"
                return [TextContent(type="text", text=json.dumps({
                    "error": "PermissionDenied",
                    "message": error_message,
                    "operation": operation_name,
                    "resource": resource
                }, indent=2))]
            
            # Check security level access
            if not user_context.can_access_security_level(security_level):
                audit_logger.log_security_violation(
                    violation_type="SecurityLevelViolation",
                    operation=operation_name,
                    resource=resource,
                    user_context=user_context,
                    details={
                        "required_level": security_level.value,
                        "user_role": user_context.role.value
                    }
                )
                
                return [TextContent(type="text", text=json.dumps({
                    "error": "SecurityLevelViolation",
                    "message": f"Insufficient security level for operation {operation_name}",
                    "required_level": security_level.value,
                    "user_role": user_context.role.value,
                    "operation": operation_name,
                    "resource": resource
                }, indent=2))]
            
            # Log operation start
            start_event_id = audit_logger.log_operation_start(
                operation=operation_name,
                resource=resource,
                user_context=user_context,
                details={
                    "function": func.__name__,
                    "security_level": security_level.value,
                    "input_params": _serialize_input_for_audit(input_data)
                }
            )
            
            try:
                # Execute the actual function
                result = await func(*args, **kwargs)
                
                # Calculate duration
                duration_ms = (time.time() - start_time) * 1000
                
                # Log successful completion
                audit_logger.log_operation_end(
                    operation=operation_name,
                    resource=resource,
                    success=True,
                    user_context=user_context,
                    duration_ms=duration_ms,
                    resource_usage={
                        "result_size": len(str(result)) if result else 0,
                        "result_count": len(result) if isinstance(result, list) else 1,
                        "security_level": security_level.value,
                        "operation": operation_name
                    }
                )
                
                return result
                
            except Exception as e:
                # Calculate duration
                duration_ms = (time.time() - start_time) * 1000
                
                # Log failed operation
                audit_logger.log_operation_end(
                    operation=operation_name,
                    resource=resource,
                    success=False,
                    user_context=user_context,
                    duration_ms=duration_ms,
                    error=str(e),
                    resource_usage={
                        "error_type": type(e).__name__,
                        "security_level": security_level.value,
                        "operation": operation_name
                    }
                )
                
                # Log as security violation if it's a security-related error
                if isinstance(e, (PermissionError, FileNotFoundError, EnhancedRateLimitError)):
                    audit_logger.log_security_violation(
                        violation_type="resource_access_failure",
                        operation=operation_name,
                        resource=resource,
                        user_context=user_context,
                        details={
                            "error_type": type(e).__name__,
                            "error_message": str(e)
                        }
                    )
                
                # Re-raise the exception
                raise
        
        return wrapper
    return decorator


def _serialize_input_for_audit(input_data: Any) -> Dict[str, Any]:
    """Serialize input data for audit logging (removing sensitive information).
    
    Args:
        input_data: Input data to serialize
        
    Returns:
        Serialized data safe for audit logs
    """
    if input_data is None:
        return {}
    
    # Convert to dict if it's a Pydantic model
    if hasattr(input_data, 'model_dump'):
        data = input_data.model_dump()
    elif hasattr(input_data, '__dict__'):
        data = input_data.__dict__.copy()
    else:
        return {"type": type(input_data).__name__}
    
    # Remove or mask sensitive fields
    sensitive_fields = {'password', 'token', 'key', 'secret'}
    for field in sensitive_fields:
        if field in data:
            data[field] = "[MASKED]"
    
    # Truncate large strings to prevent log bloat
    for key, value in data.items():
        if isinstance(value, str) and len(value) > 1000:
            data[key] = value[:1000] + "...[TRUNCATED]"
    
    return data


def get_user_context_from_request() -> UserContext:
    """Extract user context from current request.
    
    This is a placeholder for future integration with authentication systems.
    For now, returns the default MCP user context.
    
    Returns:
        UserContext for the current request
    """
    # In future, this could extract context from:
    # - HTTP headers (if running as HTTP server)
    # - Environment variables
    # - Session management system
    # - Authentication tokens
    
    return DEFAULT_USER_CONTEXT


def create_admin_user_context(user_id: str, session_id: Optional[str] = None) -> UserContext:
    """Create an admin user context for privileged operations.
    
    Args:
        user_id: Admin user identifier
        session_id: Optional session identifier
        
    Returns:
        UserContext with admin privileges
    """
    return create_user_context(
        user_id=user_id,
        role=UserRole.ADMIN,
        session_id=session_id
    )


# Pydantic models for tool inputs
class SearchToolInput(BaseModel):
    """Input model for ast_grep_search tool."""
    pattern: str = Field(..., description="AST pattern to search for (e.g., 'console.log($GREETING)')", min_length=1, max_length=8192)
    language: str = Field(..., description="Programming language identifier (js, ts, py, rust, etc.)", min_length=1, max_length=50)
    path: str = Field(..., description="File or directory path to search", min_length=1, max_length=4096)
    recursive: bool = Field(True, description="Search recursively in directories")
    output_format: str = Field("json", description="Output format (json/text)")
    include_globs: Optional[List[str]] = Field(None, description="Custom file glob patterns to include (e.g., ['*.test.js', '*.spec.ts'])", max_length=100)
    exclude_globs: Optional[List[str]] = Field(None, description="File glob patterns to exclude (e.g., ['node_modules/**', '*.min.js'])", max_length=100)
    
    @field_validator('pattern')
    @classmethod
    def validate_pattern(cls, v: str) -> str:
        """Validate AST-grep pattern syntax and security."""
        if not v.strip():
            raise ValueError("Pattern cannot be empty")
        
        # Basic security check for command injection
        dangerous_chars = [';', '&', '|', '`', '$']
        for char in dangerous_chars:
            if char in v:
                # Allow these characters in AST-grep patterns as they're part of the syntax
                # Only flag if they appear in suspicious contexts
                if char == '$' and not v.startswith('$'):
                    # '$' is allowed for variables in AST-grep patterns like $VAR
                    continue
                if char in ['&', '|'] and char * 2 not in v:
                    # Allow single & and | but not && or ||
                    continue
                raise ValueError(
                    f"Potentially dangerous character '{char}' detected in pattern. "
                    f"If this is intended AST-grep syntax, please verify the pattern is safe."
                )
        
        return v.strip()
    
    @field_validator('language')
    @classmethod
    def validate_language(cls, v: str) -> str:
        """Validate language identifier using LanguageManager."""
        if not v.strip():
            raise ValueError("Language cannot be empty")
        
        try:
            # Use LanguageManager for validation
            manager = get_language_manager()
            validated = manager.validate_language_identifier(v.strip())
            if not validated:
                # Get suggestions for similar languages
                suggestions = manager.suggest_similar_languages(v.strip())
                if suggestions:
                    raise ValueError(
                        f"Unsupported language '{v}'. Similar languages: {', '.join(suggestions[:3])}"
                    )
                else:
                    raise ValueError(f"Unsupported language '{v}'. Check supported languages list.")
            return v.strip()
        except Exception as e:
            if isinstance(e, ValueError):
                raise
            raise ValueError(f"Language validation failed: {str(e)}")
    
    @field_validator('path')
    @classmethod
    def validate_path(cls, v: str) -> str:
        """Validate and sanitize file/directory path."""
        if not v.strip():
            raise ValueError("Path cannot be empty")
        
        try:
            # Use utility function for path sanitization and validation
            sanitized = sanitize_path(v.strip())
            return str(sanitized)
        except Exception as e:
            raise ValueError(f"Invalid path '{v}': {str(e)}")
    
    @field_validator('output_format')
    @classmethod
    def validate_output_format(cls, v: str) -> str:
        """Validate output format."""
        if v not in ["json", "text"]:
            raise ValueError(f"Output format must be 'json' or 'text', got '{v}'")
        return v
    
    @field_validator('include_globs')
    @classmethod
    def validate_include_globs(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        """Validate include glob patterns for security and correctness."""
        if v is None:
            return v
        
        if not isinstance(v, list):
            raise ValueError("Include globs must be a list of glob patterns")
        
        if not v:  # Empty list
            return None
        
        # Validate list size constraints
        if len(v) > 100:
            raise ValueError(f"Too many include globs specified ({len(v)}). Maximum allowed: 100")
        
        validated_globs = []
        for i, glob_pattern in enumerate(v):
            if not isinstance(glob_pattern, str):
                raise ValueError(f"Include glob at index {i} must be a string, got: {type(glob_pattern)}")
            
            pattern = glob_pattern.strip()
            if not pattern:
                continue
            
            # Validate individual glob length
            if len(pattern) > 200:
                raise ValueError(f"Include glob at index {i} too long ({len(pattern)} chars). Maximum: 200")
            
            # Enhanced security check for dangerous characters
            dangerous_patterns = [
                ';', '&&', '||', '`', '$(', '${', '<(', '>(', 
                '&', '|', '<', '>', '"', "'", '\n', '\r', '\t'
            ]
            
            for dangerous in dangerous_patterns:
                if dangerous in pattern:
                    raise ValueError(
                        f"Include glob '{pattern}' contains potentially dangerous character or sequence '{dangerous}'"
                    )
            
            # Validate glob pattern syntax (basic check)
            if pattern.count('[') != pattern.count(']'):
                raise ValueError(f"Include glob '{pattern}' has unmatched brackets")
            
            if pattern.count('{') != pattern.count('}'):
                raise ValueError(f"Include glob '{pattern}' has unmatched braces")
            
            # Prevent overly broad patterns that could cause performance issues
            if pattern in ['*', '**', '***', '/**', '/*']:
                raise ValueError(f"Include glob '{pattern}' is too broad and may cause performance issues")
            
            validated_globs.append(pattern)
        
        return validated_globs if validated_globs else None
    
    @field_validator('exclude_globs')
    @classmethod
    def validate_exclude_globs(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        """Validate exclude glob patterns for security and correctness."""
        if v is None:
            return v
        
        if not isinstance(v, list):
            raise ValueError("Exclude globs must be a list of glob patterns")
        
        if not v:  # Empty list
            return None
        
        # Validate list size constraints
        if len(v) > 100:
            raise ValueError(f"Too many exclude globs specified ({len(v)}). Maximum allowed: 100")
        
        validated_globs = []
        for i, glob_pattern in enumerate(v):
            if not isinstance(glob_pattern, str):
                raise ValueError(f"Exclude glob at index {i} must be a string, got: {type(glob_pattern)}")
            
            pattern = glob_pattern.strip()
            if not pattern:
                continue
            
            # Validate individual glob length
            if len(pattern) > 200:
                raise ValueError(f"Exclude glob at index {i} too long ({len(pattern)} chars). Maximum: 200")
            
            # Enhanced security check for dangerous characters
            dangerous_patterns = [
                ';', '&&', '||', '`', '$(', '${', '<(', '>(', 
                '&', '|', '<', '>', '"', "'", '\n', '\r', '\t'
            ]
            
            for dangerous in dangerous_patterns:
                if dangerous in pattern:
                    raise ValueError(
                        f"Exclude glob '{pattern}' contains potentially dangerous character or sequence '{dangerous}'"
                    )
            
            # Validate glob pattern syntax (basic check)
            if pattern.count('[') != pattern.count(']'):
                raise ValueError(f"Exclude glob '{pattern}' has unmatched brackets")
            
            if pattern.count('{') != pattern.count('}'):
                raise ValueError(f"Exclude glob '{pattern}' has unmatched braces")
            
            validated_globs.append(pattern)
        
        return validated_globs if validated_globs else None


class ScanToolInput(BaseModel):
    """Input model for ast_grep_scan tool."""
    path: str = Field(..., description="Directory path to scan", min_length=1, max_length=4096)
    rules_config: Optional[str] = Field(None, description="Path to sgconfig.yml or custom rules", max_length=4096)
    output_format: str = Field("json", description="Output format (json/text)")
    
    @field_validator('path')
    @classmethod
    def validate_path(cls, v: str) -> str:
        """Validate and sanitize the scan path."""
        if not v or not v.strip():
            raise ValueError("Path cannot be empty")
        
        try:
            sanitized_path = sanitize_path(v.strip())
            return str(sanitized_path)
        except ValueError as e:
            raise ValueError(f"Invalid path: {e}")
    
    @field_validator('rules_config')
    @classmethod
    def validate_rules_config(cls, v: Optional[str]) -> Optional[str]:
        """Validate rules configuration path."""
        if v is None:
            return v
        
        if not isinstance(v, str):
            raise ValueError(f"Rules config must be a string path, got: {type(v)}")
        
        rules_config_clean = v.strip()
        if not rules_config_clean:
            return None
        
        try:
            # Validate and sanitize the rules config path
            sanitized_path = sanitize_path(rules_config_clean)
            return str(sanitized_path)
        except Exception as e:
            raise ValueError(f"Invalid rules config path '{rules_config_clean}': {str(e)}")
    
    @field_validator('output_format')
    @classmethod
    def validate_output_format(cls, v: str) -> str:
        """Validate output format."""
        valid_formats = ["json", "text"]
        v_lower = v.lower()
        if v_lower not in valid_formats:
            raise ValueError(f"Invalid output format '{v}'. Must be one of: {', '.join(valid_formats)}")
        return v_lower


class RunToolInput(BaseModel):
    """Input model for ast_grep_run tool."""
    pattern: str = Field(..., description="AST pattern for matching", min_length=1, max_length=8192)
    rewrite: Optional[str] = Field(None, description="Rewrite pattern for transformations", max_length=8192)
    language: str = Field(..., description="Programming language identifier", min_length=1, max_length=50)
    path: str = Field(..., description="File or directory path", min_length=1, max_length=4096)
    dry_run: bool = Field(True, description="Preview changes without applying them")
    output_format: str = Field("json", description="Output format (json/text)")
    
    @field_validator('pattern')
    @classmethod
    def validate_pattern(cls, v: str) -> str:
        """Validate AST-grep pattern syntax and security."""
        if not v.strip():
            raise ValueError("Pattern cannot be empty")
        
        # Check for basic pattern structure
        pattern = v.strip()
        
        # Basic security check for command injection - more permissive for AST-grep patterns
        dangerous_patterns = [';', '&&', '||', '`', '$(']
        for dangerous in dangerous_patterns:
            if dangerous in pattern:
                raise ValueError(
                    f"Pattern contains potentially dangerous sequence '{dangerous}'. "
                    f"If this is intended AST-grep syntax, please verify the pattern is safe."
                )
        
        # Enhanced meta-variable validation using utilities
        meta_vars = extract_meta_variables(pattern)
        non_compliant = [var for var in meta_vars if not validate_meta_variable_name(var)]
        if non_compliant:
            logger.warning(f"Meta-variables {non_compliant} should follow convention $UPPERCASE_NAME")
        
        return pattern
    
    @field_validator('rewrite')
    @classmethod
    def validate_rewrite(cls, v: Optional[str]) -> Optional[str]:
        """Validate rewrite pattern for meta-variable substitution."""
        if v is None:
            return v
        
        if not v.strip():
            return None
        
        rewrite_pattern = v.strip()
        
        # Security check for dangerous characters
        dangerous_patterns = [';', '&&', '||', '`', '$(']
        for dangerous in dangerous_patterns:
            if dangerous in rewrite_pattern:
                raise ValueError(
                    f"Rewrite pattern contains potentially dangerous sequence '{dangerous}'. "
                    f"If this is intended AST-grep syntax, please verify the pattern is safe."
                )
        
        # Enhanced meta-variable validation using utilities
        meta_vars = extract_meta_variables(rewrite_pattern)
        non_compliant = [var for var in meta_vars if not validate_meta_variable_name(var)]
        if non_compliant:
            logger.warning(f"Meta-variables {non_compliant} in rewrite pattern should follow convention $UPPERCASE_NAME")
        
        return rewrite_pattern
    
    @field_validator('language')
    @classmethod
    def validate_language(cls, v: str) -> str:
        """Validate language identifier using LanguageManager."""
        if not v.strip():
            raise ValueError("Language cannot be empty")
        
        try:
            # Use LanguageManager for validation
            manager = get_language_manager()
            validated = manager.validate_language_identifier(v.strip())
            if not validated:
                # Get suggestions for similar languages
                suggestions = manager.suggest_similar_languages(v.strip())
                if suggestions:
                    raise ValueError(
                        f"Unsupported language '{v}'. Similar languages: {', '.join(suggestions[:3])}"
                    )
                else:
                    raise ValueError(f"Unsupported language '{v}'. Check supported languages list.")
            return v.strip()
        except Exception as e:
            if isinstance(e, ValueError):
                raise
            raise ValueError(f"Language validation failed: {str(e)}")
    
    @field_validator('path')
    @classmethod
    def validate_path(cls, v: str) -> str:
        """Validate and sanitize file/directory path."""
        if not v.strip():
            raise ValueError("Path cannot be empty")
        
        try:
            # Use utility function for path sanitization and validation
            sanitized = sanitize_path(v.strip())
            return str(sanitized)
        except Exception as e:
            raise ValueError(f"Invalid path '{v}': {str(e)}")
    
    @field_validator('output_format')
    @classmethod
    def validate_output_format(cls, v: str) -> str:
        """Validate output format."""
        if v not in ["json", "text"]:
            raise ValueError(f"Output format must be 'json' or 'text', got '{v}'")
        return v

    @classmethod
    def model_validate(cls, obj):
        """Validate the entire model, including cross-field validation for meta-variables."""
        # First perform standard validation
        instance = super().model_validate(obj)
        
        # Cross-field validation for meta-variable consistency
        if instance.pattern and instance.rewrite:
            validation_result = validate_meta_variable_usage(instance.pattern, instance.rewrite)
            
            if validation_result["errors"]:
                error_msg = "Meta-variable validation failed: " + "; ".join(validation_result["errors"])
                if validation_result["suggestions"]:
                    error_msg += f". Suggestions: {'; '.join(validation_result['suggestions'])}"
                raise ValueError(error_msg)
            
            if validation_result["warnings"]:
                for warning in validation_result["warnings"]:
                    logger.warning(f"Meta-variable warning: {warning}")
        
        return instance


class CallGraphInput(BaseModel):
    """Input model for call_graph_generate tool."""
    path: str = Field(..., description="Directory path to analyze", min_length=1, max_length=4096)
    languages: Optional[List[str]] = Field(None, description="List of languages to include (max 20 languages)", max_length=20)
    include_external: bool = Field(False, description="Include external library calls")
    
    @field_validator('path')
    @classmethod
    def validate_path(cls, v: str) -> str:
        """Validate and sanitize the directory path for analysis."""
        if not v or not v.strip():
            raise ValueError("Path cannot be empty")
        
        try:
            sanitized_path = sanitize_path(v.strip())
            return str(sanitized_path)
        except Exception as e:
            raise ValueError(f"Invalid path '{v}': {str(e)}")
    
    @field_validator('languages')
    @classmethod
    def validate_languages(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        """Validate language identifiers using LanguageManager."""
        if v is None:
            return v
        
        if not isinstance(v, list):
            raise ValueError("Languages must be a list of language identifiers")
        
        if not v:  # Empty list
            return None
        
        # Validate list size constraints
        if len(v) > 20:
            raise ValueError(f"Too many languages specified ({len(v)}). Maximum allowed: 20")
        
        validated_languages = []
        lang_manager = get_language_manager()
        
        for i, lang in enumerate(v):
            if not isinstance(lang, str):
                raise ValueError(f"Language identifier at index {i} must be a string, got: {type(lang)}")
            
            # Validate individual string length
            if len(lang) > 50:
                raise ValueError(f"Language identifier at index {i} too long ({len(lang)} chars). Maximum: 50")
            
            lang_clean = lang.strip()
            if not lang_clean:
                continue
            
            # Check for dangerous characters in language identifiers
            dangerous_chars = [';', '&', '|', '`', '$', '(', ')', '<', '>', '"', "'"]
            for char in dangerous_chars:
                if char in lang_clean:
                    raise ValueError(f"Language identifier '{lang_clean}' contains dangerous character '{char}'")
            
            try:
                # Validate each language using LanguageManager
                validated = lang_manager.validate_language_identifier(lang_clean)
                if not validated:
                    # Get suggestions for similar languages
                    suggestions = lang_manager.suggest_similar_languages(lang_clean)
                    if suggestions:
                        raise ValueError(
                            f"Unsupported language '{lang_clean}'. Similar languages: {', '.join(suggestions[:3])}"
                        )
                    else:
                        raise ValueError(f"Unsupported language '{lang_clean}'. Check supported languages list.")
                
                validated_languages.append(lang_clean)
                
            except Exception as e:
                if isinstance(e, ValueError):
                    raise
                raise ValueError(f"Language validation failed for '{lang_clean}': {str(e)}")
        
        # Check for duplicate languages
        if len(validated_languages) != len(set(validated_languages)):
            duplicates = [lang for lang in set(validated_languages) if validated_languages.count(lang) > 1]
            raise ValueError(f"Duplicate languages found: {', '.join(duplicates)}")
        
        return validated_languages if validated_languages else None


async def _execute_ast_grep_search_cached(input_data: SearchToolInput, ast_grep_path: Path) -> Dict[str, Any]:
    """
    Execute ast-grep search operation (cacheable core implementation).
    This function contains the actual search logic without auditing decorators.
    """
    logger.info(f"Executing search with pattern: {input_data.pattern}")
    
    # Get the language manager for ast-grep language mapping
    lang_manager = get_language_manager()
    ast_grep_language = lang_manager.map_to_ast_grep_language(input_data.language)
    
    # Create AST-Grep executor
    executor = await create_ast_grep_executor(binary_path=ast_grep_path)
    
    # Prepare search paths
    search_paths = [input_data.path] if input_data.path else None
    
    # Execute the search
    result = await executor.search(
        pattern=input_data.pattern,
        language=ast_grep_language,
        paths=search_paths,
        additional_args=_build_search_args(input_data)
    )
    
    # Extract matches from the executor result
    # The executor returns parsed_output, but our formatting functions expect matches
    matches = result.get('parsed_output', [])
    processed_result = {
        **result,
        'matches': matches
    }
    
    # Return the processed result for caching
    return processed_result


@audit_operation("ast_grep_search", SecurityLevel.RESTRICTED)
async def ast_grep_search_impl(input_data: SearchToolInput, ast_grep_path: Path) -> List[TextContent]:
    """Execute ast-grep search operation with caching, streaming, and comprehensive performance metrics.
    
    Features comprehensive performance tracking including:
    - Adaptive timeouts based on historical performance
    - Load-aware optimization and error tracking
    - Detailed latency and throughput monitoring
    - System resource usage consideration
    
    Args:
        input_data: Validated input parameters
        ast_grep_path: Path to ast-grep binary
        
    Returns:
        List of text content with search results
    """
    try:
        perf_manager = _performance_manager
        
        if perf_manager is not None:
            # Extract user context for concurrency control and metrics
            user_context = get_user_context_from_request()
            
            # Create cache key for the operation
            cache_key = _create_cache_key('search', input_data)
            
            # Use enhanced performance manager with comprehensive metrics
            raw_result = await perf_manager.get_or_compute_concurrent_with_metrics(
                cache_key=cache_key,
                compute_func=lambda: _execute_ast_grep_search_cached(input_data, ast_grep_path),
                operation='ast_grep_search',
                ttl=600,  # 10 minute cache TTL for search results
                priority=5,  # Medium priority
                user_context=user_context,
                # Additional context for metrics
                pattern=input_data.pattern,
                language=input_data.language,
                paths=input_data.paths,
                result_type='search'
            )
        else:
            # Fallback to direct execution without performance management
            logger.warning("Performance manager not available, executing without caching or metrics")
            raw_result = await _execute_ast_grep_search_cached(input_data, ast_grep_path)
        
        # Format the result into TextContent based on output format
        if input_data.output_format == "json":
            formatted_result = _format_search_results_json(raw_result, input_data)
            return [TextContent(type="text", text=json.dumps(formatted_result, indent=2))]
        else:
            formatted_text = _format_search_results_text(raw_result, input_data)
            return [TextContent(type="text", text=formatted_text)]
            
    except ASTGrepError as e:
        # Handle AST-Grep specific errors
        error_response = {
            "error": "AST-Grep execution failed",
            "message": str(e),
            "pattern": input_data.pattern,
            "language": input_data.language,
            "path": input_data.path
        }
        return [TextContent(type="text", text=json.dumps(error_response, indent=2))]
    except Exception as e:
        # Handle unexpected errors
        logger.error(f"Unexpected error in ast_grep_search: {e}")
        error_response = {
            "error": "Unexpected error during search",
            "message": str(e),
            "pattern": input_data.pattern,
            "language": input_data.language,
            "path": input_data.path
        }
        return [TextContent(type="text", text=json.dumps(error_response, indent=2))]


@audit_operation("ast_grep_scan", SecurityLevel.RESTRICTED)
async def ast_grep_scan_impl(input_data: ScanToolInput, ast_grep_path: Path) -> List[TextContent]:
    """Execute ast-grep scan operation with caching, streaming, and comprehensive performance metrics.
    
    Features comprehensive performance tracking including:
    - Adaptive timeouts based on operation complexity and historical data
    - Load-aware chunk size optimization for large codebases
    - Detailed performance metrics collection
    - Memory-aware execution with resource monitoring
    
    Args:
        input_data: Validated input parameters  
        ast_grep_path: Path to ast-grep binary
        
    Returns:
        List of text content with scan results (may be streamed for large outputs)
    """
    try:
        perf_manager = _performance_manager
        
        if perf_manager is not None:
            # Extract user context
            user_context = get_user_context_from_request()
            
            # Create cache key including configuration
            cache_key = _create_cache_key('scan', input_data)
            
            # Use enhanced performance manager with comprehensive metrics
            raw_result = await perf_manager.get_or_compute_concurrent_with_metrics(
                cache_key=cache_key,
                compute_func=lambda: _execute_ast_grep_scan_cached(input_data, ast_grep_path),
                operation='ast_grep_scan', 
                ttl=900,  # 15 minute cache TTL for scan results (longer due to complexity)
                priority=6,  # Slightly higher priority due to scan complexity
                user_context=user_context,
                # Additional context for metrics
                config_path=str(input_data.config_path) if input_data.config_path else None,
                paths=input_data.paths,
                result_type='scan'
            )
        else:
            # Fallback to direct execution
            logger.warning("Performance manager not available, executing without caching or metrics")
            raw_result = await _execute_ast_grep_scan_cached(input_data, ast_grep_path)
        
        # Get the parsed config for formatting
        config = None
        if input_data.rules_config:
            try:
                config = discover_and_parse_sgconfig(Path(input_data.path), input_data.rules_config)
            except Exception as e:
                logger.warning(f"Could not parse config for formatting: {e}")
        
        # Format the result into TextContent based on output format
        if input_data.output_format == "json":
            formatted_result = _format_scan_results_json(raw_result, input_data, config)
            return [TextContent(type="text", text=json.dumps(formatted_result, indent=2))]
        else:
            formatted_text = _format_scan_results_text(raw_result, input_data, config)
            return [TextContent(type="text", text=formatted_text)]
            
    except ASTGrepError as e:
        # Handle AST-Grep specific errors
        error_response = {
            "error": "AST-Grep scan failed",
            "message": str(e),
            "path": input_data.path,
            "rules_config": input_data.rules_config
        }
        return [TextContent(type="text", text=json.dumps(error_response, indent=2))]
    except Exception as e:
        # Handle unexpected errors
        logger.error(f"Unexpected error in ast_grep_scan: {e}")
        error_response = {
            "error": "Unexpected error during scan",
            "message": str(e),
            "path": input_data.path,
            "rules_config": input_data.rules_config
        }
        return [TextContent(type="text", text=json.dumps(error_response, indent=2))]


# Helper function to create cache keys
def _create_cache_key(operation: str, input_data: Union[SearchToolInput, ScanToolInput]) -> str:
    """Create a deterministic cache key for AST-grep operations."""
    import hashlib
    import json
    
    if operation == 'search':
        key_data = {
            'operation': 'search',
            'pattern': input_data.pattern,
            'language': input_data.language,
            'paths': sorted(input_data.paths) if input_data.paths else [],
            'include_context': getattr(input_data, 'include_context', False)
        }
    elif operation == 'scan':
        key_data = {
            'operation': 'scan',
            'config_path': str(input_data.config_path) if input_data.config_path else None,
            'paths': sorted(input_data.paths) if input_data.paths else []
        }
    else:
        key_data = {'operation': operation}
    
    # Create deterministic JSON and hash it
    key_string = json.dumps(key_data, sort_keys=True)
    return hashlib.md5(key_string.encode()).hexdigest()


async def ast_grep_search_streaming(input_data: SearchToolInput, ast_grep_path: Path) -> AsyncIterator[List[TextContent]]:
    """
    Stream AST-grep search results for large outputs with comprehensive performance metrics.
    
    This function is specifically designed for handling large search results that may
    not fit efficiently in memory, providing chunked streaming with adaptive performance.
    
    Args:
        input_data: Validated search input parameters
        ast_grep_path: Path to ast-grep binary
        
    Yields:
        Chunks of text content with search results
    """
    try:
        perf_manager = _performance_manager
        
        if perf_manager is not None:
            user_context = get_user_context_from_request()
            
            # Create a generator function for the search results
            async def search_data_generator():
                # Execute the search and yield results in chunks
                results = await _execute_ast_grep_search_cached(input_data, ast_grep_path)
                # Yield all results at once for now (could be optimized for true streaming)
                yield results
            
            # Use enhanced streaming with performance metrics
            async for chunk in perf_manager.stream_large_results_concurrent_with_metrics(
                data_source=search_data_generator(),
                operation='ast_grep_search_stream',
                chunk_size=1000,  # Results per chunk
                user_context=user_context,
                pattern=input_data.pattern,
                language=input_data.language
            ):
                yield chunk
        else:
            # Fallback to regular execution
            logger.warning("Performance manager not available, executing without streaming metrics")
            results = await _execute_ast_grep_search_cached(input_data, ast_grep_path)
            yield results
            
    except Exception as e:
        logger.error(f"Error in ast_grep_search_streaming: {e}")
        raise


async def ast_grep_scan_streaming(input_data: ScanToolInput, ast_grep_path: Path) -> AsyncIterator[List[TextContent]]:
    """
    Stream AST-grep scan results for large outputs with comprehensive performance metrics.
    
    Optimized for large codebases where scan results may be substantial and benefit
    from chunked delivery with adaptive performance characteristics.
    
    Args:
        input_data: Validated scan input parameters
        ast_grep_path: Path to ast-grep binary
        
    Yields:
        Chunks of text content with scan results
    """
    try:
        perf_manager = _performance_manager
        
        if perf_manager is not None:
            user_context = get_user_context_from_request()
            
            # Create a generator function for the scan results
            async def scan_data_generator():
                # Execute the scan and yield results
                results = await _execute_ast_grep_scan_cached(input_data, ast_grep_path)
                yield results
            
            # Use enhanced streaming with performance metrics and larger chunks for scan operations
            async for chunk in perf_manager.stream_large_results_concurrent_with_metrics(
                data_source=scan_data_generator(),
                operation='ast_grep_scan_stream',
                chunk_size=500,  # Smaller chunks for potentially larger scan results
                user_context=user_context,
                config_path=str(input_data.config_path) if input_data.config_path else None
            ):
                yield chunk
        else:
            # Fallback to regular execution
            logger.warning("Performance manager not available, executing without streaming metrics")
            results = await _execute_ast_grep_scan_cached(input_data, ast_grep_path)
            yield results
            
    except Exception as e:
        logger.error(f"Error in ast_grep_scan_streaming: {e}")
        raise


async def _execute_ast_grep_scan_cached(input_data: ScanToolInput, ast_grep_path: Path) -> Dict[str, Any]:
    """
    Execute ast-grep scan operation (cacheable core implementation).
    This function contains the actual scan logic without auditing decorators.
    """
    logger.info(f"Executing scan on path: {input_data.path}")
    scan_path = Path(input_data.path)
    
    # Discover and parse sgconfig.yml configuration
    config = discover_and_parse_sgconfig(scan_path, input_data.rules_config)
    
    # Create AST-Grep executor
    executor = await create_ast_grep_executor(binary_path=ast_grep_path)
    
    # Determine scan configuration
    if config:
        # Use discovered sgconfig.yml and validate all rules
        validated_rules = discover_and_validate_rules(config)
        logger.info(f"Successfully validated rules from configuration")
        
        if not validated_rules:
            result = {"matches": [], "message": "No valid rules found in configured directories"}
        else:
            # Execute scan with validated rules from all directories
            all_matches = []
            scan_summary = {
                "total_violations": 0,
                "rules_processed": 0,
                "directories_scanned": 0,
                "execution_details": []
            }
            
            # Process each rule directory
            rule_dirs = config.get("ruleDirs", [])
            if not rule_dirs:
                result = {"matches": [], "message": "No rule directories configured in sgconfig.yml"}
            else:
                for rule_dir in rule_dirs:
                    rule_dir_path = Path(rule_dir)
                    if not rule_dir_path.exists():
                        logger.warning(f"Rule directory not found: {rule_dir_path}")
                        continue
                        
                    scan_summary["directories_scanned"] += 1
                    
                    # Find all rule files in the directory
                    rule_files = list(rule_dir_path.glob("*.yml")) + list(rule_dir_path.glob("*.yaml"))
                    
                    for rule_file in rule_files:
                        try:
                            # Execute scan for this rule file
                            scan_result = await executor.scan(
                                rule_file=str(rule_file),
                                paths=[input_data.path],
                                additional_args=["--json"] if input_data.output_format == "json" else []
                            )
                            
                            scan_summary["rules_processed"] += 1
                            
                            # Process scan results
                            if scan_result.get("success") and scan_result.get("parsed_output"):
                                matches = scan_result["parsed_output"]
                                all_matches.extend(matches)
                                scan_summary["total_violations"] += len(matches)
                                
                                scan_summary["execution_details"].append({
                                    "rule_file": str(rule_file),
                                    "matches_found": len(matches),
                                    "status": "success"
                                })
                            elif scan_result.get("stderr"):
                                logger.warning(f"Scan warning for {rule_file}: {scan_result['stderr']}")
                                scan_summary["execution_details"].append({
                                    "rule_file": str(rule_file),
                                    "matches_found": 0,
                                    "status": "warning",
                                    "message": scan_result["stderr"]
                                })
                            else:
                                scan_summary["execution_details"].append({
                                    "rule_file": str(rule_file),
                                    "matches_found": 0,
                                    "status": "no_matches"
                                })
                                
                        except Exception as e:
                            logger.error(f"Failed to scan with rule file {rule_file}: {e}")
                            scan_summary["execution_details"].append({
                                "rule_file": str(rule_file),
                                "matches_found": 0,
                                "status": "error",
                                "message": str(e)
                            })
                
                # Create combined result
                result = {
                    "success": True,
                    "matches": all_matches,
                    "summary": scan_summary,
                    "path": input_data.path,
                    "returncode": 0,
                    "config": config  # Include config for cache validation
                }
    else:
        # No sgconfig.yml found
        raise ValueError("ast-grep scan requires an sgconfig.yml file in the project directory or a custom config path")
    
    return result


def _format_single_match(match: Dict[str, Any], input_data: SearchToolInput) -> Dict[str, Any]:
    """Format a single match for streaming output.
    
    Args:
        match: Single match result
        input_data: Original input parameters
        
    Returns:
        Formatted match dictionary
    """
    return {
        "file": match.get("file", ""),
        "text": match.get("text", ""),
        "range": {
            "start": {
                "line": match.get("range", {}).get("start", {}).get("line", 0),
                "column": match.get("range", {}).get("start", {}).get("column", 0)
            },
            "end": {
                "line": match.get("range", {}).get("end", {}).get("line", 0),
                "column": match.get("range", {}).get("end", {}).get("column", 0)
            }
        },
        "metaVariables": match.get("metaVariables", {}),
        "detectedLanguage": input_data.language
    }


def _build_search_args(input_data: SearchToolInput) -> List[str]:
    """Build additional arguments for ast-grep search command.
    
    Args:
        input_data: Validated input parameters
        
    Returns:
        List of additional command arguments
    """
    args = []
    
    # Add JSON output flag for structured results
    args.append("--json")
    
    # Handle recursive flag - ast-grep searches recursively by default
    # Only add --no-recurse if recursive is False
    if not input_data.recursive:
        args.append("--no-recurse")
    
    # Handle custom include globs (takes priority over language-based patterns)
    if input_data.include_globs:
        for pattern in input_data.include_globs:
            args.extend(["--include", pattern])
    else:
        # Add file inclusion patterns based on language as fallback
        # This helps with glob pattern support for specific file types
        lang_manager = get_language_manager()
        try:
            language_info = lang_manager.get_language_info(input_data.language)
            extensions = language_info.get("extensions", [])
            
            # Add include patterns for the language's file extensions
            # ast-grep supports glob patterns with --include flag
            for ext in extensions:
                # Convert extension to glob pattern (e.g., ".js" -> "*.js")
                glob_pattern = f"*{ext}"
                args.extend(["--include", glob_pattern])
                
        except ValueError:
            # Language validation already happened, so this shouldn't occur
            logger.warning(f"Could not get language info for {input_data.language}")
    
    # Handle exclude globs
    if input_data.exclude_globs:
        for pattern in input_data.exclude_globs:
            args.extend(["--exclude", pattern])
    
    return args


def _format_search_results_json(result: Dict[str, Any], input_data: SearchToolInput) -> Dict[str, Any]:
    """Format search results as structured JSON.
    
    Args:
        result: Raw result from AST-Grep executor
        input_data: Original input parameters
        
    Returns:
        Formatted result dictionary
    """
    formatted_matches = []
    
    if "matches" in result and result["matches"]:
        for match in result["matches"]:
            formatted_match = {
                "file": match.get("file", ""),
                "text": match.get("text", ""),
                "range": {
                    "start": {
                        "line": match.get("range", {}).get("start", {}).get("line", 0),
                        "column": match.get("range", {}).get("start", {}).get("column", 0)
                    },
                    "end": {
                        "line": match.get("range", {}).get("end", {}).get("line", 0),
                        "column": match.get("range", {}).get("end", {}).get("column", 0)
                    }
                },
                "metaVariables": match.get("metaVariables", {}),
                "detectedLanguage": input_data.language
            }
            formatted_matches.append(formatted_match)
    
    return {
        "matches": formatted_matches,
        "pattern": input_data.pattern,
        "language": input_data.language,
        "path": input_data.path,
        "recursive": input_data.recursive,
        "totalMatches": len(formatted_matches),
        "status": "success" if result.get("returncode") == 0 else "completed_with_issues",
        "executionTime": result.get("execution_time"),
        "command": result.get("command", [])
    }


def _format_search_results_text(result: Dict[str, Any], input_data: SearchToolInput) -> str:
    """Format search results as human-readable text.
    
    Args:
        result: Raw result from AST-Grep executor  
        input_data: Original input parameters
        
    Returns:
        Formatted text string
    """
    lines = []
    lines.append(f"AST-Grep Search Results")
    lines.append(f"Pattern: {input_data.pattern}")
    lines.append(f"Language: {input_data.language}")
    lines.append(f"Path: {input_data.path}")
    lines.append(f"Recursive: {input_data.recursive}")
    lines.append("")
    
    if "matches" in result and result["matches"]:
        lines.append(f"Found {len(result['matches'])} matches:")
        lines.append("")
        
        for i, match in enumerate(result["matches"], 1):
            lines.append(f"Match {i}:")
            lines.append(f"  File: {match.get('file', 'Unknown')}")
            lines.append(f"  Line: {match.get('range', {}).get('start', {}).get('line', 'Unknown')}")
            lines.append(f"  Text: {match.get('text', '').strip()}")
            if match.get("metaVariables"):
                lines.append(f"  Variables: {match['metaVariables']}")
            lines.append("")
    else:
        lines.append("No matches found.")
        lines.append("")
    
    lines.append(f"Status: {'Success' if result.get('returncode') == 0 else 'Completed with issues'}")
    if result.get("execution_time"):
        lines.append(f"Execution time: {result['execution_time']}s")
    
    return "\n".join(lines)


def _format_scan_results_json(result: Dict[str, Any], input_data: ScanToolInput, config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Format scan results as structured JSON.
    
    Args:
        result: Raw result from AST-Grep executor
        input_data: Original input parameters
        config: Parsed sgconfig.yml configuration
        
    Returns:
        Formatted result dictionary
    """
    formatted_violations = []
    
    if "matches" in result and result["matches"]:
        for match in result["matches"]:
            formatted_violation = {
                "ruleId": match.get("ruleId", match.get("rule", {}).get("id", "unknown")),
                "severity": match.get("severity", "warning"),
                "message": match.get("message", "Rule violation detected"),
                "file": match.get("file", ""),
                "range": {
                    "start": {
                        "line": match.get("range", {}).get("start", {}).get("line", 0),
                        "column": match.get("range", {}).get("start", {}).get("column", 0)
                    },
                    "end": {
                        "line": match.get("range", {}).get("end", {}).get("line", 0),
                        "column": match.get("range", {}).get("end", {}).get("column", 0)
                    }
                },
                "text": match.get("text", ""),
                "fix": match.get("fix"),
                "note": match.get("note"),
                "url": match.get("url")
            }
            formatted_violations.append(formatted_violation)
    
    # Include scan summary if available
    scan_summary = result.get("summary", {})
    
    return {
        "violations": formatted_violations,
        "path": input_data.path,
        "configPath": config.get("_config_path") if config else None,
        "ruleDirs": config.get("ruleDirs", []) if config else [],
        "totalViolations": len(formatted_violations),
        "status": "success" if result.get("returncode") == 0 else "completed_with_issues",
        "executionTime": result.get("execution_time"),
        "command": result.get("command", []),
        "scanSummary": {
            "rulesProcessed": scan_summary.get("rules_processed", 0),
            "directoriesScanned": scan_summary.get("directories_scanned", 0),
            "totalViolations": scan_summary.get("total_violations", len(formatted_violations)),
            "executionDetails": scan_summary.get("execution_details", [])
        }
    }


def _format_scan_results_text(result: Dict[str, Any], input_data: ScanToolInput, config: Optional[Dict[str, Any]]) -> str:
    """Format scan results as human-readable text.
    
    Args:
        result: Raw result from AST-Grep executor
        input_data: Original input parameters
        config: Parsed sgconfig.yml configuration
        
    Returns:
        Formatted text string
    """
    lines = []
    lines.append(f"AST-Grep Scan Results")
    lines.append(f"Path: {input_data.path}")
    
    if config:
        lines.append(f"Rule Directories: {', '.join(config.get('ruleDirs', []))}")
        lines.append(f"Config File: {config.get('_config_path', 'N/A')}")
    
    # Add scan summary if available
    scan_summary = result.get("summary", {})
    if scan_summary:
        lines.append(f"Rules Processed: {scan_summary.get('rules_processed', 0)}")
        lines.append(f"Directories Scanned: {scan_summary.get('directories_scanned', 0)}")
    
    lines.append("")
    
    if "matches" in result and result["matches"]:
        total_violations = len(result["matches"])
        lines.append(f"Found {total_violations} violations:")
        lines.append("")
        
        for i, match in enumerate(result["matches"], 1):
            lines.append(f"Violation {i}:")
            lines.append(f"  Rule: {match.get('ruleId', match.get('rule', {}).get('id', 'unknown'))}")
            lines.append(f"  Severity: {match.get('severity', 'warning')}")
            lines.append(f"  File: {match.get('file', 'Unknown')}")
            lines.append(f"  Line: {match.get('range', {}).get('start', {}).get('line', 'Unknown')}")
            lines.append(f"  Message: {match.get('message', 'Rule violation detected')}")
            lines.append(f"  Text: {match.get('text', '').strip()}")
            
            if match.get("fix"):
                lines.append(f"  Suggested Fix: {match['fix']}")
            
            if match.get("note"):
                lines.append(f"  Note: {match['note']}")
                
            if match.get("url"):
                lines.append(f"  Documentation: {match['url']}")
            
            lines.append("")
    else:
        lines.append("No violations found.")
        lines.append("")
    
    # Add execution details if available
    if scan_summary and scan_summary.get("execution_details"):
        lines.append("Execution Details:")
        for detail in scan_summary["execution_details"]:
            lines.append(f"  {detail['rule_file']}: {detail['status']} ({detail['matches_found']} matches)")
            if detail.get("message"):
                lines.append(f"    Message: {detail['message']}")
        lines.append("")
    
    lines.append(f"Status: {'Success' if result.get('returncode') == 0 else 'Completed with issues'}")
    if result.get("execution_time"):
        lines.append(f"Execution time: {result['execution_time']}s")
    
    return "\n".join(lines)


@audit_operation("ast_grep_run", SecurityLevel.SENSITIVE)
async def ast_grep_run_impl(input_data: RunToolInput, ast_grep_path: Path) -> List[TextContent]:
    """Execute ast-grep run operation for code transformations.
    
    Args:
        input_data: Validated input parameters
        ast_grep_path: Path to ast-grep binary
        
    Returns:
        List of text content with run results
    """
    try:
        logger.info(f"Executing run with pattern: {input_data.pattern}")
        
        # Check if rewrite pattern is provided
        if not input_data.rewrite:
            error_result = create_error_response(
                error_type="Missing Rewrite Pattern",
                message="Rewrite pattern is required for code transformations",
                path=input_data.path,
                suggestions=[
                    "Provide a rewrite pattern using meta-variables from the search pattern",
                    "Use the same meta-variables in both pattern and rewrite for substitution",
                    "Example: pattern='console.log($MSG)', rewrite='logger.info($MSG)'"
                ]
            )
            return format_tool_response(
                data=error_result,
                output_format=input_data.output_format,
                success=False
            )
        
        # Get the language manager for ast-grep language mapping
        lang_manager = get_language_manager()
        ast_grep_language = lang_manager.map_to_ast_grep_language(input_data.language)
        
        # Create AST-Grep executor
        executor = await create_ast_grep_executor(binary_path=ast_grep_path)
        
        # Prepare paths for transformation
        paths = [input_data.path] if input_data.path else None
        
        # Build additional arguments for JSON output
        additional_args = ["--json"]
        
        # Execute the run command (always defaults to dry-run for safety)
        result = await executor.run(
            pattern=input_data.pattern,
            rewrite=input_data.rewrite,
            language=ast_grep_language,
            paths=paths,
            dry_run=input_data.dry_run,
            additional_args=additional_args
        )
        
        # Process the results
        if input_data.output_format == "json":
            formatted_result = _format_run_results_json(result, input_data)
            return [TextContent(type="text", text=json.dumps(formatted_result, indent=2))]
        else:
            formatted_result = _format_run_results_text(result, input_data)
            return [TextContent(type="text", text=formatted_result)]
            
    except ASTGrepError as e:
        error_result = handle_execution_error(
            error=e,
            path=input_data.path
        )
        
        return format_tool_response(
            data=error_result,
            output_format=input_data.output_format,
            success=False
        )
    
    except Exception as e:
        logger.exception(f"Unexpected error during run: {e}")
        error_result = create_error_response(
            error_type="Unexpected Error",
            message=str(e),
            path=input_data.path,
            suggestions=[
                "Check the pattern and rewrite syntax",
                "Verify the language identifier is correct", 
                "Ensure the target path exists and is accessible",
                "Review meta-variable usage in pattern and rewrite"
            ]
        )
        
        return format_tool_response(
            data=error_result,
            output_format=input_data.output_format,
            success=False
        )


def _format_run_results_json(result: Dict[str, Any], input_data: RunToolInput) -> Dict[str, Any]:
    """Format run results as structured JSON with enhanced validation and preview.
    
    Args:
        result: Raw result from AST-Grep executor
        input_data: Original input parameters
        
    Returns:
        Formatted result dictionary with validation and preview information
    """
    from .utils import (
        extract_meta_variables, validate_rewrite_pattern_syntax,
        validate_transformation_safety, generate_transformation_preview,
        create_transformation_report
    )
    
    # Parse ast-grep output if it's JSON string
    transformations = []
    raw_output = result.get('stdout', '')
    
    if raw_output and raw_output.strip():
        try:
            # Try to parse JSON output from ast-grep
            if raw_output.strip().startswith('[') or raw_output.strip().startswith('{'):
                parsed_output = json.loads(raw_output)
                if isinstance(parsed_output, list):
                    transformations = parsed_output
                else:
                    transformations = [parsed_output]
        except json.JSONDecodeError:
            # If not JSON, treat as plain text
            transformations = [{
                "text": raw_output,
                "type": "text_output"
            }]
    
    # Enhanced validation and preview for rewrite operations
    validation_result = None
    safety_result = None
    preview_info = None
    
    if input_data.rewrite and transformations:
        # Validate rewrite pattern syntax
        validation_result = validate_rewrite_pattern_syntax(
            input_data.pattern, input_data.rewrite, input_data.language
        )
        
        # Analyze transformation safety
        safety_result = validate_transformation_safety(
            input_data.pattern, input_data.rewrite, input_data.language, transformations
        )
        
        # Generate transformation preview
        preview_info = generate_transformation_preview(
            input_data.pattern, input_data.rewrite, transformations[:10], input_data.language
        )
    
    # Extract meta-variables from pattern for documentation
    meta_variables = extract_meta_variables(input_data.pattern)
    
    formatted_result = {
        "operation": "run",
        "status": "success" if result.get('success', False) else "error",
        "parameters": {
            "pattern": input_data.pattern,
            "rewrite": input_data.rewrite,
            "language": input_data.language,
            "path": input_data.path,
            "dry_run": input_data.dry_run
        },
        "meta_variables": meta_variables,
        "transformations": transformations,
        "summary": {
            "total_transformations": len(transformations),
            "dry_run_mode": input_data.dry_run,
            "files_processed": len(set(t.get('file', '') for t in transformations if t.get('file')))
        },
        "execution_info": {
            "exit_code": result.get('exit_code', 0),
            "command_executed": result.get('command', []),
            "working_directory": result.get('cwd', '')
        }
    }
    
    # Add validation and safety analysis if available
    if validation_result:
        formatted_result["validation"] = validation_result
    
    if safety_result:
        formatted_result["safety_analysis"] = safety_result
    
    if preview_info:
        formatted_result["preview"] = preview_info
    
    # Enhanced warnings based on validation and safety analysis
    warnings = []
    if input_data.dry_run:
        warnings.append("This was a dry-run. No files were actually modified.")
    elif transformations:
        warnings.append("Files were modified. Please review changes carefully.")
    
    if safety_result and safety_result.get("risk_level") == "high":
        warnings.append("High-risk transformation detected. Review blocking issues.")
    elif safety_result and safety_result.get("risk_level") == "medium":
        warnings.append("Medium-risk transformation. Test on a subset first.")
    
    if validation_result and not validation_result.get("valid"):
        warnings.append("Pattern validation issues detected. Review errors.")
    
    if warnings:
        formatted_result["warnings"] = warnings
    
    # Add stderr output if present
    if result.get('stderr'):
        formatted_result["stderr"] = result['stderr']
    
    # Add recommendations if available
    if safety_result and safety_result.get("recommendations"):
        formatted_result["recommendations"] = safety_result["recommendations"]
    
    return formatted_result


def _format_run_results_text(result: Dict[str, Any], input_data: RunToolInput) -> str:
    """Format run results as human-readable text with enhanced validation and preview.
    
    Args:
        result: Raw result from AST-Grep executor
        input_data: Original input parameters
        
    Returns:
        Formatted text result with validation and preview information
    """
    from .utils import (
        validate_rewrite_pattern_syntax, validate_transformation_safety,
        generate_transformation_preview, create_diff_visualization
    )
    
    lines = []
    
    # Header
    lines.append("=" * 60)
    lines.append("AST-Grep Code Transformation Results")
    lines.append("=" * 60)
    
    # Parameters
    lines.append(f"Pattern:    {input_data.pattern}")
    lines.append(f"Rewrite:    {input_data.rewrite}")
    lines.append(f"Language:   {input_data.language}")
    lines.append(f"Path:       {input_data.path}")
    lines.append(f"Dry Run:    {'Yes' if input_data.dry_run else 'No'}")
    lines.append("")
    
    # Parse transformations
    transformations = []
    raw_output = result.get('stdout', '')
    
    if raw_output and raw_output.strip():
        try:
            # Try to parse JSON output from ast-grep
            if raw_output.strip().startswith('[') or raw_output.strip().startswith('{'):
                parsed_output = json.loads(raw_output)
                transformations = parsed_output if isinstance(parsed_output, list) else [parsed_output]
        except json.JSONDecodeError:
            pass
    
    # Validation Section (if rewrite pattern exists)
    if input_data.rewrite and transformations:
        validation_result = validate_rewrite_pattern_syntax(
            input_data.pattern, input_data.rewrite, input_data.language
        )
        
        lines.append("Pattern Validation:")
        lines.append("-" * 40)
        if validation_result["valid"]:
            lines.append("✅ Pattern validation passed")
        else:
            lines.append("❌ Pattern validation failed")
            for error in validation_result["errors"]:
                lines.append(f"   • Error: {error}")
        
        if validation_result["warnings"]:
            for warning in validation_result["warnings"]:
                lines.append(f"   ⚠️  Warning: {warning}")
        
        if validation_result["suggestions"]:
            for suggestion in validation_result["suggestions"]:
                lines.append(f"   💡 Suggestion: {suggestion}")
        
        lines.append("")
        
        # Safety Analysis
        safety_result = validate_transformation_safety(
            input_data.pattern, input_data.rewrite, input_data.language, transformations
        )
        
        lines.append("Safety Analysis:")
        lines.append("-" * 40)
        risk_icons = {"low": "🟢", "medium": "🟡", "high": "🔴"}
        risk_level = safety_result.get("risk_level", "low")
        lines.append(f"{risk_icons.get(risk_level, '🟢')} Risk Level: {risk_level.upper()}")
        
        if safety_result.get("blocking_issues"):
            lines.append("❌ Blocking Issues:")
            for issue in safety_result["blocking_issues"]:
                lines.append(f"   • {issue}")
        
        if safety_result.get("warnings"):
            lines.append("⚠️  Safety Warnings:")
            for warning in safety_result["warnings"]:
                lines.append(f"   • {warning}")
        
        if safety_result.get("recommendations"):
            lines.append("💡 Recommendations:")
            for rec in safety_result["recommendations"]:
                lines.append(f"   • {rec}")
        
        lines.append("")
    
    # Transformation Results
    if transformations:
        lines.append("Transformations:")
        lines.append("-" * 40)
        
        for i, transformation in enumerate(transformations[:5], 1):  # Show first 5
            lines.append(f"\n{i}. Transformation:")
            if transformation.get('file'):
                lines.append(f"   📁 File: {transformation['file']}")
            if transformation.get('range'):
                range_info = transformation['range']
                start = range_info.get('start', {})
                end = range_info.get('end', {})
                lines.append(f"   📍 Location: Line {start.get('line', '?')}-{end.get('line', '?')}")
            
            # Show diff if we have both original and replacement
            if transformation.get('text') and transformation.get('replacement'):
                original = transformation['text']
                replacement = transformation['replacement']
                
                lines.append("   📝 Diff:")
                diff = create_diff_visualization(original, replacement, context_lines=1)
                for diff_line in diff.splitlines():
                    lines.append(f"      {diff_line}")
            elif transformation.get('text'):
                lines.append(f"   📄 Original: {transformation['text']}")
                if transformation.get('replacement'):
                    lines.append(f"   ✏️  Modified: {transformation['replacement']}")
        
        if len(transformations) > 5:
            lines.append(f"\n... and {len(transformations) - 5} more transformation(s)")
        
        lines.append(f"\n📊 Summary: {len(transformations)} transformation(s) found")
        files_affected = len(set(t.get('file', '') for t in transformations if t.get('file')))
        if files_affected:
            lines.append(f"📁 Files affected: {files_affected}")
    elif raw_output and raw_output.strip():
        lines.append("Raw Output:")
        lines.append("-" * 40)
        lines.append(raw_output)
    else:
        lines.append("No transformations found.")
    
    lines.append("")
    
    # Status and warnings
    if result.get('success', False):
        lines.append("✅ Operation completed successfully")
    else:
        lines.append("❌ Operation failed")
    
    if input_data.dry_run:
        lines.append("⚠️  DRY RUN MODE - No files were actually modified")
    elif transformations:
        lines.append("⚠️  Files were modified - Please review changes carefully")
    
    # Error output if present
    if result.get('stderr'):
        lines.append("")
        lines.append("Errors/Warnings:")
        lines.append("-" * 40)
        lines.append(result['stderr'])
    
    # Execution info
    lines.append("")
    lines.append("Execution Details:")
    lines.append("-" * 40)
    lines.append(f"Exit Code: {result.get('exit_code', 0)}")
    lines.append(f"Command: {' '.join(result.get('command', []))}")
    if result.get('cwd'):
        lines.append(f"Working Directory: {result['cwd']}")
    
    return "\n".join(lines)


@audit_operation("call_graph_generate", SecurityLevel.RESTRICTED)
async def call_graph_generate_impl(input_data: CallGraphInput, ast_grep_path: Path) -> List[TextContent]:
    """Generate call graph for the specified codebase.
    
    Args:
        input_data: Validated input parameters
        ast_grep_path: Path to ast-grep binary
        
    Returns:
        List of text content with call graph data
    """
    logger.info(f"Generating call graph for path: {input_data.path}")
    
    try:
        # Create output directory
        output_dir = Path(".reporepo/ast")
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Check for recent cached results (within last 5 minutes)
        call_graph_file = output_dir / "call-graph-base.json"
        if call_graph_file.exists():
            file_age = time.time() - call_graph_file.stat().st_mtime
            if file_age < 300:  # 5 minutes cache
                logger.info(f"Using cached call graph (age: {file_age:.1f}s)")
                try:
                    with open(call_graph_file, 'r') as f:
                        cached_data = json.load(f)
                    
                    summary = {
                        "status": "success (cached)",
                        "files_created": [str(call_graph_file)],
                        "summary": {
                            "total_functions_found": len(cached_data.get("nodes", [])),
                            "total_calls_found": len(cached_data.get("edges", [])),
                            "cached_result": True,
                            "cache_age_seconds": file_age
                        }
                    }
                    return [TextContent(type="text", text=f"Call graph retrieved from cache:\n{json.dumps(summary, indent=2)}")]
                except Exception as e:
                    logger.warning(f"Failed to load cached call graph: {e}")
                    # Continue with fresh generation
        
        # Auto-detect languages if not specified
        languages = input_data.languages
        if not languages:
            languages = _detect_languages_in_directory(input_data.path)
            logger.info(f"Auto-detected languages: {languages}")
        
        # Initialize call graph structure
        nodes = []
        edges = []
        all_function_definitions = []
        all_function_calls = []
        
        # Process all languages in parallel for better performance
        async def process_language(language: str):
            """Process a single language to find function definitions and calls."""
            lang_definitions = []
            lang_calls = []
            
            try:
                # Get language-specific patterns
                def_pattern, call_patterns = _get_language_patterns(language)
                
                # Create all tasks for this language with file filtering
                language_tasks = []
                
                # Build base args with file filtering for better performance
                base_args = [
                    str(ast_grep_path),
                    "run",
                    "--lang", language,
                ]
                
                # Add file filtering to exclude large/irrelevant files
                exclude_globs = [
                    "__pycache__/**",
                    "*.pyc",
                    "*.min.js",
                    "node_modules/**",
                    ".git/**",
                    "venv/**",
                    ".venv/**",
                    "env/**",
                    ".env/**",
                    "build/**",
                    "dist/**",
                    "target/**",
                    "*.egg-info/**",
                    ".tox/**",
                    ".pytest_cache/**",
                    ".mypy_cache/**",
                    ".ruff_cache/**",
                    "htmlcov/**",
                    "*.log"
                ]
                
                # Task for function definitions
                def_args = base_args + [
                    "--pattern", def_pattern,
                    input_data.path,
                    "--json"
                ]
                
                # Add exclude patterns
                for exclude in exclude_globs:
                    def_args.extend(["--exclude-glob", exclude])
                
                language_tasks.append(_run_ast_grep_with_timeout(def_args, "definitions", language, timeout=8.0))
                
                # Only use 1 call pattern for speed (most important one)
                if call_patterns:
                    call_args = base_args + [
                        "--pattern", call_patterns[0],  # Only use the first (most important) pattern
                        input_data.path,
                        "--json"
                    ]
                    
                    # Add exclude patterns
                    for exclude in exclude_globs:
                        call_args.extend(["--exclude-glob", exclude])
                    
                    language_tasks.append(_run_ast_grep_with_timeout(call_args, "calls_0", language, timeout=8.0))
                
                # Execute all tasks for this language in parallel with shorter timeout
                results = await asyncio.wait_for(
                    asyncio.gather(*language_tasks, return_exceptions=True),
                    timeout=15.0  # 15 second timeout per language
                )
                
                # Process results
                for result in results:
                    if isinstance(result, Exception):
                        logger.warning(f"Task failed for language {language}: {result}")
                        continue
                    
                    task_type, data = result
                    if task_type == "definitions":
                        lang_definitions.extend(data)
                    elif task_type.startswith("calls_"):
                        lang_calls.extend(data)
                        
            except asyncio.TimeoutError:
                logger.warning(f"Language processing timed out for {language}")
            except Exception as e:
                logger.error(f"Error processing language {language}: {str(e)}")
            
            return lang_definitions, lang_calls
        
        # Run all languages in parallel with shorter total timeout
        try:
            language_results = await asyncio.wait_for(
                asyncio.gather(*[process_language(lang) for lang in languages], return_exceptions=True),
                timeout=20.0  # 20 second total timeout for faster response
            )
            
            # Combine results from all languages
            for result in language_results:
                if isinstance(result, Exception):
                    logger.warning(f"Language processing failed: {result}")
                    continue
                
                lang_definitions, lang_calls = result
                all_function_definitions.extend(lang_definitions)
                all_function_calls.extend(lang_calls)
                
        except asyncio.TimeoutError:
            logger.error("Call graph generation timed out")
            return [TextContent(type="text", text="Error: Call graph generation timed out. Try specifying specific languages or a smaller path.")]
        
        # Extract function names from definitions for node creation
        function_names = set()
        for definition in all_function_definitions:
            meta_vars = definition.get("metaVariables", {})
            single_vars = meta_vars.get("single", {})
            if single_vars.get("FUNC_NAME"):
                func_name = single_vars["FUNC_NAME"]["text"]
                function_names.add(func_name)
                nodes.append({
                    "id": func_name,
                    "type": "function",
                    "file": definition.get("file", ""),
                    "line": definition.get("range", {}).get("start", {}).get("line", 0)
                })
        
        # Create edges from function calls
        for call in all_function_calls:
            meta_vars = call.get("metaVariables", {})
            single_vars = meta_vars.get("single", {})
            
            # Extract function name from various metavariables
            called_func = None
            call_type = "unknown"
            
            # Try different metavariable names based on patterns used
            if single_vars.get("CALL_NAME"):
                called_func = single_vars["CALL_NAME"]["text"]
                call_type = "function_call"
            elif single_vars.get("METHOD"):
                called_func = single_vars["METHOD"]["text"]
                call_type = "method_call"
                # For method calls, also get the object if available
                if single_vars.get("OBJ"):
                    obj_name = single_vars["OBJ"]["text"]
                    called_func = f"{obj_name}.{called_func}"
            elif single_vars.get("ASYNC_CALL"):
                called_func = single_vars["ASYNC_CALL"]["text"]
                call_type = "async_call"
            elif single_vars.get("FUNC"):
                called_func = single_vars["FUNC"]["text"]
                call_type = "module_function"
                # For module functions, also get the module if available
                if single_vars.get("MODULE"):
                    module_name = single_vars["MODULE"]["text"]
                    called_func = f"{module_name}.{called_func}"
            elif single_vars.get("CONSTRUCTOR"):
                called_func = single_vars["CONSTRUCTOR"]["text"]
                call_type = "constructor_call"
            elif single_vars.get("STATIC_METHOD"):
                called_func = single_vars["STATIC_METHOD"]["text"]
                call_type = "static_method"
                if single_vars.get("CLASS"):
                    class_name = single_vars["CLASS"]["text"]
                    called_func = f"{class_name}.{called_func}"
            
            if called_func:
                caller_file = call.get("file", "")
                
                # Try to determine caller function (simplified)
                caller_func = f"<anonymous>:{Path(caller_file).name}"
                
                # Create edge regardless of whether target function is in our function_names
                # This helps identify external calls and missed function definitions
                edges.append({
                    "from": caller_func,
                    "to": called_func,
                    "type": call_type,
                    "file": caller_file,
                    "line": call.get("range", {}).get("start", {}).get("line", 0),
                    "in_scope": called_func in function_names
                })
        
        # Build final call graph
        call_graph = {
            "nodes": nodes,
            "edges": edges,
        "metadata": {
                "total_functions": len(nodes),
                "total_calls": len(edges),
                "languages": languages,
                "path": input_data.path,
                "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "include_external": input_data.include_external
            }
        }
        
        # Save files
        files_saved = []
        
        # Save main call graph
        graph_output_file = output_dir / "call-graph-base.json"
        with open(graph_output_file, 'w') as f:
            json.dump(call_graph, f, indent=2)
        files_saved.append(str(graph_output_file))
        
        # Save function definitions
        definitions_file = output_dir / "function-definitions.json"
        with open(definitions_file, 'w') as f:
            json.dump(all_function_definitions, f, indent=2)
        files_saved.append(str(definitions_file))
        
        # Save function calls
        calls_file = output_dir / "function-calls.json"
        with open(calls_file, 'w') as f:
            json.dump(all_function_calls, f, indent=2)
        files_saved.append(str(calls_file))
        
        # Create summary
        summary = {
            "status": "success",
            "files_created": files_saved,
            "summary": {
                "total_functions_found": len(nodes),
                "total_calls_found": len(edges),
                "languages_analyzed": languages,
                "output_directory": str(output_dir)
        }
    }
    
        logger.info(f"Call graph generation completed. Files saved: {files_saved}")
        
        return [TextContent(type="text", text=f"Call graph generated successfully:\n{json.dumps(summary, indent=2)}")]
        
    except Exception as e:
        error_msg = f"Error generating call graph: {str(e)}"
        logger.error(error_msg)
        return [TextContent(type="text", text=f"Error: {error_msg}")]


def _detect_languages_in_directory(directory_path: str) -> List[str]:
    """Auto-detect programming languages in a directory based on file extensions."""
    language_mapping = {
        '.py': 'python',
        '.js': 'javascript', 
        '.jsx': 'javascript',
        '.ts': 'typescript',
        '.tsx': 'typescript',
        '.rs': 'rust',
        '.java': 'java',
        '.kt': 'kotlin',
        '.go': 'go',
        '.cpp': 'cpp',
        '.cc': 'cpp',
        '.cxx': 'cpp',
        '.c': 'c',
        '.h': 'c',
        '.hpp': 'cpp',
        '.cs': 'csharp',
        '.rb': 'ruby',
        '.php': 'php',
        '.swift': 'swift',
        '.scala': 'scala',
        '.sh': 'bash',
        '.bash': 'bash'
    }
    
    # Directories to skip for performance
    skip_dirs = {
        'node_modules', '.git', '__pycache__', '.pytest_cache', 
        'venv', 'env', '.venv', '.env', 'build', 'dist', 'target',
        '.tox', '.coverage', 'htmlcov', '.mypy_cache', '.ruff_cache',
        'egg-info', '.eggs', '.idea', '.vscode', '.vs'
    }
    
    detected_languages = set()
    files_checked = 0
    max_files_to_check = 50  # Limit file scanning for speed
    
    try:
        path_obj = Path(directory_path)
        if path_obj.is_file():
            # Single file
            suffix = path_obj.suffix.lower()
            if suffix in language_mapping:
                detected_languages.add(language_mapping[suffix])
        else:
            # Directory - fast scan with limitations
            for file_path in path_obj.rglob('*'):
                # Skip if we've checked enough files
                if files_checked >= max_files_to_check:
                    break
                    
                # Skip directories we don't want to scan
                if any(skip_dir in str(file_path) for skip_dir in skip_dirs):
                    continue
                    
                if file_path.is_file():
                    files_checked += 1
                    suffix = file_path.suffix.lower()
                    if suffix in language_mapping:
                        detected_languages.add(language_mapping[suffix])
                    
                    # Stop after finding 3 languages for speed
                    if len(detected_languages) >= 3:
                        break
    except Exception as e:
        logger.warning(f"Error detecting languages in {directory_path}: {e}")
        return ["python"]  # Default fallback
    
    return list(detected_languages) if detected_languages else ["python"]


def _get_language_patterns(language: str) -> Tuple[str, List[str]]:
    """Get function definition and call patterns for a specific language."""
    if language == "python":
        def_pattern = "def $FUNC_NAME"
        call_patterns = [
            "$CALL_NAME($$$)",  # Basic function calls
            "$OBJ.$METHOD($$$)",  # Method calls
        ]
    elif language in ["javascript", "js", "typescript", "ts"]:
        def_pattern = "function $FUNC_NAME"
        call_patterns = [
            "$CALL_NAME($$$)",  # Basic function calls
            "$OBJ.$METHOD($$$)",  # Method calls
        ]
    elif language == "rust":
        def_pattern = "fn $FUNC_NAME"
        call_patterns = [
            "$CALL_NAME($$$)",  # Function calls
            "$OBJ.$METHOD($$$)",  # Method calls
        ]
    elif language == "java":
        def_pattern = "$TYPE $FUNC_NAME"
        call_patterns = [
            "$CALL_NAME($$$)",  # Method calls
            "$OBJ.$METHOD($$$)",  # Instance method calls
        ]
    else:
        # Generic patterns for other languages
        def_pattern = "def $FUNC_NAME"
        call_patterns = [
            "$CALL_NAME($$$)",
            "$OBJ.$METHOD($$$)",
        ]
    
    return def_pattern, call_patterns


async def _run_ast_grep_with_timeout(args: List[str], task_type: str, language: str, timeout: float = 8.0) -> Tuple[str, List[dict]]:
    """Run ast-grep command with timeout and return parsed results."""
    try:
        process = await asyncio.wait_for(
            asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            ),
            timeout=timeout
        )
        
        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=timeout
        )
        
        if process.returncode == 0 and stdout:
            try:
                data = json.loads(stdout.decode())
                return task_type, data
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse JSON for {task_type} in {language}: {e}")
                return task_type, []
        else:
            if stderr:
                logger.debug(f"ast-grep stderr for {task_type} in {language}: {stderr.decode()}")
            return task_type, []
            
    except asyncio.TimeoutError:
        logger.warning(f"ast-grep timeout for {task_type} in {language}")
        return task_type, []
    except Exception as e:
        logger.warning(f"ast-grep error for {task_type} in {language}: {e}")
        return task_type, []


def register_tools(server: Server, ast_grep_path: Path) -> None:
    """Register all AST-Grep tools with the MCP server.
    
    Args:
        server: MCP server instance
        ast_grep_path: Path to ast-grep binary
    """
    
    # First, register tool schemas
    @server.list_tools()
    async def list_ast_grep_tools() -> List[Tool]:
        """List all available AST-Grep tools."""
        return [
            Tool(
                name="ast_grep_search",
                description="Search for AST patterns in code using ast-grep",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "pattern": {
                            "type": "string",
                            "description": "AST pattern to search for (e.g., 'console.log($GREETING)')",
                            "minLength": 1,
                            "maxLength": 8192
                        },
                        "language": {
                            "type": "string",
                            "description": "Programming language identifier (js, ts, py, rust, etc.)",
                            "minLength": 1,
                            "maxLength": 50
                        },
                        "path": {
                            "type": "string",
                            "description": "File or directory path to search",
                            "minLength": 1,
                            "maxLength": 4096
                        },
                        "recursive": {
                            "type": "boolean",
                            "description": "Search recursively in directories",
                            "default": True
                        },
                        "output_format": {
                            "type": "string",
                            "description": "Output format (json/text)",
                            "enum": ["json", "text"],
                            "default": "json"
                        },
                        "include_globs": {
                            "type": "array",
                            "description": "Custom file glob patterns to include (e.g., ['*.test.js', '*.spec.ts'])",
                            "items": {"type": "string"},
                            "maxItems": 100
                        },
                        "exclude_globs": {
                            "type": "array",
                            "description": "File glob patterns to exclude (e.g., ['node_modules/**', '*.min.js'])",
                            "items": {"type": "string"},
                            "maxItems": 100
                        }
                    },
                    "required": ["pattern", "language", "path"]
                }
            ),
            Tool(
                name="ast_grep_scan",
                description="Scan codebase with predefined rules using ast-grep",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Directory path to scan",
                            "minLength": 1,
                            "maxLength": 4096
                        },
                        "rules_config": {
                            "type": "string",
                            "description": "Path to sgconfig.yml or custom rules",
                            "maxLength": 4096
                        },
                        "output_format": {
                            "type": "string",
                            "description": "Output format (json/text)",
                            "enum": ["json", "text"],
                            "default": "json"
                        }
                    },
                    "required": ["path"]
                }
            ),
            Tool(
                name="ast_grep_run",
                description="Run one-time queries with pattern and rewrite capabilities",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "pattern": {
                            "type": "string",
                            "description": "AST pattern for matching",
                            "minLength": 1,
                            "maxLength": 8192
                        },
                        "rewrite": {
                            "type": "string",
                            "description": "Rewrite pattern for transformations",
                            "maxLength": 8192
                        },
                        "language": {
                            "type": "string",
                            "description": "Programming language identifier",
                            "minLength": 1,
                            "maxLength": 50
                        },
                        "path": {
                            "type": "string",
                            "description": "File or directory path",
                            "minLength": 1,
                            "maxLength": 4096
                        },
                        "dry_run": {
                            "type": "boolean",
                            "description": "Preview changes without applying them",
                            "default": True
                        },
                        "output_format": {
                            "type": "string",
                            "description": "Output format (json/text)",
                            "enum": ["json", "text"],
                            "default": "json"
                        }
                    },
                    "required": ["pattern", "language", "path"]
                }
            ),
            Tool(
                name="call_graph_generate",
                description="Generate call graph for the specified codebase",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Directory path to analyze",
                            "minLength": 1,
                            "maxLength": 4096
                        },
                        "languages": {
                            "type": "array",
                            "description": "List of languages to include (max 20 languages)",
                            "items": {"type": "string"},
                            "maxItems": 20
                        },
                        "include_external": {
                            "type": "boolean",
                            "description": "Include external library calls",
                            "default": False
                        }
                    },
                    "required": ["path"]
                }
            )
        ]
    
    # Then, register tool implementations
    @server.call_tool()
    async def ast_grep_search(arguments: Dict[str, Any]) -> List[TextContent]:
        """Search for AST patterns in code using ast-grep."""
        input_data = SearchToolInput(**arguments)
        return await ast_grep_search_tool_impl(input_data, ast_grep_path)
    
    @server.call_tool()
    async def ast_grep_scan(arguments: Dict[str, Any]) -> List[TextContent]:
        """Scan codebase with predefined rules using ast-grep."""
        input_data = ScanToolInput(**arguments)
        return await ast_grep_scan_tool_impl(input_data, ast_grep_path)
    
    @server.call_tool()
    async def ast_grep_run(arguments: Dict[str, Any]) -> List[TextContent]:
        """Run one-time queries with pattern and rewrite capabilities."""
        input_data = RunToolInput(**arguments)
        return await ast_grep_run_tool_impl(input_data, ast_grep_path)
    
    @server.call_tool()
    async def call_graph_generate(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
        """Generate call graph for the specified codebase."""
        input_data = CallGraphInput(**arguments)
        return await call_graph_generate_tool_impl(input_data, ast_grep_path)
    
    logger.info("All AST-Grep tools registered successfully with schemas and implementations")


# Tool implementation functions to avoid conflicts with MCP handlers
async def ast_grep_search_tool_impl(input_data: SearchToolInput, ast_grep_path: Path) -> List[TextContent]:
    """Implementation of ast_grep_search tool."""
    return await ast_grep_search_impl(input_data, ast_grep_path)


async def ast_grep_scan_tool_impl(input_data: ScanToolInput, ast_grep_path: Path) -> List[TextContent]:
    """Implementation of ast_grep_scan tool."""
    return await ast_grep_scan_impl(input_data, ast_grep_path)


async def ast_grep_run_tool_impl(input_data: RunToolInput, ast_grep_path: Path) -> List[TextContent]:
    """Implementation of ast_grep_run tool."""
    return await ast_grep_run_impl(input_data, ast_grep_path)


async def call_graph_generate_tool_impl(input_data: CallGraphInput, ast_grep_path: Path) -> List[TextContent]:
    """Implementation of call_graph_generate tool."""
    return await call_graph_generate_impl(input_data, ast_grep_path)


def _discover_sgconfig_file(start_path: Path, config_filename: str = "sgconfig.yml") -> Optional[Path]:
    """Discover sgconfig.yml file by traversing up the directory tree.
    
    Args:
        start_path: Starting directory path to search from
        config_filename: Name of the config file to search for (default: sgconfig.yml)
        
    Returns:
        Path to sgconfig.yml file if found, None otherwise
    """
    current_path = Path(start_path).resolve()
    
    # Traverse up the directory tree
    while True:
        config_path = current_path / config_filename
        
        if config_path.exists() and config_path.is_file():
            logger.info(f"Found {config_filename} at: {config_path}")
            return config_path
        
        # Move up one directory
        parent_path = current_path.parent
        
        # Stop if we've reached the root directory
        if parent_path == current_path:
            break
            
        current_path = parent_path
    
    logger.debug(f"No {config_filename} file found in directory tree starting from: {start_path}")
    return None


def _interpolate_environment_variables(value: Any) -> Any:
    """Recursively interpolate environment variables in configuration values.
    
    Supports ${VAR_NAME} and $VAR_NAME syntax for environment variable substitution.
    
    Args:
        value: Configuration value that may contain environment variables
        
    Returns:
        Value with environment variables interpolated
    """
    if isinstance(value, str):
        # Replace ${VAR_NAME} and $VAR_NAME patterns
        def replace_env_var(match):
            var_name = match.group(1) or match.group(2)
            return os.getenv(var_name, match.group(0))  # Return original if env var not found
        
        # Pattern matches ${VAR_NAME} or $VAR_NAME (word characters only)
        pattern = r'\$\{([A-Za-z_][A-Za-z0-9_]*)\}|\$([A-Za-z_][A-Za-z0-9_]*)'
        return re.sub(pattern, replace_env_var, value)
        
    elif isinstance(value, dict):
        return {k: _interpolate_environment_variables(v) for k, v in value.items()}
        
    elif isinstance(value, list):
        return [_interpolate_environment_variables(item) for item in value]
        
    else:
        return value


def _validate_sgconfig_structure(config: Dict[str, Any], config_path: Path) -> Dict[str, Any]:
    """Validate the structure and contents of sgconfig.yml configuration.
    
    Args:
        config: Parsed configuration dictionary
        config_path: Path to the configuration file for resolving relative paths
        
    Returns:
        Validated and normalized configuration
        
    Raises:
        ASTGrepValidationError: If configuration is invalid
    """
    if not isinstance(config, dict):
        raise ASTGrepValidationError("sgconfig.yml must contain a YAML dictionary/object")
    
    validated_config = {}
    config_dir = config_path.parent
    
    # Validate required field: ruleDirs
    if "ruleDirs" not in config:
        raise ASTGrepValidationError("sgconfig.yml must contain 'ruleDirs' field")
    
    rule_dirs = config["ruleDirs"]
    if not isinstance(rule_dirs, list):
        raise ASTGrepValidationError("'ruleDirs' must be a list of directory paths")
    
    if not rule_dirs:
        raise ASTGrepValidationError("'ruleDirs' cannot be empty")
    
    # Validate and resolve rule directories
    validated_rule_dirs = []
    for rule_dir in rule_dirs:
        if not isinstance(rule_dir, str):
            raise ASTGrepValidationError(f"Rule directory path must be a string, got: {type(rule_dir)}")
        
        # Resolve relative paths relative to sgconfig.yml location
        if not os.path.isabs(rule_dir):
            abs_rule_dir = config_dir / rule_dir
        else:
            abs_rule_dir = Path(rule_dir)
        
        validated_rule_dirs.append(str(abs_rule_dir))
    
    validated_config["ruleDirs"] = validated_rule_dirs
    
    # Validate optional fields
    
    # testConfigs
    if "testConfigs" in config:
        test_configs = config["testConfigs"]
        if not isinstance(test_configs, list):
            raise ASTGrepValidationError("'testConfigs' must be a list")
        
        validated_test_configs = []
        for test_config in test_configs:
            if not isinstance(test_config, dict):
                raise ASTGrepValidationError("Each testConfig must be a dictionary")
            
            if "testDir" not in test_config:
                raise ASTGrepValidationError("Each testConfig must have a 'testDir' field")
            
            validated_test_config = {"testDir": test_config["testDir"]}
            
            if "snapshotDir" in test_config:
                validated_test_config["snapshotDir"] = test_config["snapshotDir"]
            
            validated_test_configs.append(validated_test_config)
        
        validated_config["testConfigs"] = validated_test_configs
    
    # utilDirs
    if "utilDirs" in config:
        util_dirs = config["utilDirs"]
        if not isinstance(util_dirs, list):
            raise ASTGrepValidationError("'utilDirs' must be a list of directory paths")
        
        validated_config["utilDirs"] = util_dirs
    
    # languageGlobs
    if "languageGlobs" in config:
        language_globs = config["languageGlobs"]
        if not isinstance(language_globs, dict):
            raise ASTGrepValidationError("'languageGlobs' must be a dictionary mapping languages to glob patterns")
        
        validated_config["languageGlobs"] = language_globs
    
    # customLanguages
    if "customLanguages" in config:
        custom_languages = config["customLanguages"]
        if not isinstance(custom_languages, dict):
            raise ASTGrepValidationError("'customLanguages' must be a dictionary")
        
        validated_config["customLanguages"] = custom_languages
    
    # languageInjections (experimental)
    if "languageInjections" in config:
        language_injections = config["languageInjections"]
        if not isinstance(language_injections, list):
            raise ASTGrepValidationError("'languageInjections' must be a list")
        
        validated_config["languageInjections"] = language_injections
    
    return validated_config


def parse_sgconfig_file(config_path: Path) -> Dict[str, Any]:
    """Parse and validate an sgconfig.yml file.
    
    Args:
        config_path: Path to the sgconfig.yml file
        
    Returns:
        Parsed and validated configuration dictionary
        
    Raises:
        ASTGrepValidationError: If file cannot be read or parsed
        FileNotFoundError: If config file doesn't exist
    """
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    
    if not config_path.is_file():
        raise ASTGrepValidationError(f"Configuration path is not a file: {config_path}")
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except IOError as e:
        raise ASTGrepValidationError(f"Cannot read configuration file {config_path}: {e}")
    
    if not content.strip():
        raise ASTGrepValidationError(f"Configuration file is empty: {config_path}")
    
    try:
        # Parse YAML content
        raw_config = yaml.safe_load(content)
    except yaml.YAMLError as e:
        raise ASTGrepValidationError(f"Invalid YAML syntax in {config_path}: {e}")
    
    if raw_config is None:
        raise ASTGrepValidationError(f"Configuration file contains no data: {config_path}")
    
    # Interpolate environment variables
    config = _interpolate_environment_variables(raw_config)
    
    # Validate configuration structure
    validated_config = _validate_sgconfig_structure(config, config_path)
    
    logger.info(f"Successfully parsed and validated sgconfig.yml: {config_path}")
    return validated_config


def discover_and_parse_sgconfig(scan_path: Path, custom_config_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Discover and parse sgconfig.yml configuration for ast-grep scan.
    
    Args:
        scan_path: Path to start scanning from (used for config discovery)
        custom_config_path: Optional custom path to sgconfig.yml file
        
    Returns:
        Parsed configuration dictionary if found and valid, None if not found
        
    Raises:
        ASTGrepValidationError: If configuration file is found but invalid
    """
    config_path = None
    
    if custom_config_path:
        # Use custom config path if provided
        custom_path = Path(custom_config_path)
        if not custom_path.is_absolute():
            # Resolve relative to scan path
            config_path = scan_path / custom_path
        else:
            config_path = custom_path
        
        if not config_path.exists():
            raise ASTGrepValidationError(f"Custom configuration file not found: {config_path}")
    else:
        # Discover sgconfig.yml in directory tree
        config_path = _discover_sgconfig_file(scan_path)
    
    if config_path is None:
        logger.info("No sgconfig.yml file found - scan will proceed without project configuration")
        return None
    
    return parse_sgconfig_file(config_path)


def _validate_rule_object(rule: Dict[str, Any], rule_source: str) -> Dict[str, Any]:
    """Validate a single ast-grep rule object.
    
    Args:
        rule: Rule dictionary to validate
        rule_source: Source identifier for error messages (e.g., filename:rule_index)
        
    Returns:
        Validated rule dictionary
        
    Raises:
        ASTGrepValidationError: If rule is invalid
    """
    if not isinstance(rule, dict):
        raise ASTGrepValidationError(f"Rule must be a dictionary object in {rule_source}")
    
    validated_rule = {}
    
    # Validate required fields
    required_fields = ["id", "language", "rule"]
    for field in required_fields:
        if field not in rule:
            raise ASTGrepValidationError(f"Missing required field '{field}' in rule {rule_source}")
        
        if field == "id":
            if not isinstance(rule[field], str) or not rule[field].strip():
                raise ASTGrepValidationError(f"Rule 'id' must be a non-empty string in {rule_source}")
            validated_rule["id"] = rule[field].strip()
        
        elif field == "language":
            if not isinstance(rule[field], str) or not rule[field].strip():
                raise ASTGrepValidationError(f"Rule 'language' must be a non-empty string in {rule_source}")
            
            # Validate language identifier using LanguageManager
            lang_manager = get_language_manager()
            try:
                normalized_language = lang_manager.validate_language_identifier(rule[field].strip(), return_normalized=True)
                validated_rule["language"] = normalized_language
            except ValueError as e:
                suggestions = lang_manager.suggest_similar_languages(rule[field].strip())
                suggestion_text = f" Did you mean: {', '.join(suggestions[:3])}?" if suggestions else ""
                raise ASTGrepValidationError(f"Invalid language '{rule[field]}' in rule {rule_source}. {str(e)}{suggestion_text}")
        
        elif field == "rule":
            if not isinstance(rule[field], dict):
                raise ASTGrepValidationError(f"Rule 'rule' field must be a dictionary object in {rule_source}")
            validated_rule["rule"] = _validate_rule_pattern(rule[field], rule_source)
    
    # Validate optional fields
    optional_string_fields = ["message", "note", "url"]
    for field in optional_string_fields:
        if field in rule:
            if not isinstance(rule[field], str):
                raise ASTGrepValidationError(f"Rule '{field}' must be a string in {rule_source}")
            validated_rule[field] = rule[field]
    
    # Validate severity
    if "severity" in rule:
        valid_severities = ["hint", "info", "warning", "error", "off"]
        if rule["severity"] not in valid_severities:
            raise ASTGrepValidationError(f"Invalid severity '{rule['severity']}' in rule {rule_source}. Must be one of: {', '.join(valid_severities)}")
        validated_rule["severity"] = rule["severity"]
    
    # Validate constraints
    if "constraints" in rule:
        if not isinstance(rule["constraints"], dict):
            raise ASTGrepValidationError(f"Rule 'constraints' must be a dictionary in {rule_source}")
        validated_rule["constraints"] = rule["constraints"]
    
    # Validate utils
    if "utils" in rule:
        if not isinstance(rule["utils"], dict):
            raise ASTGrepValidationError(f"Rule 'utils' must be a dictionary in {rule_source}")
        validated_rule["utils"] = rule["utils"]
    
    # Validate transform
    if "transform" in rule:
        if not isinstance(rule["transform"], dict):
            raise ASTGrepValidationError(f"Rule 'transform' must be a dictionary in {rule_source}")
        validated_rule["transform"] = rule["transform"]
    
    # Validate fix
    if "fix" in rule:
        if not isinstance(rule["fix"], (str, dict)):
            raise ASTGrepValidationError(f"Rule 'fix' must be a string or dictionary in {rule_source}")
        validated_rule["fix"] = rule["fix"]
    
    # Validate rewriters
    if "rewriters" in rule:
        if not isinstance(rule["rewriters"], list):
            raise ASTGrepValidationError(f"Rule 'rewriters' must be a list in {rule_source}")
        validated_rule["rewriters"] = rule["rewriters"]
    
    # Validate labels
    if "labels" in rule:
        if not isinstance(rule["labels"], dict):
            raise ASTGrepValidationError(f"Rule 'labels' must be a dictionary in {rule_source}")
        validated_rule["labels"] = rule["labels"]
    
    # Validate files/ignores (glob patterns)
    for glob_field in ["files", "ignores"]:
        if glob_field in rule:
            if not isinstance(rule[glob_field], list):
                raise ASTGrepValidationError(f"Rule '{glob_field}' must be a list of glob patterns in {rule_source}")
            validated_rule[glob_field] = rule[glob_field]
    
    # Validate metadata
    if "metadata" in rule:
        if not isinstance(rule["metadata"], dict):
            raise ASTGrepValidationError(f"Rule 'metadata' must be a dictionary in {rule_source}")
        validated_rule["metadata"] = rule["metadata"]
    
    return validated_rule


def _validate_rule_pattern(rule_pattern: Dict[str, Any], rule_source: str) -> Dict[str, Any]:
    """Validate the rule pattern structure.
    
    Args:
        rule_pattern: Rule pattern dictionary
        rule_source: Source identifier for error messages
        
    Returns:
        Validated rule pattern dictionary
        
    Raises:
        ASTGrepValidationError: If rule pattern is invalid
    """
    if not isinstance(rule_pattern, dict):
        raise ASTGrepValidationError(f"Rule pattern must be a dictionary in {rule_source}")
    
    # Check for at least one valid pattern type
    valid_pattern_types = ["pattern", "kind", "regex", "any", "all", "not", "matches", "inside", "has"]
    
    if not any(pattern_type in rule_pattern for pattern_type in valid_pattern_types):
        raise ASTGrepValidationError(f"Rule must contain at least one valid pattern type {valid_pattern_types} in {rule_source}")
    
    validated_pattern = {}
    
    # Validate pattern field
    if "pattern" in rule_pattern:
        if not isinstance(rule_pattern["pattern"], str) or not rule_pattern["pattern"].strip():
            raise ASTGrepValidationError(f"Rule 'pattern' must be a non-empty string in {rule_source}")
        validated_pattern["pattern"] = rule_pattern["pattern"].strip()
    
    # Validate kind field
    if "kind" in rule_pattern:
        if not isinstance(rule_pattern["kind"], str) or not rule_pattern["kind"].strip():
            raise ASTGrepValidationError(f"Rule 'kind' must be a non-empty string in {rule_source}")
        validated_pattern["kind"] = rule_pattern["kind"].strip()
    
    # Validate regex field
    if "regex" in rule_pattern:
        if not isinstance(rule_pattern["regex"], str) or not rule_pattern["regex"].strip():
            raise ASTGrepValidationError(f"Rule 'regex' must be a non-empty string in {rule_source}")
        
        # Validate regex syntax
        try:
            re.compile(rule_pattern["regex"])
        except re.error as e:
            raise ASTGrepValidationError(f"Invalid regex pattern in rule {rule_source}: {e}")
        
        validated_pattern["regex"] = rule_pattern["regex"].strip()
    
    # Validate composite rule types (any, all, not)
    for composite_type in ["any", "all", "not"]:
        if composite_type in rule_pattern:
            if composite_type == "not":
                # 'not' expects a single rule object
                if not isinstance(rule_pattern[composite_type], dict):
                    raise ASTGrepValidationError(f"Rule '{composite_type}' must be a rule object in {rule_source}")
                validated_pattern[composite_type] = rule_pattern[composite_type]
            else:
                # 'any' and 'all' expect lists of rule objects
                if not isinstance(rule_pattern[composite_type], list):
                    raise ASTGrepValidationError(f"Rule '{composite_type}' must be a list of rule objects in {rule_source}")
                validated_pattern[composite_type] = rule_pattern[composite_type]
    
    # Validate relational rule types (matches, inside, has)
    for relational_type in ["matches", "inside", "has"]:
        if relational_type in rule_pattern:
            if not isinstance(rule_pattern[relational_type], (str, dict)):
                raise ASTGrepValidationError(f"Rule '{relational_type}' must be a string or rule object in {rule_source}")
            validated_pattern[relational_type] = rule_pattern[relational_type]
    
    return validated_pattern


def parse_rule_file(rule_file_path: Path) -> List[Dict[str, Any]]:
    """Parse and validate a rule file containing one or more ast-grep rules.
    
    Args:
        rule_file_path: Path to the rule file
        
    Returns:
        List of validated rule dictionaries
        
    Raises:
        ASTGrepValidationError: If rule file is invalid
        FileNotFoundError: If rule file doesn't exist
    """
    if not rule_file_path.exists():
        raise FileNotFoundError(f"Rule file not found: {rule_file_path}")
    
    if not rule_file_path.is_file():
        raise ASTGrepValidationError(f"Rule path is not a file: {rule_file_path}")
    
    try:
        with open(rule_file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except IOError as e:
        raise ASTGrepValidationError(f"Cannot read rule file {rule_file_path}: {e}")
    
    if not content.strip():
        raise ASTGrepValidationError(f"Rule file is empty: {rule_file_path}")
    
    try:
        # Parse YAML content - can contain multiple documents separated by ---
        raw_rules = list(yaml.safe_load_all(content))
    except yaml.YAMLError as e:
        raise ASTGrepValidationError(f"Invalid YAML syntax in rule file {rule_file_path}: {e}")
    
    if not raw_rules or all(rule is None for rule in raw_rules):
        raise ASTGrepValidationError(f"Rule file contains no valid rules: {rule_file_path}")
    
    validated_rules = []
    
    for i, raw_rule in enumerate(raw_rules):
        if raw_rule is None:
            continue
            
        rule_source = f"{rule_file_path.name}:rule#{i+1}"
        
        # Interpolate environment variables
        rule = _interpolate_environment_variables(raw_rule)
        
        # Validate rule structure
        validated_rule = _validate_rule_object(rule, rule_source)
        validated_rules.append(validated_rule)
    
    if not validated_rules:
        raise ASTGrepValidationError(f"No valid rules found in file: {rule_file_path}")
    
    logger.info(f"Successfully parsed and validated {len(validated_rules)} rules from: {rule_file_path}")
    return validated_rules


def discover_and_validate_rules(config: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """Discover and validate all rule files in the configured rule directories.
    
    Args:
        config: Parsed sgconfig.yml configuration
        
    Returns:
        Dictionary mapping rule directory paths to lists of validated rules
        
    Raises:
        ASTGrepValidationError: If any rule files are invalid
    """
    rule_dirs = config.get("ruleDirs", [])
    all_rules = {}
    
    for rule_dir_str in rule_dirs:
        rule_dir = Path(rule_dir_str)
        
        if not rule_dir.exists():
            logger.warning(f"Rule directory does not exist: {rule_dir}")
            continue
        
        if not rule_dir.is_dir():
            logger.warning(f"Rule path is not a directory: {rule_dir}")
            continue
        
        # Discover rule files recursively (YAML files)
        rule_files = []
        for pattern in ["*.yml", "*.yaml"]:
            rule_files.extend(rule_dir.rglob(pattern))
        
        if not rule_files:
            logger.warning(f"No rule files found in directory: {rule_dir}")
            continue
        
        directory_rules = []
        
        for rule_file in rule_files:
            try:
                file_rules = parse_rule_file(rule_file)
                directory_rules.extend(file_rules)
                logger.info(f"Loaded {len(file_rules)} rules from: {rule_file}")
            except (ASTGrepValidationError, FileNotFoundError) as e:
                raise ASTGrepValidationError(f"Failed to load rules from {rule_file}: {e}")
        
        all_rules[str(rule_dir)] = directory_rules
        logger.info(f"Loaded {len(directory_rules)} total rules from directory: {rule_dir}")
    
    total_rules = sum(len(rules) for rules in all_rules.values())
    logger.info(f"Successfully loaded and validated {total_rules} rules from {len(all_rules)} directories")
    
    return all_rules