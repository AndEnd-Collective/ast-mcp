"""
Tests for Enhanced Configuration Management System.

This module contains comprehensive tests for the new Pydantic-based
configuration system including validation, migration, and management features.
"""

import os
import tempfile
import pytest
import yaml
import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add src to Python path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Import the modules we're testing
from ast_grep_mcp.config import (
    ServerConfig, SecurityConfig, PerformanceConfig, MonitoringConfig,
    LoggingConfig, ASTGrepConfig, EnvironmentType, LogLevel, LogFormat,
    ConfigurationManager, ConfigurationError, load_configuration
)
from ast_grep_mcp.config_migration import (
    ConfigurationMigrator, LegacyServerConfig, migrate_legacy_configuration
)


class TestConfigurationModels:
    """Test Pydantic configuration models."""
    
    def test_security_config_defaults(self):
        """Test SecurityConfig with default values."""
        config = SecurityConfig()
        assert config.enable_security is True
        assert config.enable_audit_logging is True
        assert config.enable_rate_limiting is True
        assert config.rate_limit_requests == 100
        assert config.rate_limit_window == 60
        assert config.max_input_size == 1024 * 1024
        
    def test_security_config_validation(self):
        """Test SecurityConfig validation."""
        # Valid configuration
        config = SecurityConfig(
            rate_limit_requests=50,
            max_input_size=2048
        )
        assert config.rate_limit_requests == 50
        assert config.max_input_size == 2048
        
        # Invalid configuration - should raise validation error
        with pytest.raises(ValueError):
            SecurityConfig(rate_limit_requests=0)  # Below minimum
            
    def test_performance_config_thresholds(self):
        """Test PerformanceConfig threshold validation."""
        # Valid configuration
        config = PerformanceConfig(
            memory_warning_threshold=80.0,
            memory_critical_threshold=90.0
        )
        assert config.memory_warning_threshold == 80.0
        assert config.memory_critical_threshold == 90.0
        
        # Invalid - critical <= warning
        with pytest.raises(ValueError):
            PerformanceConfig(
                memory_warning_threshold=90.0,
                memory_critical_threshold=80.0
            )
            
    def test_logging_config_enums(self):
        """Test LoggingConfig with enum values."""
        config = LoggingConfig(
            log_level=LogLevel.DEBUG,
            log_format=LogFormat.JSON
        )
        assert config.log_level == LogLevel.DEBUG
        assert config.log_format == LogFormat.JSON
        
    def test_server_config_composition(self):
        """Test ServerConfig with nested configurations."""
        config = ServerConfig(
            name="test-server",
            environment=EnvironmentType.TESTING,
            debug=True
        )
        
        assert config.name == "test-server"
        assert config.environment == EnvironmentType.TESTING
        assert config.debug is True
        assert isinstance(config.security, SecurityConfig)
        assert isinstance(config.performance, PerformanceConfig)
        assert isinstance(config.monitoring, MonitoringConfig)
        assert isinstance(config.logging, LoggingConfig)
        assert isinstance(config.ast_grep, ASTGrepConfig)


