"""AST-Grep MCP Server - A Model Context Protocol server for ast-grep."""

__version__ = "1.0.0"
__author__ = "AndEnd Collective"
__description__ = "Model Context Protocol server wrapping ast-grep for AI-powered code analysis"

# Main server components
from .server import (
    create_server,
    ASTGrepMCPServer,
    ServerConfig
)

# Core utilities
from .utils import (
    setup_logging,
    validate_ast_grep_installation,
    ASTGrepError,
    ASTGrepNotFoundError,
    ASTGrepValidationError,
    get_language_manager,
    validate_language,
    detect_language_from_file
)

# Performance system
from .performance import (
    EnhancedPerformanceManager,
    MemoryMonitor,
    PerformanceMetricsCollector
)
from .tools import (
    initialize_performance_system,
    shutdown_performance_system,
    get_performance_manager,
    get_memory_manager,
    get_metrics_manager
)

# Security system
from .security import (
    SecurityManager,
    initialize_security,
    get_security_manager,
    ValidationConfig,
    SecurityLevel,
    UserRole,
    UserContext,
    EnhancedAuditLogger,
    get_audit_logger
)

# Enhanced logging system
from .logging_config import (
    LoggingConfig,
    setup_enhanced_logging,
    shutdown_logging,
    get_logging_manager,
    with_correlation_id,
    log_function_call
)

# Tool input schemas for external use
from .tools import (
    # Tool input models
    SearchToolInput,
    ScanToolInput,
    RunToolInput,
    CallGraphInput
)

__all__ = [
    # Version info
    "__version__",
    
    # Main server
    "create_server",
    "ASTGrepMCPServer", 
    "ServerConfig",
    
    # Core utilities
    "setup_logging",
    "validate_ast_grep_installation",
    "ASTGrepError",
    "ASTGrepNotFoundError", 
    "ASTGrepValidationError",
    "get_language_manager",
    "validate_language",
    "detect_language_from_file",
    
    # Performance system
    "EnhancedPerformanceManager",
    "MemoryMonitor",
    "PerformanceMetricsCollector",
    "initialize_performance_system",
    "shutdown_performance_system",
    "get_performance_manager",
    "get_memory_manager",
    "get_metrics_manager",
    
    # Security system
    "SecurityManager",
    "initialize_security",
    "get_security_manager",
    "ValidationConfig",
    "SecurityLevel",
    "UserRole", 
    "UserContext",
    "EnhancedAuditLogger",
    "get_audit_logger",
    
    # Enhanced logging system
    "LoggingConfig",
    "setup_enhanced_logging",
    "shutdown_logging",
    "get_logging_manager",
    "with_correlation_id",
    "log_function_call",
    
    # Schemas
    "SearchToolInput",
    "ScanToolInput", 
    "RunToolInput",
    "CallGraphInput"
] 