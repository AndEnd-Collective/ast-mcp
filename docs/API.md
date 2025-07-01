# AST-Grep MCP Server API Documentation

This document provides comprehensive documentation for all MCP tools and resources available in the AST-Grep MCP Server.

## Table of Contents
- [Overview](#overview)
- [MCP Tools](#mcp-tools)
- [MCP Resources](#mcp-resources)
- [Error Handling](#error-handling)
- [Rate Limiting](#rate-limiting)
- [Examples](#examples)
- [Performance Considerations](#performance-considerations)

## Overview

The AST-Grep MCP Server implements the [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) specification, providing AI assistants with powerful semantic code search and analysis capabilities.

### Server Information
- **Protocol Version**: MCP 2024-11-05
- **Server Name**: ast-grep-mcp
- **Server Version**: 1.0.0
- **Supported Languages**: 20+ programming languages

### Authentication
The server supports several authentication methods:
- **None**: Default for development
- **API Key**: Header-based authentication
- **Bearer Token**: OAuth-style authentication

## MCP Tools

Tools are the primary way to interact with the AST-Grep MCP Server. Each tool represents a specific operation that can be performed.

### 1. Semantic Search (`ast_grep_search`)

Perform semantic code search using AST-based patterns.

#### Schema
```json
{
  "name": "ast_grep_search",
  "description": "Search for code patterns using AST-based queries",
  "inputSchema": {
    "type": "object",
    "properties": {
      "pattern": {
        "type": "string",
        "description": "AST pattern to search for (e.g., 'function $NAME($ARGS) { $BODY }')"
      },
      "language": {
        "type": "string",
        "description": "Programming language",
        "enum": ["javascript", "typescript", "python", "java", "rust", "go", "c", "cpp", "csharp", "ruby", "php", "swift", "kotlin", "scala", "lua", "bash", "yaml", "json", "html", "css"]
      },
      "paths": {
        "type": "array",
        "items": {"type": "string"},
        "description": "File paths or directories to search in",
        "default": ["."]
      },
      "limit": {
        "type": "integer",
        "description": "Maximum number of results to return",
        "default": 100,
        "minimum": 1,
        "maximum": 1000
      },
      "include_content": {
        "type": "boolean",
        "description": "Include matched code content in results",
        "default": true
      }
    },
    "required": ["pattern", "language"]
  }
}
```

#### Example Request
```json
{
  "method": "tools/call",
  "params": {
    "name": "ast_grep_search",
    "arguments": {
      "pattern": "function $NAME($_) { $BODY }",
      "language": "javascript",
      "paths": ["src/"],
      "limit": 50,
      "include_content": true
    }
  }
}
```

#### Example Response
```json
{
  "content": [
    {
      "type": "text",
      "text": "Found 15 matches for pattern 'function $NAME($_) { $BODY }'"
    },
    {
      "type": "text",
      "text": "Results:\n\n**src/utils.js:23-30**\n```javascript\nfunction validateInput(data) {\n  if (!data) {\n    throw new Error('Data is required');\n  }\n  return true;\n}\n```\n\n**src/api.js:45-52**\n```javascript\nfunction processRequest(req) {\n  const result = validateInput(req.body);\n  return handleResponse(result);\n}\n```"
    }
  ]
}
```

### 2. Code Scanning (`ast_grep_scan`)

Scan codebase using predefined or custom AST-Grep rules.

#### Schema
```json
{
  "name": "ast_grep_scan",
  "description": "Scan codebase with AST-Grep rules",
  "inputSchema": {
    "type": "object",
    "properties": {
      "rule_path": {
        "type": "string",
        "description": "Path to AST-Grep rule file (.yml or .yaml)"
      },
      "paths": {
        "type": "array",
        "items": {"type": "string"},
        "description": "Paths to scan",
        "default": ["."]
      },
      "output_format": {
        "type": "string",
        "enum": ["json", "yaml", "text"],
        "description": "Output format for results",
        "default": "json"
      },
      "severity": {
        "type": "string",
        "enum": ["info", "warning", "error"],
        "description": "Minimum severity level to report"
      }
    },
    "required": ["rule_path"]
  }
}
```

#### Example Request
```json
{
  "method": "tools/call",
  "params": {
    "name": "ast_grep_scan",
    "arguments": {
      "rule_path": "rules/security.yml",
      "paths": ["src/", "lib/"],
      "output_format": "json",
      "severity": "warning"
    }
  }
}
```

#### Example Response
```json
{
  "content": [
    {
      "type": "text",
      "text": "Scan completed: 3 issues found"
    },
    {
      "type": "text",
      "text": "{\n  \"results\": [\n    {\n      \"rule\": \"no-eval\",\n      \"severity\": \"error\",\n      \"file\": \"src/unsafe.js\",\n      \"line\": 42,\n      \"column\": 15,\n      \"message\": \"Use of eval() is dangerous\",\n      \"context\": \"eval(userInput)\"\n    }\n  ]\n}"
    }
  ]
}
```

### 3. Rule Execution (`ast_grep_run`)

Execute AST-Grep with custom configuration.

#### Schema
```json
{
  "name": "ast_grep_run",
  "description": "Run AST-Grep with custom configuration",
  "inputSchema": {
    "type": "object",
    "properties": {
      "config_path": {
        "type": "string",
        "description": "Path to AST-Grep configuration file"
      },
      "paths": {
        "type": "array",
        "items": {"type": "string"},
        "description": "Target paths",
        "default": ["."]
      },
      "fix": {
        "type": "boolean",
        "description": "Apply automatic fixes",
        "default": false
      },
      "interactive": {
        "type": "boolean",
        "description": "Interactive mode for fixes",
        "default": false
      }
    },
    "required": ["config_path"]
  }
}
```

### 4. Call Graph Generation (`call_graph_generate`)

Generate function call dependency graphs.

#### Schema
```json
{
  "name": "call_graph_generate",
  "description": "Generate function call dependency graph",
  "inputSchema": {
    "type": "object",
    "properties": {
      "entry_points": {
        "type": "array",
        "items": {"type": "string"},
        "description": "Entry point files to start analysis from"
      },
      "language": {
        "type": "string",
        "description": "Programming language",
        "enum": ["javascript", "typescript", "python", "java", "rust", "go", "c", "cpp"]
      },
      "max_depth": {
        "type": "integer",
        "description": "Maximum call depth to analyze",
        "default": 10,
        "minimum": 1,
        "maximum": 20
      },
      "include_external": {
        "type": "boolean",
        "description": "Include external library calls",
        "default": false
      },
      "output_format": {
        "type": "string",
        "enum": ["json", "mermaid", "dot"],
        "description": "Output format",
        "default": "json"
      }
    },
    "required": ["entry_points", "language"]
  }
}
```

#### Example Request
```json
{
  "method": "tools/call",
  "params": {
    "name": "call_graph_generate",
    "arguments": {
      "entry_points": ["src/main.py"],
      "language": "python",
      "max_depth": 5,
      "include_external": false,
      "output_format": "mermaid"
    }
  }
}
```

#### Example Response
```json
{
  "content": [
    {
      "type": "text",
      "text": "Call graph generated successfully"
    },
    {
      "type": "text",
      "text": "```mermaid\ngraph TD\n    A[main] --> B[process_data]\n    A --> C[setup_logging]\n    B --> D[validate_input]\n    B --> E[transform_data]\n    E --> F[save_results]\n```"
    }
  ]
}
```

### 5. Function Detection (`detect_functions`)

Detect and analyze function definitions in code.

#### Schema
```json
{
  "name": "detect_functions",
  "description": "Detect function definitions and their metadata",
  "inputSchema": {
    "type": "object",
    "properties": {
      "paths": {
        "type": "array",
        "items": {"type": "string"},
        "description": "Paths to analyze",
        "default": ["."]
      },
      "language": {
        "type": "string",
        "description": "Programming language"
      },
      "include_private": {
        "type": "boolean",
        "description": "Include private/internal functions",
        "default": true
      },
      "include_metadata": {
        "type": "boolean",
        "description": "Include function metadata (parameters, return type, etc.)",
        "default": true
      }
    }
  }
}
```

### 6. Call Detection (`detect_calls`)

Detect function calls and their relationships.

#### Schema
```json
{
  "name": "detect_calls",
  "description": "Detect function calls and analyze call patterns",
  "inputSchema": {
    "type": "object",
    "properties": {
      "paths": {
        "type": "array",
        "items": {"type": "string"},
        "description": "Paths to analyze"
      },
      "language": {
        "type": "string",
        "description": "Programming language"
      },
      "target_functions": {
        "type": "array",
        "items": {"type": "string"},
        "description": "Specific functions to track calls for"
      },
      "include_context": {
        "type": "boolean",
        "description": "Include surrounding code context",
        "default": true
      }
    }
  }
}
```

## MCP Resources

Resources provide static information about the server capabilities and documentation.

### 1. Language Support (`ast-grep://languages`)

Lists all supported programming languages and their capabilities.

#### Example Response
```json
{
  "contents": [
    {
      "type": "text",
      "text": "# Supported Languages\n\nAST-Grep MCP Server supports the following programming languages:\n\n## Web Technologies\n- **JavaScript** (js, mjs, jsx)\n- **TypeScript** (ts, tsx)\n- **HTML** (html, htm)\n- **CSS** (css, scss, sass)\n- **JSON** (json)\n\n## Systems Programming\n- **C** (c, h)\n- **C++** (cpp, cxx, cc, hpp)\n- **Rust** (rs)\n- **Go** (go)\n\n## Enterprise Languages\n- **Java** (java)\n- **C#** (cs)\n- **Kotlin** (kt)\n- **Scala** (scala)\n\n## Scripting Languages\n- **Python** (py)\n- **Ruby** (rb)\n- **PHP** (php)\n- **Lua** (lua)\n- **Bash** (sh, bash)\n\n## Mobile Development\n- **Swift** (swift)\n- **Dart** (dart)\n\n## Data Languages\n- **SQL** (sql)\n- **YAML** (yml, yaml)\n\n## Other Languages\n- **Haskell** (hs)\n- **Elixir** (ex, exs)"
    }
  ]
}
```

### 2. Pattern Syntax (`ast-grep://patterns`)

Documentation for AST pattern syntax and meta-variables.

#### Example Response
```json
{
  "contents": [
    {
      "type": "text",
      "text": "# AST Pattern Syntax\n\n## Meta-variables\nMeta-variables are placeholders that match AST nodes:\n\n- `$VAR` - Matches any single AST node\n- `$_` - Anonymous meta-variable (matches but doesn't capture)\n- `$$ARGS` - Matches multiple nodes (variadic)\n\n## Examples\n\n### Function Definitions\n```javascript\n// Pattern\nfunction $NAME($ARGS) { $BODY }\n\n// Matches\nfunction hello(name) { console.log('Hello ' + name); }\nfunction add(a, b) { return a + b; }\n```\n\n### Method Calls\n```javascript\n// Pattern\n$OBJ.$METHOD($ARGS)\n\n// Matches\nuser.getName()\nconsole.log('message')\narray.push(item)\n```\n\n### Conditional Statements\n```javascript\n// Pattern\nif ($CONDITION) { $THEN }\n\n// Matches\nif (user.isActive) { processUser(user); }\nif (count > 0) { displayResults(); }\n```"
    }
  ]
}
```

### 3. Usage Examples (`ast-grep://examples`)

Common usage patterns and examples.

### 4. Call Graph Schema (`ast-grep://schemas/call-graph`)

JSON schema for call graph output format.

## Error Handling

The AST-Grep MCP Server provides detailed error information for troubleshooting.

### Error Response Format
```json
{
  "error": {
    "code": -32000,
    "message": "AST-Grep execution failed",
    "data": {
      "type": "EXECUTION_ERROR",
      "details": "Pattern syntax error at line 1: unexpected token '$INVALID'",
      "ast_grep_error": "...",
      "suggestions": [
        "Check pattern syntax",
        "Verify language is supported"
      ]
    }
  }
}
```

### Common Error Types

#### 1. Pattern Syntax Errors
```json
{
  "error": {
    "code": -32600,
    "message": "Invalid pattern syntax",
    "data": {
      "type": "PATTERN_SYNTAX_ERROR",
      "details": "Meta-variable '$INVALID-NAME' contains invalid characters",
      "line": 1,
      "column": 12
    }
  }
}
```

#### 2. File Not Found
```json
{
  "error": {
    "code": -32000,
    "message": "File or directory not found",
    "data": {
      "type": "FILE_NOT_FOUND",
      "path": "/nonexistent/path",
      "suggestions": ["Check file path", "Verify permissions"]
    }
  }
}
```

#### 3. Language Not Supported
```json
{
  "error": {
    "code": -32602,
    "message": "Language not supported",
    "data": {
      "type": "UNSUPPORTED_LANGUAGE",
      "language": "cobol",
      "supported_languages": ["javascript", "python", "java", "..."]
    }
  }
}
```

#### 4. Rate Limit Exceeded
```json
{
  "error": {
    "code": -32000,
    "message": "Rate limit exceeded",
    "data": {
      "type": "RATE_LIMIT_EXCEEDED",
      "limit": 100,
      "window": 60,
      "retry_after": 45
    }
  }
}
```

#### 5. Resource Limits
```json
{
  "error": {
    "code": -32000,
    "message": "Resource limit exceeded",
    "data": {
      "type": "RESOURCE_LIMIT_EXCEEDED",
      "limit_type": "memory",
      "current": "512MB",
      "limit": "256MB"
    }
  }
}
```

## Rate Limiting

The server implements configurable rate limiting to prevent abuse.

### Rate Limit Headers
When rate limiting is enabled, responses include headers:

```http
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 87
X-RateLimit-Window: 60
X-RateLimit-Reset: 2024-01-01T12:34:56Z
```

### Rate Limit Configuration
```yaml
security:
  enable_rate_limiting: true
  rate_limit_requests: 100
  rate_limit_window: 60  # seconds
```

## Examples

### Example 1: Finding All Function Definitions

```json
{
  "method": "tools/call",
  "params": {
    "name": "ast_grep_search",
    "arguments": {
      "pattern": "function $NAME($PARAMS) { $BODY }",
      "language": "javascript",
      "paths": ["src/"],
      "limit": 50
    }
  }
}
```

### Example 2: Security Scanning

```json
{
  "method": "tools/call",
  "params": {
    "name": "ast_grep_scan",
    "arguments": {
      "rule_path": "security-rules.yml",
      "paths": ["src/", "lib/"],
      "severity": "warning"
    }
  }
}
```

### Example 3: Call Graph Analysis

```json
{
  "method": "tools/call",
  "params": {
    "name": "call_graph_generate",
    "arguments": {
      "entry_points": ["src/main.py"],
      "language": "python",
      "max_depth": 3,
      "output_format": "mermaid"
    }
  }
}
```

### Example 4: Finding Deprecated API Usage

```json
{
  "method": "tools/call",
  "params": {
    "name": "ast_grep_search",
    "arguments": {
      "pattern": "$OBJ.deprecatedMethod($ARGS)",
      "language": "java",
      "paths": ["src/main/java/"]
    }
  }
}
```

## Performance Considerations

### Optimization Tips

1. **Use Specific Paths**: Limit search to relevant directories
2. **Set Reasonable Limits**: Use appropriate result limits
3. **Language-Specific Patterns**: Use language-appropriate patterns
4. **Cache Results**: Enable caching for repeated queries
5. **Parallel Processing**: Server automatically parallelizes when possible

### Performance Monitoring

The server provides performance metrics:

```json
{
  "method": "resources/read",
  "params": {
    "uri": "ast-grep://metrics/performance"
  }
}
```

### Best Practices

1. **Pattern Complexity**: Keep patterns as simple as possible
2. **Path Filtering**: Use specific paths rather than searching entire repositories
3. **Result Limits**: Set appropriate limits based on your needs
4. **Batch Operations**: Group similar operations when possible
5. **Error Handling**: Implement proper error handling and retries

---

## Server Capabilities

### MCP Protocol Support
- **Protocol Version**: 2024-11-05
- **Capabilities**: tools, resources, logging, progress
- **Transport**: stdio, HTTP, WebSocket

### Security Features
- Input validation and sanitization
- Path traversal protection
- Command injection prevention
- Rate limiting and throttling
- Audit logging

### Monitoring & Observability
- Health check endpoints
- Performance metrics
- Audit logging
- Error tracking
- Resource usage monitoring

---

*For more information, see the [Configuration Guide](CONFIGURATION.md) and [Deployment Guide](DEPLOYMENT.md).* 