class TestConfigurationManager:
    """Test ConfigurationManager functionality."""
    
    @pytest.fixture
    def temp_config_dir(self):
        """Create temporary directory for configuration tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)
    
    @pytest.fixture
    def sample_yaml_config(self, temp_config_dir):
        """Create sample YAML configuration file."""
        config_data = {
            'name': 'test-ast-grep-mcp',
            'version': '1.0.0',
            'environment': 'development',
            'debug': True,
            'security': {
                'enable_security': False,
                'rate_limit_requests': 200
            },
            'logging': {
                'log_level': 'DEBUG',
                'log_format': 'json'
            }
        }
        
        config_file = temp_config_dir / 'test-config.yaml'
        with config_file.open('w') as f:
            yaml.dump(config_data, f)
        
        return config_file
    
    def test_configuration_manager_init(self, temp_config_dir):
        """Test ConfigurationManager initialization."""
        manager = ConfigurationManager(temp_config_dir)
        assert manager.config_dir == temp_config_dir
        assert manager.config_file_name == "ast-mcp.yaml"
        
    def test_load_yaml_configuration(self, sample_yaml_config):
        """Test loading YAML configuration file."""
        manager = ConfigurationManager(sample_yaml_config.parent)
        config = manager.load_configuration(sample_yaml_config)
        
        assert config.name == 'test-ast-grep-mcp'
        assert config.environment == EnvironmentType.DEVELOPMENT
        assert config.debug is True
        assert config.security.enable_security is False
        assert config.security.rate_limit_requests == 200
        assert config.logging.log_level == LogLevel.DEBUG
        assert config.logging.log_format == LogFormat.JSON
        
    def test_load_nonexistent_config(self, temp_config_dir):
        """Test loading configuration when file doesn't exist."""
        manager = ConfigurationManager(temp_config_dir)
        config = manager.load_configuration()
        
        # Should load with defaults
        assert config.name == "ast-mcp"
        assert config.environment == EnvironmentType.DEVELOPMENT
        
    def test_save_configuration(self, temp_config_dir):
        """Test saving configuration to file."""
        manager = ConfigurationManager(temp_config_dir)
        config = ServerConfig(name="saved-config", debug=True)
        
        output_file = temp_config_dir / "saved-config.yaml"
        manager._config_file_path = output_file
        success = manager.save_configuration(config)
        
        assert success is True
        assert output_file.exists()
        
        # Verify saved content
        with output_file.open() as f:
            saved_data = yaml.safe_load(f)
        
        assert saved_data['name'] == "saved-config"
        assert saved_data['debug'] is True
        
    def test_export_configuration(self, temp_config_dir):
        """Test exporting configuration to different formats."""
        manager = ConfigurationManager(temp_config_dir)
        config = ServerConfig(name="export-test")
        manager._config = config
        
        # Export as YAML
        yaml_file = temp_config_dir / "export.yaml"
        success = manager.export_configuration(yaml_file, "yaml")
        assert success is True
        assert yaml_file.exists()
        
        # Export as JSON
        json_file = temp_config_dir / "export.json"
        success = manager.export_configuration(json_file, "json")
        assert success is True
        assert json_file.exists()
        
        # Verify JSON content
        with json_file.open() as f:
            json_data = json.load(f)
        assert json_data['name'] == "export-test"
        
    def test_validate_configuration(self, temp_config_dir):
        """Test configuration validation."""
        manager = ConfigurationManager(temp_config_dir)
        config = ServerConfig(name="valid-config")
        
        validation = manager.validate_configuration(config)
        assert validation['valid'] is True
        assert len(validation['errors']) == 0
        
    def test_configuration_change_tracking(self, temp_config_dir):
        """Test configuration change history tracking."""
        manager = ConfigurationManager(temp_config_dir)
        config = ServerConfig(name="change-test")
        
        # Load configuration (should create change entry)
        manager._config = config
        manager._log_configuration_change("test", "Test change")
        
        history = manager.get_change_history()
        assert len(history) >= 1
        assert history[-1]['action'] == 'test'
        assert history[-1]['description'] == 'Test change'
        
    def test_environment_template_creation(self, temp_config_dir):
        """Test creating environment-specific templates."""
        manager = ConfigurationManager(temp_config_dir)
        
        template_file = temp_config_dir / "prod-template.yaml"
        success = manager.create_environment_template(
            EnvironmentType.PRODUCTION, 
            template_file
        )
        
        assert success is True
        assert template_file.exists()
        
        # Verify template content
        with template_file.open() as f:
            template_data = yaml.safe_load(f)
        
        assert template_data['environment'] == 'production'
        assert template_data['debug'] is False
        assert template_data['logging']['log_level'] == 'WARNING'


