# Dependency Analysis Report: "ast-grep-mcp" → "ast-mcp" Renaming Impact

## Executive Summary

This report analyzes the impact of renaming the package from "ast-grep-mcp" to "ast-mcp" across all interconnected dependencies in the codebase. The analysis reveals multiple dependency chains that must be updated atomically to maintain system integrity.

## 1. Package Configuration Dependencies

### 1.1 PyPI Package Definition Chain
**File**: `/Users/Naor.Penso/code/ast-mcp/pyproject.toml`
```toml
[project]
name = "ast-grep-mcp"  # → "ast-mcp"

[project.scripts]
ast-grep-mcp = "ast_grep_mcp.server:main_sync"  # → "ast-mcp"
```

**Impact**: This is the root dependency that propagates to all downstream systems.

### 1.2 Setuptools Generated Files
**Location**: `/Users/Naor.Penso/code/ast-mcp/src/ast_grep_mcp.egg-info/`
- `PKG-INFO` → Contains package metadata
- `entry_points.txt` → CLI command definitions
- Auto-regenerated during build process

**Impact**: These files are automatically regenerated from pyproject.toml, creating a consistent propagation chain.

## 2. MCP Server Configuration Chains

### 2.1 Claude Desktop Configuration
**File**: `/Users/Naor.Penso/code/ast-mcp/config/claude_desktop_config.json`
```json
{
  "mcpServers": {
    "ast-grep-mcp": {  // → "ast-mcp"
      "command": "ast-grep-mcp",  // → "ast-mcp"
      "args": []
    }
  }
}
```

### 2.2 Cursor IDE Configuration
**File**: `/Users/Naor.Penso/code/ast-mcp/.cursor/mcp.json`
```json
{
  "mcpServers": {
    "ast-grep-mcp": {  // → "ast-mcp"
      "command": "/Users/Naor.Penso/code/ast-mcp/venv/bin/ast-grep-mcp",  // → "ast-mcp"
      "env": {
        "AST_GREP_MCP_NAME": "ast-grep-mcp"  // → "ast-mcp"
      }
    }
  }
}
```

### 2.3 Continue Configuration
**File**: `/Users/Naor.Penso/code/ast-mcp/config/continue_config.json`
```json
{
  "name": "ast-grep-mcp",  // → "ast-mcp"
  "command": "ast-grep-mcp"  // → "ast-mcp"
}
```

## 3. Runtime Configuration Dependencies

### 3.1 Server Configuration Files
**Files**: 
- `/Users/Naor.Penso/code/ast-mcp/config/production.yaml`
- `/Users/Naor.Penso/code/ast-mcp/config/development.yaml`

```yaml
name: "ast-grep-mcp"  # → "ast-mcp"
logging:
  log_file_path: "/var/log/ast-grep-mcp/ast-grep-mcp.log"  # → "ast-mcp"
```

### 3.2 Application Code References
**File**: `/Users/Naor.Penso/code/ast-mcp/src/ast_grep_mcp/server.py`
```python
self.name = os.getenv("AST_GREP_MCP_NAME", "ast-grep-mcp")  # → "ast-mcp"
```

**File**: `/Users/Naor.Penso/code/ast-mcp/src/ast_grep_mcp/config.py`
```python
name: str = Field("ast-grep-mcp", description="Server name")  # → "ast-mcp"
self.config_file_name = "ast-grep-mcp.yaml"  # → "ast-mcp.yaml"
```

## 4. Documentation Cross-References

### 4.1 Documentation Files
**Files requiring updates**:
- `/Users/Naor.Penso/code/ast-mcp/docs/API.md`
- `/Users/Naor.Penso/code/ast-mcp/docs/TROUBLESHOOTING.md`
- `/Users/Naor.Penso/code/ast-mcp/docs/DEPLOYMENT.md`
- `/Users/Naor.Penso/code/ast-mcp/docs/CONFIGURATION.md`

**Impact**: 20+ references to "ast-grep-mcp" in command examples, configuration snippets, and troubleshooting guides.

### 4.2 README and Installation
**Files**: 
- `/Users/Naor.Penso/code/ast-mcp/README.md` (embedded in PKG-INFO)
- `/Users/Naor.Penso/code/ast-mcp/INSTALL.md`

