# AST-Grep MCP Enhancement for GitHub Copilot

Use AST-Grep MCP for semantic code analysis to enhance suggestions.

## Quick Reference:
```javascript
// Find patterns: ast_grep_search
{"pattern": "function $NAME($ARGS) { $BODY }", "language": "javascript", "paths": ["src/"]}

// Map dependencies: call_graph_generate  
{"paths": ["src/"], "max_depth": 2}

// Security scan: ast_grep_scan
{"rule_path": ".reporepo/ast/rules/", "severity": "warning"}
```

## Patterns:
- React: `const [$STATE, $SET] = useState($INIT)`
- API: `fetch($URL, $OPTIONS)`
- Auth: `if (!req.user) { $BODY }`
- Classes: `class $NAME { $BODY }`

## Workflow:
1. Search patterns with ast_grep_search
2. Analyze dependencies with call_graph_generate
3. Validate with ast_grep_scan
4. Suggest improvements based on findings

Use semantic queries instead of reading files. Target specific paths and set reasonable limits for efficiency.