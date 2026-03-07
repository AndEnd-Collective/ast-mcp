# Public Release Preparation Design

**Date:** 2026-03-07
**Status:** Approved
**Branch:** feat/rules-galore
**Target:** Single PR to main

## Goal

Prepare ast-mcp for public release as an MCP server and Claude Code plugin. Target audience: end-users, contributors, and coding agent plugin consumers.

## Decisions

- **License:** MIT (replacing Apache 2.0 LICENSE file; pyproject.toml already says MIT)
- **Python:** Minimum 3.12, target 3.14, classifiers for 3.12/3.13/3.14
- **Version:** 1.0.0 (unify pyproject.toml and __init__.py)
- **Plugin targets:** Claude Code, Codex, OpenCode (no Cursor/Windsurf/Continue)
- **Approach:** Bottom-up refactor — restructure first, then test against final shape

## Phase 1: Housekeeping & Sensitive Info Cleanup

1. Replace LICENSE file content with MIT license text, copyright AndEnd-Collective
2. Update pyproject.toml: `requires-python = ">=3.12"`, classifiers for 3.12/3.13/3.14
3. Fix `__init__.py` version from `0.1.0` to `1.0.0`
4. Fix INSTALL.md: Python `3.8+` to `3.12+`
5. Fix PyPI status across README.md and HOW-TO-USE.md: consistent "install from source" messaging
6. Update CI workflows: Python matrix to `[3.12, 3.13, 3.14]`
7. Verify .gitignore covers .env, logs/, dist/ (confirmed clean)
8. No secrets in git history (confirmed clean)

## Phase 2: Refactor performance.py

Split the 2,966-line monolith into focused modules under `src/ast_grep_mcp/`:

| New File | Classes | Responsibility |
|----------|---------|---------------|
| `cache.py` | CacheConfig, CacheEntry, CacheStatistics, AsyncLRUCache, cached() | Result caching with TTL and LRU eviction |
| `metrics.py` | MetricsConfig, OperationMetrics, PerformanceMetricsCollector | Operation timing, percentile stats |
| `monitoring.py` | MemoryConfig, MemorySnapshot, MemoryAlert, MemoryMonitor | Memory tracking and leak detection |
| `concurrency.py` | ConcurrencyConfig, DistributedLock, RequestPriority, QueuedRequest, ConcurrentRequestManager | Request concurrency management |
| `streaming.py` | StreamingConfig, StreamingManager | Chunked result streaming |
| `performance.py` (slim) | PerformanceManager, EnhancedPerformanceManager | Orchestrator, re-exports for backward compat |

### Deduplication

Delete `TokenBucketRateLimit` from performance.py. The canonical rate limiter is `TokenBucket` in security.py.

### Backward Compatibility

`performance.py` re-exports all symbols from sub-modules via `__all__` so existing imports in server.py, tools.py, and __init__.py continue to work without changes.

## Phase 3: Test Coverage

### Delete empty/stub test files (8 files)

- test_code.py (empty)
- test_mcp_performance.py (stub)
- test_mcp_protocol.py (stub)
- test_mcp_protocol_messages.py (stub)
- test_mcp_schema_compliance.py (stub)
- test_mcp_structured_output.py (stub)
- test_mcp_transport.py (stub)
- test_mcp_client_integration.py (stub)

### New test files (9 files)

| Test File | Module | Key Test Areas |
|-----------|--------|---------------|
| test_cache.py | cache.py | LRU eviction, TTL expiry, memory limits, decorator, stats |
| test_metrics.py | metrics.py | Operation recording, percentiles, collector lifecycle |
| test_monitoring.py | monitoring.py | Snapshots, alert thresholds, leak detection |
| test_concurrency.py | concurrency.py | Lock acquire/release/timeout, queuing, priority |
| test_streaming.py | streaming.py | Chunk iteration, config validation |
| test_performance_manager.py | performance.py | Manager init/shutdown, sub-module integration |
| test_security.py | security.py | SecurityManager, PermissionManager, path validation, command sanitization, audit logger |
| test_logging_config.py | logging_config.py | SensitiveDataFilter, correlation IDs, structured formatter, async handler |
| test_server.py | server.py | ASTGrepMCPServer lifecycle, health checks, system monitor |

### Expand existing tests (5 files)

- test_ast_grep_scan.py: expand from 6 tests
- test_call_graph_generation.py: expand from 4 tests
- test_function_detection.py: expand from 8 tests
- test_mcp.py: expand from 2 tests
- test_mcp_tools_registration.py: expand from 1 test

### Test markers

Properly mark integration tests with `@pytest.mark.integration` where they invoke the ast-grep binary.

## Phase 4: GitHub Community Files

| File | Content |
|------|---------|
| CONTRIBUTING.md | Dev setup, coding standards, PR process, rule authoring guide |
| CODE_OF_CONDUCT.md | Contributor Covenant v2.1 |
| SECURITY.md | Vulnerability disclosure process, supported versions |
| CHANGELOG.md | Version history starting with 1.0.0 |

## Phase 5: Documentation Fixes

| File | Changes |
|------|---------|
| README.md | Fix CONTRIBUTING.md link, Python 3.12+, PyPI status, plugin configs for Claude Code/Codex/OpenCode only |
| INSTALL.md | Python 3.12+, consistent install instructions |
| HOW-TO-USE.md | Python 3.12+, fix PyPI status |
| docs/API.md | Verify accuracy against tool signatures |
| docs/CONFIGURATION.md | Verify completeness |
| docs/DEPLOYMENT.md | Verify completeness |
| docs/TROUBLESHOOTING.md | Verify completeness |
| .github/workflows/test.yml | Python matrix [3.12, 3.13, 3.14] |

## Phase 6: Plugin Packaging

1. Create `plugin.json` at repo root for Claude Code discovery
2. Create `src/ast_grep_mcp/__main__.py` for `python -m ast_grep_mcp` support
3. Update README.md with config examples for Claude Code, Codex, OpenCode
4. Verify `main_sync()` entry point works via stdio

## Audit Findings (for reference)

### Sensitive Info (clean)
- .env is gitignored, never committed
- No hardcoded secrets in source, config, or scripts
- GitHub workflows use proper ${{ secrets.* }} references
- Recommendation: rotate local API keys as precaution

### Test Coverage Gaps (to be fixed)
- performance.py: 0% coverage (3000 LOC)
- logging_config.py: 0% coverage
- security.py: ~23% coverage
- server.py: ~4% coverage
- 8 test files with zero actual test functions

### Docs/Dependencies (to be fixed)
- License mismatch: MIT in pyproject.toml vs Apache 2.0 in LICENSE
- Missing: CONTRIBUTING.md, CODE_OF_CONDUCT.md, SECURITY.md
- Python version inconsistency across docs
- PyPI status contradiction across docs
