# AST-Grep MCP Server Configuration Guide

This guide covers the enhanced Pydantic-based configuration system that provides comprehensive validation, multi-environment support, and advanced features.

## Table of Contents
- [Configuration Overview](#configuration-overview)
- [Configuration Sources](#configuration-sources)
- [Configuration Sections](#configuration-sections)
- [Environment Variables](#environment-variables)
- [Configuration Files](#configuration-files)
- [Migration Guide](#migration-guide)
- [Advanced Features](#advanced-features)
- [Validation and Troubleshooting](#validation-and-troubleshooting)

## Configuration Overview

The AST-Grep MCP Server uses a sophisticated configuration system built with Pydantic that provides:

- **Type Safety**: All configuration values are validated with proper types
- **Multi-Environment Support**: Development, staging, and production profiles
- **Multiple Sources**: Environment variables, YAML/JSON files, command-line arguments
- **Validation**: Comprehensive validation with clear error messages
- **Migration Support**: Automatic migration from legacy environment-based configuration
- **Encryption**: Optional encryption for sensitive configuration values
- **Hot Reload**: Configuration changes can be detected and applied without restart

### Configuration Precedence (highest to lowest)
1. **Command-line arguments**
2. **Environment variables**
3. **Configuration files** (YAML/JSON/TOML)
4. **Default values**

## Configuration Sources

### Using Configuration Files (Recommended)
```bash
# Create configuration from template
python scripts/config_manager.py create-template production config.yaml

# Start server with configuration file
ast-grep-mcp --config config.yaml

# Or specify environment
ast-grep-mcp --config config.yaml --environment production
```

### Using Environment Variables
```bash
# Set environment variables
export AST_GREP_MCP_ENVIRONMENT=production
export AST_GREP_SECURITY__ENABLE_SECURITY=true

# Start server (will auto-detect environment variables)
ast-grep-mcp
```

### Using Command-Line Arguments
```bash
# Override specific values
ast-grep-mcp --config config.yaml --debug true --security.rate_limit_requests 200
```

## Configuration Sections

The configuration is organized into logical sections:

### 1. Server Configuration
Basic server settings and operational parameters.

```yaml
# Basic server identification
name: "ast-grep-mcp"
version: "1.0.0"
environment: "production"  # development, staging, production
debug: false

# Server lifecycle
shutdown_timeout: 30.0
force_shutdown_timeout: 10.0
```

**Environment Variables:**
```bash
export AST_GREP_MCP_NAME="ast-grep-mcp"
export AST_GREP_MCP_VERSION="1.0.0"
export AST_GREP_MCP_ENVIRONMENT="production"
export AST_GREP_MCP_DEBUG="false"
export AST_GREP_MCP_SHUTDOWN_TIMEOUT="30.0"
export AST_GREP_MCP_FORCE_SHUTDOWN_TIMEOUT="10.0"
```

### 2. Security Configuration
Security features including rate limiting, input validation, and path protection.

```yaml
security:
  # Main security toggle
  enable_security: true
  enable_audit_logging: true
  
  # Rate limiting
  enable_rate_limiting: true
  rate_limit_requests: 100
  rate_limit_window: 60
  
  # Input validation
  enable_input_validation: true
  max_input_size: 1048576      # 1MB
  max_output_size: 10485760    # 10MB
  
  # Path protection
  enable_path_traversal_protection: true
  allowed_paths: []
  blocked_paths: []
  
  # Command injection protection
  enable_command_injection_protection: true
```

**Environment Variables:**
```bash
export AST_GREP_SECURITY__ENABLE_SECURITY="true"
export AST_GREP_SECURITY__ENABLE_AUDIT_LOGGING="true"
export AST_GREP_SECURITY__ENABLE_RATE_LIMITING="true"
export AST_GREP_SECURITY__RATE_LIMIT_REQUESTS="100"
export AST_GREP_SECURITY__RATE_LIMIT_WINDOW="60"
export AST_GREP_SECURITY__ENABLE_INPUT_VALIDATION="true"
export AST_GREP_SECURITY__MAX_INPUT_SIZE="1048576"
export AST_GREP_SECURITY__MAX_OUTPUT_SIZE="10485760"
export AST_GREP_SECURITY__ENABLE_PATH_TRAVERSAL_PROTECTION="true"
export AST_GREP_SECURITY__ALLOWED_PATHS="[]"
export AST_GREP_SECURITY__BLOCKED_PATHS="[]"
export AST_GREP_SECURITY__ENABLE_COMMAND_INJECTION_PROTECTION="true"
```

### 3. Performance Configuration
Performance optimization settings including caching, concurrency, and resource management.

```yaml
performance:
  # Performance monitoring
  enable_performance: true
  enable_caching: true
  
  # Cache settings
  cache_ttl: 600                # 10 minutes
  cache_max_size: 1000
  cache_strategy: "lru"
  
  # Concurrency
  max_concurrent_requests: 20
  max_execution_time: 60.0
  
  # Resource thresholds
  memory_warning_threshold: 80.0
  memory_critical_threshold: 95.0
  cpu_warning_threshold: 85.0
  disk_warning_threshold: 90.0
```

**Environment Variables:**
```bash
export AST_GREP_PERFORMANCE__ENABLE_PERFORMANCE="true"
export AST_GREP_PERFORMANCE__ENABLE_CACHING="true"
export AST_GREP_PERFORMANCE__CACHE_TTL="600"
export AST_GREP_PERFORMANCE__CACHE_MAX_SIZE="1000"
export AST_GREP_PERFORMANCE__CACHE_STRATEGY="lru"
export AST_GREP_PERFORMANCE__MAX_CONCURRENT_REQUESTS="20"
export AST_GREP_PERFORMANCE__MAX_EXECUTION_TIME="60.0"
export AST_GREP_PERFORMANCE__MEMORY_WARNING_THRESHOLD="80.0"
export AST_GREP_PERFORMANCE__MEMORY_CRITICAL_THRESHOLD="95.0"
export AST_GREP_PERFORMANCE__CPU_WARNING_THRESHOLD="85.0"
export AST_GREP_PERFORMANCE__DISK_WARNING_THRESHOLD="90.0"
```

### 4. Monitoring Configuration
Health monitoring, alerting, and metrics collection settings.

```yaml
monitoring:
  # Health monitoring
  enable_monitoring: true
  enable_alerting: true
  health_check_interval: 30
  
  # Metrics collection
  enable_metrics: true
  metrics_collection_interval: 60
  
  # Alerting thresholds
  response_time_threshold: 5.0
  error_rate_threshold: 0.05
  
  # System monitoring
  system_monitoring_enabled: true
  resource_monitoring_enabled: true
```

**Environment Variables:**
```bash
export AST_GREP_MONITORING__ENABLE_MONITORING="true"
export AST_GREP_MONITORING__ENABLE_ALERTING="true"
export AST_GREP_MONITORING__HEALTH_CHECK_INTERVAL="30"
export AST_GREP_MONITORING__ENABLE_METRICS="true"
export AST_GREP_MONITORING__METRICS_COLLECTION_INTERVAL="60"
export AST_GREP_MONITORING__RESPONSE_TIME_THRESHOLD="5.0"
export AST_GREP_MONITORING__ERROR_RATE_THRESHOLD="0.05"
export AST_GREP_MONITORING__SYSTEM_MONITORING_ENABLED="true"
export AST_GREP_MONITORING__RESOURCE_MONITORING_ENABLED="true"
```

### 5. Logging Configuration
Comprehensive logging configuration with multiple output formats and destinations.

```yaml
logging:
  # Basic logging
  log_level: "INFO"              # DEBUG, INFO, WARNING, ERROR, CRITICAL
  log_format: "json"             # json, text, structured
  
  # File logging
  enable_file_logging: true
  log_file_path: "/var/log/ast-grep-mcp.log"
  log_file_max_size: 10485760    # 10MB
  log_file_backup_count: 5
  
  # Rotation
  enable_log_rotation: true
  
  # Specialized logging
  enable_performance_logging: true
  enable_security_logging: true
  enable_audit_logging: true
  
  # Filtering
  enable_sensitive_data_filtering: true
```

**Environment Variables:**
```bash
export AST_GREP_LOGGING__LOG_LEVEL="INFO"
export AST_GREP_LOGGING__LOG_FORMAT="json"
export AST_GREP_LOGGING__ENABLE_FILE_LOGGING="true"
export AST_GREP_LOGGING__LOG_FILE_PATH="/var/log/ast-grep-mcp.log"
export AST_GREP_LOGGING__LOG_FILE_MAX_SIZE="10485760"
export AST_GREP_LOGGING__LOG_FILE_BACKUP_COUNT="5"
export AST_GREP_LOGGING__ENABLE_LOG_ROTATION="true"
export AST_GREP_LOGGING__ENABLE_PERFORMANCE_LOGGING="true"
export AST_GREP_LOGGING__ENABLE_SECURITY_LOGGING="true"
export AST_GREP_LOGGING__ENABLE_AUDIT_LOGGING="true"
export AST_GREP_LOGGING__ENABLE_SENSITIVE_DATA_FILTERING="true"
```

### 6. AST-Grep Configuration
AST-Grep specific settings for the underlying tool.

```yaml
ast_grep:
  # Binary configuration
  ast_grep_path: "/usr/local/bin/ast-grep"
  verify_installation: true
  
  # Execution settings
  default_timeout: 30
  max_timeout: 60
  
  # Result settings
  max_results: 1000
  max_match_length: 1000
  
  # Language settings
  supported_languages: []  # Empty = all supported
  
  # Rule configuration
  enable_custom_rules: true
  custom_rules_path: ""
  
  # Output settings
  default_output_format: "json"
```

**Environment Variables:**
```bash
export AST_GREP_AST_GREP__AST_GREP_PATH="/usr/local/bin/ast-grep"
export AST_GREP_AST_GREP__VERIFY_INSTALLATION="true"
export AST_GREP_AST_GREP__DEFAULT_TIMEOUT="30"
export AST_GREP_AST_GREP__MAX_TIMEOUT="60"
export AST_GREP_AST_GREP__MAX_RESULTS="1000"
export AST_GREP_AST_GREP__MAX_MATCH_LENGTH="1000"
export AST_GREP_AST_GREP__SUPPORTED_LANGUAGES="[]"
export AST_GREP_AST_GREP__ENABLE_CUSTOM_RULES="true"
export AST_GREP_AST_GREP__CUSTOM_RULES_PATH=""
export AST_GREP_AST_GREP__DEFAULT_OUTPUT_FORMAT="json"
```

## Configuration Files

### YAML Configuration (Recommended)
```yaml
# config.yaml
name: "ast-grep-mcp"
environment: "production"
debug: false

security:
  enable_security: true
  rate_limit_requests: 100

performance:
  enable_caching: true
  cache_ttl: 600

logging:
  log_level: "INFO"
  log_format: "json"
  enable_file_logging: true
  log_file_path: "/var/log/ast-grep-mcp.log"

ast_grep:
  ast_grep_path: "/usr/local/bin/ast-grep"
  default_timeout: 30
```

### JSON Configuration
```json
{
  "name": "ast-grep-mcp",
  "environment": "production",
  "debug": false,
  "security": {
    "enable_security": true,
    "rate_limit_requests": 100
  },
  "performance": {
    "enable_caching": true,
    "cache_ttl": 600
  },
  "logging": {
    "log_level": "INFO",
    "log_format": "json",
    "enable_file_logging": true,
    "log_file_path": "/var/log/ast-grep-mcp.log"
  },
  "ast_grep": {
    "ast_grep_path": "/usr/local/bin/ast-grep",
    "default_timeout": 30
  }
}
```

### TOML Configuration
```toml
name = "ast-grep-mcp"
environment = "production"
debug = false

[security]
enable_security = true
rate_limit_requests = 100

[performance]
enable_caching = true
cache_ttl = 600

[logging]
log_level = "INFO"
log_format = "json"
enable_file_logging = true
log_file_path = "/var/log/ast-grep-mcp.log"

[ast_grep]
ast_grep_path = "/usr/local/bin/ast-grep"
default_timeout = 30
```

## Environment Variables

### Nested Configuration with Double Underscore
The configuration system supports nested configuration through double underscores:

```bash
# Basic format: AST_GREP_<SECTION>__<KEY>
export AST_GREP_SECURITY__ENABLE_SECURITY="true"
export AST_GREP_PERFORMANCE__CACHE_TTL="600"
export AST_GREP_LOGGING__LOG_LEVEL="INFO"

# For deeply nested configuration
export AST_GREP_SECURITY__RATE_LIMITING__REQUESTS="100"
export AST_GREP_SECURITY__RATE_LIMITING__WINDOW="60"
```

### Data Type Conversion
Environment variables are automatically converted to appropriate types:

```bash
# Boolean values
export AST_GREP_MCP_DEBUG="true"          # -> bool
export AST_GREP_MCP_DEBUG="false"         # -> bool

# Numeric values
export AST_GREP_SECURITY__RATE_LIMIT_REQUESTS="100"  # -> int
export AST_GREP_PERFORMANCE__CACHE_TTL="600.5"       # -> float

# Lists (JSON format)
export AST_GREP_SECURITY__ALLOWED_PATHS='["/workspace", "/projects"]'

# Dictionaries (JSON format)
export AST_GREP_CUSTOM_SETTINGS='{"key": "value", "nested": {"key": "value"}}'
```

## Migration Guide

### Migrating from Legacy Configuration
If you're upgrading from a version that used the old environment-based configuration:

```bash
# 1. Create migration
python scripts/config_manager.py migrate --output new-config.yaml

# 2. Validate the migration
python scripts/config_manager.py validate --config new-config.yaml

# 3. Compare with current configuration
python scripts/config_manager.py show --config new-config.yaml

# 4. Test the new configuration
ast-grep-mcp --config new-config.yaml --dry-run

# 5. Switch to new configuration
ast-grep-mcp --config new-config.yaml
```

### Manual Migration
If you need to manually migrate configuration:

**Old Environment Variables:**
```bash
export LOG_LEVEL="INFO"
export MAX_FILE_SIZE="1048576"
export EXECUTION_TIMEOUT="30"
```

**New Environment Variables:**
```bash
export AST_GREP_LOGGING__LOG_LEVEL="INFO"
export AST_GREP_SECURITY__MAX_INPUT_SIZE="1048576"
export AST_GREP_AST_GREP__DEFAULT_TIMEOUT="30"
```

## Advanced Features

### Configuration Encryption
Sensitive configuration values can be encrypted:

```bash
# Encrypt a configuration file
python scripts/config_manager.py encrypt --config config.yaml --output encrypted-config.yaml

# Decrypt configuration (automatically handled by server)
python scripts/config_manager.py decrypt --config encrypted-config.yaml --output decrypted-config.yaml
```

### Configuration Validation
The configuration system provides comprehensive validation:

```bash
# Validate configuration file
python scripts/config_manager.py validate --config config.yaml

# Validate with detailed output
python scripts/config_manager.py validate --config config.yaml --verbose

# Validate environment variables
python scripts/config_manager.py validate-env
```

### Configuration Templates
Generate configuration templates for different environments:

```bash
# Development template
python scripts/config_manager.py create-template development dev-config.yaml

# Production template
python scripts/config_manager.py create-template production prod-config.yaml

# Custom template with specific features
python scripts/config_manager.py create-template custom custom-config.yaml \
  --enable-security true \
  --enable-caching true \
  --log-level INFO
```

### Configuration Profiles
Create reusable configuration profiles:

```yaml
# profiles.yaml
profiles:
  high-security:
    security:
      enable_security: true
      rate_limit_requests: 50
      max_input_size: 262144  # 256KB
    
  high-performance:
    performance:
      enable_caching: true
      cache_ttl: 3600
      max_concurrent_requests: 50
    
  debug:
    debug: true
    logging:
      log_level: "DEBUG"
      enable_performance_logging: true
```

```bash
# Use profile
ast-grep-mcp --config config.yaml --profile high-security
```

### Hot Reload Configuration
Monitor configuration changes and reload without restart:

```yaml
# Enable hot reload
monitoring:
  enable_config_monitoring: true
  config_check_interval: 30
```

```bash
# Reload configuration via signal
kill -SIGHUP $(pgrep ast-grep-mcp)

# Or via API
curl -X POST http://localhost:8000/admin/reload-config
```

## Validation and Troubleshooting

### Configuration Validation
The system provides detailed validation with helpful error messages:

```bash
# Validate configuration
python scripts/config_manager.py validate --config config.yaml
```

**Example validation output:**
```
✅ Configuration validation successful!

📊 Configuration Summary:
- Environment: production
- Security: enabled
- Performance: caching enabled
- Logging: INFO level, file logging enabled
- AST-Grep: /usr/local/bin/ast-grep (verified)

🔍 Validation Details:
- All required fields present
- All values within valid ranges
- AST-Grep binary accessible
- Log file path writable
- Cache directory accessible
```

### Common Validation Errors

#### 1. Invalid Environment Variable Format
```bash
# ❌ Wrong
export AST_GREP_SECURITY_RATE_LIMIT="100"

# ✅ Correct
export AST_GREP_SECURITY__RATE_LIMIT_REQUESTS="100"
```

#### 2. Invalid Data Types
```bash
# ❌ Wrong
export AST_GREP_MCP_DEBUG="yes"

# ✅ Correct
export AST_GREP_MCP_DEBUG="true"
```

#### 3. Invalid Enum Values
```bash
# ❌ Wrong
export AST_GREP_LOGGING__LOG_LEVEL="VERBOSE"

# ✅ Correct
export AST_GREP_LOGGING__LOG_LEVEL="DEBUG"
```

#### 4. Missing Required Fields
```yaml
# ❌ Missing ast_grep_path
ast_grep:
  default_timeout: 30

# ✅ Complete
ast_grep:
  ast_grep_path: "/usr/local/bin/ast-grep"
  default_timeout: 30
```

### Debugging Configuration Issues

#### 1. View Effective Configuration
```bash
# Show current configuration
python scripts/config_manager.py show

# Show configuration with sources
python scripts/config_manager.py show --show-sources

# Export configuration
python scripts/config_manager.py export --format yaml --output current-config.yaml
```

#### 2. Test Configuration
```bash
# Dry run with configuration
ast-grep-mcp --config config.yaml --dry-run

# Health check with configuration
python scripts/config_manager.py health --config config.yaml
```

#### 3. Environment Variable Debugging
```bash
# List all AST-Grep environment variables
env | grep AST_GREP

# Show environment variable parsing
python scripts/config_manager.py debug-env
```

### Performance Considerations

#### 1. Configuration File Size
- Keep configuration files under 1MB
- Use references for large repeated sections
- Consider splitting large configurations

#### 2. Environment Variable Count
- Limit to essential environment variables
- Use configuration files for complex settings
- Group related settings in configuration files

#### 3. Validation Performance
- Configuration validation is cached
- Hot reload only validates changed sections
- Complex validations are optimized

---

## Configuration Management CLI

The configuration management CLI provides comprehensive tools:

```bash
# Create templates
python scripts/config_manager.py create-template <environment> <output>

# Validate configuration
python scripts/config_manager.py validate --config <file>

# Show current configuration
python scripts/config_manager.py show [--config <file>]

# Export configuration
python scripts/config_manager.py export --format <yaml|json|toml> --output <file>

# Migrate configuration
python scripts/config_manager.py migrate --output <file>

# Health check
python scripts/config_manager.py health [--config <file>]

# Encrypt/decrypt configuration
python scripts/config_manager.py encrypt --config <input> --output <output>
python scripts/config_manager.py decrypt --config <input> --output <output>
```

---

*For more information, see the [Deployment Guide](DEPLOYMENT.md) and [API Documentation](API.md).* 