# GitHub Actions and CI/CD Documentation

This directory contains the GitHub Actions workflows, templates, and configuration for the AST-Grep MCP Server project.

## 📁 Directory Structure

```
.github/
├── workflows/
│   ├── test.yml              # Main test and validation workflow
│   ├── security.yml          # Security scanning workflow
│   ├── manual-test.yml       # Manual test execution workflow
│   └── release.yml           # Release and distribution workflow
├── ISSUE_TEMPLATE/
│   ├── bug_report.md         # Bug report template
│   └── feature_request.md    # Feature request template
├── pull_request_template.md  # Pull request template
├── CODEOWNERS               # Code ownership definitions
├── branch-protection-rules.md # Branch protection configuration
└── README.md               # This file
```

## 🚀 Workflows

### 1. Test and Validation (`test.yml`)

**Triggers:**
- Push to `develop` and `feature/*` branches
- Pull requests to `main` and `develop`
- Manual dispatch

**Features:**
- **Matrix Testing**: Python 3.8-3.12 across Ubuntu
- **Comprehensive Testing**: Validation, integration, protocol compliance
- **Performance Benchmarking**: On pull requests
- **Build Validation**: Package creation and installation testing
- **Coverage Reporting**: Code coverage with Codecov integration

**Jobs:**
1. `test` - Core functionality testing across Python versions
2. `integration-test` - End-to-end MCP server testing
3. `build-test` - Package build and distribution validation
4. `performance-test` - Performance regression detection
5. `status-check` - Overall results aggregation

### 2. Security Scanning (`security.yml`)

**Triggers:**
- Push to `develop` and `feature/*` branches
- Pull requests to `main` and `develop`
- Daily scheduled scan at 2 AM UTC
- Manual dispatch

**Security Tools:**
- **Semgrep**: Static analysis with security-focused rules
- **Bandit**: Python security linter
- **Safety**: Dependency vulnerability scanning
- **GitLeaks**: Secret detection in code and history
- **CodeQL**: Advanced semantic security analysis
- **License Compliance**: GPL/copyleft license detection

**SARIF Integration**: Results uploaded to GitHub Security tab

### 3. Manual Test Execution (`manual-test.yml`)

**Trigger:** Manual dispatch only

**Options:**
- **Test Suite Selection**: all, validation, integration, security, performance
- **Python Version**: 3.8-3.12
- **Debug Mode**: Enhanced logging and diagnostics
- **Custom Commands**: Execute arbitrary test commands

**Use Cases:**
- Debugging specific test failures
- Testing against specific Python versions
- Custom validation scenarios
- Performance benchmarking with different parameters

### 4. Release Workflow (`release.yml`)

**Triggers:**
- Push to `main` branch
- Manual dispatch for hotfixes

**Features:**
- Automated version bumping
- Package building and PyPI publishing
- GitHub release creation
- Release notes generation

## 🛡️ Security Configuration

### Branch Protection Rules

**Main Branch (`main`):**
- ✅ Require pull request reviews (1 approval minimum)
- ✅ Require status checks:
  - All Python version tests (3.8-3.12)
  - Integration testing
  - Security scans (Semgrep, CodeQL)
  - Build validation
- ✅ Require conversation resolution
- ✅ Restrict force pushes
- ✅ No direct commits allowed

**Development Branch (`develop`):**
- ✅ Require pull request reviews (1 approval)
- ✅ Require core status checks
- ✅ Allow force pushes for maintainers

### Security Scanning Matrix

| Tool | Purpose | Frequency | Blocking |
|------|---------|-----------|----------|
| Semgrep | Static security analysis | Every push/PR + Daily | Yes |
| Bandit | Python security issues | Every push/PR | No |
| Safety | Dependency vulnerabilities | Every push/PR + Daily | No |
| GitLeaks | Secret detection | Every push/PR | Yes |
| CodeQL | Advanced code analysis | Every push/PR + Weekly | Yes |

## 📋 Templates

### Pull Request Template

**Comprehensive sections:**
- Change description and type classification
- Testing requirements and validation
- Security considerations and checklist
- Performance impact assessment
- Documentation updates
- Deployment notes and rollback plans

### Issue Templates

**Bug Report:**
- Environment information
- Reproduction steps
- Error logs and debug output
- Impact assessment

**Feature Request:**
- Detailed requirements and use cases
- Implementation considerations
- MCP protocol integration
- Success criteria and acceptance tests

## 👥 Code Ownership (CODEOWNERS)

