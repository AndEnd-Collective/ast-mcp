# AST-MCP Rules Collection

This directory contains a comprehensive collection of AST-grep rules designed to enhance AI-assisted development workflows. The rules are organized into three main categories: generic patterns, language-specific patterns, and use-case-specific patterns.

## 📊 Overview

- **Total Rules**: 33 YAML rule files
- **Languages Covered**: 8 programming languages
- **Use Cases**: 12 specialized workflow scenarios
- **Focus Areas**: Code quality, security, AI-assisted development, and maintainability

## 🗂️ Directory Structure

```
rules/
├── generic/                    # Language-agnostic patterns
├── language-specific/          # Language-specific patterns
└── use-cases/                 # Workflow-specific patterns
```

## 📁 Rule Categories

### Generic Rules (5 rules)
Universal patterns that work across multiple programming languages:

- **`complexity-detection.yaml`**: Identifies complex code structures
- **`error-handling-patterns.yaml`**: Detects error handling approaches
- **`find-functions.yaml`**: Locates function definitions
- **`find-imports.yaml`**: Finds import/include statements
- **`find-variables.yaml`**: Identifies variable declarations

### Language-Specific Rules (18 rules)
Patterns tailored to specific programming languages:

#### C++ (2 rules)
- **`memory-management.yaml`**: Memory allocation, RAII, smart pointers
- **`modern-cpp.yaml`**: Modern C++ features (C++11/14/17/20)

#### C# (1 rule)
- **`dotnet-patterns.yaml`**: .NET patterns, LINQ, async/await

#### Go (1 rule)
- **`concurrency-patterns.yaml`**: Goroutines, channels, synchronization

#### Java (2 rules)
- **`exception-handling.yaml`**: Exception patterns, try-catch-finally
- **`oop-patterns.yaml`**: Object-oriented design patterns

#### JavaScript (3 rules)
- **`async-await-patterns.yaml`**: Asynchronous programming patterns
- **`react-patterns.yaml`**: React components and hooks
- **`typescript-patterns.yaml`**: TypeScript-specific patterns

#### Python (3 rules)
- **`async-patterns.yaml`**: Async/await, asyncio patterns
- **`django-patterns.yaml`**: Django web framework patterns
- **`security-patterns.yaml`**: Security best practices

#### Rust (1 rule)
- **`memory-safety.yaml`**: Memory safety, ownership, borrowing

### Use-Case Rules (10 rules)
Workflow-specific patterns for specialized development scenarios:

#### AI Coding Issues (5 rules)
Rules designed to address common problems with AI-generated code:

- **`hallucination-detection.yaml`**: Non-existent functions/APIs
- **`security-vulnerabilities.yaml`**: Common security flaws
- **`vibe-coding-antipatterns.yaml`**: Low-quality rapid coding patterns
- **`incomplete-implementation.yaml`**: Placeholder and stub code
- **`context-loss-patterns.yaml`**: Inconsistencies from context limits

#### LLM Assistance (4 rules)
Patterns for AI-assisted development workflows:

- **`analysis-boundaries.yaml`**: Code analysis scope definition
- **`context-switching.yaml`**: Context management patterns
- **`locker-mcp-integration.yaml`**: File state coordination
- **`progress-tracking.yaml`**: Development progress patterns

#### Refactoring (3 rules)
Code improvement and maintenance patterns:

- **`dead-code-detection.yaml`**: Unused code identification
- **`extract-method-candidates.yaml`**: Method extraction opportunities
- **`rename-safety-check.yaml`**: Safe renaming validation

#### Testing (3 rules)
Test quality and coverage patterns:

- **`test-coverage-analysis.yaml`**: Test coverage assessment
- **`test-data-coherency.yaml`**: Test data consistency
- **`test-structure-validation.yaml`**: Test organization patterns

## 🎯 Key Features

### AI-Assisted Development Focus
This collection is specifically designed to enhance AI-assisted development workflows:

- **Quality Assurance**: Catch common AI coding mistakes
- **Security**: Identify vulnerabilities in AI-generated code
- **Consistency**: Maintain code quality across AI-generated sections
- **Context Management**: Handle AI context limitations effectively

### Comprehensive Coverage
- **Multi-language support**: 8 major programming languages
- **Full development lifecycle**: From development to testing and refactoring
- **Real-world patterns**: Based on actual development challenges
- **Scalable organization**: Easy to extend and maintain

### Integration Ready
- **AST-grep compatible**: Uses standard AST-grep rule format
- **CI/CD friendly**: Suitable for automated pipelines
- **Editor integration**: Works with AST-grep editor plugins
- **Locker-MCP coordination**: Integrates with file state management

