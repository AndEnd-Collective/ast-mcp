# Contributing to AST-MCP

Thank you for your interest in contributing to AST-MCP! This guide will help you get started.

## Prerequisites

- Python 3.12 or higher
- ast-grep CLI (`pip install ast-grep-cli`)
- Git

## Development Setup

```bash
# Clone the repository
git clone https://github.com/AndEnd-Collective/ast-mcp.git
cd ast-mcp

# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install in development mode with all dependencies
pip install -e ".[dev]"
```

## Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run unit tests only
pytest tests/ -m "not integration" -v

# Run integration tests (requires ast-grep binary)
pytest tests/ -m integration -v

# Run with coverage report
pytest tests/ --cov=src --cov-report=html
```

## Code Style

We use the following tools to maintain code quality:

- **black** (line-length 88): Code formatting
- **isort** (profile=black): Import sorting
- **flake8**: Linting
- **mypy** (strict): Type checking

```bash
# Format code
black src/ tests/
isort src/ tests/

# Lint
flake8 src/ tests/
mypy src/
```

## Adding AST-grep Rules

Rules are organized in the `rules/` directory:

```
rules/
  generic/              # Language-agnostic patterns
  language-specific/    # Per-language patterns (python/, javascript/, etc.)
  use-cases/           # Workflow-specific patterns (refactoring/, testing/, etc.)
```

### Rule Format

Each rule is a YAML file with metadata:

```yaml
metadata:
  version: "1.0.0"
  author: "Your Name"
  description: "What this rule detects"
  creation_date: "2026-03-07"
  last_edit_date: "2026-03-07"

rules:
  - id: rule-name
    language: python
    severity: warning
    message: "Description of the issue"
    pattern: |
      # AST-grep pattern here
```

### Testing Rules

```bash
# Test a rule against sample code
ast-grep scan --rule rules/your-rule.yaml --path ./test-files/

# Validate rule syntax
ast-grep scan --rule rules/your-rule.yaml --dry-run
```

## Pull Request Process

1. Create a feature branch from `main`
2. Make your changes with tests
3. Ensure all tests pass: `pytest tests/ -v`
4. Ensure code passes linting: `black --check src/ tests/ && isort --check src/ tests/`
5. Submit a PR using the pull request template
6. One approval is required for merge

## Reporting Issues

Use the issue templates provided:

- **Bug reports**: Include steps to reproduce, expected vs actual behavior
- **Feature requests**: Describe the use case and proposed solution

## Questions?

Open a discussion on GitHub or reach out at contact@andend.org.
