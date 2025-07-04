# Branch Protection Rules Configuration

This document outlines the required branch protection rules for the AST-Grep MCP Server repository.

## Main Branch Protection

Configure the following settings for the `main` branch in GitHub repository settings:

### Required Settings

**General Protection Rules:**
- ✅ **Require a pull request before merging**
  - Require approvals: **1 approval minimum**
  - Dismiss stale PR approvals when new commits are pushed
  - Require review from code owners (if CODEOWNERS file exists)

- ✅ **Require status checks to pass before merging**
  - Require branches to be up to date before merging
  - **Required status checks:**
    - `test / Run Tests and Validation (3.8)`
    - `test / Run Tests and Validation (3.9)` 
    - `test / Run Tests and Validation (3.10)`
    - `test / Run Tests and Validation (3.11)`
    - `test / Run Tests and Validation (3.12)`
    - `integration-test / Integration Testing`
    - `build-test / Build and Distribution Test`
    - `semgrep / Semgrep Security Scan`
    - `codeql / CodeQL Security Analysis`

- ✅ **Require conversation resolution before merging**
- ✅ **Require signed commits** (recommended)
- ✅ **Require linear history** (optional, prevents merge commits)

**Administrative Settings:**
- ✅ **Restrict pushes that create files**
- ✅ **Restrict force pushes**
- ✅ **Allow force pushes by administrators** (for emergency fixes only)
- ✅ **Allow deletions by administrators only**

## Development Branch Protection (develop)

Configure lighter protection for the `develop` branch:

**Settings:**
- ✅ **Require a pull request before merging**
  - Require approvals: **1 approval minimum**
- ✅ **Require status checks to pass before merging**
  - **Required status checks:**
    - `test / Run Tests and Validation (3.11)` (single Python version)
    - `semgrep / Semgrep Security Scan`
- ✅ **Require conversation resolution before merging**

## How to Configure

### Via GitHub Web Interface

1. Go to repository **Settings** → **Branches**
2. Click **Add rule** for `main` branch
3. Configure all settings as specified above
4. Repeat for `develop` branch with appropriate settings

### Via GitHub CLI (if available)

```bash
# Main branch protection
gh api repos/:owner/:repo/branches/main/protection \
  --method PUT \
  --field required_status_checks='{"strict":true,"contexts":["test / Run Tests and Validation (3.11)","semgrep / Semgrep Security Scan","codeql / CodeQL Security Analysis"]}' \
  --field enforce_admins=true \
  --field required_pull_request_reviews='{"required_approving_review_count":1,"dismiss_stale_reviews":true}' \
  --field restrictions=null
```

### Via Terraform (for Infrastructure as Code)

```hcl
resource "github_branch_protection" "main" {
  repository_id = github_repository.repo.node_id
  pattern       = "main"
  
  required_status_checks {
    strict = true
    contexts = [
      "test / Run Tests and Validation (3.11)",
      "integration-test / Integration Testing", 
      "semgrep / Semgrep Security Scan",
      "codeql / CodeQL Security Analysis"
    ]
  }
  
  required_pull_request_reviews {
    required_approving_review_count = 1
    dismiss_stale_reviews = true
  }
  
  enforce_admins = true
  require_signed_commits = true
  require_conversation_resolution = true
  
  restrict_pushes {
    push_allowances = []
  }
}
```

## Workflow Protection

The GitHub Actions workflows themselves include additional protections:

- **Matrix testing** across Python 3.8-3.12
- **Comprehensive security scanning** with multiple tools
- **Integration testing** with real ast-grep binary
- **Performance benchmarking** on PRs
- **Build validation** and distribution testing

## Emergency Procedures

In case of critical security fixes or production issues:

1. **Hotfix Process:**
   - Create `hotfix/description` branch from `main`
   - Implement minimal fix
   - Run security scans locally: `semgrep --config=auto .`
   - Create PR with `[HOTFIX]` prefix
   - Expedited review process (administrator override if needed)

2. **Bypass Procedures:**
   - Administrator can temporarily disable branch protection
   - Must document reason and re-enable immediately after
   - All bypassed changes must go through post-hoc review

## Monitoring and Compliance

- **Weekly review** of branch protection rule compliance
- **Audit trail** of all force pushes and bypasses
- **Security scan results** tracked in GitHub Security tab
- **Dependency updates** via Dependabot with auto-merge for patches

## Status Checks Reference

| Check Name | Purpose | Failure Action |
|------------|---------|----------------|
| `test / Run Tests and Validation` | Core functionality testing | Block merge |
| `integration-test / Integration Testing` | End-to-end validation | Block merge |
| `semgrep / Semgrep Security Scan` | Security vulnerability detection | Block merge |
| `codeql / CodeQL Security Analysis` | Advanced code analysis | Block merge |
| `build-test / Build and Distribution Test` | Package build validation | Block merge |
| `performance-test / Performance Testing` | Performance regression detection | Warning only |