# AST-Grep MCP Server

A powerful [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) server that provides AI assistants with semantic code search and analysis capabilities using [ast-grep](https://ast-grep.github.io/).

## 🙏 Acknowledgments

This project is built upon the incredible work of the [ast-grep](https://ast-grep.github.io/) project by [Herrington Darkholme](https://github.com/HerringtonDarkholme). ast-grep is a revolutionary tool that makes abstract syntax tree (AST) manipulation accessible and powerful for developers worldwide.

**Special thanks to the ast-grep team for:**
- Creating an intuitive, jQuery-like API for AST traversal
- Supporting 20+ programming languages with consistent syntax
- Providing excellent documentation and community support
- Building a fast, reliable Rust-based foundation
- Making semantic code search accessible to everyone

🔗 **Learn more about ast-grep**: [https://ast-grep.github.io/](https://ast-grep.github.io/)  
⭐ **Star the ast-grep project**: [https://github.com/ast-grep/ast-grep](https://github.com/ast-grep/ast-grep)

This MCP server simply provides a bridge between AI assistants and the amazing capabilities that ast-grep already offers.

## 🚀 Features

### Core Capabilities
- **Semantic Code Search**: Advanced AST-based pattern matching across 20+ programming languages
- **Code Analysis**: Function detection, call graph generation, and relationship mapping
- **Rule-Based Scanning**: Custom security and quality rule enforcement
- **Multi-Language Support**: JavaScript, TypeScript, Python, Java, Rust, Go, C/C++, and more

### Enterprise-Grade Features
- **🔐 Security First**: Input validation, path traversal protection, rate limiting
- **📊 Performance Monitoring**: Comprehensive metrics, caching, resource management
- **🛠️ Configuration Management**: Pydantic-based validation, multi-environment support
- **📝 Audit Logging**: Detailed operation tracking and security event logging
- **🔄 Health Monitoring**: Real-time health checks and status reporting

### Advanced Functionality
- **Enhanced Configuration System**: YAML/JSON config files with environment variable support
- **Migration Tools**: Seamless upgrade path from legacy configurations
- **Multi-Environment Profiles**: Development, staging, and production configurations
- **Hot Reload**: Dynamic configuration updates without restart
- **Comprehensive Documentation**: Deployment, configuration, API, and troubleshooting guides

## 📋 Quick Start

### Installation

#### For End Users (Recommended)
```bash
# Install from PyPI
pip install ast-grep-mcp

# Or install from GitHub
pip install git+https://github.com/AndEnd-Org/ast-mcp.git
```

#### Prerequisites
- Python 3.8+
- **No additional setup required!** The ast-grep binary is automatically included via the `ast-grep-cli` package dependency.

> **Note**: The ast-grep binary is automatically installed when you install this package. No manual installation of ast-grep is required!

### MCP Client Configuration

#### Claude Desktop
Add to your `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "ast-grep-mcp": {
      "command": "ast-grep-mcp",
      "args": []
    }
  }
}
```

**Location**:
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

#### Other MCP Clients
Use the command `ast-grep-mcp` with stdio transport.

See [INSTALL.md](INSTALL.md) for detailed installation instructions.

### Developer Installation

1. **Install the MCP server**:
   ```bash
   git clone https://github.com/AndEnd-Org/ast-mcp.git
   cd ast-mcp
   pip install -e .
   ```

   > **Note**: The ast-grep binary is automatically installed as a dependency. No manual installation required!

2. **Basic configuration**:
   ```bash
   # Create development configuration
   python scripts/config_manager.py create-template development --output config.yaml
   
   # Validate configuration
   python scripts/config_manager.py validate --config config.yaml
   ```

### Using with Cursor

Add to your `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "ast-grep": {
      "command": "python",
      "args": ["-m", "ast_grep_mcp.server"],
      "env": {
        "AST_GREP_LOGGING__LOG_LEVEL": "INFO"
      }
    }
  }
}
```

## 🛠️ MCP Tools

### Core Search Tools
- **`ast_grep_search`**: Semantic code pattern search
- **`ast_grep_scan`**: Rule-based code scanning
- **`ast_grep_run`**: Custom AST-Grep configuration execution

### Analysis Tools
- **`call_graph_generate`**: Function call dependency analysis
- **`detect_functions`**: Function definition detection
- **`detect_calls`**: Function call pattern analysis

### Example Usage

```javascript
// Find all function definitions
{
  "name": "ast_grep_search",
  "arguments": {
    "pattern": "function $NAME($ARGS) { $BODY }",
    "language": "javascript",
    "paths": ["src/"],
    "limit": 50
  }
}

// Security scan
{
  "name": "ast_grep_scan",
  "arguments": {
    "rule_path": "security-rules.yml",
    "paths": ["src/", "lib/"],
    "severity": "warning"
  }
}
```

## 📚 Comprehensive Documentation

### 📖 User Guides
- **[Configuration Guide](docs/CONFIGURATION.md)**: Complete configuration reference with examples
- **[Deployment Guide](docs/DEPLOYMENT.md)**: Production deployment strategies and best practices
- **[API Documentation](docs/API.md)**: Detailed API reference with examples and schemas
- **[Troubleshooting Guide](docs/TROUBLESHOOTING.md)**: Common issues and solutions

### 🔧 Development Resources
- **[Scripts & Tools](scripts/)**: Configuration management and utilities
- **[Example Configurations](config/)**: Templates for different environments
- **[Comprehensive Tests](tests/)**: Full test suite with coverage reporting

## ⚙️ Configuration

The server supports a sophisticated configuration system:

### Configuration Sources (Priority Order)
1. **Command Line Arguments**: `--config`, `--debug`, etc.
2. **Environment Variables**: `AST_GREP_SECTION__SETTING`
3. **Configuration Files**: YAML, JSON, or TOML format
4. **Default Values**: Built-in sensible defaults

### Quick Configuration Examples

**Development Environment**:
```yaml
name: "ast-grep-mcp"
environment: "development"
debug: true

security:
  enable_security: false
  enable_rate_limiting: false

performance:
  enable_caching: false
  max_concurrent_requests: 10
```

**Production Environment**:
```yaml
name: "ast-grep-mcp"
environment: "production"
debug: false

security:
  enable_security: true
  enable_rate_limiting: true
  rate_limit_requests: 100
  rate_limit_window: 60

performance:
  enable_caching: true
  max_concurrent_requests: 5
```

### Configuration Management CLI

```bash
# Create configuration template
python scripts/config_manager.py create-template production --output config.yaml

# Validate configuration
python scripts/config_manager.py validate --config config.yaml

# Migrate from legacy configuration
python scripts/config_manager.py migrate --output new-config.yaml

# System health check
python scripts/config_manager.py health
```

## 🔒 Security Features

### Input Validation & Protection
- **Pattern Validation**: AST pattern syntax validation
- **Path Traversal Protection**: Configurable allowed/blocked paths
- **Input Size Limits**: Configurable maximum input/output sizes
- **Command Injection Prevention**: Safe parameter handling

### Access Control & Monitoring
- **Rate Limiting**: Configurable per-client request limits
- **Audit Logging**: Comprehensive security event tracking
- **Resource Monitoring**: Memory and CPU usage tracking
- **Health Checks**: System status and availability monitoring

### Configuration Example
```yaml
security:
  enable_security: true
  enable_rate_limiting: true
  rate_limit_requests: 100
  rate_limit_window: 60
  
  max_input_size: 1048576  # 1MB
  max_output_size: 10485760  # 10MB
  
  allowed_paths: ["/workspace", "/home/user/projects"]
  blocked_paths: ["/etc", "/proc", "/sys"]
```

## 📊 Performance & Monitoring

### Performance Features
- **Smart Caching**: Configurable result caching for repeated queries
- **Resource Limits**: Memory and execution time controls
- **Concurrent Request Management**: Configurable concurrency limits
- **Performance Metrics**: Detailed timing and resource usage tracking

### Monitoring Capabilities
- **Health Endpoints**: Real-time system status checks
- **Performance Metrics**: Request timing, memory usage, cache hit rates
- **Audit Trails**: Comprehensive operation logging
- **Error Tracking**: Detailed error reporting and analysis

### Configuration Example
```yaml
performance:
  enable_performance: true
  enable_caching: true
  cache_ttl: 600
  
  max_concurrent_requests: 10
  max_execution_time: 30
  memory_warning_threshold: 70.0
  memory_critical_threshold: 90.0

monitoring:
  enable_health_checks: true
  health_check_interval: 30
  enable_metrics_collection: true
```

## 🧪 Testing

### Comprehensive Test Suite
- **Unit Tests**: Individual component testing
- **Integration Tests**: End-to-end functionality testing
- **Performance Tests**: Load and stress testing
- **Security Tests**: Validation and protection testing

### Running Tests
```bash
# Run all tests
python -m pytest tests/

# Run specific test categories
python -m pytest tests/test_ast_grep_search.py -v
python -m pytest tests/test_configuration.py -v
python -m pytest tests/test_security.py -v

# Run with coverage
python -m pytest tests/ --cov=src/ast_grep_mcp --cov-report=html

# Performance testing
python -m pytest tests/test_performance.py --benchmark-only
```

### Validation Scripts
```bash
# Validate core functionality
python scripts/validate_function_detection.py
python scripts/validate_call_graph_generation.py
python scripts/validate_call_detection.py
```

## 🚀 Deployment

### Deployment Options
- **Development**: Local testing and development
- **Staging**: Pre-production validation environment
- **Production**: High-availability production deployment
- **Containerized**: Docker and Kubernetes deployment

### Quick Deployment
```bash
# Create production configuration
python scripts/config_manager.py create-template production --output production.yaml

# Validate deployment
python scripts/config_manager.py validate --config production.yaml

# Start server
python -m ast_grep_mcp.server --config production.yaml
```

For detailed deployment instructions, see the [Deployment Guide](docs/DEPLOYMENT.md).

## 🤝 Contributing

### Development Setup
1. **Clone the repository**:
   ```bash
   git clone https://github.com/your-org/ast-grep-mcp.git
   cd ast-grep-mcp
   ```

2. **Set up development environment**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -e .[dev]
   ```

3. **Install pre-commit hooks**:
   ```bash
   pre-commit install
   ```

4. **Run tests**:
   ```bash
   python -m pytest tests/ -v
   ```

### Code Quality
- **Type Safety**: Full type hints with mypy validation
- **Code Formatting**: Black and isort for consistent formatting
- **Linting**: Flake8 for code quality checks
- **Security**: Bandit for security vulnerability scanning

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🆘 Support & Troubleshooting

### Getting Help
- **📖 Documentation**: Comprehensive guides in the [docs/](docs/) directory
- **🐛 Issues**: Report bugs and feature requests on GitHub
- **💬 Discussions**: Community discussions and questions
- **🔧 Troubleshooting**: Detailed [troubleshooting guide](docs/TROUBLESHOOTING.md)

### Quick Troubleshooting
```bash
# Check system health
python scripts/config_manager.py health

# Validate configuration
python scripts/config_manager.py validate --config config.yaml --verbose

# Test ast-grep integration
ast-grep --version
python -c "import ast_grep_mcp; print('Package installed successfully')"

# Debug with detailed logging
AST_GREP_LOGGING__LOG_LEVEL=DEBUG python -m ast_grep_mcp.server
```

For comprehensive troubleshooting, see the [Troubleshooting Guide](docs/TROUBLESHOOTING.md).

---

## 🏗️ Architecture

### Core Components
- **🧠 MCP Server**: Protocol implementation and tool orchestration
- **🔍 AST-Grep Integration**: Pattern matching and code analysis
- **⚙️ Configuration System**: Pydantic-based validation and management
- **🔒 Security Layer**: Input validation and access control
- **📊 Performance System**: Monitoring and optimization
- **📝 Logging System**: Comprehensive audit and debug logging

### Data Flow
```
AI Assistant → MCP Client → AST-Grep MCP Server → ast-grep binary → Code Analysis → Results
```

### Key Design Principles
- **Type Safety**: Comprehensive Pydantic models for all data structures
- **Security First**: Multiple layers of input validation and protection
- **Performance Optimized**: Caching, resource limits, and efficient processing
- **Highly Configurable**: Flexible configuration system for all environments
- **Observable**: Comprehensive logging and monitoring capabilities

---

**Built with ❤️ for AI-powered code analysis**

*AST-Grep MCP Server - Empowering AI assistants with semantic code understanding* 