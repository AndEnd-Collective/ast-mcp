"""
Enhanced Configuration Management System for AST-Grep MCP Server.

This module provides comprehensive configuration management with:
- Pydantic model validation
- Multi-format configuration files (YAML, JSON, TOML)
- Environment variable support
- Secret management and encryption
- Multi-environment profiles
- Configuration audit logging
- Hot reload capabilities
"""

import os
import json
import yaml
import hashlib
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List, Union, Literal
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum
import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from pydantic import BaseModel, Field, validator, root_validator
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


class EnvironmentType(str, Enum):
    """Supported environment types."""
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TESTING = "testing"


class LogLevel(str, Enum):
    """Supported log levels."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class LogFormat(str, Enum):
    """Supported log formats."""
    STRUCTURED = "structured"
    TEXT = "text"
    JSON = "json"


class SecurityConfig(BaseModel):
    """Security-related configuration."""
    
    enable_security: bool = Field(True, description="Enable security features")
    enable_audit_logging: bool = Field(True, description="Enable audit logging")
    enable_rate_limiting: bool = Field(True, description="Enable rate limiting")
    enable_input_validation: bool = Field(True, description="Enable input validation")
    enable_path_traversal_protection: bool = Field(True, description="Enable path traversal protection")
    enable_command_injection_protection: bool = Field(True, description="Enable command injection protection")
    
    # Rate limiting settings
    rate_limit_requests: int = Field(100, ge=1, description="Maximum requests per window")
    rate_limit_window: int = Field(60, ge=1, description="Rate limit window in seconds")
    
    # Validation settings
    max_input_size: int = Field(1024 * 1024, ge=1024, description="Maximum input size in bytes")
    max_output_size: int = Field(10 * 1024 * 1024, ge=1024, description="Maximum output size in bytes")
    
    # Path restrictions
    allowed_paths: List[str] = Field(default_factory=list, description="Allowed base paths for file operations")
    blocked_paths: List[str] = Field(default_factory=list, description="Blocked paths for file operations")
    
    class Config:
        env_prefix = "AST_GREP_SECURITY_"


class PerformanceConfig(BaseModel):
    """Performance-related configuration."""
    
    enable_performance: bool = Field(True, description="Enable performance monitoring")
    enable_caching: bool = Field(True, description="Enable result caching")
    enable_memory_monitoring: bool = Field(True, description="Enable memory monitoring")
    enable_metrics_collection: bool = Field(True, description="Enable metrics collection")
    
    # Cache settings
    cache_ttl: int = Field(300, ge=1, description="Cache TTL in seconds")
    cache_max_size: int = Field(1000, ge=1, description="Maximum cache entries")
    
    # Memory settings
    memory_warning_threshold: float = Field(85.0, ge=0.0, le=100.0, description="Memory warning threshold (%)")
    memory_critical_threshold: float = Field(95.0, ge=0.0, le=100.0, description="Memory critical threshold (%)")
    
    # CPU settings
    cpu_warning_threshold: float = Field(80.0, ge=0.0, le=100.0, description="CPU warning threshold (%)")
    cpu_critical_threshold: float = Field(95.0, ge=0.0, le=100.0, description="CPU critical threshold (%)")
    
    # Execution limits
    max_execution_time: int = Field(30, ge=1, description="Maximum execution time in seconds")
    max_concurrent_requests: int = Field(10, ge=1, description="Maximum concurrent requests")
    
    @validator('memory_critical_threshold')
    def validate_memory_critical(cls, value, values):
        if 'memory_warning_threshold' in values and value <= values['memory_warning_threshold']:
            raise ValueError('Memory critical threshold must be greater than warning threshold')
        return value
    
    @validator('cpu_critical_threshold')
    def validate_cpu_critical(cls, value, values):
        if 'cpu_warning_threshold' in values and value <= values['cpu_warning_threshold']:
            raise ValueError('CPU critical threshold must be greater than warning threshold')
        return value
    
    class Config:
        env_prefix = "AST_GREP_PERFORMANCE_"


class MonitoringConfig(BaseModel):
    """Monitoring and health check configuration."""
    
    enable_monitoring: bool = Field(True, description="Enable monitoring features")
    enable_health_checks: bool = Field(True, description="Enable health checks")
    enable_system_monitoring: bool = Field(True, description="Enable system resource monitoring")
    enable_dependency_checks: bool = Field(True, description="Enable dependency health checks")
    enable_alerting: bool = Field(True, description="Enable alerting")
    enable_detailed_diagnostics: bool = Field(True, description="Enable detailed diagnostics")
    
    # Health check settings
    health_check_interval: int = Field(30, ge=1, description="Health check interval in seconds")
    max_health_history: int = Field(100, ge=1, description="Maximum health check history entries")
    dependency_check_timeout: int = Field(10, ge=1, description="Dependency check timeout in seconds")
    
    # Alert settings
    alert_cooldown: int = Field(300, ge=1, description="Alert cooldown period in seconds")
    max_alerts: int = Field(100, ge=1, description="Maximum alerts to keep in history")
    
    class Config:
        env_prefix = "AST_GREP_MONITORING_"


class LoggingConfig(BaseModel):
    """Logging configuration."""
    
    enable_enhanced_logging: bool = Field(True, description="Enable enhanced logging features")
    log_level: LogLevel = Field(LogLevel.INFO, description="Logging level")
    log_format: LogFormat = Field(LogFormat.STRUCTURED, description="Log format")
    enable_correlation_ids: bool = Field(True, description="Enable correlation ID tracking")
    enable_performance_logging: bool = Field(True, description="Enable performance logging")
    enable_audit_logging: bool = Field(True, description="Enable audit logging")
    
    # File logging settings
    enable_file_logging: bool = Field(False, description="Enable file logging")
    log_file_path: Optional[str] = Field(None, description="Log file path")
    log_file_max_size: int = Field(10 * 1024 * 1024, ge=1024, description="Log file max size in bytes")
    log_file_backup_count: int = Field(5, ge=1, description="Number of backup log files")
    
    # Console logging settings
    enable_console_logging: bool = Field(True, description="Enable console logging")
    console_log_level: Optional[LogLevel] = Field(None, description="Console log level (defaults to log_level)")
    
    # Sensitive data filtering
    enable_sensitive_data_filtering: bool = Field(True, description="Enable sensitive data filtering")
    sensitive_patterns: List[str] = Field(
        default_factory=lambda: [
            r'(?i)(password|secret|key|token|credential)[\s]*[:=][\s]*["\']?([^"\'\s]+)',
            r'(?i)(api[_-]?key)[\s]*[:=][\s]*["\']?([^"\'\s]+)',
            r'(?i)(auth[_-]?token)[\s]*[:=][\s]*["\']?([^"\'\s]+)'
        ],
        description="Patterns for sensitive data filtering"
    )
    
    class Config:
        env_prefix = "AST_GREP_LOGGING_"


class ASTGrepConfig(BaseModel):
    """AST-Grep specific configuration."""
    
    # Binary location
    ast_grep_path: Optional[str] = Field(None, description="Path to ast-grep binary")
    auto_detect_binary: bool = Field(True, description="Auto-detect ast-grep binary")
    
    # Execution settings
    default_timeout: int = Field(30, ge=1, description="Default execution timeout in seconds")
    max_timeout: int = Field(300, ge=1, description="Maximum allowed timeout in seconds")
    
    # Language settings
    supported_languages: List[str] = Field(
        default_factory=lambda: [
            "python", "javascript", "typescript", "java", "c", "cpp", "rust", "go",
            "ruby", "php", "swift", "kotlin", "scala", "csharp", "html", "css",
            "json", "yaml", "xml", "sql", "bash", "powershell"
        ],
        description="Supported programming languages"
    )
    
    # Pattern settings
    max_pattern_length: int = Field(10000, ge=1, description="Maximum pattern length")
    max_results: int = Field(1000, ge=1, description="Maximum results per query")
    
    class Config:
        env_prefix = "AST_GREP_"


class ServerConfig(BaseModel):
    """Main server configuration."""
    
    # Basic server settings
    name: str = Field("ast-grep-mcp", description="Server name")
    version: str = Field("1.0.0", description="Server version")
    environment: EnvironmentType = Field(EnvironmentType.DEVELOPMENT, description="Environment type")
    debug: bool = Field(False, description="Enable debug mode")
    
    # Shutdown settings
    shutdown_timeout: float = Field(30.0, ge=0.0, description="Graceful shutdown timeout in seconds")
    force_shutdown_timeout: float = Field(10.0, ge=0.0, description="Force shutdown timeout in seconds")
    
    # Component configurations
    security: SecurityConfig = Field(default_factory=SecurityConfig, description="Security configuration")
    performance: PerformanceConfig = Field(default_factory=PerformanceConfig, description="Performance configuration")
    monitoring: MonitoringConfig = Field(default_factory=MonitoringConfig, description="Monitoring configuration")
    logging: LoggingConfig = Field(default_factory=LoggingConfig, description="Logging configuration")
    ast_grep: ASTGrepConfig = Field(default_factory=ASTGrepConfig, description="AST-Grep configuration")
    
    class Config:
        env_prefix = "AST_GREP_MCP_"
        env_nested_delimiter = "__"
        case_sensitive = False


class ConfigurationManager:
    """Enhanced configuration manager with multi-format support and secret management."""
    
    def __init__(self, config_dir: Optional[Union[str, Path]] = None):
        """Initialize configuration manager."""
        self.config_dir = Path(config_dir) if config_dir else Path.cwd()
        self.config_file_name = "ast-grep-mcp.yaml"
        self.secrets_file_name = "secrets.yaml"
        self.config_schema_file = "config-schema.json"
        
        self._config: Optional[ServerConfig] = None
        self._config_file_path: Optional[Path] = None
        self._secrets_file_path: Optional[Path] = None
        self._config_hash: Optional[str] = None
        self._encryption_key: Optional[bytes] = None
        
        # Configuration change tracking
        self._change_history: List[Dict[str, Any]] = []
        self._max_change_history = 100
        
    def load_configuration(self, config_file: Optional[Union[str, Path]] = None) -> ServerConfig:
        """Load configuration from file and environment variables."""
        try:
            # Determine config file path
            if config_file:
                self._config_file_path = Path(config_file)
            else:
                self._config_file_path = self.config_dir / self.config_file_name
            
            # Load configuration data
            config_data = {}
            if self._config_file_path.exists():
                config_data = self._load_config_file(self._config_file_path)
                logger.info(f"Loaded configuration from {self._config_file_path}")
            else:
                logger.info(f"No configuration file found at {self._config_file_path}, using defaults")
            
            # Load secrets if available
            secrets_data = self._load_secrets()
            if secrets_data:
                config_data.update(secrets_data)
                logger.info("Loaded encrypted secrets")
            
            # Create configuration with environment variable overrides
            self._config = ServerConfig(**config_data)
            
            # Calculate configuration hash for change detection
            self._config_hash = self._calculate_config_hash()
            
            # Log configuration loading
            self._log_configuration_change("loaded", "Configuration loaded successfully")
            
            return self._config
            
        except Exception as e:
            logger.error(f"Failed to load configuration: {e}")
            raise ConfigurationError(f"Configuration loading failed: {e}")
    
    def _load_config_file(self, config_path: Path) -> Dict[str, Any]:
        """Load configuration from YAML, JSON, or TOML file."""
        try:
            content = config_path.read_text(encoding='utf-8')
            
            if config_path.suffix.lower() == '.yaml' or config_path.suffix.lower() == '.yml':
                return yaml.safe_load(content) or {}
            elif config_path.suffix.lower() == '.json':
                return json.loads(content)
            elif config_path.suffix.lower() == '.toml':
                import tomllib
                return tomllib.loads(content)
            else:
                raise ConfigurationError(f"Unsupported configuration file format: {config_path.suffix}")
                
        except Exception as e:
            raise ConfigurationError(f"Failed to parse configuration file {config_path}: {e}")
    
    def _load_secrets(self) -> Optional[Dict[str, Any]]:
        """Load encrypted secrets from secrets file."""
        secrets_path = self.config_dir / self.secrets_file_name
        if not secrets_path.exists():
            return None
        
        try:
            # Load encrypted secrets
            with secrets_path.open('rb') as f:
                encrypted_data = f.read()
            
            # Decrypt if encryption key is available
            if self._encryption_key:
                fernet = Fernet(self._encryption_key)
                decrypted_data = fernet.decrypt(encrypted_data)
                return yaml.safe_load(decrypted_data.decode('utf-8'))
            else:
                # Assume plaintext for development
                return yaml.safe_load(encrypted_data.decode('utf-8'))
                
        except Exception as e:
            logger.warning(f"Failed to load secrets: {e}")
            return None
    
    def _calculate_config_hash(self) -> str:
        """Calculate SHA-256 hash of current configuration."""
        if not self._config:
            return ""
        
        config_json = self._config.json(sort_keys=True)
        return hashlib.sha256(config_json.encode()).hexdigest()
    
    def _log_configuration_change(self, action: str, description: str):
        """Log configuration change for audit trail."""
        change_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "action": action,
            "description": description,
            "config_hash": self._config_hash,
            "user": os.getenv("USER", "unknown"),
            "pid": os.getpid()
        }
        
        self._change_history.append(change_entry)
        
        # Limit history size
        if len(self._change_history) > self._max_change_history:
            self._change_history = self._change_history[-self._max_change_history:]
        
        logger.info(f"Configuration change: {action} - {description}")
    
    def get_configuration(self) -> ServerConfig:
        """Get current configuration."""
        if not self._config:
            return self.load_configuration()
        return self._config
    
    def reload_configuration(self) -> bool:
        """Reload configuration and detect changes."""
        try:
            old_hash = self._config_hash
            new_config = self.load_configuration()
            
            if self._config_hash != old_hash:
                self._log_configuration_change("reloaded", "Configuration reloaded with changes")
                return True
            else:
                logger.info("Configuration reloaded - no changes detected")
                return False
                
        except Exception as e:
            logger.error(f"Failed to reload configuration: {e}")
            return False
    
    def save_configuration(self, config: Optional[ServerConfig] = None) -> bool:
        """Save configuration to file."""
        try:
            config_to_save = config or self._config
            if not config_to_save:
                raise ConfigurationError("No configuration to save")
            
            # Ensure config directory exists
            self.config_dir.mkdir(parents=True, exist_ok=True)
            
            # Convert to dictionary
            config_dict = config_to_save.dict()
            
            # Save to YAML file
            config_path = self._config_file_path or (self.config_dir / self.config_file_name)
            with config_path.open('w', encoding='utf-8') as f:
                yaml.dump(config_dict, f, default_flow_style=False, indent=2)
            
            self._log_configuration_change("saved", f"Configuration saved to {config_path}")
            logger.info(f"Configuration saved to {config_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save configuration: {e}")
            return False
    
    def export_configuration(self, output_path: Union[str, Path], format: str = "yaml") -> bool:
        """Export configuration to specified format."""
        try:
            if not self._config:
                raise ConfigurationError("No configuration loaded")
            
            output_path = Path(output_path)
            config_dict = self._config.dict()
            
            if format.lower() == "yaml":
                with output_path.open('w', encoding='utf-8') as f:
                    yaml.dump(config_dict, f, default_flow_style=False, indent=2)
            elif format.lower() == "json":
                with output_path.open('w', encoding='utf-8') as f:
                    json.dump(config_dict, f, indent=2, default=str)
            else:
                raise ConfigurationError(f"Unsupported export format: {format}")
            
            self._log_configuration_change("exported", f"Configuration exported to {output_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to export configuration: {e}")
            return False
    
    def validate_configuration(self, config: Optional[ServerConfig] = None) -> Dict[str, Any]:
        """Validate configuration and return validation results."""
        try:
            config_to_validate = config or self._config
            if not config_to_validate:
                return {"valid": False, "errors": ["No configuration to validate"]}
            
            # Pydantic validation is automatic, but we can add custom validation
            validation_results = {
                "valid": True,
                "errors": [],
                "warnings": [],
                "info": []
            }
            
            # Custom validation rules
            self._validate_paths(config_to_validate, validation_results)
            self._validate_thresholds(config_to_validate, validation_results)
            self._validate_dependencies(config_to_validate, validation_results)
            
            return validation_results
            
        except Exception as e:
            return {
                "valid": False,
                "errors": [f"Validation failed: {str(e)}"],
                "warnings": [],
                "info": []
            }
    
    def _validate_paths(self, config: ServerConfig, results: Dict[str, Any]):
        """Validate file paths in configuration."""
        # Validate log file path
        if config.logging.enable_file_logging and config.logging.log_file_path:
            log_dir = Path(config.logging.log_file_path).parent
            if not log_dir.exists():
                results["warnings"].append(f"Log file directory does not exist: {log_dir}")
        
        # Validate AST-Grep path
        if config.ast_grep.ast_grep_path:
            ast_grep_path = Path(config.ast_grep.ast_grep_path)
            if not ast_grep_path.exists():
                results["warnings"].append(f"AST-Grep binary not found: {ast_grep_path}")
    
    def _validate_thresholds(self, config: ServerConfig, results: Dict[str, Any]):
        """Validate threshold configurations."""
        # Already validated by Pydantic validators
        pass
    
    def _validate_dependencies(self, config: ServerConfig, results: Dict[str, Any]):
        """Validate system dependencies."""
        # Check for required Python packages
        required_packages = ['pydantic', 'yaml', 'cryptography']
        for package in required_packages:
            try:
                __import__(package)
            except ImportError:
                results["errors"].append(f"Required package not installed: {package}")
                results["valid"] = False
    
    def get_change_history(self) -> List[Dict[str, Any]]:
        """Get configuration change history."""
        return self._change_history.copy()
    
    def create_environment_template(self, environment: EnvironmentType, output_path: Union[str, Path]) -> bool:
        """Create configuration template for specific environment."""
        try:
            template_config = ServerConfig(environment=environment)
            
            # Customize based on environment
            if environment == EnvironmentType.PRODUCTION:
                template_config.debug = False
                template_config.logging.log_level = LogLevel.WARNING
                template_config.security.enable_security = True
                template_config.performance.enable_caching = True
            elif environment == EnvironmentType.DEVELOPMENT:
                template_config.debug = True
                template_config.logging.log_level = LogLevel.DEBUG
                template_config.security.enable_security = False
                template_config.performance.enable_caching = False
            
            # Save template
            output_path = Path(output_path)
            with output_path.open('w', encoding='utf-8') as f:
                yaml.dump(template_config.dict(), f, default_flow_style=False, indent=2)
            
            logger.info(f"Created {environment.value} configuration template at {output_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create configuration template: {e}")
            return False
    
    def set_encryption_key(self, password: str):
        """Set encryption key for secrets management."""
        salt = b'ast-grep-mcp-salt'  # In production, use a random salt
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        self._encryption_key = key


class ConfigurationError(Exception):
    """Configuration-related error."""
    pass


# Global configuration manager instance
_config_manager: Optional[ConfigurationManager] = None


def get_config_manager(config_dir: Optional[Union[str, Path]] = None) -> ConfigurationManager:
    """Get global configuration manager instance."""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigurationManager(config_dir)
    return _config_manager


def load_configuration(config_file: Optional[Union[str, Path]] = None, 
                      config_dir: Optional[Union[str, Path]] = None) -> ServerConfig:
    """Load configuration using global configuration manager."""
    manager = get_config_manager(config_dir)
    return manager.load_configuration(config_file)


def get_configuration() -> ServerConfig:
    """Get current configuration."""
    manager = get_config_manager()
    return manager.get_configuration()


def reload_configuration() -> bool:
    """Reload configuration and detect changes."""
    manager = get_config_manager()
    return manager.reload_configuration() 