**Review Requirements:**
- **Core files**: `@AndEnd-Org/core-maintainers`
- **Security**: `@AndEnd-Org/security-team`
- **CI/CD**: `@AndEnd-Org/devops-team`
- **Documentation**: `@AndEnd-Org/documentation-team`
- **Releases**: `@AndEnd-Org/release-team`

## 🚀 Getting Started

### For Contributors

1. **Fork and Clone:**
   ```bash
   git clone https://github.com/your-username/ast-mcp.git
   cd ast-mcp
   ```

2. **Create Feature Branch:**
   ```bash
   git checkout -b feature/your-feature-name
   ```

3. **Install Development Dependencies:**
   ```bash
   pip install -e .[dev]
   ```

4. **Run Tests Locally:**
   ```bash
   python tests/run_all_tests.py
   ```

5. **Create Pull Request:**
   - Use the provided PR template
   - Ensure all tests pass
   - Address security scan findings

### For Maintainers

1. **Configure Branch Protection:**
   - Follow instructions in `branch-protection-rules.md`
   - Set up required status checks
   - Configure reviewer requirements

2. **Set Up Secrets:**
   ```
   CODECOV_TOKEN      # For coverage reporting
   PYPI_API_TOKEN     # For package publishing
   GITLEAKS_LICENSE   # For GitLeaks (org only)
   ```

3. **Monitor Security:**
   - Review security scan results daily
   - Address high-severity findings promptly
   - Keep dependencies updated

## 🔧 Customization

### Adding New Tests

1. **Create Test File:**
   ```python
   # tests/test_new_feature.py
   def test_new_functionality():
       # Test implementation
       pass
   ```

2. **Update Test Runner:**
   ```python
   # tests/run_all_tests.py
   test_scripts.append(("tests/test_new_feature.py", "New Feature Tests"))
   ```

3. **Add to Workflow:**
   ```yaml
   # .github/workflows/test.yml
   - name: Run new feature tests
     run: python tests/test_new_feature.py
   ```

### Adding Security Rules

1. **Custom Semgrep Rules:**
   ```yaml
   # .semgrep.yml
   rules:
     - id: custom-rule
       pattern: dangerous_pattern()
       message: Custom security check
       severity: ERROR
   ```

2. **Update Security Workflow:**
   ```yaml
   # .github/workflows/security.yml
   config: |
     auto
     .semgrep.yml
   ```

### Performance Monitoring

1. **Add Benchmarks:**
   ```python
   # tests/benchmark_new_feature.py
   import time
   
   def benchmark_feature():
       start = time.time()
       # Feature execution
       duration = time.time() - start
       assert duration < THRESHOLD
   ```

2. **Update Performance Test:**
   ```yaml
   # .github/workflows/test.yml (performance-test job)
   - name: Run new benchmark
     run: python tests/benchmark_new_feature.py
   ```

## 📊 Monitoring and Maintenance

### Weekly Tasks
- [ ] Review failed test runs
- [ ] Check security scan results
- [ ] Update dependencies (Dependabot PRs)
- [ ] Monitor performance trends

### Monthly Tasks
- [ ] Review branch protection rules
- [ ] Update security scanning rules
- [ ] Performance baseline updates
- [ ] Documentation updates

### Quarterly Tasks
- [ ] Security audit and penetration testing
- [ ] Performance optimization review
- [ ] CI/CD pipeline optimization
- [ ] Tool and dependency major updates

## 🔗 Resources

- [GitHub Actions Documentation](https://docs.github.com/actions)
- [Semgrep Rules](https://semgrep.dev/docs/writing-rules/)
- [CodeQL Documentation](https://codeql.github.com/docs/)
- [SARIF Specification](https://sarifweb.azurewebsites.net/)
- [Branch Protection Rules](https://docs.github.com/repositories/configuring-branches-and-merges-in-your-repository/defining-the-mergeability-of-pull-requests)

## 🆘 Troubleshooting

### Common Issues

**Tests Failing in CI but Passing Locally:**
- Check Python version compatibility
- Verify environment variables are set
- Review dependency versions

**Security Scans Producing False Positives:**
- Add specific ignore rules to `.semgrep.yml`
- Update Bandit configuration in `pyproject.toml`
- Document exceptions in security review

**Performance Tests Unstable:**
- Increase timeout thresholds
- Use relative performance comparisons
- Consider machine-specific variations

**Build Failures:**
- Check dependency conflicts
- Verify package manifest includes all files
- Test in clean virtual environment