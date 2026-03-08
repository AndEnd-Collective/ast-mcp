# AST-Grep MCP Installation Guide

## Quick Install for End Users

### Option 1: Install from Source (Current)
```bash
git clone https://github.com/AndEnd-Collective/ast-mcp.git
cd ast-mcp
pip install -e .
```

### Option 2: Install from GitHub (Direct)
```bash
pip install git+https://github.com/AndEnd-Collective/ast-mcp.git
```

> **Note**: PyPI package is planned for a future release. For now, install from source.

## Prerequisites

1. **Python 3.12+** - Required for the MCP server
2. **AST-Grep Binary** - Install from [ast-grep.github.io](https://ast-grep.github.io/guide/quick-start.html#installation)

### Installing AST-Grep

#### macOS (Homebrew)
```bash
brew install ast-grep
```

#### Linux/macOS (Cargo)
```bash
cargo install ast-grep
```

#### Windows/Linux (Pre-built Binary)
Download from [GitHub Releases](https://github.com/ast-grep/ast-grep/releases)

## MCP Client Configuration

### Claude Code

Add to your `.claude/settings.json` or project-level `.mcp.json`:

```json
{
  "mcpServers": {
    "ast-mcp": {
      "command": "python",
      "args": ["-m", "ast_grep_mcp.server"],
      "cwd": "/path/to/ast-mcp"
    }
  }
}
```

### Codex

Add to your MCP configuration:

```json
{
  "mcpServers": {
    "ast-mcp": {
      "command": "python",
      "args": ["-m", "ast_grep_mcp.server"],
      "cwd": "/path/to/ast-mcp"
    }
  }
}
```

### OpenCode

Add to your `opencode.json` MCP configuration:

```json
{
  "mcpServers": {
    "ast-mcp": {
      "command": "python",
      "args": ["-m", "ast_grep_mcp.server"],
      "cwd": "/path/to/ast-mcp"
    }
  }
}
```

### Other MCP Clients

For other MCP-compatible clients, use:
- **Command**: `python -m ast_grep_mcp.server`
- **Transport**: stdio
- **Capabilities**: tools, resources

## Quick Test

After installation, test the server:

```bash
# Test basic functionality
ast-grep-mcp --help

# Test server startup (should respond to MCP protocol)
echo '{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}' | ast-grep-mcp
```

## What You Get

✅ **7 MCP Tools**:
- `ast_grep_search` - Pattern-based code search
- `ast_grep_scan` - Rule-based code scanning  
- `ast_grep_run` - Pattern matching with rewriting
- `call_graph_generate` - Code dependency analysis
- `create_config_file` - Setup AST-Grep configuration
- `read_config` - Read configuration files
- `manage_config` - Full CRUD rule management

✅ **25+ Built-in Rules**:
- Python (6 rules): print statements, bare except, formatting, etc.
- JavaScript (6 rules): console.log, var usage, strict equality, etc.
- TypeScript (3 rules): any type, console statements, interfaces
- Rust (5 rules): unwrap/panic, variables, unsafe patterns  
- Go (4 rules): error handling, nil checks, unused vars

✅ **Enterprise Features**:
- Role-based access control
- Comprehensive audit logging
- Rate limiting protection
- Performance monitoring
- Memory management

## Troubleshooting

### AST-Grep Not Found
```bash
# Check if ast-grep is installed
which ast-grep

# Install if missing (macOS)
brew install ast-grep
```

### Permission Issues
```bash
# Install with user permissions
pip install --user ast-grep-mcp
```

### MCP Connection Issues
1. Verify Python environment
2. Check ast-grep-mcp is in PATH
3. Test server startup manually
4. Check client configuration syntax

## Advanced Configuration

### Custom Rules Directory
Set environment variable:
```bash
export AST_GREP_RULES_DIR="/path/to/custom/rules"
```

### Security Settings
```bash
export AST_GREP_ENABLE_SECURITY="true"
export AST_GREP_RATE_LIMIT_REQUESTS="100"
```

### Performance Tuning
```bash
export AST_GREP_ENABLE_PERFORMANCE="true"
export AST_GREP_CACHE_SIZE="1000"
```

For complete configuration options, see the [main README](README.md).