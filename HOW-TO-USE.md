# 📚 AST-MCP How-To Guide

**Complete guide to using AST-MCP for semantic code analysis with AI assistants**

This guide will walk you through everything you need to know to get the most out of AST-MCP, from basic setup to advanced usage patterns.

## 📋 Table of Contents

- [Quick Start](#-quick-start)
- [Installation Guide](#-installation-guide)
- [Basic Usage](#-basic-usage)
- [Advanced Patterns](#-advanced-patterns)
- [Language-Specific Examples](#-language-specific-examples)
- [Security Scanning](#-security-scanning)
- [Performance Tips](#-performance-tips)
- [Troubleshooting](#-troubleshooting)
- [Best Practices](#-best-practices)

## 🚀 Quick Start

### Prerequisites
- Python 3.10 or higher
- Claude Desktop, Continue, or any MCP-compatible AI assistant

### 1-Minute Setup
```bash
# Install AST-MCP
pip install ast-mcp

# Verify installation
ast-mcp --help
```

### Add to Claude Desktop
Add this to your `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "ast-mcp": {
      "command": "ast-mcp"
    }
  }
}
```

**That's it!** You can now use AST-MCP with Claude.

## 🔧 Installation Guide

### Option 1: pip (Recommended)
```bash
pip install ast-mcp
```

### Option 2: From Source
```bash
git clone https://github.com/AndEnd-Org/ast-mcp.git
cd ast-mcp
pip install -e .
```

### Option 3: pipx (Isolated)
```bash
pipx install ast-mcp
```

### Verify Installation
```bash
# Check version
ast-mcp --version

# Test basic functionality
python -c "import ast_grep_mcp; print('✅ Installation successful')"
```

## 📖 Basic Usage

### Core Tools Overview

AST-MCP provides three main tools:

| Tool | Purpose | When to Use |
|------|---------|-------------|
| `ast_grep_search` | Find code patterns | Searching for functions, variables, specific code structures |
| `ast_grep_scan` | Security & quality checks | Code review, vulnerability detection, best practice enforcement |
| `ast_grep_run` | Custom configurations | Advanced transformations, complex analysis |

### Your First Search

Ask Claude:
```
"Use ast_grep_search to find all function definitions in my Python files"
```

Claude will use the tool and show you results like:
```
Found 15 functions across 8 files:
- calculate_total() in src/utils.py:42
- process_data() in src/main.py:18
- validate_input() in src/validators.py:7
```

### Basic Query Patterns

#### Find Functions
```
"Find all async functions in my TypeScript code"
"Show me functions with more than 5 parameters"
"List all private methods in Python classes"
```

#### Find Variables & Constants
```
"Find all global variables in my JavaScript files"
"Show me all TODO comments in the codebase"
"Find hardcoded strings that might need localization"
```

#### Find Patterns
```
"Find all try-catch blocks without proper error handling"
"Show me all database queries in the code"
"Find places where we're using deprecated APIs"
```

## 🎯 Advanced Patterns

### Complex Searches

#### Multi-Language Analysis
```
"Find all function calls to 'authenticate' across Python, JavaScript, and TypeScript files"
```

#### Dependency Analysis
```
"Show me all imports and requires for the 'axios' library"
"Find all files that import React components"
```

#### Code Quality Patterns
```
"Find functions longer than 50 lines"
"Show me all magic numbers in the codebase"
"Find console.log statements that should be removed before production"
```

### Security Analysis

```
"Scan for potential SQL injection vulnerabilities"
"Find hardcoded passwords or API keys"
"Check for unsafe deserialization patterns"
"Find XSS vulnerabilities in template code"
```

### Refactoring Assistance

```
"Find all usages of the deprecated getUserData function"
"Show me everywhere we call the old API endpoint"
"Find components that need to be updated for React 18"
```

## 🌍 Language-Specific Examples

### Python
```python
# Find Python patterns
"Find all classes that inherit from BaseModel"
"Show me async/await usage without proper exception handling"
"Find all @deprecated decorators"
"List all Flask routes in the application"
```

### JavaScript/TypeScript
```javascript
// Find JS/TS patterns
"Find all React useEffect hooks with missing dependencies"
"Show me all Promise chains that could use async/await"
"Find unused imported modules"
"List all Express.js route handlers"
```

### Java
```java
// Find Java patterns
"Find all @Autowired annotations"
"Show me public methods without JavaDoc"
"Find synchronized blocks that might cause deadlocks"
"List all Spring @Controller classes"
```

### Rust
```rust
// Find Rust patterns
"Find all unsafe blocks in the codebase"
"Show me unwrap() calls that should use proper error handling"
"Find all #[derive] macros"
"List all public struct definitions"
```

### Go
```go
// Find Go patterns
"Find all goroutine leaks (missing channel closes)"
"Show me error handling that ignores errors"
"Find all HTTP handlers"
"List all interface definitions"
```

## 🛡️ Security Scanning

AST-MCP includes 25+ built-in security rules. Use them like this:

### Run Security Scan
```
"Run ast_grep_scan to check for security vulnerabilities in my code"
```

### Specific Security Checks
```
"Check for SQL injection vulnerabilities"
"Scan for hardcoded secrets"
"Find potential XSS issues"
"Check for insecure random number generation"
"Find unvalidated user inputs"
```

### Custom Security Rules
```
"Use ast_grep_run to check for our custom security pattern: any function named 'admin_*' that doesn't have proper authentication"
```

## ⚡ Performance Tips

### 1. Scope Your Searches
Instead of:
```
"Find all functions in the entire repository"
```

Use:
```
"Find all functions in the src/ directory"
"Find functions in *.py files only"
```

### 2. Use Specific Patterns
Instead of:
```
"Find everything related to user authentication"
```

Use:
```
"Find function calls to authenticate(), login(), or verify_token()"
```

### 3. Batch Related Queries
Instead of multiple separate queries, ask:
```
"Find all React hooks, their dependencies, and any missing cleanup in useEffect"
```

### 4. Use Language-Specific Patterns
```
"Find Python list comprehensions that could be optimized"
"Find JavaScript arrow functions that could be regular functions"
```

## 🔍 Troubleshooting

### Common Issues

#### 1. "No matches found"
**Cause**: Pattern might be too specific or syntax issue
**Solution**: 
- Try simpler patterns first
- Check if you're in the right directory
- Verify file extensions

#### 2. "Tool timeout"
**Cause**: Search too broad or large codebase
**Solution**:
- Narrow down the search scope
- Use more specific patterns
- Search in subdirectories

#### 3. "Language not supported"
**Cause**: Unsupported file extension
**Solution**:
- Check supported languages: JavaScript, TypeScript, Python, Java, Rust, Go, C/C++, and more
- Verify file extensions are standard

### Debug Mode
Add debug information to your queries:
```
"Use ast_grep_search with verbose output to find React components"
```

## 💡 Best Practices

### 1. Start Simple, Get Specific
```
✅ Good progression:
1. "Find all functions"
2. "Find all async functions" 
3. "Find all async functions without error handling"

❌ Don't start with:
"Find all complex async functions with specific error patterns and logging"
```

### 2. Use Natural Language
```
✅ Good: "Find functions that are too long"
✅ Good: "Show me potential memory leaks"
✅ Good: "Find security vulnerabilities"

❌ Avoid: "ast_grep_search pattern='function.*{.*\\n.*\\n.*}'"
```

### 3. Combine Tools Effectively
```
1. Use ast_grep_search to find patterns
2. Use ast_grep_scan for quality/security
3. Use ast_grep_run for complex custom analysis
```

### 4. Iterative Refinement
```
"Find all API calls" → "Find all external API calls" → "Find all external API calls without error handling"
```

### 5. Context-Aware Queries
```
✅ Good: "In this React app, find components that don't use TypeScript"
✅ Good: "In our Express.js backend, find routes without authentication"

❌ Generic: "Find bad code patterns"
```

## 🎓 Advanced Use Cases

### Code Migration
```
"Find all jQuery selectors that need to be converted to vanilla JavaScript"
"Show me Python 2 print statements that need updating for Python 3"
"Find all class components that could be converted to hooks"
```

### Architecture Analysis
```
"Map all the dependencies between our microservices"
"Find circular imports in our Python modules"
"Show me all database access patterns across the application"
```

### Performance Optimization
```
"Find expensive operations in render functions"
"Show me all synchronous file operations that could be async"
"Find N+1 query patterns in our ORM usage"
```

### Documentation & Maintenance
```
"Find all public APIs without documentation"
"Show me functions without type hints"
"Find all TODO comments and their priorities"
```

## 🤝 Integration Examples

### With Continue IDE
Add to your Continue config:
```json
{
  "mcpServers": {
    "ast-mcp": {
      "command": "ast-mcp"
    }
  }
}
```

### With Custom Scripts
```python
# Use AST-MCP in your own scripts
from ast_grep_mcp import search_code

results = search_code("function.*async", "src/**/*.js")
```

### CI/CD Integration
```yaml
# GitHub Actions example
- name: Security Scan
  run: |
    ast-mcp scan --security-only --output=json > security-report.json
```

## 📞 Getting Help

- **GitHub Issues**: [Report bugs or request features](https://github.com/AndEnd-Org/ast-mcp/issues)
- **Documentation**: Check the `/docs` folder for detailed API docs
- **Examples**: Look at the `/examples` directory for more use cases

---

**Ready to supercharge your code analysis?** Start with simple queries and gradually explore AST-MCP's powerful semantic understanding capabilities!