## 🚀 Usage Examples

### Basic Usage
```bash
# Scan for AI hallucinations
ast-grep scan --rule rules/use-cases/ai-coding-issues/hallucination-detection.yaml

# Check Python security patterns
ast-grep scan --rule rules/language-specific/python/security-patterns.yaml

# Find refactoring opportunities
ast-grep scan --rule rules/use-cases/refactoring/extract-method-candidates.yaml
```

### Advanced Usage
```bash
# Scan entire codebase with all rules
ast-grep scan --rule rules/ --path ./src/

# Language-specific analysis
ast-grep scan --rule rules/language-specific/javascript/ --path ./frontend/

# AI coding quality check
ast-grep scan --rule rules/use-cases/ai-coding-issues/ --path ./src/
```

### CI/CD Integration
```yaml
# GitHub Actions example
- name: AST-grep Analysis
  run: |
    ast-grep scan --rule rules/use-cases/ai-coding-issues/ --json > analysis.json
    ast-grep scan --rule rules/language-specific/python/security-patterns.yaml --json >> analysis.json
```

## 🔧 Configuration

### Environment Setup
```bash
# Install ast-grep
npm install -g @ast-grep/cli

# Clone rules
git clone <repository-url>
cd ast-mcp/rules
```

### Rule Customization
Each rule file includes:
- **Metadata**: Version, author, description
- **Pattern definitions**: AST-grep patterns
- **Severity levels**: Critical, high, medium, low
- **Examples**: Good and bad code samples
- **Fix suggestions**: Remediation guidance

## 🎨 Rule Development Guidelines

### Adding New Rules
1. **Choose appropriate category**: Generic, language-specific, or use-case
2. **Follow naming convention**: `kebab-case.yaml`
3. **Include comprehensive metadata**:
   ```yaml
   metadata:
     version: "1.0.0"
     author: "Your Name"
     description: "Clear description of what this rule detects"
     creation_date: "2025-07-06"
     last_edit_date: "2025-07-06"
   ```
4. **Provide examples**: Both problematic and corrected code
5. **Add severity and remediation guidance**

### Testing Rules
```bash
# Test rule on sample code
ast-grep scan --rule your-rule.yaml --path ./test-files/

# Validate rule syntax
ast-grep scan --rule your-rule.yaml --dry-run
```

## 🤝 Integration with Other Tools

### Locker-MCP Integration
The rules work seamlessly with Locker-MCP for file state management:

```bash
# Check file state before analysis
locker-mcp status ./src/critical-file.js

# Analyze if unlocked or confidence is sufficient
ast-grep scan --rule rules/use-cases/ai-coding-issues/ --path ./src/critical-file.js

# Update lock state after successful changes
locker-mcp lock ./src/critical-file.js "Analysis complete, refactoring done"
```

### Editor Integration
- **VSCode**: AST-grep extension with custom rules
- **Neovim**: AST-grep plugin with rule configuration
- **Sublime Text**: Custom build systems

### Development Workflow
1. **Pre-commit hooks**: Catch issues before commit
2. **CI/CD pipelines**: Automated quality checks
3. **Code review**: Enhanced review process
4. **Documentation**: Generated from rule analysis

## 📚 Documentation

Each rule category includes detailed documentation:
- **Generic Rules**: `generic/README.md`
- **Language-Specific**: Individual language documentation
- **Use Cases**: `use-cases/*/README.md`
- **AI Coding Issues**: `use-cases/ai-coding-issues/README.md`

## 🔄 Maintenance

### Regular Updates
- **Language evolution**: Update rules for new language features
- **Security patches**: Add new vulnerability patterns
- **AI model changes**: Adapt to new AI coding patterns
- **Community feedback**: Incorporate user suggestions

### Version Control
- **Semantic versioning**: Follow semver for rule updates
- **Changelog**: Document changes and additions
- **Compatibility**: Maintain backward compatibility where possible

## 🎯 Future Enhancements

### Planned Additions
- **More languages**: Kotlin, Swift, PHP, Ruby
- **Framework-specific**: Vue.js, Angular, Django REST
- **Cloud patterns**: AWS, Azure, GCP specific rules
- **Performance patterns**: Optimization opportunities

### Community Contributions
- **Rule suggestions**: Submit new patterns
- **Bug reports**: Report false positives/negatives
- **Documentation**: Improve examples and guides
- **Testing**: Add test cases and validation

---

*This rule collection is actively maintained and regularly updated to address evolving development patterns and AI-assisted coding challenges.*