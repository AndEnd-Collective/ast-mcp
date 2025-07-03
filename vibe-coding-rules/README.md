# 🎯 Vibe Coding Rules for AST-Grep MCP

Compact, ready-to-use rule files for AI coding assistants to effectively utilize AST-Grep MCP.

## 📁 Available Rules

| Assistant | File | Usage |
|-----------|------|-------|
| **Cursor** | `cursor/.cursorrules` | Copy to project root |
| **Claude Desktop** | `claude/system_prompt.txt` | Add to system prompt |
| **GitHub Copilot** | `copilot/instructions.md` | Reference in workspace |

## 🚀 Quick Setup

### Cursor
```bash
cp vibe-coding-rules/cursor/.cursorrules .cursorrules
```

### Claude Desktop  
Copy contents of `claude/system_prompt.txt` into your conversation or system prompt.

### GitHub Copilot
Reference `copilot/instructions.md` in your workspace or IDE settings.

## 🎯 Key Benefits

- **90% token reduction** vs traditional file reading
- **Semantic understanding** of code structure
- **Security-first** approach with built-in scans
- **Dependency mapping** before making changes

## 📋 Core Workflow

1. **DISCOVER**: `ast_grep_search` for patterns
2. **ANALYZE**: `call_graph_generate` for dependencies  
3. **VALIDATE**: `ast_grep_scan` for security/quality
4. **IMPLEMENT**: Make informed changes

All rules follow this efficient, safe workflow pattern.