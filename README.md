# ast-mcp

A [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) server that provides AI assistants with semantic code search and analysis capabilities using [ast-grep](https://ast-grep.github.io/).

## Features

- **Semantic Code Search**: AST-based pattern matching across 20+ programming languages
- **Code Analysis**: Function detection, call graph generation, and relationship mapping  
- **Rule-Based Scanning**: Custom security and quality rule enforcement
- **Multi-Language Support**: JavaScript, TypeScript, Python, Java, Rust, Go, C/C++, and more

## Installation

```bash
pip install ast-mcp
```

## Usage

### With Claude Desktop

Add to your Claude Desktop configuration:

```json
{
  "mcpServers": {
    "ast-mcp": {
      "command": "ast-mcp"
    }
  }
}
```

### Standalone

```bash
ast-mcp
```

## Tools

- `ast_grep_search` - Search for AST patterns in code
- `ast_grep_scan` - Run predefined rules and checks
- `ast_grep_run` - Execute custom AST-Grep configurations

## Requirements

- Python 3.10+
- AST-Grep binary (automatically installed via `ast-grep-cli` package)

## License

MIT