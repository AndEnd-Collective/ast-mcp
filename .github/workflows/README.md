# GitHub Actions Workflows

This directory contains comprehensive CI/CD workflows that ensure the AST-Grep MCP server is foundationally correct, fully compliant with MCP specifications, and production-ready.

## Workflows Overview

### 1. `test.yml` - MCP Validation and Testing

**Primary Purpose**: Comprehensive validation of MCP compliance and foundational correctness

**Triggers**:
- Push to `main`, `develop`, or `feature/*` branches
- Pull requests to `main` or `develop`
- Manual workflow dispatch with optional performance testing

**Jobs**:

#### Foundation Check
- Verifies basic environment setup and dependencies
- Installs ast-grep binary and Python dependencies
- Validates package installation
- **Exit Criteria**: Package imports successfully and ast-grep is functional

#### MCP Protocol Compliance
- **Protocol Message Validation**: Tests JSON-RPC 2.0 compliance and MCP message formats
- **Client-Server Integration**: Validates complete MCP handshake and communication
- **Schema Compliance**: Ensures tool/resource schemas meet MCP specifications
- **Structured Output**: Validates Pydantic models and JSON serialization
- **Exit Criteria**: All MCP core protocol tests pass (required for PR approval)

#### Transport Layer Validation
- Tests stdio transport reliability and error handling
- Validates message framing, ordering, and large payload handling
- Tests connection lifecycle management
- **Exit Criteria**: Transport layer functions correctly for real-world usage

#### AST-Grep Functionality Tests
- **Search Functionality**: Tests AST pattern searching across languages
- **Scan Functionality**: Tests rule-based code scanning
- **Tools Registration**: Validates MCP tool registration and schemas
- **Resource Management**: Tests MCP resource listing and reading
- **Exit Criteria**: All core AST-Grep features work through MCP interface

#### Performance & Load Tests *(Optional)*
- Tests concurrent request handling and memory management
- Validates performance under sustained load
- Tests large payload processing
- **Exit Criteria**: Server remains stable and responsive under load
- **Note**: Can be disabled for faster CI via workflow input

#### Comprehensive MCP Validation
- Runs the complete MCP validation suite (`run_mcp_validation_tests.py`)
- Generates detailed compliance metrics and reports
- **Critical Thresholds**:
  - Protocol/Integration modules: Must achieve ≥85% success rate
  - Other modules: Target ≥90% success rate
- **Exit Criteria**: All critical compliance thresholds met

#### Python Compatibility
- Tests across Python 3.10, 3.11, and 3.12
- Validates core MCP functionality on each version
- **Exit Criteria**: Basic MCP validation passes on all Python versions

#### Final Status & Compliance Report
- Aggregates all test results
- Generates comprehensive validation report
- **Exit Criteria**: All critical jobs must pass for overall success

### 2. `security.yml` - Security Scanning

**Purpose**: Automated security vulnerability scanning and code quality checks

**Key Features**:
- Dependency vulnerability scanning
- Static code analysis
- Secret detection
- License compliance checking

### 3. `release.yml` - Release Automation

**Purpose**: Automated package building, testing, and publishing for releases

**Triggers**:
- Git tags matching version patterns
- Manual release workflow dispatch

### 4. `manual-test.yml` - Manual Testing Utilities

**Purpose**: On-demand testing and validation for development workflows

## MCP Compliance Validation

### Compliance Targets

The CI system enforces strict compliance thresholds:

1. **Critical Modules (≥85% required)**:
   - Protocol message validation
   - Client-server integration
   - Transport layer functionality

2. **Standard Modules (≥90% target)**:
   - Schema compliance
   - Structured output validation
   - Performance metrics

3. **Foundational Requirements**:
   - All AST-Grep functionality must work through MCP
   - Cross-platform Python compatibility (3.10-3.12)
   - Complete MCP handshake and communication

### Validation Reports

Each workflow run generates:
- **Validation Results JSON**: Detailed test metrics and compliance scores
- **Test Artifacts**: Logs and debugging information for failed tests
- **Final Compliance Report**: Summary of foundational correctness

## Development Workflow

### Pre-PR Requirements

Before creating a PR, ensure:
1. All MCP validation tests pass locally
2. Core functionality tests succeed
3. No regressions in existing test suites

### PR Approval Criteria

For PR approval, the following must pass:
- ✅ Foundation check
- ✅ MCP protocol compliance (all tests)
- ✅ Transport layer validation
- ✅ AST-Grep functionality tests
- ✅ Comprehensive validation (≥85% critical, ≥90% standard)
- ✅ Python compatibility tests

### Performance Testing

Performance tests are included by default but can be disabled for faster CI:
- **Automatic**: Runs on all pushes to main/develop
- **Optional**: Can be disabled via workflow dispatch input
- **Timeout**: 10-minute limit to prevent CI delays

## Quality Assurance

### Test Categories

1. **Unit Tests**: Individual component validation
2. **Integration Tests**: MCP protocol compliance
3. **Functional Tests**: End-to-end AST-Grep operations
4. **Performance Tests**: Load and stress testing
5. **Compatibility Tests**: Multi-version Python support

### Coverage Requirements

- **MCP Protocol**: 100% of MCP specification features
- **AST-Grep Integration**: All tools and resources
- **Error Handling**: Comprehensive edge case coverage
- **Security**: Input validation and safe operation

### Monitoring

Each workflow provides:
- Real-time test progress with emojis and clear status
- Detailed error messages for debugging
- Artifact collection for failed tests
- Comprehensive final reports

This testing framework ensures that every change maintains the foundational correctness and production readiness of the AST-Grep MCP server.