# AST-Grep MCP Server Deployment Guide

This guide covers deploying the AST-Grep MCP Server in various environments, from development to production.

## Table of Contents
- [Prerequisites](#prerequisites)
- [Installation Methods](#installation-methods)
- [Configuration](#configuration)
- [Deployment Environments](#deployment-environments)
- [Health Monitoring](#health-monitoring)
- [Security Considerations](#security-considerations)
- [Troubleshooting](#troubleshooting)

## Prerequisites

### System Requirements
- **Python 3.8+** with pip
- **Memory**: Minimum 512MB, recommended 2GB+ for large codebases
- **Storage**: 100MB for application + space for logs and cache
- **CPU**: Single core minimum, multi-core recommended for concurrent operations

### Dependencies
1. **ast-grep binary** (required):
   ```bash
   # Via Cargo (Rust)
   cargo install ast-grep
   
   # Via npm
   npm install -g @ast-grep/cli
   
   # Via Homebrew (macOS)
   brew install ast-grep
   
   # Via package manager (Linux)
   apt-get install ast-grep  # or equivalent
   ```

2. **Python dependencies** (installed automatically):
   - pydantic >= 2.0
   - typing-extensions
   - pyyaml
   - cryptography (optional, for configuration encryption)

## Installation Methods

### Method 1: From Source (Recommended for Development)
```bash
# Clone repository
git clone https://github.com/your-org/ast-grep-mcp.git
cd ast-grep-mcp

# Install in development mode
pip install -e .

# Or with development dependencies
pip install -e .[dev]
```

### Method 2: From PyPI (Production)
```bash
# Install from PyPI (when published)
pip install ast-grep-mcp

# Or with specific version
pip install ast-grep-mcp==1.0.0
```

### Method 3: Docker Deployment
```bash
# Build Docker image
docker build -t ast-grep-mcp:latest .

# Run container
docker run -d \
  --name ast-grep-mcp \
  -p 8000:8000 \
  -v /path/to/your/code:/workspace \
  -e AST_GREP_MCP_ENVIRONMENT=production \
  ast-grep-mcp:latest
```

### Method 4: Using Configuration Management
```bash
# Create configuration first
python scripts/config_manager.py create-template production prod-config.yaml

# Edit configuration
# Configure environment variables or config file
# Deploy with configuration
ast-grep-mcp --config prod-config.yaml
```

## Configuration

### Configuration Methods (in order of precedence)
1. **Command line arguments**
2. **Environment variables**
3. **Configuration files** (YAML/JSON)
4. **Default values**

### Quick Start Configuration
```bash
# Create development configuration
python scripts/config_manager.py create-template development dev-config.yaml

# Validate configuration
python scripts/config_manager.py validate --config dev-config.yaml

# Show current configuration
python scripts/config_manager.py show --config dev-config.yaml
```

### Environment Variables
```bash
# Basic server settings
export AST_GREP_MCP_NAME="my-ast-grep-server"
export AST_GREP_MCP_ENVIRONMENT="production"
export AST_GREP_MCP_DEBUG="false"

# AST-Grep settings
export AST_GREP_PATH="/usr/local/bin/ast-grep"
export AST_GREP_DEFAULT_TIMEOUT="30"

# Security settings
export AST_GREP_SECURITY__ENABLE_SECURITY="true"
export AST_GREP_SECURITY__RATE_LIMIT_REQUESTS="100"
export AST_GREP_SECURITY__MAX_INPUT_SIZE="1048576"

# Performance settings
export AST_GREP_PERFORMANCE__ENABLE_CACHING="true"
export AST_GREP_PERFORMANCE__CACHE_TTL="600"
export AST_GREP_PERFORMANCE__MAX_CONCURRENT_REQUESTS="20"

# Logging settings
export AST_GREP_LOGGING__LOG_LEVEL="WARNING"
export AST_GREP_LOGGING__LOG_FORMAT="json"
export AST_GREP_LOGGING__LOG_FILE_PATH="/var/log/ast-grep-mcp.log"
```

### Configuration File Example
```yaml
# production-config.yaml
name: "ast-grep-mcp-prod"
environment: "production"
debug: false

security:
  enable_security: true
  enable_rate_limiting: true
  rate_limit_requests: 100
  max_input_size: 524288  # 512KB

performance:
  enable_caching: true
  cache_ttl: 600
  max_concurrent_requests: 20
  memory_warning_threshold: 80.0

monitoring:
  enable_monitoring: true
  enable_alerting: true
  health_check_interval: 15

logging:
  log_level: "WARNING"
  log_format: "json"
  enable_file_logging: true
  log_file_path: "/var/log/ast-grep-mcp/server.log"

ast_grep:
  ast_grep_path: "/usr/local/bin/ast-grep"
  default_timeout: 20
  max_timeout: 60
```

## Deployment Environments

### Development Environment
```bash
# Use development template
python scripts/config_manager.py create-template development dev-config.yaml

# Run with development settings
ast-grep-mcp --config dev-config.yaml

# Or with environment variables
export AST_GREP_MCP_ENVIRONMENT=development
export AST_GREP_MCP_DEBUG=true
export AST_GREP_LOGGING__LOG_LEVEL=DEBUG
ast-grep-mcp
```

**Development Features:**
- Debug mode enabled
- Verbose logging (DEBUG level)
- Security features relaxed
- File logging enabled
- Smaller resource limits

### Staging Environment
```bash
# Create staging configuration
cp config/production.yaml staging-config.yaml
# Edit for staging-specific settings

# Deploy to staging
ast-grep-mcp --config staging-config.yaml
```

**Staging Features:**
- Production-like configuration
- Moderate security settings
- Performance monitoring enabled
- Audit logging active

### Production Environment
```bash
# Use production template
python scripts/config_manager.py create-template production prod-config.yaml

# Edit for your specific needs
vim prod-config.yaml

# Validate before deployment
python scripts/config_manager.py validate --config prod-config.yaml

# Deploy
ast-grep-mcp --config prod-config.yaml
```

**Production Features:**
- Maximum security enabled
- Rate limiting active
- Minimal logging (WARNING+ only)
- Performance optimizations
- Health monitoring and alerting
- Resource limits enforced

### Docker Production Deployment
```dockerfile
# Dockerfile
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install ast-grep
RUN curl -L https://github.com/ast-grep/ast-grep/releases/latest/download/ast-grep-x86_64-unknown-linux-gnu.tar.gz \
    | tar -xz -C /usr/local/bin/

# Copy application
COPY . /app
WORKDIR /app

# Install Python dependencies
RUN pip install -e .

# Create non-root user
RUN useradd -r -s /bin/false astgrep
USER astgrep

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

# Run server
CMD ["ast-grep-mcp", "--config", "/app/config/production.yaml"]
```

```yaml
# docker-compose.yml
version: '3.8'

services:
  ast-grep-mcp:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - ./logs:/app/logs
      - ./config:/app/config
    environment:
      - AST_GREP_MCP_ENVIRONMENT=production
      - AST_GREP_LOGGING__LOG_FILE_PATH=/app/logs/server.log
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
```

### Kubernetes Deployment
```yaml
# k8s-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ast-grep-mcp
spec:
  replicas: 3
  selector:
    matchLabels:
      app: ast-grep-mcp
  template:
    metadata:
      labels:
        app: ast-grep-mcp
    spec:
      containers:
      - name: ast-grep-mcp
        image: ast-grep-mcp:latest
        ports:
        - containerPort: 8000
        env:
        - name: AST_GREP_MCP_ENVIRONMENT
          value: "production"
        resources:
          requests:
            memory: "512Mi"
            cpu: "250m"
          limits:
            memory: "2Gi"
            cpu: "1000m"
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: ast-grep-mcp-service
spec:
  selector:
    app: ast-grep-mcp
  ports:
    - protocol: TCP
      port: 80
      targetPort: 8000
  type: ClusterIP
```

## Health Monitoring

### Health Check Endpoints
```bash
# Basic health check
curl http://localhost:8000/health

# Detailed health information
curl http://localhost:8000/health/detailed

# System metrics
curl http://localhost:8000/metrics
```

### Health Check Response
```json
{
  "status": "healthy",
  "timestamp": "2024-01-01T12:00:00Z",
  "version": "1.0.0",
  "checks": {
    "ast_grep_binary": "healthy",
    "configuration": "healthy",
    "memory_usage": "healthy",
    "disk_space": "healthy"
  },
  "metrics": {
    "memory_usage_percent": 45.2,
    "cpu_usage_percent": 12.1,
    "disk_usage_percent": 23.5,
    "uptime_seconds": 3600
  }
}
```

### Monitoring Integration
```bash
# Prometheus metrics endpoint
curl http://localhost:8000/metrics

# Custom monitoring script
#!/bin/bash
HEALTH_URL="http://localhost:8000/health"
if ! curl -f $HEALTH_URL > /dev/null 2>&1; then
  echo "ALERT: AST-Grep MCP Server is unhealthy"
  # Send alert to monitoring system
fi
```

## Security Considerations

### Network Security
- **Firewall**: Only expose necessary ports (typically 8000)
- **TLS/HTTPS**: Use reverse proxy (nginx, Apache) for TLS termination
- **Network isolation**: Deploy in private network/VPC when possible

### Application Security
- **Rate limiting**: Configure appropriate limits for your use case
- **Input validation**: All inputs are validated by default
- **Path traversal protection**: Enabled by default in production
- **Resource limits**: Configure memory, CPU, and execution timeouts

### Secrets Management
- **Environment variables**: Store sensitive configuration in secure environment
- **Configuration encryption**: Use built-in encryption for sensitive config values
- **Key rotation**: Regularly rotate any encryption keys used

### Security Configuration Example
```yaml
security:
  enable_security: true
  enable_audit_logging: true
  enable_rate_limiting: true
  rate_limit_requests: 100
  rate_limit_window: 60
  
  # Input validation
  enable_input_validation: true
  max_input_size: 524288  # 512KB
  max_output_size: 5242880  # 5MB
  
  # Path protection
  enable_path_traversal_protection: true
  allowed_paths: ["/workspace", "/projects"]
  blocked_paths: ["/etc", "/proc", "/sys", "/root"]
  
  # Command injection protection
  enable_command_injection_protection: true
```

## Troubleshooting

### Common Issues

#### 1. Server Won't Start
```bash
# Check configuration
python scripts/config_manager.py validate --config your-config.yaml

# Check system health
python scripts/config_manager.py health

# Check logs
tail -f /var/log/ast-grep-mcp.log
```

#### 2. ast-grep Binary Not Found
```bash
# Verify installation
which ast-grep

# Test binary
ast-grep --version

# Configure path
export AST_GREP_PATH="/path/to/ast-grep"
```

#### 3. Permission Errors
```bash
# Check file permissions
ls -la /var/log/ast-grep-mcp.log

# Create log directory
sudo mkdir -p /var/log/ast-grep-mcp
sudo chown $(whoami) /var/log/ast-grep-mcp
```

#### 4. High Memory Usage
```yaml
# Adjust performance settings
performance:
  enable_caching: false  # Disable caching
  max_concurrent_requests: 5  # Reduce concurrency
  memory_warning_threshold: 70.0  # Lower threshold
```

#### 5. Rate Limiting Issues
```yaml
# Adjust rate limits
security:
  rate_limit_requests: 200  # Increase limit
  rate_limit_window: 60    # Time window
```

### Debug Mode
```bash
# Enable debug logging
export AST_GREP_LOGGING__LOG_LEVEL=DEBUG

# Run with debug
ast-grep-mcp --debug

# Or in config file
logging:
  log_level: "DEBUG"
  enable_performance_logging: true
```

### Log Analysis
```bash
# View recent errors
grep -i error /var/log/ast-grep-mcp.log | tail -20

# Monitor performance
grep -i performance /var/log/ast-grep-mcp.log

# Check health status
grep -i health /var/log/ast-grep-mcp.log
```

### Performance Tuning
```yaml
# Optimize for large codebases
performance:
  enable_caching: true
  cache_ttl: 3600  # 1 hour
  cache_max_size: 5000
  max_concurrent_requests: 10
  max_execution_time: 60

ast_grep:
  default_timeout: 45
  max_timeout: 120
  max_results: 500  # Limit result size
```

### Migration from Legacy Configuration
```bash
# Migrate from environment variables
python scripts/config_manager.py migrate --output new-config.yaml

# Validate migration
python scripts/config_manager.py validate --config new-config.yaml

# Compare configurations
diff legacy-config.env new-config.yaml
```

---

## Support

For additional support:
- **Issues**: https://github.com/your-org/ast-grep-mcp/issues
- **Documentation**: https://your-docs-site.com
- **Community**: https://your-community-forum.com

---

*Last updated: January 2024* 