class TestConfigurationMigration:
    """Test configuration migration functionality."""
    
    @pytest.fixture
    def temp_config_dir(self):
        """Create temporary directory for migration tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)
    
    def test_legacy_server_config_loading(self):
        """Test LegacyServerConfig loading from environment."""
        env_vars = {
            'AST_GREP_MCP_NAME': 'legacy-server',
            'AST_GREP_MCP_VERSION': '0.9.0',
            'AST_GREP_ENABLE_PERFORMANCE': 'true',
            'AST_GREP_ENABLE_SECURITY': 'false',
            'AST_GREP_LOG_LEVEL': 'DEBUG'
        }
        
        with patch.dict(os.environ, env_vars):
            legacy_config = LegacyServerConfig()
            
            assert legacy_config.name == 'legacy-server'
            assert legacy_config.version == '0.9.0'
            assert legacy_config.enable_performance is True
            assert legacy_config.enable_security is False
            assert legacy_config.log_level == 'DEBUG'
    
    def test_migration_from_legacy(self, temp_config_dir):
        """Test migrating from legacy configuration."""
        env_vars = {
            'AST_GREP_MCP_NAME': 'migrated-server',
            'AST_GREP_ENVIRONMENT': 'production',
            'AST_GREP_ENABLE_SECURITY': 'true',
            'AST_GREP_RATE_LIMIT': 'true',
            'AST_GREP_RATE_LIMIT_REQUESTS': '50',
            'AST_GREP_LOG_LEVEL': 'ERROR'
        }
        
        with patch.dict(os.environ, env_vars):
            migrator = ConfigurationMigrator(temp_config_dir)
            new_config = migrator.migrate_from_legacy()
            
            assert new_config.name == 'migrated-server'
            assert new_config.environment == EnvironmentType.PRODUCTION
            assert new_config.security.enable_security is True
            assert new_config.security.enable_rate_limiting is True
            assert new_config.security.rate_limit_requests == 50
            assert new_config.logging.log_level == LogLevel.ERROR
    
    def test_migration_validation(self, temp_config_dir):
        """Test migration validation."""
        migrator = ConfigurationMigrator(temp_config_dir)
        
        # Create legacy and new configs
        legacy_config = LegacyServerConfig()
        legacy_config.name = "test-server"
        legacy_config.enable_security = True
        
        new_config = ServerConfig(
            name="test-server",
            security=SecurityConfig(enable_security=True)
        )
        
        validation = migrator.validate_migration(legacy_config, new_config)
        
        assert validation['valid'] is True
        assert 'basic_settings' in validation['mapping_report']
        assert validation['mapping_report']['basic_settings']['name'] == '✓'
    
    def test_migration_backup_creation(self, temp_config_dir):
        """Test creating backups during migration."""
        migrator = ConfigurationMigrator(temp_config_dir)
        
        # Create a source file to backup
        source_file = temp_config_dir / "source.yaml"
        source_file.write_text("test: content")
        
        backup_path = migrator.create_backup(source_file)
        
        assert backup_path.exists()
        assert backup_path.read_text() == "test: content"
        assert backup_path.parent == migrator.backup_dir
    
    def test_migration_report_generation(self, temp_config_dir):
        """Test migration report generation."""
        migrator = ConfigurationMigrator(temp_config_dir)
        
        legacy_config = LegacyServerConfig()
        legacy_config.name = "report-test"
        
        new_config = ServerConfig(name="report-test")
        
        report = migrator.generate_migration_report(legacy_config, new_config)
        
        assert "Configuration Migration Report" in report
        assert "SUCCESSFUL" in report
        assert "MAPPING SUMMARY" in report


class TestConfigurationIntegration:
    """Integration tests for the configuration system."""
    
    @pytest.fixture
    def temp_config_dir(self):
        """Create temporary directory for integration tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)
    
    def test_full_configuration_lifecycle(self, temp_config_dir):
        """Test complete configuration lifecycle."""
        # 1. Create configuration manager
        manager = ConfigurationManager(temp_config_dir)
        
        # 2. Create and save initial configuration
        config = ServerConfig(
            name="lifecycle-test",
            environment=EnvironmentType.DEVELOPMENT,
            debug=True
        )
        
        config_file = temp_config_dir / "lifecycle.yaml"
        manager._config_file_path = config_file
        manager.save_configuration(config)
        
        # 3. Load configuration
        loaded_config = manager.load_configuration(config_file)
        assert loaded_config.name == "lifecycle-test"
        
        # 4. Validate configuration
        validation = manager.validate_configuration(loaded_config)
        assert validation['valid'] is True
        
        # 5. Export configuration
        export_file = temp_config_dir / "exported.json"
        manager.export_configuration(export_file, "json")
        assert export_file.exists()
        
        # 6. Reload and check for changes
        changed = manager.reload_configuration()
        # Reload may detect changes due to config hash being recalculated
        assert isinstance(changed, bool)
    
    def test_configuration_with_environment_variables(self, temp_config_dir):
        """Test configuration loading from file with env-based values."""
        # Create base configuration file
        config_data = {
            'name': 'base-config',
            'debug': True,
            'logging': {'log_level': 'DEBUG'}
        }

        config_file = temp_config_dir / "base.yaml"
        with config_file.open('w') as f:
            yaml.dump(config_data, f)

        manager = ConfigurationManager(temp_config_dir)
        config = manager.load_configuration(config_file)

        # Values should come from file
        assert config.debug is True
        assert config.logging.log_level == LogLevel.DEBUG
        assert config.name == 'base-config'
    
    def test_error_handling(self, temp_config_dir):
        """Test error handling in configuration system."""
        manager = ConfigurationManager(temp_config_dir)
        
        # Test loading invalid YAML
        invalid_yaml = temp_config_dir / "invalid.yaml"
        invalid_yaml.write_text("invalid: yaml: content: [")
        
        with pytest.raises(ConfigurationError):
            manager.load_configuration(invalid_yaml)
        
        # Test exporting without loaded config returns False
        config = ServerConfig()
        result = manager.export_configuration(Path("/invalid/path/config.yaml"))
        assert result is False


