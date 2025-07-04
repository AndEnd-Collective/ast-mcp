---
name: Bug Report
about: Create a report to help us improve the AST-Grep MCP Server
title: '[BUG] '
labels: ['bug', 'needs-triage']
assignees: ''

---

## 🐛 Bug Description

**Clear and concise description of the bug:**
<!-- A clear and concise description of what the bug is. -->

## 🔄 Steps to Reproduce

**Steps to reproduce the behavior:**
1. Install AST-Grep MCP with `...`
2. Configure with `...`
3. Run command `...`
4. See error

## ✅ Expected Behavior

**What you expected to happen:**
<!-- A clear and concise description of what you expected to happen. -->

## ❌ Actual Behavior

**What actually happened:**
<!-- A clear and concise description of what actually happened. -->

## 📋 Environment Information

**Please complete the following information:**
- OS: [e.g. macOS 14.0, Ubuntu 22.04, Windows 11]
- Python Version: [e.g. 3.11.5]
- AST-Grep MCP Version: [e.g. 1.0.0]
- AST-Grep Version: [e.g. 0.38.6]
- MCP Client: [e.g. Claude Desktop, Continue, Custom]

**Installation method:**
- [ ] PyPI (`pip install ast-grep-mcp`)
- [ ] Git (`pip install git+https://github.com/AndEnd-Org/ast-mcp.git`)
- [ ] Local development (`pip install -e .`)

## 📜 Error Logs

**Relevant error logs or output:**
```
Paste error logs here
```

**Debug output (if available):**
```bash
# Run with debug logging
AST_GREP_LOGGING__LOG_LEVEL=DEBUG python -m ast_grep_mcp.server
```

## 🧪 Test Case

**Minimal test case to reproduce the issue:**
```python
# Minimal Python code that reproduces the issue
```

**Test files (if relevant):**
```javascript
// Example code file that triggers the bug
```

## 🔧 Configuration

**MCP Server Configuration:**
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

**AST-Grep MCP Config (if using custom config):**
```yaml
# Custom configuration
```

## 🔍 Additional Context

**Screenshots:**
<!-- If applicable, add screenshots to help explain your problem. -->

**Related Issues:**
<!-- Link to related issues or discussions -->

**Workarounds:**
<!-- Any workarounds you've found -->

## 🧹 Impact Assessment

**Impact Level:**
- [ ] Critical (server won't start, major functionality broken)
- [ ] High (important feature not working)
- [ ] Medium (minor feature issue, workaround available)
- [ ] Low (cosmetic issue, nice to have)

**Affected Components:**
- [ ] MCP Server startup
- [ ] Tool registration
- [ ] AST-Grep search functionality
- [ ] Security/validation
- [ ] Performance
- [ ] Documentation
- [ ] Other: ___________

## ✅ Checklist

- [ ] I have searched for similar issues
- [ ] I have tested with the latest version
- [ ] I have provided all required information
- [ ] I have included relevant error logs
- [ ] I have tested the minimal reproduction case