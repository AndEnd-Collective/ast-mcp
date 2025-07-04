"""Security and input validation layer for AST-Grep MCP server."""

import os
import re
import logging
import hashlib
import time
import subprocess
import tempfile
import ipaddress
from pathlib import Path
from typing import Dict, Any, List, Optional, Set, Union, Tuple
from urllib.parse import unquote, quote
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum

from pydantic import BaseModel, Field, field_validator, ValidationError

logger = logging.getLogger(__name__)


class SecurityError(Exception):
    """Base exception for security-related errors."""
    pass


class PathTraversalError(SecurityError):
    """Exception raised when path traversal attempts are detected."""
    pass


class CommandInjectionError(SecurityError):
    """Exception raised when command injection attempts are detected."""
    pass


class ResourceLimitError(SecurityError):
    """Exception raised when resource limits are exceeded."""
    pass


class RateLimitError(SecurityError):
    """Exception raised when rate limits are exceeded."""
    pass


class SecurityLevel(Enum):
    """Security levels for operations and users."""
    PUBLIC = "public"
    RESTRICTED = "restricted"
    SENSITIVE = "sensitive"
    CRITICAL = "critical"


class UserRole(Enum):
    """User roles for RBAC."""
    GUEST = "guest"
    USER = "user"
    DEVELOPER = "developer"
    ADMIN = "admin"
    SYSTEM = "system"


@dataclass
class UserContext:
    """User context for audit logging and permissions."""
    user_id: str
    role: UserRole = UserRole.USER
    session_id: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    permissions: Set[str] = field(default_factory=set)
    
    def has_permission(self, permission: str) -> bool:
        """Check if user has specific permission."""
        return permission in self.permissions or self.role == UserRole.ADMIN
    
    def can_access_security_level(self, level: SecurityLevel) -> bool:
        """Check if user can access operations at given security level."""
        role_levels = {
            UserRole.GUEST: {SecurityLevel.PUBLIC},
            UserRole.USER: {SecurityLevel.PUBLIC, SecurityLevel.RESTRICTED},
            UserRole.DEVELOPER: {SecurityLevel.PUBLIC, SecurityLevel.RESTRICTED, SecurityLevel.SENSITIVE},
            UserRole.ADMIN: {SecurityLevel.PUBLIC, SecurityLevel.RESTRICTED, SecurityLevel.SENSITIVE, SecurityLevel.CRITICAL},
            UserRole.SYSTEM: {SecurityLevel.PUBLIC, SecurityLevel.RESTRICTED, SecurityLevel.SENSITIVE, SecurityLevel.CRITICAL}
        }
        return level in role_levels.get(self.role, set())


@dataclass
class AuditEvent:
    """Comprehensive audit event structure."""
    event_id: str
    timestamp: float
    event_type: str
    user_context: Optional[UserContext]
    operation: str
    resource: str
    success: bool
    security_level: SecurityLevel
    details: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    duration_ms: Optional[float] = None
    resource_usage: Dict[str, Any] = field(default_factory=dict)
    risk_score: int = 0  # 0-100 risk assessment
    tags: Set[str] = field(default_factory=set)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "user_context": {
                "user_id": self.user_context.user_id,
                "role": self.user_context.role.value,
                "session_id": self.user_context.session_id,
                "ip_address": self.user_context.ip_address
            } if self.user_context else None,
            "operation": self.operation,
            "resource": self.resource,
            "success": self.success,
            "security_level": self.security_level.value,
            "details": self.details,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "resource_usage": self.resource_usage,
            "risk_score": self.risk_score,
            "tags": list(self.tags)
        }


class PermissionManager:
    """Role-based access control and permission management."""
    
    def __init__(self):
        """Initialize permission manager."""
        self.logger = logging.getLogger("ast_grep_mcp.security.permissions")
        self._operation_permissions = {
            "ast_grep_search": {"ast_grep.search", "file.read"},
            "ast_grep_scan": {"ast_grep.scan", "file.read", "config.read"},
            "ast_grep_run": {"ast_grep.run", "file.read", "file.write"},
            "call_graph_generate": {"ast_grep.analyze", "file.read"},
            "resource_access": {"resource.access"},
            "config_modify": {"config.write", "admin.access"},
            "system_command": {"system.execute", "admin.access"}
        }
        
        self._security_levels = {
            "ast_grep_search": SecurityLevel.RESTRICTED,
            "ast_grep_scan": SecurityLevel.RESTRICTED,
            "ast_grep_run": SecurityLevel.SENSITIVE,
            "call_graph_generate": SecurityLevel.RESTRICTED,
            "config_modify": SecurityLevel.CRITICAL,
            "system_command": SecurityLevel.CRITICAL
        }
    
    def check_permission(
        self,
        user_context: UserContext,
        operation: str,
        resource: Optional[str] = None
    ) -> Tuple[bool, Optional[str]]:
        """Check if user has permission for operation.
        
        Returns:
            Tuple of (has_permission, denial_reason)
        """
        # Check security level access
        security_level = self._security_levels.get(operation, SecurityLevel.RESTRICTED)
        if not user_context.can_access_security_level(security_level):
            return False, f"Insufficient role for {security_level.value} operation"
        
        # Check specific permissions
        required_permissions = self._operation_permissions.get(operation, set())
        for permission in required_permissions:
            if not user_context.has_permission(permission):
                return False, f"Missing required permission: {permission}"
        
        # Additional resource-based checks
        if resource and operation in {"ast_grep_run", "config_modify"}:
            if not self._check_resource_access(user_context, resource):
                return False, f"Access denied to resource: {resource}"
        
        return True, None
    
    def _check_resource_access(self, user_context: UserContext, resource: str) -> bool:
        """Check resource-specific access permissions."""
        # Implement resource-specific logic here
        # For now, basic checks based on role
        if user_context.role == UserRole.GUEST:
            return False
        
        # Check for sensitive paths
        sensitive_patterns = ['/etc', '/proc', '/sys', 'C:\\\\Windows']
        for pattern in sensitive_patterns:
            if pattern.lower() in resource.lower():
                return user_context.role in {UserRole.ADMIN, UserRole.SYSTEM}
        
        return True


