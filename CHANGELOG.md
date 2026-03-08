# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-03-07

### Added
- MCP server with 3 tools: `ast_grep_search`, `ast_grep_scan`, `ast_grep_run`
- 33 AST-grep rules across 8 programming languages
- Semantic code search with multi-language support (20+ languages)
- Security scanning with 25+ built-in vulnerability detection rules
- Call graph generation and function detection
- Result caching with TTL and LRU eviction
- Performance metrics collection with adaptive timeouts
- Memory monitoring and leak detection
- Concurrent request management with rate limiting
- Structured logging with sensitive data filtering
- Claude Code plugin manifest for AI agent integration
- Comprehensive test suite with 400+ tests

### Changed
- Minimum Python version is now 3.12 (previously 3.10)
- Performance module refactored from monolithic file into focused sub-modules

### Fixed
- License file now correctly uses MIT (matching pyproject.toml declaration)
- Documentation consistency for Python version requirements
