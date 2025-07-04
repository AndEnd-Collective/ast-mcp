## 📋 Pull Request Description

### Summary
<!-- Provide a clear and concise description of what this PR accomplishes -->

### Type of Change
<!-- Mark the relevant option with an "x" -->
- [ ] 🐛 Bug fix (non-breaking change that fixes an issue)
- [ ] ✨ New feature (non-breaking change that adds functionality)
- [ ] 💥 Breaking change (fix or feature that would cause existing functionality to not work as expected)
- [ ] 📚 Documentation update
- [ ] 🧹 Code cleanup/refactoring
- [ ] 🔧 Build/CI changes
- [ ] 🔒 Security fix
- [ ] ⚡ Performance improvement
- [ ] 🧪 Test improvements

### Related Issues
<!-- Link any related issues using "Closes #123" or "Fixes #123" -->
- Closes #
- Related to #

---

## 🧪 Testing

### Test Coverage
<!-- Describe how this change has been tested -->
- [ ] Unit tests added/updated
- [ ] Integration tests added/updated
- [ ] Manual testing performed
- [ ] Performance testing completed (if applicable)
- [ ] Security testing completed (if applicable)

### Test Results
<!-- Provide evidence of testing -->
```bash
# Example: Paste test output or commands run
python tests/run_all_tests.py
# All tests passed: ✅
```

### MCP Validation
<!-- For changes affecting MCP functionality -->
- [ ] MCP protocol compliance verified
- [ ] Tool registration tested
- [ ] Resource endpoints validated
- [ ] Error handling tested
- [ ] Input validation confirmed

---

## 🔒 Security Considerations

### Security Impact
<!-- Describe any security implications -->
- [ ] No security impact
- [ ] Security improvement
- [ ] Potential security risk (explain below)

### Security Checklist
- [ ] No secrets or sensitive data exposed
- [ ] Input validation implemented
- [ ] Error messages don't leak information
- [ ] Dependencies are secure and up-to-date
- [ ] Security scans pass (Semgrep, Bandit, etc.)

---

## 📊 Performance Impact

### Performance Considerations
- [ ] No performance impact
- [ ] Performance improvement
- [ ] Potential performance regression (benchmarked below)

### Benchmarks
<!-- If performance is affected, provide before/after metrics -->
```
Before: X ms
After:  Y ms
Impact: Z% improvement/regression
```

---

## 🗃️ Database/Configuration Changes

### Schema Changes
- [ ] No database changes
- [ ] Database migration required
- [ ] Configuration changes required

### Migration Notes
<!-- If migrations are needed, describe the process -->

---

## 📚 Documentation

### Documentation Updates
- [ ] Code comments updated
- [ ] README updated
- [ ] API documentation updated
- [ ] Configuration documentation updated
- [ ] No documentation changes needed

### Breaking Changes Documentation
<!-- If this is a breaking change, document the migration path -->

---

## ✅ Checklist

### Code Quality
- [ ] Code follows the project's style guidelines
- [ ] Self-review of code completed
- [ ] Code is well-commented and self-documenting
- [ ] No console.log/print statements left in production code
- [ ] Error handling is appropriate

### Testing
- [ ] Tests have been added that prove the fix is effective or the feature works
- [ ] New and existing unit tests pass locally
- [ ] Integration tests pass
- [ ] Manual testing completed

### Dependencies
- [ ] No new dependencies added, or dependencies are justified
- [ ] All dependencies are compatible with project requirements
- [ ] Security scan of dependencies completed

### Git
- [ ] Commit messages are clear and follow conventions
- [ ] Branch is up to date with target branch
- [ ] No merge conflicts

---

## 🔄 Deployment Notes

### Deployment Requirements
- [ ] Can be deployed directly
- [ ] Requires configuration changes
- [ ] Requires database migration
- [ ] Requires service restart
- [ ] Has rollback plan

### Environment Variables
<!-- List any new or changed environment variables -->
```
NEW_VAR=example_value
UPDATED_VAR=new_value
```

### Rollback Plan
<!-- Describe how to rollback if issues occur -->

---

## 📸 Screenshots/Examples

### Before/After (if UI changes)
<!-- Add screenshots for visual changes -->

### Usage Examples
<!-- Provide examples of how to use new features -->
```python
# Example usage
from ast_grep_mcp import new_feature
result = new_feature.do_something()
```

---

## 👥 Review Notes

### Areas of Focus
<!-- Highlight specific areas that need reviewer attention -->
- Focus on security implications in `src/security.py`
- Review performance of new algorithm in `src/tools.py`
- Validate error handling in edge cases

### Questions for Reviewers
<!-- Any specific questions or concerns -->
1. Is the error handling sufficient for edge case X?
2. Should we add additional logging for operation Y?

---

## 📝 Additional Notes

### Future Work
<!-- Note any follow-up work or technical debt -->

### Known Limitations
<!-- Document any known limitations or temporary solutions -->

---

**Reviewer Guidelines:**
- Ensure all tests pass before approving
- Verify security implications are addressed
- Check that documentation is updated appropriately
- Confirm backward compatibility (unless breaking change is justified)
- Validate that the change aligns with project architecture and patterns