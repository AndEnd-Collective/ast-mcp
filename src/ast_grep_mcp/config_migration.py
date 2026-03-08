"""
Configuration Migration Utility for AST-Grep MCP Server.

This module provides utilities to migrate from the old environment-based
ServerConfig to the new enhanced configuration system with Pydantic models.
"""

import os
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
import yaml

from .config import (
    ServerConfig as NewServerConfig,
    SecurityConfig, PerformanceConfig, MonitoringConfig, 
    LoggingConfig, ASTGrepConfig, EnvironmentType, LogLevel, LogFormat,
    ConfigurationManager, ConfigurationError
)

logger = logging.getLogger(__name__)


class LegacyServerConfig:
    """Legacy ServerConfig class for migration purposes."""
    
    def __init__(self):
        """Initialize legacy configuration from environment variables."""
        self.name = os.getenv("AST_GREP_MCP_NAME", "ast-mcp")
        self.version = os.getenv("AST_GREP_MCP_VERSION", "1.0.0")
        
        # Performance settings
        self.enable_performance = os.getenv("AST_GREP_ENABLE_PERFORMANCE", "true").lower() == "true"
        self.enable_security = os.getenv("AST_GREP_ENABLE_SECURITY", "true").lower() == "true"
        self.enable_monitoring = os.getenv("AST_GREP_ENABLE_MONITORING", "true").lower() == "true"
        
        # Enhanced monitoring settings
        self.health_check_interval = int(os.getenv("AST_GREP_HEALTH_CHECK_INTERVAL", "30"))
        self.max_health_history = int(os.getenv("AST_GREP_MAX_HEALTH_HISTORY", "100"))
        self.system_monitoring_enabled = os.getenv("AST_GREP_SYSTEM_MONITORING", "true").lower() == "true"
        self.dependency_check_enabled = os.getenv("AST_GREP_DEPENDENCY_CHECK", "true").lower() == "true"
        self.alerting_enabled = os.getenv("AST_GREP_ALERTING", "true").lower() == "true"
        self.detailed_diagnostics = os.getenv("AST_GREP_DETAILED_DIAGNOSTICS", "true").lower() == "true"
        
        # System resource monitoring thresholds
        self.cpu_warning_threshold = float(os.getenv("AST_GREP_CPU_WARNING", "80.0"))
        self.cpu_critical_threshold = float(os.getenv("AST_GREP_CPU_CRITICAL", "95.0"))
        self.memory_warning_threshold = float(os.getenv("AST_GREP_MEMORY_WARNING", "85.0"))
        self.memory_critical_threshold = float(os.getenv("AST_GREP_MEMORY_CRITICAL", "95.0"))
        
        # Rate limiting
        self.rate_limit_enabled = os.getenv("AST_GREP_RATE_LIMIT", "true").lower() == "true"
        self.rate_limit_requests = int(os.getenv("AST_GREP_RATE_LIMIT_REQUESTS", "100"))
        self.rate_limit_window = int(os.getenv("AST_GREP_RATE_LIMIT_WINDOW", "60"))
        
        # Enhanced logging settings
        self.enable_enhanced_logging = os.getenv("AST_GREP_ENHANCED_LOGGING", "true").lower() == "true"
        self.log_level = os.getenv("AST_GREP_LOG_LEVEL", "INFO").upper()
        self.log_format = os.getenv("AST_GREP_LOG_FORMAT", "structured").lower()
        self.log_correlation_ids = os.getenv("AST_GREP_LOG_CORRELATION_IDS", "true").lower() == "true"


