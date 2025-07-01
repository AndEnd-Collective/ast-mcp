# AST-Grep MCP Server Troubleshooting Guide

This guide helps diagnose and resolve common issues with the AST-Grep MCP Server.

## Table of Contents
- [Quick Diagnostics](#quick-diagnostics)
- [Installation Issues](#installation-issues)
- [Configuration Problems](#configuration-problems)
- [Runtime Errors](#runtime-errors)
- [Performance Issues](#performance-issues)
- [MCP Integration Issues](#mcp-integration-issues)
- [Security and Rate Limiting](#security-and-rate-limiting)
- [Log Analysis](#log-analysis)
- [Common Error Messages](#common-error-messages)

## Quick Diagnostics

### Health Check
Start troubleshooting with basic health checks:

```bash
# Check if ast-grep binary is available
which ast-grep
ast-grep --version

# Check Python package installation
python -c "import ast_grep_mcp; print('Package installed successfully')"

# Validate configuration
python scripts/config_manager.py validate

# System health check
python scripts/config_manager.py health

# Test server startup (dry run)
ast-grep-mcp --config config.yaml --dry-run
```

### Environment Check
```bash
# Check Python version
python --version  # Should be 3.8+

# Check installed packages
pip list | grep -E "(pydantic|yaml|cryptography)"

# Check environment variables
env | grep AST_GREP
```

## Installation Issues

### Issue: ast-grep Binary Not Found

**Symptoms:**
- Error: "ast-grep binary not found"
- Command `which ast-grep` returns nothing

**Solutions:**

1. **Install ast-grep via Cargo:**
   ```bash
   cargo install ast-grep
   # Add ~/.cargo/bin to PATH if not already added
   echo 'export PATH="$HOME/.cargo/bin:$PATH"' >> ~/.bashrc
   source ~/.bashrc
   ```

2. **Install via npm:**
   ```bash
   npm install -g @ast-grep/cli
   ```

3. **Install via Homebrew (macOS):**
   ```bash
   brew install ast-grep
   ```

4. **Manual installation:**
   ```bash
   # Download latest release
   curl -L https://github.com/ast-grep/ast-grep/releases/latest/download/ast-grep-x86_64-unknown-linux-gnu.tar.gz | tar -xz
   sudo mv ast-grep /usr/local/bin/
   ```

5. **Set custom path:**
   ```bash
   export AST_GREP_PATH="/custom/path/to/ast-grep"
   # Or in configuration file:
   ast_grep:
     ast_grep_path: "/custom/path/to/ast-grep"
   ```

### Issue: Python Package Installation Fails

**Symptoms:**
- `pip install` fails with dependency errors
- Import errors for `ast_grep_mcp`

**Solutions:**

1. **Update pip and setuptools:**
   ```bash
   pip install --upgrade pip setuptools wheel
   ```

2. **Install in virtual environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -e .
   ```

3. **Install dependencies manually:**
   ```bash
   pip install pydantic>=2.0 typing-extensions pyyaml
   pip install -e .
   ```

4. **Check Python version compatibility:**
   ```bash
   python --version  # Must be 3.8 or higher
   ```

### Issue: Missing System Dependencies

**Symptoms:**
- Cryptography installation fails
- Binary compilation errors

**Solutions:**

1. **Install system dependencies (Ubuntu/Debian):**
   ```bash
   sudo apt-get update
   sudo apt-get install build-essential libssl-dev libffi-dev python3-dev
   ```

2. **Install system dependencies (CentOS/RHEL):**
   ```bash
   sudo yum install gcc openssl-devel libffi-devel python3-devel
   ```

3. **Install system dependencies (macOS):**
   ```bash
   xcode-select --install
   brew install openssl libffi
   ```

## Configuration Problems

### Issue: Configuration Validation Fails

**Symptoms:**
- Server won't start with configuration errors
- "Configuration validation failed" messages

**Diagnosis:**
```bash
# Validate configuration with detailed output
python scripts/config_manager.py validate --config config.yaml --verbose

# Check configuration syntax
python -c "import yaml; yaml.safe_load(open('config.yaml'))"
```

**Common Problems:**

1. **Invalid YAML syntax:**
   ```bash
   # Check for syntax errors
   python -c "import yaml; print(yaml.safe_load(open('config.yaml')))"
   ```

2. **Wrong data types:**
   ```yaml
   # ❌ Wrong
   debug: "true"
   rate_limit_requests: "100"
   
   # ✅ Correct
   debug: true
   rate_limit_requests: 100
   ```

3. **Missing required fields:**
   ```yaml
   # ❌ Missing ast_grep_path
   ast_grep:
     default_timeout: 30
   
   # ✅ Complete
   ast_grep:
     ast_grep_path: "/usr/local/bin/ast-grep"
     default_timeout: 30
   ```

### Issue: Environment Variable Problems

**Symptoms:**
- Configuration not loading from environment
- Type conversion errors

**Solutions:**

1. **Check environment variable format:**
   ```bash
   # ❌ Wrong format
   export AST_GREP_SECURITY_ENABLE_SECURITY=true
   
   # ✅ Correct format (double underscore)
   export AST_GREP_SECURITY__ENABLE_SECURITY=true
   ```

2. **Verify data types:**
   ```bash
   # Boolean values
   export AST_GREP_MCP_DEBUG=true
   export AST_GREP_MCP_DEBUG=false
   
   # Numeric values
   export AST_GREP_SECURITY__RATE_LIMIT_REQUESTS=100
   
   # Arrays (JSON format)
   export AST_GREP_SECURITY__ALLOWED_PATHS='["/workspace", "/home"]'
   ```

3. **Debug environment variable parsing:**
   ```bash
   python scripts/config_manager.py debug-env
   ```

### Issue: Configuration Migration Problems

**Symptoms:**
- Migration from legacy configuration fails
- Settings not properly transferred

**Solutions:**

1. **Run migration with backup:**
   ```bash
   # Backup current configuration
   cp .env .env.backup
   
   # Run migration
   python scripts/config_manager.py migrate --output migrated-config.yaml
   
   # Validate migration
   python scripts/config_manager.py validate --config migrated-config.yaml
   ```

2. **Manual migration mapping:**
   ```bash
   # Old -> New mappings
   LOG_LEVEL -> AST_GREP_LOGGING__LOG_LEVEL
   MAX_FILE_SIZE -> AST_GREP_SECURITY__MAX_INPUT_SIZE
   EXECUTION_TIMEOUT -> AST_GREP_AST_GREP__DEFAULT_TIMEOUT
   ```

## Runtime Errors

### Issue: Server Startup Failures

**Symptoms:**
- Server exits immediately after startup
- "Failed to initialize server" messages

**Diagnosis:**
```bash
# Check logs for startup errors
tail -f /var/log/ast-grep-mcp.log

# Run with debug logging
export AST_GREP_LOGGING__LOG_LEVEL=DEBUG
ast-grep-mcp --config config.yaml

# Test with minimal configuration
ast-grep-mcp --debug
```

**Common Causes:**

1. **Port already in use:**
   ```bash
   # Check what's using the port
   lsof -i :8000
   
   # Use different port
   export AST_GREP_MCP_PORT=8001
   ```

2. **Permission errors:**
   ```bash
   # Check log file permissions
   ls -la /var/log/ast-grep-mcp.log
   
   # Create log directory with proper permissions
   sudo mkdir -p /var/log/ast-grep-mcp
   sudo chown $(whoami) /var/log/ast-grep-mcp
   ```

3. **Missing dependencies:**
   ```bash
   # Verify all Python dependencies
   pip check
   
   # Reinstall if needed
   pip install -e . --force-reinstall
   ```

### Issue: MCP Tool Execution Failures

**Symptoms:**
- Tools return errors or timeout
- "Tool execution failed" messages

**Diagnosis:**
```bash
# Test ast-grep directly
ast-grep --help

# Test with simple pattern
ast-grep -p "function" --lang javascript src/

# Check server logs during tool execution
tail -f /var/log/ast-grep-mcp.log
```

**Solutions:**

1. **Check pattern syntax:**
   ```bash
   # Test pattern manually
   ast-grep -p "function $NAME($ARGS)" --lang javascript src/
   ```

2. **Verify file paths:**
   ```bash
   # Check if paths exist and are accessible
   ls -la src/
   find src/ -name "*.js" | head -5
   ```

3. **Increase timeouts:**
   ```yaml
   ast_grep:
     default_timeout: 60  # Increase from 30
     max_timeout: 120
   ```

### Issue: Memory or Performance Problems

**Symptoms:**
- High memory usage
- Slow response times
- Out of memory errors

**Solutions:**

1. **Adjust resource limits:**
   ```yaml
   performance:
     max_concurrent_requests: 5  # Reduce from 20
     max_execution_time: 30
     memory_warning_threshold: 70.0
   
   security:
     max_input_size: 524288  # 512KB instead of 1MB
   ```

2. **Enable performance monitoring:**
   ```yaml
   performance:
     enable_performance: true
   logging:
     enable_performance_logging: true
   ```

3. **Disable caching if needed:**
   ```yaml
   performance:
     enable_caching: false
   ```

## Performance Issues

### Issue: Slow Search Performance

**Symptoms:**
- Searches take too long to complete
- Timeouts on large codebases

**Solutions:**

1. **Optimize search patterns:**
   ```bash
   # ❌ Too broad
   pattern: "$_"
   
   # ✅ More specific
   pattern: "function $NAME($ARGS) { $BODY }"
   ```

2. **Limit search paths:**
   ```bash
   # ❌ Search entire repository
   paths: ["."]
   
   # ✅ Specific directories
   paths: ["src/", "lib/"]
   ```

3. **Adjust result limits:**
   ```bash
   # Set reasonable limits
   limit: 100  # Instead of 1000
   ```

4. **Enable caching:**
   ```yaml
   performance:
     enable_caching: true
     cache_ttl: 600
   ```

### Issue: High Memory Usage

**Symptoms:**
- Server consumes excessive memory
- System becomes unresponsive

**Solutions:**

1. **Monitor memory usage:**
   ```bash
   # Check current memory usage
   ps aux | grep ast-grep-mcp
   
   # Monitor with top
   top -p $(pgrep ast-grep-mcp)
   ```

2. **Adjust memory settings:**
   ```yaml
   performance:
     memory_warning_threshold: 70.0
     memory_critical_threshold: 90.0
   
   security:
     max_input_size: 262144  # 256KB
     max_output_size: 2621440  # 2.5MB
   ```

3. **Limit concurrent operations:**
   ```yaml
   performance:
     max_concurrent_requests: 5
   ```

## MCP Integration Issues

### Issue: MCP Client Connection Problems

**Symptoms:**
- Client can't connect to server
- "MCP server not responding" messages

**Diagnosis:**
```bash
# Test MCP server directly
echo '{"jsonrpc": "2.0", "method": "initialize", "id": 1}' | ast-grep-mcp

# Check if server is running
ps aux | grep ast-grep-mcp

# Test with curl if HTTP transport
curl -X POST http://localhost:8000/mcp -d '{"jsonrpc": "2.0", "method": "ping", "id": 1}'
```

**Solutions:**

1. **Check transport configuration:**
   ```json
   {
     "mcpServers": {
       "ast-grep": {
         "command": "ast-grep-mcp",
         "args": ["--config", "config.yaml"],
         "env": {}
       }
     }
   }
   ```

2. **Verify server startup:**
   ```bash
   # Test server startup
   ast-grep-mcp --config config.yaml --test-mode
   ```

3. **Check logs for connection errors:**
   ```bash
   grep -i "connection\|transport" /var/log/ast-grep-mcp.log
   ```

### Issue: Tool Registration Problems

**Symptoms:**
- MCP tools not available in client
- "Unknown tool" errors

**Diagnosis:**
```bash
# Check tool registration
python -c "
from src.ast_grep_mcp.tools import get_available_tools
print([tool.name for tool in get_available_tools()])
"

# Test tools loading
python -c "
from src.ast_grep_mcp.server import ASTGrepMCPServer
server = ASTGrepMCPServer()
print('Tools loaded:', len(server.tools))
"
```

**Solutions:**

1. **Verify tool imports:**
   ```python
   # Check if all tools import correctly
   from src.ast_grep_mcp.tools import (
       ast_grep_search,
       ast_grep_scan,
       ast_grep_run,
       call_graph_generate,
       detect_functions,
       detect_calls
   )
   ```

2. **Check server initialization:**
   ```bash
   # Run with debug to see tool registration
   AST_GREP_LOGGING__LOG_LEVEL=DEBUG ast-grep-mcp
   ```

## Security and Rate Limiting

### Issue: Rate Limiting Too Restrictive

**Symptoms:**
- "Rate limit exceeded" errors
- Legitimate requests being blocked

**Solutions:**

1. **Adjust rate limits:**
   ```yaml
   security:
     rate_limit_requests: 200  # Increase from 100
     rate_limit_window: 60
   ```

2. **Disable rate limiting for testing:**
   ```yaml
   security:
     enable_rate_limiting: false
   ```

3. **Monitor rate limit usage:**
   ```bash
   grep -i "rate.limit" /var/log/ast-grep-mcp.log
   ```

### Issue: Security Features Blocking Valid Requests

**Symptoms:**
- Path traversal errors for valid paths
- Input validation rejecting valid patterns

**Solutions:**

1. **Configure allowed paths:**
   ```yaml
   security:
     allowed_paths: ["/workspace", "/home/user/projects"]
     blocked_paths: ["/etc", "/proc"]
   ```

2. **Adjust input limits:**
   ```yaml
   security:
     max_input_size: 2097152  # 2MB
     max_output_size: 20971520  # 20MB
   ```

3. **Temporarily disable for debugging:**
   ```yaml
   security:
     enable_security: false  # Only for debugging!
   ```

## Log Analysis

### Finding Relevant Log Entries

```bash
# Recent errors
grep -i error /var/log/ast-grep-mcp.log | tail -20

# Performance issues
grep -i "performance\|slow\|timeout" /var/log/ast-grep-mcp.log

# Security events
grep -i "security\|rate.limit\|blocked" /var/log/ast-grep-mcp.log

# Configuration issues
grep -i "config\|validation" /var/log/ast-grep-mcp.log

# Tool execution logs
grep -i "tool\|ast.grep" /var/log/ast-grep-mcp.log
```

### Log Levels and Debugging

```bash
# Enable debug logging
export AST_GREP_LOGGING__LOG_LEVEL=DEBUG

# Enable performance logging
export AST_GREP_LOGGING__ENABLE_PERFORMANCE_LOGGING=true

# Enable security audit logging
export AST_GREP_LOGGING__ENABLE_SECURITY_LOGGING=true
```

### Log File Rotation Issues

```bash
# Check log file size
ls -lh /var/log/ast-grep-mcp.log

# Configure rotation
logging:
  enable_log_rotation: true
  log_file_max_size: 10485760  # 10MB
  log_file_backup_count: 5
```

## Common Error Messages

### "Configuration validation failed"
**Cause:** Invalid configuration syntax or values
**Solution:** Run `python scripts/config_manager.py validate --config config.yaml --verbose`

### "ast-grep binary not found"
**Cause:** ast-grep not installed or not in PATH
**Solution:** Install ast-grep or set `AST_GREP_PATH` environment variable

### "Pattern syntax error"
**Cause:** Invalid AST pattern syntax
**Solution:** Check pattern syntax against AST-Grep documentation

### "Rate limit exceeded"
**Cause:** Too many requests in time window
**Solution:** Increase rate limits or reduce request frequency

### "File path not allowed"
**Cause:** Path traversal protection blocking access
**Solution:** Add path to `allowed_paths` in security configuration

### "Tool execution timeout"
**Cause:** ast-grep operation taking too long
**Solution:** Increase timeout or optimize search pattern

### "Memory limit exceeded"
**Cause:** Operation consuming too much memory
**Solution:** Reduce concurrent requests or increase memory limits

### "Invalid language specified"
**Cause:** Unsupported programming language
**Solution:** Check supported languages with `ast-grep://languages` resource

## Advanced Debugging

### Enable Detailed Logging
```yaml
logging:
  log_level: "DEBUG"
  enable_performance_logging: true
  enable_security_logging: true
  enable_audit_logging: true
```

### Profile Performance
```bash
# Run with profiling
python -m cProfile -o profile.out scripts/ast_grep_mcp.py

# Analyze profile
python -c "import pstats; pstats.Stats('profile.out').sort_stats('cumulative').print_stats(20)"
```

### Test Individual Components
```bash
# Test configuration loading
python -c "from src.ast_grep_mcp.config import load_configuration; print(load_configuration())"

# Test ast-grep integration
python -c "from src.ast_grep_mcp.utils import test_ast_grep_binary; test_ast_grep_binary()"

# Test MCP tools
python -c "from src.ast_grep_mcp.tools import ast_grep_search; print(ast_grep_search)"
```

### Collect Diagnostic Information
```bash
#!/bin/bash
# Create diagnostic report
echo "=== AST-Grep MCP Diagnostics ===" > diagnostics.txt
echo "Date: $(date)" >> diagnostics.txt
echo "" >> diagnostics.txt

echo "=== System Information ===" >> diagnostics.txt
uname -a >> diagnostics.txt
python --version >> diagnostics.txt
which ast-grep >> diagnostics.txt
ast-grep --version >> diagnostics.txt
echo "" >> diagnostics.txt

echo "=== Configuration ===" >> diagnostics.txt
python scripts/config_manager.py show >> diagnostics.txt
echo "" >> diagnostics.txt

echo "=== Recent Logs ===" >> diagnostics.txt
tail -50 /var/log/ast-grep-mcp.log >> diagnostics.txt
```

---

## Getting Help

If troubleshooting doesn't resolve your issue:

1. **Check the logs** with debug level enabled
2. **Create a minimal reproduction case**
3. **Collect diagnostic information** using the script above
4. **Open an issue** on GitHub with:
   - System information
   - Configuration files (redacted)
   - Error messages and logs
   - Steps to reproduce

For immediate help:
- **GitHub Issues**: https://github.com/your-org/ast-grep-mcp/issues
- **Documentation**: https://your-docs-site.com
- **Community Forum**: https://your-community-forum.com

---

*This troubleshooting guide is continuously updated based on common issues reported by users.* 