**Impact**: Installation instructions, configuration examples, and usage patterns.

## 5. Build and Development Dependencies

### 5.1 Scripts and Utilities
**Files requiring updates**:
- `/Users/Naor.Penso/code/ast-mcp/scripts/config_manager.py`
- `/Users/Naor.Penso/code/ast-mcp/scripts/validate_*.py`

**Impact**: Development and validation scripts that reference the package name.

### 5.2 Test Configuration
**Files**: All test files import from `ast_grep_mcp` module
**Impact**: Module imports are internal and remain unchanged (ast_grep_mcp module name stays the same).

## 6. Dependency Classification

### 6.1 ATOMIC UPDATES (Must be done together)

#### Group A: Package Identity Chain
1. `pyproject.toml` - Package name and CLI entry point
2. All MCP configuration files (Claude Desktop, Cursor, Continue)
3. Runtime configuration files (production.yaml, development.yaml)
4. Application code defaults (server.py, config.py)

**Reason**: These form the core identity chain. If any are inconsistent, the system fails to start or be discovered.

#### Group B: Documentation Chain
1. All documentation files (docs/*.md)
2. README.md and INSTALL.md
3. Configuration examples and troubleshooting guides

**Reason**: These provide user guidance and must be consistent with the actual package behavior.

### 6.2 INDEPENDENT UPDATES (Can be done separately)

#### Group C: Development Tools
1. Script files (scripts/*.py)
2. Logging file names and paths
3. Schema references (schemas.py)

**Reason**: These are internal development tools and don't affect external users immediately.

## 7. Risk Assessment

### 7.1 HIGH RISK - System Failure
- **MCP Server Discovery**: If CLI command name doesn't match configuration
- **Installation Failure**: If PyPI package name changes but configurations don't
- **Runtime Errors**: If environment variables reference old names

### 7.2 MEDIUM RISK - User Confusion
- **Documentation Inconsistency**: Users follow outdated instructions
- **Configuration Drift**: Multiple configurations with different names

### 7.3 LOW RISK - Development Impact
- **Internal tooling**: Scripts and utilities can be updated incrementally
- **Log file names**: Non-critical for system operation

## 8. Recommended Update Strategy

### Phase 1: Core Package Identity (ATOMIC)
1. Update `pyproject.toml` (package name and CLI entry point)
2. Update all MCP configuration files simultaneously
3. Update runtime configuration files
4. Update application code defaults
5. Test entire chain end-to-end

### Phase 2: Documentation Consistency (BATCH)
1. Update all documentation files
2. Update README and installation guides
3. Update configuration examples
4. Verify all references are consistent

### Phase 3: Development Tools (INCREMENTAL)
1. Update scripts and utilities
2. Update logging configurations
3. Update schema references
4. Update any remaining internal references

## 9. Validation Points

### 9.1 Package Installation
```bash
pip install ast-mcp
ast-mcp --help  # Should work
```

### 9.2 MCP Server Discovery
```bash
# Claude Desktop should find the server
# Cursor should connect successfully
# Continue should load the server
```

### 9.3 Configuration Consistency
```bash
# All configuration files should reference "ast-mcp"
# No references to "ast-grep-mcp" should remain
```

## 10. Migration Checklist

- [ ] Update pyproject.toml package name and CLI entry point
- [ ] Update all MCP configuration files (3 files)
- [ ] Update runtime configuration files (2 files)
- [ ] Update application code defaults (2 files)
- [ ] Test package installation and CLI availability
- [ ] Test MCP server discovery in all clients
- [ ] Update documentation files (4+ files)
- [ ] Update README and installation guides
- [ ] Update scripts and utilities (4 files)
- [ ] Update logging and schema references
- [ ] Final validation of all references
- [ ] Update version control and CI/CD if needed

## Conclusion

The renaming from "ast-grep-mcp" to "ast-mcp" creates a significant dependency chain that spans package configuration, MCP server discovery, runtime configuration, and documentation. The most critical updates must be performed atomically to maintain system integrity, while documentation and development tools can be updated in subsequent phases.

The key risk is ensuring that the CLI command availability matches the MCP client configurations - any mismatch will result in complete system failure for end users.