class EnhancedAuditLogger:
    """Enhanced audit logging with comprehensive forensic capabilities."""
    
    def __init__(self, max_events: int = 50000):
        """Initialize enhanced audit logger.
        
        Args:
            max_events: Maximum number of events to keep in memory
        """
        self.logger = logging.getLogger("ast_grep_mcp.security.audit")
        self._event_history: deque = deque(maxlen=max_events)
        self._event_counter = 0
        self._session_events: Dict[str, List[str]] = defaultdict(list)
        self._risk_threshold = 50  # Events above this risk score trigger alerts
        
        # Setup structured logging format
        self._setup_structured_logging()
    
    def _setup_structured_logging(self) -> None:
        """Setup structured logging with JSON format."""
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            '{"timestamp": "%(asctime)s", "level": "%(levelname)s", '
            '"logger": "%(name)s", "message": %(message)s}'
        )
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)
        self.logger.setLevel(logging.INFO)
    
    def _generate_event_id(self) -> str:
        """Generate unique event ID."""
        self._event_counter += 1
        return f"audit_{int(time.time())}_{self._event_counter:06d}"
    
    def _calculate_risk_score(
        self,
        event_type: str,
        operation: str,
        user_context: Optional[UserContext],
        success: bool,
        details: Dict[str, Any]
    ) -> int:
        """Calculate risk score for the event (0-100)."""
        risk_score = 0
        
        # Base risk by event type
        base_risks = {
            "security_violation": 80,
            "permission_denied": 60,
            "command_execution": 40,
            "file_write": 30,
            "file_read": 10,
            "authentication": 20
        }
        risk_score += base_risks.get(event_type, 10)
        
        # Risk by operation
        operation_risks = {
            "ast_grep_run": 30,  # Can modify files
            "system_command": 50,
            "config_modify": 40
        }
        risk_score += operation_risks.get(operation, 0)
        
        # User context risks
        if user_context:
            if user_context.role == UserRole.GUEST:
                risk_score += 20
            elif user_context.ip_address and self._is_suspicious_ip(user_context.ip_address):
                risk_score += 30
        
        # Failure increases risk
        if not success:
            risk_score += 20
        
        # Sensitive details increase risk
        if details.get("elevated_privileges"):
            risk_score += 25
        if details.get("system_path_access"):
            risk_score += 15
        
        return min(100, risk_score)
    
    def _is_suspicious_ip(self, ip_address: str) -> bool:
        """Check if IP address is suspicious."""
        try:
            ip = ipaddress.ip_address(ip_address)
            # Add your suspicious IP logic here
            # For now, just check if it's not private
            return not ip.is_private
        except ValueError:
            return True  # Invalid IP is suspicious
    
    def log_event(
        self,
        event_type: str,
        operation: str,
        resource: str,
        success: bool,
        user_context: Optional[UserContext] = None,
        security_level: SecurityLevel = SecurityLevel.RESTRICTED,
        details: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        duration_ms: Optional[float] = None,
        resource_usage: Optional[Dict[str, Any]] = None,
        tags: Optional[Set[str]] = None
    ) -> str:
        """Log a comprehensive audit event.
        
        Returns:
            Event ID for correlation
        """
        event_id = self._generate_event_id()
        timestamp = time.time()
        
        # Calculate risk score
        risk_score = self._calculate_risk_score(
            event_type, operation, user_context, success, details or {}
        )
        
        # Create audit event
        event = AuditEvent(
            event_id=event_id,
            timestamp=timestamp,
            event_type=event_type,
            user_context=user_context,
            operation=operation,
            resource=resource,
            success=success,
            security_level=security_level,
            details=details or {},
            error=error,
            duration_ms=duration_ms,
            resource_usage=resource_usage or {},
            risk_score=risk_score,
            tags=tags or set()
        )
        
        # Store event
        self._event_history.append(event)
        
        # Track session events
        if user_context and user_context.session_id:
            self._session_events[user_context.session_id].append(event_id)
        
        # Log with appropriate level based on risk
        log_level = self._determine_log_level(risk_score, success)
        log_message = self._format_log_message(event)
        
        self.logger.log(log_level, log_message)
        
        # Trigger alerts for high-risk events
        if risk_score >= self._risk_threshold:
            self._trigger_security_alert(event)
        
        return event_id
    
    def _determine_log_level(self, risk_score: int, success: bool) -> int:
        """Determine appropriate log level based on risk and success."""
        if risk_score >= 80:
            return logging.CRITICAL
        elif risk_score >= 60:
            return logging.ERROR
        elif risk_score >= 40 or not success:
            return logging.WARNING
        else:
            return logging.INFO
    
    def _format_log_message(self, event: AuditEvent) -> str:
        """Format audit event as JSON log message."""
        import json
        return json.dumps(event.to_dict(), separators=(',', ':'))
    
    def _trigger_security_alert(self, event: AuditEvent) -> None:
        """Trigger security alert for high-risk events."""
        alert_message = (
            f"HIGH RISK SECURITY EVENT: {event.event_type} "
            f"(Risk: {event.risk_score}/100, Operation: {event.operation}, "
            f"Resource: {event.resource})"
        )
        self.logger.critical(alert_message)
        
        # Could integrate with external alerting systems here
        # e.g., send to SIEM, notification service, etc.
    
    def log_operation_start(
        self,
        operation: str,
        resource: str,
        user_context: Optional[UserContext] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> str:
        """Log the start of an operation."""
        return self.log_event(
            event_type="operation_start",
            operation=operation,
            resource=resource,
            success=True,
            user_context=user_context,
            details=details,
            tags={"lifecycle"}
        )
    
    def log_operation_end(
        self,
        operation: str,
        resource: str,
        success: bool,
        user_context: Optional[UserContext] = None,
        duration_ms: Optional[float] = None,
        resource_usage: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None
    ) -> str:
        """Log the end of an operation."""
        return self.log_event(
            event_type="operation_end",
            operation=operation,
            resource=resource,
            success=success,
            user_context=user_context,
            duration_ms=duration_ms,
            resource_usage=resource_usage,
            error=error,
            tags={"lifecycle"}
        )
    
    def log_permission_check(
        self,
        operation: str,
        resource: str,
        user_context: UserContext,
        granted: bool,
        reason: Optional[str] = None
    ) -> str:
        """Log permission check results."""
        return self.log_event(
            event_type="permission_check",
            operation=operation,
            resource=resource,
            success=granted,
            user_context=user_context,
            security_level=SecurityLevel.SENSITIVE,
            details={
                "permission_granted": granted,
                "denial_reason": reason
            },
            tags={"permissions", "rbac"}
        )
    
    def log_security_violation(
        self,
        violation_type: str,
        operation: str,
        resource: str,
        user_context: Optional[UserContext] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> str:
        """Log security violations."""
        return self.log_event(
            event_type="security_violation",
            operation=operation,
            resource=resource,
            success=False,
            user_context=user_context,
            security_level=SecurityLevel.CRITICAL,
            details={"violation_type": violation_type, **(details or {})},
            tags={"security", "violation"}
        )
    
    def log_command_execution(
        self,
        command: str,
        args: List[str],
        working_dir: str,
        user_context: Optional[UserContext] = None,
        success: bool = True,
        duration_ms: Optional[float] = None,
        return_code: Optional[int] = None,
        resource_usage: Optional[Dict[str, Any]] = None
    ) -> str:
        """Log command execution with full context."""
        return self.log_event(
            event_type="command_execution",
            operation="system_command",
            resource=working_dir,
            success=success,
            user_context=user_context,
            security_level=SecurityLevel.SENSITIVE,
            details={
                "command": command,
                "args": args,
                "working_directory": working_dir,
                "return_code": return_code
            },
            duration_ms=duration_ms,
            resource_usage=resource_usage,
            tags={"execution", "command"}
        )
    
    def get_events(
        self,
        event_type: Optional[str] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        operation: Optional[str] = None,
        min_risk_score: Optional[int] = None,
        success: Optional[bool] = None,
        limit: int = 100,
        since: Optional[float] = None
    ) -> List[AuditEvent]:
        """Get filtered audit events."""
        events = list(self._event_history)
        
        # Apply filters
        if event_type:
            events = [e for e in events if e.event_type == event_type]
        
        if user_id:
            events = [e for e in events if e.user_context and e.user_context.user_id == user_id]
        
        if session_id:
            events = [e for e in events if e.user_context and e.user_context.session_id == session_id]
        
        if operation:
            events = [e for e in events if e.operation == operation]
        
        if min_risk_score is not None:
            events = [e for e in events if e.risk_score >= min_risk_score]
        
        if success is not None:
            events = [e for e in events if e.success == success]
        
        if since:
            events = [e for e in events if e.timestamp >= since]
        
        # Sort by timestamp (newest first) and limit
        events.sort(key=lambda e: e.timestamp, reverse=True)
        return events[:limit]
    
    def get_security_summary(self, hours: int = 24) -> Dict[str, Any]:
        """Get security summary for the specified time period."""
        since = time.time() - (hours * 3600)
        events = self.get_events(since=since, limit=10000)
        
        # Calculate metrics
        total_events = len(events)
        security_violations = len([e for e in events if e.event_type == "security_violation"])
        failed_operations = len([e for e in events if not e.success])
        high_risk_events = len([e for e in events if e.risk_score >= self._risk_threshold])
        
        # Top operations and users
        operations = defaultdict(int)
        users = defaultdict(int)
        for event in events:
            operations[event.operation] += 1
            if event.user_context:
                users[event.user_context.user_id] += 1
        
        return {
            "time_period_hours": hours,
            "total_events": total_events,
            "security_violations": security_violations,
            "failed_operations": failed_operations,
            "high_risk_events": high_risk_events,
            "top_operations": dict(sorted(operations.items(), key=lambda x: x[1], reverse=True)[:10]),
            "top_users": dict(sorted(users.items(), key=lambda x: x[1], reverse=True)[:10]),
            "risk_distribution": self._calculate_risk_distribution(events)
        }
    
    def _calculate_risk_distribution(self, events: List[AuditEvent]) -> Dict[str, int]:
        """Calculate distribution of events by risk level."""
        distribution = {"low": 0, "medium": 0, "high": 0, "critical": 0}
        
        for event in events:
            if event.risk_score < 25:
                distribution["low"] += 1
            elif event.risk_score < 50:
                distribution["medium"] += 1
            elif event.risk_score < 75:
                distribution["high"] += 1
            else:
                distribution["critical"] += 1
        
        return distribution


# Global instances
_audit_logger: Optional[EnhancedAuditLogger] = None
_permission_manager: Optional[PermissionManager] = None


def get_audit_logger() -> EnhancedAuditLogger:
    """Get the global enhanced audit logger instance."""
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = EnhancedAuditLogger()
    return _audit_logger


def get_permission_manager() -> PermissionManager:
    """Get the global permission manager instance."""
    global _permission_manager
    if _permission_manager is None:
        _permission_manager = PermissionManager()
    return _permission_manager


def create_user_context(
    user_id: str,
    role: UserRole = UserRole.USER,
    session_id: Optional[str] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    permissions: Optional[Set[str]] = None
) -> UserContext:
    """Create a user context for audit logging and permissions.
    
    Args:
        user_id: Unique user identifier
        role: User role for RBAC
        session_id: Session identifier
        ip_address: Client IP address
        user_agent: Client user agent
        permissions: Specific permissions (in addition to role-based)
    
    Returns:
        UserContext instance
    """
    # Default permissions based on role
    default_permissions = {
        UserRole.GUEST: set(),
        UserRole.USER: {"file.read", "ast_grep.search"},
        UserRole.DEVELOPER: {"file.read", "file.write", "ast_grep.search", "ast_grep.scan", "ast_grep.run", "ast_grep.analyze"},
        UserRole.ADMIN: {"*"},  # Admin has all permissions
        UserRole.SYSTEM: {"*"}  # System has all permissions
    }
    
    user_permissions = default_permissions.get(role, set())
    if permissions:
        user_permissions.update(permissions)
    
    return UserContext(
        user_id=user_id,
        role=role,
        session_id=session_id,
        ip_address=ip_address,
        user_agent=user_agent,
                 permissions=user_permissions
     )


class ValidationConfig(BaseModel):
    """Configuration for security validation."""
    max_path_length: int = Field(4096, description="Maximum allowed path length")
    max_pattern_length: int = Field(10000, description="Maximum allowed pattern length")
    max_file_size: int = Field(100 * 1024 * 1024, description="Maximum file size to process (100MB)")
    max_files_per_request: int = Field(1000, description="Maximum files per request")
    allowed_extensions: Set[str] = Field(
        default_factory=lambda: {
            '.js', '.ts', '.jsx', '.tsx', '.py', '.pyi', '.java', '.kt', '.kts',
            '.rs', '.go', '.c', '.h', '.cpp', '.hpp', '.cc', '.cxx', '.cs',
            '.swift', '.php', '.rb', '.scala', '.sh', '.bash', '.zsh',
            '.yaml', '.yml', '.json', '.xml', '.html', '.css', '.md', '.txt'
        },
        description="Allowed file extensions"
    )
    blocked_paths: Set[str] = Field(
        default_factory=lambda: {
            '/etc', '/proc', '/sys', '/dev', '/root', '/tmp',  # nosec B108 - this is a list of blocked paths, not usage
            'C:\\Windows', 'C:\\System32', 'C:\\Users\\Administrator'
        },
        description="Blocked system paths"
    )
    blocked_patterns: Set[str] = Field(
        default_factory=lambda: {
            r'\.\./', r'\.\.\\', r'\$\(', r'`', r';', r'&&', r'\|\|',
            r'nc\s', r'netcat\s', r'curl\s', r'wget\s', r'ssh\s'
        },
        description="Blocked regex patterns"
    )


class SecurityManager:
    """Central security manager for all security operations."""
    
    def __init__(self, config: Optional[ValidationConfig] = None):
        """Initialize SecurityManager with configuration."""
        self.config = config or ValidationConfig()
        self._rate_limiter = RateLimiter()
        self._audit_logger = AuditLogger()
        self._request_counter = 0
        
        # Compile regex patterns for performance
        self._compiled_patterns = {
            pattern: re.compile(pattern, re.IGNORECASE | re.MULTILINE)
            for pattern in self.config.blocked_patterns
        }
        
        logger.info(f"SecurityManager initialized with config: {self.config}")
    
    def validate_path(self, path: Union[str, Path], base_path: Optional[Union[str, Path]] = None) -> Path:
        """
        Validate and sanitize a file path, preventing path traversal attacks.
        
        Args:
            path: Path to validate
            base_path: Optional base path to restrict access to
            
        Returns:
            Validated and resolved Path object
            
        Raises:
            PathTraversalError: If path traversal is detected
            ValidationError: If path is invalid
        """
        try:
            # Convert to string and decode URL encoding if present
            if isinstance(path, Path):
                path_str = str(path)
            else:
                path_str = str(path).strip()
            
            # Decode URL encoding
            path_str = unquote(path_str)
            
            # Check path length
            if len(path_str) > self.config.max_path_length:
                raise PathTraversalError(f"Path too long: {len(path_str)} > {self.config.max_path_length}")
            
            # Check for empty path
            if not path_str:
                raise ValidationError("Path cannot be empty")
            
            # Check for dangerous path traversal patterns
            self._check_path_traversal_patterns(path_str)
            
            # Convert to Path object for normalization
            path_obj = Path(path_str)
            
            # Check for absolute paths to blocked locations
            if path_obj.is_absolute():
                self._check_blocked_absolute_paths(path_obj)
            
            # Resolve path (this normalizes .. and . components)
            try:
                if base_path:
                    base_path_obj = Path(base_path).resolve()
                    resolved_path = (base_path_obj / path_obj).resolve()
                    
                    # Ensure resolved path is within base_path
                    try:
                        resolved_path.relative_to(base_path_obj)
                    except ValueError:
                        raise PathTraversalError(
                            f"Path {path_str} attempts to access outside base directory {base_path}"
                        )
                else:
                    resolved_path = path_obj.resolve()
            except (OSError, ValueError) as e:
                raise ValidationError(f"Invalid path: {e}")
            
            # Final security checks on resolved path
            self._check_resolved_path_security(resolved_path)
            
            # Log successful path validation
            self._audit_logger.log_path_access(str(resolved_path), success=True)
            
            return resolved_path
            
        except (PathTraversalError, ValidationError) as e:
            # Log failed path validation
            self._audit_logger.log_path_access(path_str, success=False, error=str(e))
            raise
        except Exception as e:
            # Log unexpected errors
            self._audit_logger.log_path_access(path_str, success=False, error=f"Unexpected error: {e}")
            raise ValidationError(f"Path validation failed: {e}")
    
    def _check_path_traversal_patterns(self, path_str: str) -> None:
        """Check for path traversal patterns in the path string."""
        # Check for various path traversal patterns
        dangerous_patterns = [
            r'\.\./',      # Unix path traversal
            r'\.\.\\',     # Windows path traversal  
            r'\.\.',       # Any .. sequence
            r'%2e%2e',     # URL encoded ..
            r'%252e',      # Double URL encoded .
            r'\\\.\\\.\\', # Windows variant
            r'/\.\./\.\.',  # Multiple traversals
        ]
        
        for pattern in dangerous_patterns:
            if re.search(pattern, path_str, re.IGNORECASE):
                raise PathTraversalError(f"Path traversal pattern detected: {pattern}")
        
        # Check for null bytes and other dangerous characters
        if '\x00' in path_str:
            raise PathTraversalError("Null byte detected in path")
        
        # Check for excessively long path components
        components = path_str.replace('\\', '/').split('/')
        for component in components:
            if len(component) > 255:  # Max filename length on most systems
                raise PathTraversalError(f"Path component too long: {len(component)}")
    
    def _check_blocked_absolute_paths(self, path_obj: Path) -> None:
        """Check if absolute path accesses blocked system directories."""
        path_str = str(path_obj).lower()
        
        for blocked_path in self.config.blocked_paths:
            if path_str.startswith(blocked_path.lower()):
                raise PathTraversalError(f"Access to blocked path: {blocked_path}")
    
    def _check_resolved_path_security(self, resolved_path: Path) -> None:
        """Perform final security checks on resolved path."""
        path_str = str(resolved_path)
        
        # Check file extension if it's a file
        if resolved_path.is_file() or '.' in resolved_path.name:
            suffix = resolved_path.suffix.lower()
            if suffix and suffix not in self.config.allowed_extensions:
                raise ValidationError(f"File extension not allowed: {suffix}")
        
        # Check file size if file exists
        if resolved_path.is_file():
            try:
                file_size = resolved_path.stat().st_size
                if file_size > self.config.max_file_size:
                    raise ResourceLimitError(
                        f"File too large: {file_size} bytes > {self.config.max_file_size}"
                    )
            except OSError:
                # File might not be accessible, let downstream handle it
                pass
    
    def sanitize_command_args(self, command: str, args: List[str]) -> Tuple[str, List[str]]:
        """
        Sanitize command and arguments to prevent command injection.
        
        Args:
            command: Command to execute
            args: List of command arguments
            
        Returns:
            Tuple of (sanitized_command, sanitized_args)
            
        Raises:
            CommandInjectionError: If command injection is detected
        """
        # Check if command is allowed
        allowed_commands = {'ast-grep', 'sg'}
        if command not in allowed_commands:
            raise CommandInjectionError(f"Command not allowed: {command}")
        
        # Sanitize each argument
        sanitized_args = []
        for arg in args:
            sanitized_arg = self._sanitize_single_arg(arg)
            sanitized_args.append(sanitized_arg)
        
        # Log command execution attempt
        self._audit_logger.log_command_execution(command, sanitized_args)
        
        return command, sanitized_args
    
    def _sanitize_single_arg(self, arg: str) -> str:
        """Sanitize a single command argument."""
        if not isinstance(arg, str):
            raise CommandInjectionError(f"Invalid argument type: {type(arg)}")
        
        # Check for dangerous patterns
        for pattern_name, compiled_pattern in self._compiled_patterns.items():
            if compiled_pattern.search(arg):
                raise CommandInjectionError(f"Dangerous pattern detected in argument: {pattern_name}")
        
        # Check for shell metacharacters
        dangerous_chars = {';', '&', '|', '`', '$', '(', ')', '[', ']', '{', '}', '<', '>'}
        for char in dangerous_chars:
            if char in arg:
                # Allow some characters in specific contexts
                if char == '$' and re.match(r'^\$[A-Z_][A-Z0-9_]*$', arg):
                    # Allow environment variable syntax like $VAR
                    continue
                raise CommandInjectionError(f"Dangerous character detected: {char}")
        
        return arg
    
    def check_rate_limit(self, identifier: str, action: str = "default") -> None:
        """
        Check if request is within rate limits.
        
        Args:
            identifier: Unique identifier for rate limiting (e.g., IP, user ID)
            action: Action type for different rate limits
            
        Raises:
            RateLimitError: If rate limit is exceeded
        """
        if not self._rate_limiter.check_limit(identifier, action):
            remaining_time = self._rate_limiter.get_reset_time(identifier, action)
            raise RateLimitError(
                f"Rate limit exceeded for {identifier}. Try again in {remaining_time} seconds."
            )
    
    def validate_pattern(self, pattern: str) -> str:
        """
        Validate AST-grep pattern for security issues.
        
        Args:
            pattern: Pattern to validate
            
        Returns:
            Validated pattern
            
        Raises:
            ValidationError: If pattern is invalid or dangerous
        """
        if not pattern or not pattern.strip():
            raise ValidationError("Pattern cannot be empty")
        
        pattern = pattern.strip()
        
        # Check pattern length
        if len(pattern) > self.config.max_pattern_length:
            raise ValidationError(f"Pattern too long: {len(pattern)} > {self.config.max_pattern_length}")
        
        # Check for dangerous patterns
        for pattern_name, compiled_pattern in self._compiled_patterns.items():
            if compiled_pattern.search(pattern):
                # Some patterns might be legitimate in AST-grep context
                if pattern_name in {r'\$\('}:  # $(command) is dangerous but $VAR is ok
                    if not re.match(r'^.*\$[A-Z_][A-Z0-9_]*.*$', pattern):
                        raise ValidationError(f"Potentially dangerous pattern: {pattern_name}")
                else:
                    raise ValidationError(f"Dangerous pattern detected: {pattern_name}")
        
        return pattern
    
    def create_secure_temp_dir(self) -> Path:
        """Create a secure temporary directory for operations."""
        temp_dir = Path(tempfile.mkdtemp(prefix="ast_grep_mcp_"))
        temp_dir.chmod(0o700)  # Owner read/write/execute only
        return temp_dir
    
    def enforce_resource_limits(self, operation: str, **limits) -> None:
        """
        Enforce resource limits for operations.
        
        Args:
            operation: Operation type
            **limits: Specific limits to enforce
        """
        if operation == "file_count" and "count" in limits:
            if limits["count"] > self.config.max_files_per_request:
                raise ResourceLimitError(
                    f"Too many files: {limits['count']} > {self.config.max_files_per_request}"
                )


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting."""
    # Operation-specific rate limits (requests per minute)
    search_rpm: int = 30      # AST-grep search operations
    scan_rpm: int = 10        # AST-grep scan operations 
    run_rpm: int = 5          # AST-grep run operations (write operations)
    call_graph_rpm: int = 15  # Call graph generation
    
    # Global rate limits
    global_rpm: int = 60      # Total requests per minute
    burst_rpm: int = 100      # Burst limit per minute
    
    # IP-based rate limits
    ip_rpm: int = 100         # Requests per minute per IP
    ip_burst_rpm: int = 200   # IP burst limit
    
    # Throttling settings
    enable_backoff: bool = True
    max_backoff_seconds: int = 300  # 5 minutes max backoff
    backoff_multiplier: float = 2.0
    
    # Window settings
    window_size_seconds: int = 60  # 1 minute windows
    cleanup_interval_seconds: int = 300  # Clean old entries every 5 minutes
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "search_rpm": self.search_rpm,
            "scan_rpm": self.scan_rpm,
            "run_rpm": self.run_rpm,
            "call_graph_rpm": self.call_graph_rpm,
            "global_rpm": self.global_rpm,
            "burst_rpm": self.burst_rpm,
            "ip_rpm": self.ip_rpm,
            "ip_burst_rpm": self.ip_burst_rpm,
            "enable_backoff": self.enable_backoff,
            "max_backoff_seconds": self.max_backoff_seconds,
            "backoff_multiplier": self.backoff_multiplier,
            "window_size_seconds": self.window_size_seconds,
            "cleanup_interval_seconds": self.cleanup_interval_seconds
        }


@dataclass
class TokenBucket:
    """Token bucket implementation for rate limiting."""
    capacity: int           # Maximum tokens
    tokens: float          # Current tokens available
    refill_rate: float     # Tokens per second
    last_refill: float     # Last refill timestamp
    
    def __post_init__(self):
        """Initialize token bucket."""
        if self.last_refill == 0:
            self.last_refill = time.time()
    
    def refill(self) -> None:
        """Refill tokens based on elapsed time."""
        now = time.time()
        elapsed = now - self.last_refill
        
        # Add tokens based on elapsed time
        tokens_to_add = elapsed * self.refill_rate
        self.tokens = min(self.capacity, self.tokens + tokens_to_add)
        self.last_refill = now
    
    def consume(self, tokens: int = 1) -> bool:
        """Try to consume tokens from the bucket.
        
        Args:
            tokens: Number of tokens to consume
            
        Returns:
            True if tokens were consumed, False if insufficient tokens
        """
        self.refill()
        
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False
    
    def available_tokens(self) -> int:
        """Get number of available tokens."""
        self.refill()
        return int(self.tokens)
    
    def time_until_tokens(self, tokens: int = 1) -> float:
        """Calculate time until specified tokens will be available.
        
        Args:
            tokens: Number of tokens needed
            
        Returns:
            Time in seconds until tokens will be available
        """
        self.refill()
        
        if self.tokens >= tokens:
            return 0.0
        
        tokens_needed = tokens - self.tokens
        return tokens_needed / self.refill_rate


@dataclass
class RateLimitEntry:
    """Rate limiting entry for tracking requests."""
    bucket: TokenBucket
    violation_count: int = 0
    last_violation: float = 0
    backoff_until: float = 0
    total_requests: int = 0
    total_violations: int = 0
    
    def is_in_backoff(self) -> bool:
        """Check if currently in backoff period."""
        return time.time() < self.backoff_until
    
    def calculate_backoff(self, config: RateLimitConfig) -> float:
        """Calculate backoff duration based on violation history.
        
        Args:
            config: Rate limit configuration
            
        Returns:
            Backoff duration in seconds
        """
        if not config.enable_backoff:
            return 0.0
        
        # Exponential backoff based on consecutive violations
        base_backoff = min(1.0 * (config.backoff_multiplier ** self.violation_count), 
                          config.max_backoff_seconds)
        
        return base_backoff
    
    def record_violation(self, config: RateLimitConfig) -> None:
        """Record a rate limit violation.
        
        Args:
            config: Rate limit configuration
        """
        now = time.time()
        self.violation_count += 1
        self.total_violations += 1
        self.last_violation = now
        
        # Set backoff period
        backoff_duration = self.calculate_backoff(config)
        self.backoff_until = now + backoff_duration
    
    def record_success(self) -> None:
        """Record a successful request (resets violation count)."""
        self.violation_count = 0
        self.total_requests += 1


class EnhancedRateLimitError(Exception):
    """Enhanced exception for rate limit violations."""
    
    def __init__(self, message: str, retry_after: float = 0, 
                 limit_type: str = "unknown", current_usage: int = 0, 
                 limit: int = 0):
        super().__init__(message)
        self.retry_after = retry_after
        self.limit_type = limit_type
        self.current_usage = current_usage
        self.limit = limit
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON responses."""
        return {
            "error": "RateLimitExceeded",
            "message": str(self),
            "retry_after": self.retry_after,
            "limit_type": self.limit_type,
            "current_usage": self.current_usage,
            "limit": self.limit
        }


class RateLimitManager:
    """Comprehensive rate limiting manager with token bucket algorithm."""
    
    def __init__(self, config: Optional[RateLimitConfig] = None):
        """Initialize rate limit manager.
        
        Args:
            config: Rate limiting configuration
        """
        self.config = config or RateLimitConfig()
        self.logger = logging.getLogger(__name__)
        
        # Rate limit stores
        self.user_limits: Dict[str, Dict[str, RateLimitEntry]] = defaultdict(dict)
        self.ip_limits: Dict[str, RateLimitEntry] = {}
        self.global_limits: Dict[str, RateLimitEntry] = {}
        
        # Cleanup tracking
        self.last_cleanup = time.time()
        
        # Operation limits mapping
        self.operation_limits = {
            "ast_grep_search": self.config.search_rpm,
            "ast_grep_scan": self.config.scan_rpm,
            "ast_grep_run": self.config.run_rpm,
            "call_graph_generate": self.config.call_graph_rpm
        }
        
        self.logger.info(f"Rate limiter initialized with config: {self.config.to_dict()}")
    
    def _create_token_bucket(self, rpm: int) -> TokenBucket:
        """Create a token bucket for the given rate per minute.
        
        Args:
            rpm: Requests per minute
            
        Returns:
            Configured TokenBucket instance
        """
        # Convert RPM to tokens per second
        tokens_per_second = rpm / 60.0
        
        return TokenBucket(
            capacity=rpm,
            tokens=float(rpm),  # Start with full bucket
            refill_rate=tokens_per_second,
            last_refill=time.time()
        )
    
    def _get_user_limit(self, user_id: str, operation: str) -> RateLimitEntry:
        """Get or create rate limit entry for user and operation.
        
        Args:
            user_id: User identifier
            operation: Operation name
            
        Returns:
            RateLimitEntry for the user and operation
        """
        if operation not in self.user_limits[user_id]:
            rpm = self.operation_limits.get(operation, self.config.global_rpm)
            bucket = self._create_token_bucket(rpm)
            self.user_limits[user_id][operation] = RateLimitEntry(bucket=bucket)
        
        return self.user_limits[user_id][operation]
    
    def _get_ip_limit(self, ip_address: str) -> RateLimitEntry:
        """Get or create rate limit entry for IP address.
        
        Args:
            ip_address: IP address
            
        Returns:
            RateLimitEntry for the IP address
        """
        if ip_address not in self.ip_limits:
            bucket = self._create_token_bucket(self.config.ip_rpm)
            self.ip_limits[ip_address] = RateLimitEntry(bucket=bucket)
        
        return self.ip_limits[ip_address]
    
    def _get_global_limit(self, operation: str) -> RateLimitEntry:
        """Get or create global rate limit entry for operation.
        
        Args:
            operation: Operation name
            
        Returns:
            RateLimitEntry for global operation limit
        """
        if operation not in self.global_limits:
            rpm = self.operation_limits.get(operation, self.config.global_rpm)
            bucket = self._create_token_bucket(rpm)
            self.global_limits[operation] = RateLimitEntry(bucket=bucket)
        
        return self.global_limits[operation]
    
    def check_rate_limit(self, user_context: UserContext, operation: str, 
                        ip_address: Optional[str] = None) -> Tuple[bool, Optional[EnhancedRateLimitError]]:
        """Check if request is within rate limits.
        
        Args:
            user_context: User context for the request
            operation: Operation being performed
            ip_address: Optional IP address for IP-based limiting
            
        Returns:
            Tuple of (allowed, error_if_not_allowed)
        """
        # Check user-specific rate limit
        user_limit = self._get_user_limit(user_context.user_id, operation)
        
        # Check if user is in backoff
        if user_limit.is_in_backoff():
            retry_after = user_limit.backoff_until - time.time()
            error = EnhancedRateLimitError(
                f"User {user_context.user_id} is in backoff period for {operation}",
                retry_after=retry_after,
                limit_type="user_backoff",
                current_usage=user_limit.violation_count,
                limit=0
            )
            return False, error
        
        # Check user operation limit
        if not user_limit.bucket.consume():
            retry_after = user_limit.bucket.time_until_tokens()
            user_limit.record_violation(self.config)
            
            rpm = self.operation_limits.get(operation, self.config.global_rpm)
            error = EnhancedRateLimitError(
                f"Rate limit exceeded for user {user_context.user_id} on {operation}. Limit: {rpm} RPM",
                retry_after=retry_after,
                limit_type="user_operation",
                current_usage=user_limit.total_requests,
                limit=rpm
            )
            return False, error
        
        # Check IP-based rate limit if IP provided
        if ip_address:
            ip_limit = self._get_ip_limit(ip_address)
            
            if ip_limit.is_in_backoff():
                retry_after = ip_limit.backoff_until - time.time()
                error = EnhancedRateLimitError(
                    f"IP {ip_address} is in backoff period",
                    retry_after=retry_after,
                    limit_type="ip_backoff",
                    current_usage=ip_limit.violation_count,
                    limit=0
                )
                return False, error
            
            if not ip_limit.bucket.consume():
                retry_after = ip_limit.bucket.time_until_tokens()
                ip_limit.record_violation(self.config)
                
                error = EnhancedRateLimitError(
                    f"Rate limit exceeded for IP {ip_address}. Limit: {self.config.ip_rpm} RPM",
                    retry_after=retry_after,
                    limit_type="ip",
                    current_usage=ip_limit.total_requests,
                    limit=self.config.ip_rpm
                )
                return False, error
            
            # Record successful IP request
            ip_limit.record_success()
        
        # Check global operation limit
        global_limit = self._get_global_limit(operation)
        
        if not global_limit.bucket.consume():
            retry_after = global_limit.bucket.time_until_tokens()
            global_limit.record_violation(self.config)
            
            rpm = self.operation_limits.get(operation, self.config.global_rpm)
            error = EnhancedRateLimitError(
                f"Global rate limit exceeded for {operation}. Limit: {rpm} RPM",
                retry_after=retry_after,
                limit_type="global_operation",
                current_usage=global_limit.total_requests,
                limit=rpm
            )
            return False, error
        
        # All checks passed - record successful request
        user_limit.record_success()
        global_limit.record_success()
        
        return True, None
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get comprehensive rate limiting statistics.
        
        Returns:
            Dictionary with rate limiting statistics
        """
        stats = {
            "config": self.config.to_dict(),
            "active_users": len(self.user_limits),
            "active_ips": len(self.ip_limits),
            "global_operations": len(self.global_limits),
            "total_user_operations": sum(len(ops) for ops in self.user_limits.values()),
            "last_cleanup": self.last_cleanup,
            "current_time": time.time()
        }
        
        # User statistics
        user_stats = {
            "total_requests": 0,
            "total_violations": 0,
            "users_in_backoff": 0
        }
        
        for user_id, operations in self.user_limits.items():
            for operation, entry in operations.items():
                user_stats["total_requests"] += entry.total_requests
                user_stats["total_violations"] += entry.total_violations
                if entry.is_in_backoff():
                    user_stats["users_in_backoff"] += 1
        
        stats["user_statistics"] = user_stats
        
        # IP statistics
        ip_stats = {
            "total_requests": sum(entry.total_requests for entry in self.ip_limits.values()),
            "total_violations": sum(entry.total_violations for entry in self.ip_limits.values()),
            "ips_in_backoff": sum(1 for entry in self.ip_limits.values() if entry.is_in_backoff())
        }
        
        stats["ip_statistics"] = ip_stats
        
        return stats


class RateLimiter:
    """Legacy rate limiting implementation using token bucket algorithm."""
    
    def __init__(self):
        """Initialize rate limiter."""
        self._buckets: Dict[str, Dict[str, Any]] = defaultdict(dict)
        self._config = {
            "default": {"capacity": 100, "refill_rate": 10, "window": 60},  # 100 requests per minute
            "search": {"capacity": 50, "refill_rate": 5, "window": 60},     # 50 searches per minute
            "scan": {"capacity": 10, "refill_rate": 1, "window": 60},       # 10 scans per minute
            "run": {"capacity": 20, "refill_rate": 2, "window": 60},        # 20 runs per minute
        }
    
    def check_limit(self, identifier: str, action: str = "default") -> bool:
        """Check if request is within rate limit."""
        config = self._config.get(action, self._config["default"])
        key = f"{identifier}:{action}"
        
        now = time.time()
        bucket = self._buckets[key]
        
        if "last_refill" not in bucket:
            bucket.update({
                "tokens": config["capacity"],
                "last_refill": now
            })
        
        # Refill tokens based on time elapsed
        time_elapsed = now - bucket["last_refill"]
        tokens_to_add = int(time_elapsed * config["refill_rate"])
        bucket["tokens"] = min(config["capacity"], bucket["tokens"] + tokens_to_add)
        bucket["last_refill"] = now
        
        # Check if request can be served
        if bucket["tokens"] >= 1:
            bucket["tokens"] -= 1
            return True
        
        return False
    
    def get_reset_time(self, identifier: str, action: str = "default") -> int:
        """Get time until rate limit resets."""
        config = self._config.get(action, self._config["default"])
        return max(1, int(config["capacity"] / config["refill_rate"]))


class AuditLogger:
    """Audit logging for security events."""
    
    def __init__(self):
        """Initialize audit logger."""
        self.logger = logging.getLogger("ast_grep_mcp.security.audit")
        self._event_history: deque = deque(maxlen=10000)  # Keep last 10k events
    
    def log_path_access(self, path: str, success: bool, error: Optional[str] = None) -> None:
        """Log path access attempts."""
        event = {
            "type": "path_access",
            "path": path,
            "success": success,
            "error": error,
            "timestamp": time.time()
        }
        
        self._event_history.append(event)
        
        if success:
            self.logger.info(f"Path access granted: {path}")
        else:
            self.logger.warning(f"Path access denied: {path} - {error}")
    
    def log_command_execution(self, command: str, args: List[str]) -> None:
        """Log command execution attempts."""
        event = {
            "type": "command_execution",
            "command": command,
            "args": args,
            "timestamp": time.time()
        }
        
        self._event_history.append(event)
        self.logger.info(f"Command execution: {command} {' '.join(args)}")
    
    def log_security_violation(self, violation_type: str, details: Dict[str, Any]) -> None:
        """Log security violations."""
        event = {
            "type": "security_violation",
            "violation_type": violation_type,
            "details": details,
            "timestamp": time.time()
        }
        
        self._event_history.append(event)
        self.logger.error(f"Security violation - {violation_type}: {details}")
    
    def get_recent_events(self, event_type: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent audit events."""
        events = list(self._event_history)
        
        if event_type:
            events = [e for e in events if e.get("type") == event_type]
        
        return events[-limit:]


# Global security manager instance
_security_manager: Optional[SecurityManager] = None


def get_security_manager() -> SecurityManager:
    """Get the global security manager instance."""
    global _security_manager
    if _security_manager is None:
        _security_manager = SecurityManager()
    return _security_manager


def initialize_security(config: Optional[ValidationConfig] = None) -> SecurityManager:
    """Initialize the global security manager with custom config."""
    global _security_manager
    _security_manager = SecurityManager(config)
    return _security_manager


# Convenience functions for common security operations
def secure_validate_path(path: Union[str, Path], base_path: Optional[Union[str, Path]] = None) -> Path:
    """Validate path using global security manager."""
    return get_security_manager().validate_path(path, base_path)


def secure_validate_pattern(pattern: str) -> str:
    """Validate pattern using global security manager."""
    return get_security_manager().validate_pattern(pattern)


def secure_sanitize_command(command: str, args: List[str]) -> Tuple[str, List[str]]:
    """Sanitize command using global security manager."""
    return get_security_manager().sanitize_command_args(command, args)


def secure_check_rate_limit(identifier: str, action: str = "default") -> None:
    """Check rate limit using global security manager."""
    return get_security_manager().check_rate_limit(identifier, action)


# Global rate limit manager instance
_rate_limit_manager: Optional[RateLimitManager] = None


def get_rate_limit_manager(config: Optional[RateLimitConfig] = None) -> RateLimitManager:
    """Get or create global rate limit manager instance.
    
    Args:
        config: Optional rate limit configuration
        
    Returns:
        Global RateLimitManager instance
    """
    global _rate_limit_manager
    
    if _rate_limit_manager is None:
        _rate_limit_manager = RateLimitManager(config)
    
    return _rate_limit_manager


def reset_rate_limit_manager() -> None:
    """Reset global rate limit manager (mainly for testing)."""
    global _rate_limit_manager
    _rate_limit_manager = None 