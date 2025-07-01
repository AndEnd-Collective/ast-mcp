# AST-Grep MCP Server

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![MCP](https://img.shields.io/badge/MCP-Compatible-green.svg)](https://modelcontextprotocol.io/)

A powerful **Model Context Protocol (MCP) Server** that wraps the open-source [ast-grep](https://ast-grep.github.io/) tool, providing AI assistants with advanced semantic code search and analysis capabilities.

## 🚀 Features

### Core Capabilities
- **🔍 Semantic Code Search**: Find code patterns across multiple programming languages using AST-based queries
- **📊 Code Scanning**: Comprehensive codebase analysis with customizable rules and patterns  
- **🏃‍♂️ Rule Execution**: Run predefined or custom ast-grep rules against codebases
- **📈 Call Graph Generation**: Visualize function dependencies and call relationships

### Language Support
Supports **20+ programming languages** including:
- **Web**: JavaScript, TypeScript, HTML, CSS, JSON
- **Systems**: C, C++, Rust, Go
- **Enterprise**: Java, C#, Kotlin, Scala
- **Scripting**: Python, Ruby, PHP, Lua
- **Mobile**: Swift, Dart
- **Data**: SQL, YAML
- **And more**: Bash, Haskell, etc.

### MCP Integration
- **Secure**: Sandboxed execution with configurable resource limits
- **Async**: Non-blocking operations for responsive AI interactions  
- **Validated**: Strict input validation using Pydantic models
- **Documented**: Comprehensive resource documentation and examples

## 📋 Prerequisites

1. **Python 3.8+** with pip
2. **ast-grep binary** installed via one of:
   ```bash
   # Via Cargo (Rust)
   cargo install ast-grep
   
   # Via npm  
   npm install -g @ast-grep/cli
   
   # Via Homebrew (macOS)
   brew install ast-grep
   
   # Via package manager (Linux)
   # See: https://ast-grep.github.io/guide/quick-start.html
   ```

## 🛠️ Installation

### From Source
```bash
# Clone the repository
git clone https://github.com/example/ast-grep-mcp.git
cd ast-grep-mcp

# Install in development mode
pip install -e .

# Or install with development dependencies
pip install -e .[dev]
```

### For Development
```bash
# Install development dependencies
pip install -e .[dev]

# Set up pre-commit hooks
pre-commit install

# Run tests
pytest

# Run type checking
mypy src/

# Format code
black src/ tests/
isort src/ tests/
```

## 🚀 Usage

### As MCP Server
The server can be integrated with MCP-compatible AI assistants:

```json
{
  "mcpServers": {
    "ast-grep": {
      "command": "ast-grep-mcp",
      "args": [],
      "env": {
        "AST_GREP_PATH": "/path/to/ast-grep"
      }
    }
  }
}
```

### Available Tools

#### 1. Semantic Search (`ast_grep_search`)
Find code patterns using AST-based queries:

```json
{
  "pattern": "function $NAME($ARGS) { $BODY }",
  "language": "javascript",
  "paths": ["src/"],
  "limit": 10
}
```

#### 2. Code Scanning (`ast_grep_scan`) 
Scan codebase with predefined rules:

```json
{
  "rule_path": "rules/security.yml",
  "paths": ["src/", "lib/"],
  "output_format": "json"
}
```

#### 3. Rule Execution (`ast_grep_run`)
Execute custom ast-grep configurations:

```json
{
  "config_path": "ast-grep.yml",
  "paths": ["src/"],
  "fix": false
}
```

#### 4. Call Graph Generation (`call_graph_generate`)
Generate function call dependency graphs:

```json
{
  "entry_points": ["src/main.py"],
  "language": "python", 
  "max_depth": 5,
  "include_external": false
}
```

### Available Resources

- **📚 Language Support** (`ast-grep://languages`): Complete list of supported languages
- **🔧 Pattern Syntax** (`ast-grep://patterns`): AST pattern syntax documentation  
- **💡 Examples** (`ast-grep://examples`): Usage examples and common patterns
- **📋 Call Graph Schema** (`ast-grep://schemas/call-graph`): JSON schema for call graph output

## ⚙️ Configuration

### Environment Variables
```bash
# AST-Grep binary path (auto-detected if not set)
AST_GREP_PATH=/usr/local/bin/ast-grep

# Resource limits
MAX_FILE_SIZE=10485760        # 10MB max file size
MAX_SEARCH_RESULTS=1000       # Max search results
EXECUTION_TIMEOUT=30          # 30 second timeout

# Logging
LOG_LEVEL=INFO               # DEBUG, INFO, WARNING, ERROR
LOG_FILE=ast-grep-mcp.log    # Log file path
```

### Security
- **Path Traversal Protection**: Prevents access outside specified directories
- **Resource Limits**: Configurable limits on file size, results, and execution time
- **Input Validation**: Strict validation using Pydantic models
- **Sandboxed Execution**: ast-grep runs in controlled environment

## 🔧 Development

### Project Structure
```
ast-grep-mcp/
├── src/ast_grep_mcp/          # Main package
│   ├── __init__.py           # Package initialization
│   ├── server.py             # MCP server implementation  
│   ├── tools.py              # MCP tool implementations
│   ├── resources.py          # MCP resource providers
│   └── utils.py              # Utilities and helpers
├── tests/                    # Test suite
├── docs/                     # Documentation
├── pyproject.toml           # Project configuration
└── README.md                # This file
```

### Development Workflow
1. **Setup**: `pip install -e .[dev]`
2. **Code**: Follow type hints and docstrings
3. **Test**: `pytest` with coverage
4. **Lint**: `black`, `isort`, `flake8`, `mypy`
5. **Security**: `bandit` security scanning
6. **Commit**: Pre-commit hooks ensure quality

### Testing
```bash
# Run all tests
pytest

# With coverage
pytest --cov=src --cov-report=html

# Specific test categories  
pytest -m unit          # Unit tests only
pytest -m integration   # Integration tests only
pytest -m "not slow"    # Skip slow tests
```

## 🤝 Contributing

1. **Fork** the repository
2. **Create** a feature branch (`git checkout -b feature/amazing-feature`)
3. **Commit** your changes (`git commit -m 'Add amazing feature'`)
4. **Push** to the branch (`git push origin feature/amazing-feature`)
5. **Open** a Pull Request

### Code Standards
- **Type Safety**: Full type annotations required
- **Documentation**: Docstrings for all public APIs
- **Testing**: Comprehensive test coverage
- **Code Quality**: Black formatting, import sorting
- **Security**: Bandit security scanning

## 📚 Resources

- **AST-Grep Documentation**: https://ast-grep.github.io/
- **Model Context Protocol**: https://modelcontextprotocol.io/
- **Python Packaging**: https://packaging.python.org/

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- **[ast-grep](https://ast-grep.github.io/)** - The powerful AST-based code search tool
- **[Model Context Protocol](https://modelcontextprotocol.io/)** - The protocol enabling AI-tool integration
- **Open Source Community** - For the amazing tools and libraries that make this possible

---

**Built with ❤️ for the AI and developer community** 