class ConfigurationMigrator:
    """Handles migration from legacy to new configuration system."""
    
    def __init__(self, config_dir: Optional[Path] = None):
        """Initialize migration utility."""
        self.config_dir = config_dir or Path.cwd()
        self.backup_dir = self.config_dir / "config_backups"
        self.backup_dir.mkdir(exist_ok=True)
        
    def migrate_from_legacy(self, output_file: Optional[Path] = None) -> NewServerConfig:
        """Migrate from legacy environment-based configuration to new system."""
        try:
            logger.info("Starting configuration migration from legacy system")
            
            # Load legacy configuration
            legacy_config = LegacyServerConfig()
            
            # Create new configuration structure
            new_config = self._convert_legacy_to_new(legacy_config)
            
            # Save to file if specified
            if output_file:
                self._save_migrated_config(new_config, output_file)
                logger.info(f"Migrated configuration saved to {output_file}")
            
            logger.info("Configuration migration completed successfully")
            return new_config
            
        except Exception as e:
            logger.error(f"Configuration migration failed: {e}")
            raise ConfigurationError(f"Migration failed: {e}")
    
    def _convert_legacy_to_new(self, legacy: LegacyServerConfig) -> NewServerConfig:
        """Convert legacy configuration to new structure."""
        
        # Map legacy environment type
        environment = EnvironmentType.DEVELOPMENT  # Default
        if os.getenv("AST_GREP_ENVIRONMENT"):
            env_str = os.getenv("AST_GREP_ENVIRONMENT").lower()
            if env_str in ["production", "prod"]:
                environment = EnvironmentType.PRODUCTION
            elif env_str in ["staging", "stage"]:
                environment = EnvironmentType.STAGING
            elif env_str in ["testing", "test"]:
                environment = EnvironmentType.TESTING
        
        # Map legacy log level
        log_level = LogLevel.INFO
        try:
            log_level = LogLevel(legacy.log_level)
        except ValueError:
            logger.warning(f"Unknown log level '{legacy.log_level}', using INFO")
        
        # Map legacy log format
        log_format = LogFormat.STRUCTURED
        if legacy.log_format == "json":
            log_format = LogFormat.JSON
        elif legacy.log_format == "text":
            log_format = LogFormat.TEXT
        
        # Create component configurations
        security_config = SecurityConfig(
            enable_security=legacy.enable_security,
            enable_rate_limiting=legacy.rate_limit_enabled,
            rate_limit_requests=legacy.rate_limit_requests,
            rate_limit_window=legacy.rate_limit_window
        )
        
        performance_config = PerformanceConfig(
            enable_performance=legacy.enable_performance,
            cpu_warning_threshold=legacy.cpu_warning_threshold,
            cpu_critical_threshold=legacy.cpu_critical_threshold,
            memory_warning_threshold=legacy.memory_warning_threshold,
            memory_critical_threshold=legacy.memory_critical_threshold
        )
        
        monitoring_config = MonitoringConfig(
            enable_monitoring=legacy.enable_monitoring,
            enable_system_monitoring=legacy.system_monitoring_enabled,
            enable_dependency_checks=legacy.dependency_check_enabled,
            enable_alerting=legacy.alerting_enabled,
            enable_detailed_diagnostics=legacy.detailed_diagnostics,
            health_check_interval=legacy.health_check_interval,
            max_health_history=legacy.max_health_history
        )
        
        logging_config = LoggingConfig(
            enable_enhanced_logging=legacy.enable_enhanced_logging,
            log_level=log_level,
            log_format=log_format,
            enable_correlation_ids=legacy.log_correlation_ids
        )
        
        ast_grep_config = ASTGrepConfig()
        
        # Create main configuration
        new_config = NewServerConfig(
            name=legacy.name,
            version=legacy.version,
            environment=environment,
            security=security_config,
            performance=performance_config,
            monitoring=monitoring_config,
            logging=logging_config,
            ast_grep=ast_grep_config
        )
        
        return new_config
    
    def _save_migrated_config(self, config: NewServerConfig, output_file: Path):
        """Save migrated configuration to file."""
        try:
            # Ensure output directory exists
            output_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Convert to dictionary and save as YAML
            config_dict = config.model_dump(mode='json')
            
            with output_file.open('w', encoding='utf-8') as f:
                yaml.dump(config_dict, f, default_flow_style=False, indent=2)
                
        except Exception as e:
            raise ConfigurationError(f"Failed to save migrated configuration: {e}")
    
    def create_backup(self, source_file: Path, backup_name: Optional[str] = None) -> Path:
        """Create backup of existing configuration file."""
        try:
            if not source_file.exists():
                raise ConfigurationError(f"Source file does not exist: {source_file}")
            
            # Generate backup name
            if not backup_name:
                timestamp = self._get_timestamp()
                backup_name = f"{source_file.stem}_{timestamp}{source_file.suffix}"
            
            backup_path = self.backup_dir / backup_name
            
            # Copy file to backup location
            import shutil
            shutil.copy2(source_file, backup_path)
            
            logger.info(f"Configuration backup created: {backup_path}")
            return backup_path
            
        except Exception as e:
            raise ConfigurationError(f"Failed to create backup: {e}")
    
    def validate_migration(self, legacy_config: LegacyServerConfig, 
                          new_config: NewServerConfig) -> Dict[str, Any]:
        """Validate that migration preserved all important settings."""
        try:
            validation_results = {
                "valid": True,
                "errors": [],
                "warnings": [],
                "mapping_report": {}
            }
            
            # Check basic settings
            self._validate_basic_settings(legacy_config, new_config, validation_results)
            
            # Check component mappings
            self._validate_security_mapping(legacy_config, new_config, validation_results)
            self._validate_performance_mapping(legacy_config, new_config, validation_results)
            self._validate_monitoring_mapping(legacy_config, new_config, validation_results)
            self._validate_logging_mapping(legacy_config, new_config, validation_results)
            
            # Report unmapped settings
            self._check_unmapped_settings(legacy_config, validation_results)
            
            return validation_results
            
        except Exception as e:
            return {
                "valid": False,
                "errors": [f"Validation failed: {str(e)}"],
                "warnings": [],
                "mapping_report": {}
            }
    
    def _validate_basic_settings(self, legacy: LegacyServerConfig, 
                                new: NewServerConfig, results: Dict[str, Any]):
        """Validate basic server settings migration."""
        if legacy.name != new.name:
            results["errors"].append(f"Name mismatch: {legacy.name} != {new.name}")
            results["valid"] = False
        
        if legacy.version != new.version:
            results["errors"].append(f"Version mismatch: {legacy.version} != {new.version}")
            results["valid"] = False
        
        results["mapping_report"]["basic_settings"] = {
            "name": "✓" if legacy.name == new.name else "✗",
            "version": "✓" if legacy.version == new.version else "✗"
        }
    
    def _validate_security_mapping(self, legacy: LegacyServerConfig, 
                                  new: NewServerConfig, results: Dict[str, Any]):
        """Validate security settings migration."""
        security_mapping = {}
        
        if legacy.enable_security != new.security.enable_security:
            results["warnings"].append("Security enable setting may have changed during migration")
        security_mapping["enable_security"] = "✓" if legacy.enable_security == new.security.enable_security else "?"
        
        if legacy.rate_limit_enabled != new.security.enable_rate_limiting:
            results["warnings"].append("Rate limiting setting may have changed during migration")
        security_mapping["rate_limiting"] = "✓" if legacy.rate_limit_enabled == new.security.enable_rate_limiting else "?"
        
        results["mapping_report"]["security"] = security_mapping
    
    def _validate_performance_mapping(self, legacy: LegacyServerConfig, 
                                     new: NewServerConfig, results: Dict[str, Any]):
        """Validate performance settings migration."""
        performance_mapping = {}
        
        performance_mapping["enable_performance"] = "✓" if legacy.enable_performance == new.performance.enable_performance else "?"
        performance_mapping["cpu_warning"] = "✓" if legacy.cpu_warning_threshold == new.performance.cpu_warning_threshold else "?"
        performance_mapping["memory_warning"] = "✓" if legacy.memory_warning_threshold == new.performance.memory_warning_threshold else "?"
        
        results["mapping_report"]["performance"] = performance_mapping
    
    def _validate_monitoring_mapping(self, legacy: LegacyServerConfig, 
                                    new: NewServerConfig, results: Dict[str, Any]):
        """Validate monitoring settings migration."""
        monitoring_mapping = {}
        
        monitoring_mapping["enable_monitoring"] = "✓" if legacy.enable_monitoring == new.monitoring.enable_monitoring else "?"
        monitoring_mapping["health_interval"] = "✓" if legacy.health_check_interval == new.monitoring.health_check_interval else "?"
        monitoring_mapping["system_monitoring"] = "✓" if legacy.system_monitoring_enabled == new.monitoring.enable_system_monitoring else "?"
        
        results["mapping_report"]["monitoring"] = monitoring_mapping
    
    def _validate_logging_mapping(self, legacy: LegacyServerConfig, 
                                 new: NewServerConfig, results: Dict[str, Any]):
        """Validate logging settings migration."""
        logging_mapping = {}
        
        logging_mapping["enhanced_logging"] = "✓" if legacy.enable_enhanced_logging == new.logging.enable_enhanced_logging else "?"
        logging_mapping["correlation_ids"] = "✓" if legacy.log_correlation_ids == new.logging.enable_correlation_ids else "?"
        
        # Check log level mapping
        try:
            legacy_level = LogLevel(legacy.log_level)
            logging_mapping["log_level"] = "✓" if legacy_level == new.logging.log_level else "?"
        except ValueError:
            logging_mapping["log_level"] = "?"
            results["warnings"].append(f"Could not validate log level mapping for '{legacy.log_level}'")
        
        results["mapping_report"]["logging"] = logging_mapping
    
    def _check_unmapped_settings(self, legacy: LegacyServerConfig, results: Dict[str, Any]):
        """Check for legacy settings that weren't mapped to new configuration."""
        # This would contain logic to identify settings that exist in legacy
        # but don't have a clear mapping in the new system
        unmapped = []
        
        # Add logic here to detect unmapped settings
        # For now, just add a placeholder
        if hasattr(legacy, 'deprecated_setting'):
            unmapped.append('deprecated_setting')
        
        if unmapped:
            results["warnings"].extend([f"Unmapped legacy setting: {setting}" for setting in unmapped])
            results["mapping_report"]["unmapped"] = unmapped
    
    def _get_timestamp(self) -> str:
        """Get timestamp string for backup files."""
        from datetime import datetime
        return datetime.now().strftime("%Y%m%d_%H%M%S")
    
    def generate_migration_report(self, legacy_config: LegacyServerConfig,
                                 new_config: NewServerConfig) -> str:
        """Generate a human-readable migration report."""
        validation = self.validate_migration(legacy_config, new_config)
        
        report = []
        report.append("=== Configuration Migration Report ===")
        report.append(f"Migration Status: {'SUCCESSFUL' if validation['valid'] else 'COMPLETED WITH ISSUES'}")
        report.append("")
        
        if validation['errors']:
            report.append("ERRORS:")
            for error in validation['errors']:
                report.append(f"  ❌ {error}")
            report.append("")
        
        if validation['warnings']:
            report.append("WARNINGS:")
            for warning in validation['warnings']:
                report.append(f"  ⚠️  {warning}")
            report.append("")
        
        report.append("MAPPING SUMMARY:")
        for component, mappings in validation['mapping_report'].items():
            if isinstance(mappings, dict):
                report.append(f"  {component}:")
                for setting, status in mappings.items():
                    report.append(f"    {setting}: {status}")
            else:
                report.append(f"  {component}: {mappings}")
        
        report.append("")
        report.append("=== End Migration Report ===")
        
        return "\n".join(report)


def migrate_legacy_configuration(output_file: Optional[Path] = None,
                                config_dir: Optional[Path] = None) -> NewServerConfig:
    """Convenience function to migrate legacy configuration."""
    migrator = ConfigurationMigrator(config_dir)
    return migrator.migrate_from_legacy(output_file)


def create_migration_backup(source_file: Path, config_dir: Optional[Path] = None) -> Path:
    """Convenience function to create configuration backup."""
    migrator = ConfigurationMigrator(config_dir)
    return migrator.create_backup(source_file) 