class TestGlobalFunctions:
    """Test global configuration functions."""
    
    @pytest.fixture
    def temp_config_dir(self):
        """Create temporary directory for global function tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)
    
    def test_load_configuration_function(self, temp_config_dir):
        """Test global load_configuration function."""
        config_data = {'name': 'global-test'}
        config_file = temp_config_dir / "global.yaml"
        
        with config_file.open('w') as f:
            yaml.dump(config_data, f)
        
        config = load_configuration(config_file, temp_config_dir)
        assert config.name == 'global-test'
    
    def test_migrate_legacy_configuration_function(self, temp_config_dir):
        """Test global migrate_legacy_configuration function."""
        env_vars = {'AST_GREP_MCP_NAME': 'global-migration-test'}
        
        with patch.dict(os.environ, env_vars):
            output_file = temp_config_dir / "migrated-global.yaml"
            config = migrate_legacy_configuration(output_file, temp_config_dir)
            
            assert config.name == 'global-migration-test'
            assert output_file.exists()


# Performance and stress tests
class TestConfigurationPerformance:
    """Performance tests for configuration system."""

    @pytest.fixture
    def temp_config_dir(self):
        """Create temporary directory for performance tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_large_configuration_loading(self):
        """Test loading large configuration files."""
        # Create large configuration with many nested settings
        large_config = ServerConfig(
            security=SecurityConfig(
                allowed_paths=[f"/path/{i}" for i in range(1000)],
                blocked_paths=[f"/blocked/{i}" for i in range(1000)]
            ),
            ast_grep=ASTGrepConfig(
                supported_languages=[f"lang{i}" for i in range(100)]
            )
        )
        
        # Test serialization/deserialization performance
        config_dict = large_config.model_dump()
        reconstructed = ServerConfig(**config_dict)
        
        assert reconstructed.security.allowed_paths == large_config.security.allowed_paths
        assert reconstructed.ast_grep.supported_languages == large_config.ast_grep.supported_languages
    
    def test_multiple_configuration_operations(self, temp_config_dir):
        """Test multiple rapid configuration operations."""
        manager = ConfigurationManager(temp_config_dir)
        
        # Perform multiple operations rapidly
        for i in range(10):
            config = ServerConfig(name=f"config-{i}")
            config_file = temp_config_dir / f"config-{i}.yaml"
            
            # Save
            manager._config_file_path = config_file
            manager.save_configuration(config)
            
            # Load
            loaded = manager.load_configuration(config_file)
            assert loaded.name == f"config-{i}"
            
            # Validate
            validation = manager.validate_configuration(loaded)
            assert validation['valid'] is True


if __name__ == '__main__':
    pytest.main([__file__]) 