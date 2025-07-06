# AI Coding Issues Detection Rules

This directory contains AST-grep rules specifically designed to detect and prevent common issues with AI-generated code. These rules address the most frequently reported problems with AI coding assistants and "vibe coding" practices.

## Overview

As AI coding assistants become more prevalent, new categories of code quality issues have emerged. This collection of rules helps identify:

- **Hallucinations**: Non-existent functions, libraries, or APIs
- **Security vulnerabilities**: Common security flaws in AI-generated code
- **Vibe coding anti-patterns**: Low-quality patterns that create technical debt
- **Incomplete implementations**: Placeholder code that needs completion
- **Context loss patterns**: Inconsistencies from AI context window limitations

## Rule Categories

### 1. Hallucination Detection (`hallucination-detection.yaml`)

**Purpose**: Identifies AI-generated code that references non-existent functions, libraries, or APIs.

**Common Issues Detected**:
- React hooks like `useMetadata()` that don't exist
- Fictional library methods like `requests.auto_get()`
- Non-existent APIs with "magic" or "auto" prefixes
- References to deprecated or removed functionality

**Usage Example**:
```bash
ast-grep scan --rule rules/use-cases/ai-coding-issues/hallucination-detection.yaml --path ./src/
```

### 2. Security Vulnerabilities (`security-vulnerabilities.yaml`)

**Purpose**: Detects security flaws commonly introduced by AI coding assistants.

**Vulnerabilities Detected**:
- SQL injection through string concatenation
- XSS via unsafe DOM manipulation (`innerHTML`)
- Command injection in system calls
- Hardcoded credentials and API keys
- Weak cryptographic algorithms (MD5, SHA1)
- Insecure random number generation

**Critical Patterns**:
- `"SELECT * FROM users WHERE id = '" + userId + "'"`
- `element.innerHTML = userInput`
- `password = "password123"`
- `hashlib.md5(data)`

### 3. Vibe Coding Anti-patterns (`vibe-coding-antipatterns.yaml`)

**Purpose**: Identifies harmful patterns from rapid, unvetted AI code generation.

**Anti-patterns Detected**:
- Generic error handling that hides issues
- Hardcoded values that should be configurable
- Inconsistent naming patterns
- Missing null safety checks
- Copy-paste code without adaptation

**Example Issues**:
```javascript
// Generic error handling
try {
  // code
} catch (error) {
  console.log(error); // ❌ Hides real issues
}

// Hardcoded values
setTimeout(callback, 1000); // ❌ Magic number
```

### 4. Incomplete Implementation (`incomplete-implementation.yaml`)

**Purpose**: Finds placeholder code and incomplete implementations.

**Patterns Detected**:
- TODO comments indicating missing functionality
- Placeholder return values (`return null; // TODO`)
- Empty function bodies with implementation notes
- Generic test placeholders
- Configuration stubs

**Common Indicators**:
- `// TODO: Implement this`
- `throw new Error('Not implemented')`
- `return {}; // Empty object`
- `pass  # TODO: Add logic`

### 5. Context Loss Patterns (`context-loss-patterns.yaml`)

**Purpose**: Identifies inconsistencies caused by AI context window limitations.

**Context Loss Indicators**:
- Mixed naming conventions in same file
- Duplicate function definitions
- Inconsistent error handling patterns
- Architectural drift within modules
- Comments questioning previous decisions

**Example Problems**:
```javascript
// Inconsistent naming within same file
function getUserData(id) { /* ... */ }
function fetch_user_profile(userId) { /* ... */ } // Different pattern
const API_ENDPOINT = "..."; // Different style
```

## Integration with Locker-MCP

The `locker-mcp-integration.yaml` rule provides patterns for coordinating AST-MCP analysis with Locker-MCP file state management:

### Workflow Integration
1. **AST Analysis**: Use AST-MCP to understand file structure and dependencies
2. **Confidence Assessment**: Evaluate edit confidence based on AST analysis
3. **Lock State Check**: Check Locker-MCP state before editing
4. **Threshold Evaluation**: For locked-context files, assess confidence against threshold
5. **Safe Editing**: Proceed only if confidence meets requirements
6. **State Update**: Update Locker-MCP after successful changes

### Confidence Factors
- **High (80%+)**: Isolated functions, private methods, comprehensive tests
- **Medium (50-80%)**: Limited dependencies, partial test coverage
- **Low (<50%)**: Complex dependencies, core functionality, limited tests

## Usage Guidelines

### For Developers
1. **Run before commits**: Include these rules in pre-commit hooks
2. **Code review**: Use as checklist during AI-assisted development
3. **Learning tool**: Understand common AI pitfalls

### For Teams
1. **CI Integration**: Add to continuous integration pipelines
2. **Code standards**: Incorporate into coding guidelines
3. **Training**: Use examples for developer education

### Command Examples

```bash
# Check for AI hallucinations
ast-grep scan --rule rules/use-cases/ai-coding-issues/hallucination-detection.yaml

# Security audit of AI-generated code
ast-grep scan --rule rules/use-cases/ai-coding-issues/security-vulnerabilities.yaml

# Find incomplete implementations
ast-grep scan --rule rules/use-cases/ai-coding-issues/incomplete-implementation.yaml

# Check for vibe coding issues
ast-grep scan --rule rules/use-cases/ai-coding-issues/vibe-coding-antipatterns.yaml

# Detect context loss patterns
ast-grep scan --rule rules/use-cases/ai-coding-issues/context-loss-patterns.yaml

# Run all AI coding issue checks
ast-grep scan --rule rules/use-cases/ai-coding-issues/ --path ./src/
```

## Best Practices

### Prevention
- **Review AI output**: Never accept AI-generated code without review
- **Test thoroughly**: All AI-generated code needs comprehensive testing
- **Security audit**: Pay special attention to security implications
- **Context management**: Keep AI context focused and relevant

### Remediation
- **Immediate fixes**: Address critical security issues first
- **Incremental improvement**: Fix anti-patterns during regular development
- **Documentation**: Document architectural decisions to prevent context loss
- **Training**: Educate team on common AI coding pitfalls

### Integration with Development Workflow
- **Pre-commit hooks**: Catch issues before they enter the repository
- **IDE integration**: Real-time feedback during development
- **Code review**: Include as standard review checklist
- **Continuous monitoring**: Regular scans of codebase for new issues

## Contributing

When adding new rules for AI coding issues:

1. **Research**: Document the problem with real-world examples
2. **Pattern identification**: Create precise AST-grep patterns
3. **Severity assessment**: Classify issues appropriately
4. **Remediation guidance**: Provide clear fix instructions
5. **Examples**: Include both problematic and corrected code
6. **Testing**: Verify rules catch intended patterns without false positives

## Related Resources

- [AST-grep Documentation](https://ast-grep.github.io/)
- [Locker-MCP Integration Guide](../llm-assistance/locker-mcp-integration.yaml)
- [Security Best Practices](../../security/)
- [Code Quality Guidelines](../../refactoring/)

---

*These rules are based on research into common AI coding assistant issues as of 2025. Patterns may evolve as AI models improve and new issues emerge.*