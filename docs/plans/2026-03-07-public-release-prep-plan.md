# Public Release Preparation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Prepare ast-mcp for public release with clean code, full test coverage, proper docs, and Claude Code plugin support.

**Architecture:** Bottom-up refactor approach. Fix housekeeping first, then split the performance.py monolith into focused modules, write tests for all modules, add community files, fix docs, and package as a Claude Code plugin.

**Tech Stack:** Python 3.12+, pytest, pytest-asyncio, MCP SDK, ast-grep-cli, psutil

---

### Task 1: Replace LICENSE with MIT

**Files:**
- Overwrite: `LICENSE`

**Step 1: Replace LICENSE file**

Write the MIT license file:

```
MIT License

Copyright (c) 2025 AndEnd-Collective

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

**Step 2: Commit**

```bash
git add LICENSE
git commit -m "chore: Replace Apache 2.0 license with MIT to match pyproject.toml"
```

---

### Task 2: Update Python version and project metadata

**Files:**
- Modify: `pyproject.toml` (lines 30-31, classifiers)
- Modify: `src/ast_grep_mcp/__init__.py` (line 3)

**Step 1: Update pyproject.toml**

Change `requires-python` from `">=3.10"` to `">=3.12"`. Replace classifiers:
```python
    "Programming Language :: Python :: 3.10",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
```
with:
```python
    "Programming Language :: Python :: 3.12",
    "Programming Language :: Python :: 3.13",
    "Programming Language :: Python :: 3.14",
```

**Step 2: Update __init__.py version**

Change `__version__ = "0.1.0"` to `__version__ = "1.0.0"`.

**Step 3: Update CI workflow**

In `.github/workflows/test.yml`, find the Python version matrix and change it to `[3.12, 3.13, 3.14]`. Do the same for any other workflow files that specify Python versions.

**Step 4: Commit**

```bash
git add pyproject.toml src/ast_grep_mcp/__init__.py .github/workflows/
git commit -m "chore: Update Python to >=3.12, target 3.14, version 1.0.0"
```

---

### Task 3: Split performance.py - Create cache.py

**Files:**
- Create: `src/ast_grep_mcp/cache.py`
- Test: `tests/test_cache.py`

**Step 1: Create cache.py**

Extract from `performance.py` (lines 1-573):
- `CacheConfig` dataclass
- `CacheEntry` dataclass
- `CacheStatistics` dataclass
- `AsyncLRUCache` class
- `cached()` decorator function
- Type definitions (`CacheKey`, `CacheValue`, `T`)

Include these imports at the top:
```python
"""Async-compatible result caching with TTL and LRU eviction."""

import asyncio
import hashlib
import json
import logging
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from functools import wraps
from pathlib import Path
from threading import RLock
from typing import Any, Callable, Dict, List, Optional, Set, TypeVar

T = TypeVar('T')
CacheKey = str
CacheValue = Any

logger = logging.getLogger(__name__)
```

**Step 2: Write failing tests for cache.py**

Create `tests/test_cache.py`:

```python
"""Tests for the cache module."""

import asyncio
import pytest
import time

from ast_grep_mcp.cache import (
    CacheConfig, CacheEntry, CacheStatistics, AsyncLRUCache, cached
)


class TestCacheConfig:
    def test_default_values(self):
        config = CacheConfig()
        assert config.max_entries == 1000
        assert config.default_ttl == 300
        assert config.max_memory_mb == 512

    def test_custom_values(self):
        config = CacheConfig(max_entries=500, default_ttl=60)
        assert config.max_entries == 500
        assert config.default_ttl == 60


class TestCacheEntry:
    def test_is_expired_false(self):
        entry = CacheEntry(
            value="test", created_at=time.time(),
            last_accessed=time.time(), access_count=0, ttl=300
        )
        assert not entry.is_expired()

    def test_is_expired_true(self):
        entry = CacheEntry(
            value="test", created_at=time.time() - 400,
            last_accessed=time.time(), access_count=0, ttl=300
        )
        assert entry.is_expired()

    def test_touch(self):
        entry = CacheEntry(
            value="test", created_at=time.time(),
            last_accessed=time.time() - 10, access_count=0, ttl=300
        )
        old_accessed = entry.last_accessed
        entry.touch()
        assert entry.access_count == 1
        assert entry.last_accessed > old_accessed


class TestCacheStatistics:
    def test_default_counters(self):
        stats = CacheStatistics()
        assert stats.hits == 0
        assert stats.misses == 0
        assert stats.evictions == 0


class TestAsyncLRUCache:
    @pytest.fixture
    def cache(self):
        config = CacheConfig(max_entries=10, default_ttl=60)
        return AsyncLRUCache(config)

    @pytest.mark.asyncio
    async def test_set_and_get(self, cache):
        await cache.set("key1", "value1")
        result = await cache.get("key1")
        assert result == "value1"

    @pytest.mark.asyncio
    async def test_get_missing_key(self, cache):
        result = await cache.get("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_delete(self, cache):
        await cache.set("key1", "value1")
        deleted = await cache.delete("key1")
        assert deleted is True
        result = await cache.get("key1")
        assert result is None

    @pytest.mark.asyncio
    async def test_clear(self, cache):
        await cache.set("key1", "value1")
        await cache.set("key2", "value2")
        await cache.clear()
        assert await cache.get("key1") is None
        assert await cache.get("key2") is None

    @pytest.mark.asyncio
    async def test_lru_eviction(self):
        config = CacheConfig(max_entries=3, default_ttl=60)
        cache = AsyncLRUCache(config)
        await cache.set("key1", "value1")
        await cache.set("key2", "value2")
        await cache.set("key3", "value3")
        await cache.set("key4", "value4")  # Should evict key1
        assert await cache.get("key1") is None
        assert await cache.get("key4") == "value4"

    @pytest.mark.asyncio
    async def test_ttl_expiry(self):
        config = CacheConfig(max_entries=10, default_ttl=1, min_ttl=1)
        cache = AsyncLRUCache(config)
        await cache.set("key1", "value1", ttl=1)
        await asyncio.sleep(1.1)
        result = await cache.get("key1")
        assert result is None

    @pytest.mark.asyncio
    async def test_statistics_tracking(self, cache):
        await cache.set("key1", "value1")
        await cache.get("key1")  # hit
        await cache.get("missing")  # miss
        stats = cache.get_statistics()
        assert stats.hits >= 1
        assert stats.misses >= 1

    @pytest.mark.asyncio
    async def test_invalidate_group(self, cache):
        await cache.set("key1", "value1", group="group1")
        await cache.set("key2", "value2", group="group1")
        await cache.set("key3", "value3", group="group2")
        count = await cache.invalidate_group("group1")
        assert count == 2
        assert await cache.get("key1") is None
        assert await cache.get("key3") == "value3"


class TestCachedDecorator:
    @pytest.mark.asyncio
    async def test_cached_function(self):
        call_count = 0

        @cached(ttl=60)
        async def expensive_func(x):
            nonlocal call_count
            call_count += 1
            return x * 2

        result1 = await expensive_func(5)
        result2 = await expensive_func(5)
        assert result1 == 10
        assert result2 == 10
        # Should only compute once due to caching
        assert call_count == 1
```

**Step 3: Run tests to verify they fail**

Run: `cd /Users/Naor.Penso/code/ast-mcp && python -m pytest tests/test_cache.py -v`
Expected: FAIL (module `ast_grep_mcp.cache` does not exist yet)

**Step 4: Create cache.py with the extracted code**

Move the classes from performance.py lines 1-573 into `src/ast_grep_mcp/cache.py`.

**Step 5: Run tests to verify they pass**

Run: `cd /Users/Naor.Penso/code/ast-mcp && python -m pytest tests/test_cache.py -v`
Expected: All PASS

**Step 6: Commit**

```bash
git add src/ast_grep_mcp/cache.py tests/test_cache.py
git commit -m "refactor: Extract cache module from performance.py with full tests"
```

---

### Task 4: Split performance.py - Create metrics.py

**Files:**
- Create: `src/ast_grep_mcp/metrics.py`
- Test: `tests/test_metrics.py`

**Step 1: Create metrics.py**

Extract from `performance.py`:
- `MetricsConfig` dataclass (lines 964-995)
- `OperationMetrics` dataclass (lines 2499-2572)
- `PerformanceMetricsCollector` class (lines 2575-2890)
- Global accessor functions: `get_metrics_collector()`, `set_metrics_collector()`

**Step 2: Write failing tests for metrics.py**

Create `tests/test_metrics.py`:

```python
"""Tests for the metrics module."""

import pytest
import time

from ast_grep_mcp.metrics import (
    MetricsConfig, OperationMetrics, PerformanceMetricsCollector,
    get_metrics_collector, set_metrics_collector
)


class TestMetricsConfig:
    def test_defaults(self):
        config = MetricsConfig()
        assert config.enable_detailed_metrics is True
        assert config.base_timeout_ms == 10000
        assert config.timeout_percentile == 95

    def test_custom_values(self):
        config = MetricsConfig(base_timeout_ms=5000)
        assert config.base_timeout_ms == 5000


class TestOperationMetrics:
    def test_default_counters(self):
        metrics = OperationMetrics()
        assert metrics.total_requests == 0
        assert metrics.successful_requests == 0
        assert metrics.failed_requests == 0

    def test_add_latency_bucket(self):
        metrics = OperationMetrics()
        metrics.add_latency_bucket(10.0)
        assert 10.0 in metrics.latency_buckets
        assert metrics.latency_buckets[10.0] == 1

    def test_add_latency_bucket_enforces_limit(self):
        metrics = OperationMetrics()
        for i in range(60):
            metrics.add_latency_bucket(float(i))
        assert len(metrics.latency_buckets) <= metrics._max_latency_buckets

    def test_cleanup_old_data(self):
        metrics = OperationMetrics()
        metrics.last_cleanup = time.time() - 400  # Force cleanup
        metrics.request_timestamps.append(time.time() - 7200)  # 2 hours old
        metrics.request_timestamps.append(time.time())  # current
        metrics.cleanup_old_data()
        assert len(metrics.request_timestamps) == 1

    def test_to_dict(self):
        metrics = OperationMetrics()
        result = metrics.to_dict()
        assert "total_requests" in result
        assert "current_percentiles" in result


class TestPerformanceMetricsCollector:
    @pytest.fixture
    def collector(self):
        config = MetricsConfig()
        return PerformanceMetricsCollector(config)

    def test_record_operation_start(self, collector):
        ctx = collector.record_operation_start(
            operation="search", operation_id="op1",
            cache_key="key1"
        )
        assert ctx is not None

    def test_record_operation_complete(self, collector):
        collector.record_operation_start(
            operation="search", operation_id="op1",
            cache_key="key1"
        )
        collector.record_operation_complete(
            operation="search", operation_id="op1",
            success=True, latency_ms=50.0
        )
        metrics = collector.get_operation_metrics("search")
        assert metrics.successful_requests >= 1

    def test_get_timeout_for_operation(self, collector):
        timeout = collector.get_timeout_for_operation("search")
        assert timeout > 0

    def test_update_system_metrics(self, collector):
        collector.update_system_metrics(
            cpu_usage=50.0, memory_usage=60.0,
            active_requests=5, queue_length=2
        )
        # Should not raise


class TestGlobalAccessors:
    def test_get_set_metrics_collector(self):
        config = MetricsConfig()
        collector = PerformanceMetricsCollector(config)
        set_metrics_collector(collector)
        assert get_metrics_collector() is collector
        set_metrics_collector(None)
```

**Step 3: Run tests to verify they fail, then implement, then verify pass**

**Step 4: Commit**

```bash
git add src/ast_grep_mcp/metrics.py tests/test_metrics.py
git commit -m "refactor: Extract metrics module from performance.py with full tests"
```

---

### Task 5: Split performance.py - Create monitoring.py

**Files:**
- Create: `src/ast_grep_mcp/monitoring.py`
- Test: `tests/test_monitoring.py`

**Step 1: Create monitoring.py**

Extract from `performance.py`:
- `MemoryConfig` dataclass (lines 935-962)
- `MemorySnapshot` dataclass (lines 1888-1922)
- `MemoryAlert` dataclass (lines 1925-1945)
- `MemoryMonitor` class (lines 1948-2486)
- Global accessors: `get_memory_monitor()`, `set_memory_monitor()`

**Step 2: Write tests**

Create `tests/test_monitoring.py` covering:
- `MemoryConfig` defaults and custom values
- `MemorySnapshot.to_dict()` serialization
- `MemoryAlert.to_dict()` serialization
- `MemoryMonitor` init, `start()`, `stop()`, `get_current_usage()`, `_take_snapshot()`
- Threshold checking (warning/critical)
- Global accessor get/set

**Step 3: TDD cycle — fail, implement, pass**

**Step 4: Commit**

```bash
git add src/ast_grep_mcp/monitoring.py tests/test_monitoring.py
git commit -m "refactor: Extract monitoring module from performance.py with full tests"
```

---

### Task 6: Split performance.py - Create concurrency.py

**Files:**
- Create: `src/ast_grep_mcp/concurrency.py`
- Test: `tests/test_concurrency.py`

**Step 1: Create concurrency.py**

Extract from `performance.py`:
- `ConcurrencyConfig` dataclass (lines 872-908)
- `RequestPriority` enum (lines 1058-1080)
- `QueuedRequest` dataclass (lines 1081-1091)
- `DistributedLock` class (lines 1092-1132)
- `ConcurrentRequestManager` class (lines 1133-1494)

**Remove** `TokenBucketRateLimit` (lines 998-1057) — use `TokenBucket` from `security.py` instead. Update `ConcurrentRequestManager` to import from `security.py`.

**Step 2: Write tests**

Create `tests/test_concurrency.py` covering:
- `ConcurrencyConfig` defaults
- `DistributedLock` acquire, release, timeout behavior
- `RequestPriority` enum values
- `ConcurrentRequestManager` request lifecycle, queue stats

**Step 3: TDD cycle**

**Step 4: Commit**

```bash
git add src/ast_grep_mcp/concurrency.py tests/test_concurrency.py
git commit -m "refactor: Extract concurrency module, remove duplicate TokenBucketRateLimit"
```

---

### Task 7: Split performance.py - Create streaming.py

**Files:**
- Create: `src/ast_grep_mcp/streaming.py`
- Test: `tests/test_streaming.py`

**Step 1: Create streaming.py**

Extract from `performance.py`:
- `StreamingConfig` dataclass (lines 910-933)
- `StreamingManager` class (lines 2902-2958)
- Global accessors: `get_streaming_manager()`, `set_streaming_manager()`

**Step 2: Write tests**

Create `tests/test_streaming.py` covering:
- `StreamingConfig` defaults
- `StreamingManager` stream_results chunking behavior
- Stats tracking per stream
- Global accessor get/set

**Step 3: TDD cycle**

**Step 4: Commit**

```bash
git add src/ast_grep_mcp/streaming.py tests/test_streaming.py
git commit -m "refactor: Extract streaming module from performance.py with full tests"
```

---

### Task 8: Slim down performance.py and update imports

**Files:**
- Rewrite: `src/ast_grep_mcp/performance.py`
- Modify: `src/ast_grep_mcp/__init__.py`
- Test: `tests/test_performance_manager.py`

**Step 1: Rewrite performance.py as thin orchestrator**

Replace the 2966-line file with a slim module (~400 lines) containing only:
- `PerformanceManager` class
- `EnhancedPerformanceManager` class
- Global accessor: `get_performance_manager()`
- Re-exports from sub-modules for backward compatibility:

```python
"""Performance management orchestrator for AST-Grep MCP Server."""

# Re-export sub-module symbols for backward compatibility
from .cache import (
    CacheConfig, CacheEntry, CacheStatistics, AsyncLRUCache, cached,
    CacheKey, CacheValue
)
from .metrics import (
    MetricsConfig, OperationMetrics, PerformanceMetricsCollector,
    get_metrics_collector, set_metrics_collector
)
from .monitoring import (
    MemoryConfig, MemorySnapshot, MemoryAlert, MemoryMonitor,
    get_memory_monitor, set_memory_monitor
)
from .concurrency import (
    ConcurrencyConfig, RequestPriority, QueuedRequest,
    DistributedLock, ConcurrentRequestManager
)
from .streaming import (
    StreamingConfig, StreamingManager,
    get_streaming_manager, set_streaming_manager
)

# ... PerformanceManager and EnhancedPerformanceManager classes ...
# ... get_global_performance_manager, set_global_performance_manager ...
```

**Step 2: Verify existing imports still work**

Check that `server.py`, `tools.py`, and `__init__.py` imports resolve correctly. They import from `.performance` which now re-exports everything.

**Step 3: Write tests**

Create `tests/test_performance_manager.py`:
- `PerformanceManager` init, cache_key generation, get_or_compute
- `EnhancedPerformanceManager` start/shutdown lifecycle
- Global accessor get/set

**Step 4: Run ALL existing tests to verify no regressions**

Run: `python -m pytest tests/ -v`

**Step 5: Commit**

```bash
git add src/ast_grep_mcp/performance.py tests/test_performance_manager.py
git commit -m "refactor: Slim performance.py to orchestrator with backward-compat re-exports"
```

---

### Task 9: Write tests for security.py

**Files:**
- Create: `tests/test_security.py`

**Step 1: Write tests**

```python
"""Tests for the security module."""

import pytest
import time
from pathlib import Path

from ast_grep_mcp.security import (
    SecurityManager, PermissionManager, EnhancedAuditLogger,
    ValidationConfig, SecurityLevel, UserRole, UserContext,
    TokenBucket, RateLimitEntry, RateLimitConfig,
    secure_validate_path, secure_validate_pattern, secure_sanitize_command,
    initialize_security, get_security_manager, create_user_context,
    PathTraversalError, CommandInjectionError, SecurityError
)


class TestSecurityExceptions:
    def test_path_traversal_error(self):
        with pytest.raises(PathTraversalError):
            raise PathTraversalError("traversal attempt")

    def test_command_injection_error(self):
        with pytest.raises(CommandInjectionError):
            raise CommandInjectionError("injection attempt")


class TestSecurityLevel:
    def test_enum_values(self):
        assert SecurityLevel.PUBLIC.value == "public"
        assert SecurityLevel.CRITICAL.value == "critical"


class TestUserRole:
    def test_enum_values(self):
        assert UserRole.GUEST.value == "guest"
        assert UserRole.DEVELOPER.value == "developer"


class TestTokenBucket:
    def test_initial_capacity(self):
        bucket = TokenBucket(capacity=10, tokens=10.0, refill_rate=1.0, last_refill=time.time())
        assert bucket.available_tokens() == 10

    def test_consume(self):
        bucket = TokenBucket(capacity=10, tokens=10.0, refill_rate=1.0, last_refill=time.time())
        assert bucket.consume(5) is True
        assert bucket.available_tokens() <= 6  # approximate due to refill

    def test_consume_insufficient(self):
        bucket = TokenBucket(capacity=10, tokens=0.0, refill_rate=0.1, last_refill=time.time())
        assert bucket.consume(5) is False

    def test_refill(self):
        bucket = TokenBucket(capacity=10, tokens=0.0, refill_rate=100.0, last_refill=time.time() - 1)
        bucket.refill()
        assert bucket.tokens == 10.0  # capped at capacity

    def test_time_until_tokens(self):
        bucket = TokenBucket(capacity=10, tokens=0.0, refill_rate=1.0, last_refill=time.time())
        wait = bucket.time_until_tokens(5)
        assert wait > 0


class TestSecureValidatePath:
    def test_valid_path(self, tmp_path):
        test_file = tmp_path / "test.py"
        test_file.write_text("x = 1")
        result = secure_validate_path(str(test_file), str(tmp_path))
        assert result == test_file

    def test_path_traversal_blocked(self, tmp_path):
        with pytest.raises((PathTraversalError, SecurityError, ValueError)):
            secure_validate_path("../../etc/passwd", str(tmp_path))


class TestSecureSanitizeCommand:
    def test_safe_command(self):
        cmd, args = secure_sanitize_command("ast-grep", ["search", "--pattern", "foo"])
        assert cmd == "ast-grep"

    def test_dangerous_chars_blocked(self):
        with pytest.raises((CommandInjectionError, SecurityError, ValueError)):
            secure_sanitize_command("ast-grep; rm -rf /", [])


class TestValidationConfig:
    def test_default_values(self):
        config = ValidationConfig()
        assert config is not None


class TestSecurityManager:
    def test_initialization(self):
        config = ValidationConfig()
        manager = SecurityManager(config)
        assert manager is not None
```

**Step 2: Run tests, fix any import issues, verify pass**

**Step 3: Commit**

```bash
git add tests/test_security.py
git commit -m "test: Add comprehensive security module tests"
```

---

### Task 10: Write tests for logging_config.py

**Files:**
- Create: `tests/test_logging_config.py`

**Step 1: Write tests**

Cover: `LoggingConfig` defaults, `SensitiveDataFilter` redaction, `CorrelationContextManager`, `StructuredFormatter`, `setup_enhanced_logging()`, `shutdown_logging()`, `get_logging_manager()`.

**Step 2: TDD cycle**

**Step 3: Commit**

```bash
git add tests/test_logging_config.py
git commit -m "test: Add comprehensive logging config tests"
```

---

### Task 11: Write tests for server.py

**Files:**
- Create: `tests/test_server.py`

**Step 1: Write tests**

Cover: `ServerConfig` defaults/env vars, `ASTGrepMCPServer` creation via `create_server()`, `HealthMetrics`, `HealthThresholds`, `SystemResourceMonitor`, `DependencyHealthChecker`.

**Step 2: TDD cycle**

**Step 3: Commit**

```bash
git add tests/test_server.py
git commit -m "test: Add comprehensive server module tests"
```

---

### Task 12: Expand existing thin test files

**Files:**
- Modify: `tests/test_ast_grep_scan.py` (expand from 6 tests)
- Modify: `tests/test_call_graph_generation.py` (expand from 4 tests)
- Modify: `tests/test_function_detection.py` (expand from 8 tests)
- Modify: `tests/test_mcp.py` (expand from 2 tests)
- Modify: `tests/test_mcp_tools_registration.py` (expand from 1 test)

**Step 1: Read each file, identify gaps, add tests**

For each file, add tests covering untested branches and edge cases in the corresponding source module.

**Step 2: Run full test suite**

Run: `python -m pytest tests/ -v`

**Step 3: Commit**

```bash
git add tests/
git commit -m "test: Expand coverage for scan, call graph, function detection, MCP, and tools"
```

---

### Task 13: Delete empty/stub test files

**Files:**
- Delete: `tests/test_code.py`
- Delete: `tests/test_mcp_performance.py`
- Delete: `tests/test_mcp_protocol.py`
- Delete: `tests/test_mcp_protocol_messages.py`
- Delete: `tests/test_mcp_schema_compliance.py`
- Delete: `tests/test_mcp_structured_output.py`
- Delete: `tests/test_mcp_transport.py`
- Delete: `tests/test_mcp_client_integration.py`

**Step 1: Delete files**

```bash
git rm tests/test_code.py tests/test_mcp_performance.py tests/test_mcp_protocol.py \
  tests/test_mcp_protocol_messages.py tests/test_mcp_schema_compliance.py \
  tests/test_mcp_structured_output.py tests/test_mcp_transport.py \
  tests/test_mcp_client_integration.py
```

**Step 2: Run full test suite to verify nothing breaks**

Run: `python -m pytest tests/ -v`

**Step 3: Commit**

```bash
git commit -m "chore: Remove empty/stub test files that pretended coverage"
```

---

### Task 14: Add integration test markers

**Files:**
- Modify: Various test files that invoke the ast-grep binary

**Step 1: Identify tests that call ast-grep**

Search for tests that use subprocess or invoke ast-grep. Mark them with `@pytest.mark.integration`.

**Step 2: Run tests filtering by marker**

Run: `python -m pytest tests/ -m "not integration" -v` (unit tests only)
Run: `python -m pytest tests/ -m integration -v` (integration tests only)

**Step 3: Commit**

```bash
git add tests/
git commit -m "test: Add @pytest.mark.integration markers to ast-grep-dependent tests"
```

---

### Task 15: Create CONTRIBUTING.md

**Files:**
- Create: `CONTRIBUTING.md`

**Step 1: Write CONTRIBUTING.md**

Include:
- Prerequisites (Python 3.12+, ast-grep CLI)
- Dev environment setup (clone, venv, pip install -e ".[dev]")
- Running tests (`pytest`, integration vs unit)
- Code style (black, isort, flake8, mypy)
- How to add new AST-grep rules (directory structure, YAML format, testing)
- PR process (branch from main, tests must pass, one approval required)
- Issue reporting guidelines

**Step 2: Commit**

```bash
git add CONTRIBUTING.md
git commit -m "docs: Add CONTRIBUTING.md for public release"
```

---

### Task 16: Create CODE_OF_CONDUCT.md

**Files:**
- Create: `CODE_OF_CONDUCT.md`

**Step 1: Write CODE_OF_CONDUCT.md**

Use the Contributor Covenant v2.1 with `contact@andend.org` as enforcement contact.

**Step 2: Commit**

```bash
git add CODE_OF_CONDUCT.md
git commit -m "docs: Add Contributor Covenant Code of Conduct"
```

---

### Task 17: Create SECURITY.md

**Files:**
- Create: `SECURITY.md`

**Step 1: Write SECURITY.md**

Include:
- Supported versions table (1.0.x)
- How to report vulnerabilities (email contact@andend.org, NOT public issues)
- Response timeline expectations
- Disclosure policy

**Step 2: Commit**

```bash
git add SECURITY.md
git commit -m "docs: Add security vulnerability disclosure policy"
```

---

### Task 18: Create CHANGELOG.md

**Files:**
- Create: `CHANGELOG.md`

**Step 1: Write CHANGELOG.md**

Format: Keep a Changelog. Document 1.0.0 with:
- Added: MCP server with 3 tools, 33 AST-grep rules, security scanning, performance caching
- Changed: Python 3.12+ required
- Fixed: License alignment (MIT)

**Step 2: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs: Add CHANGELOG.md for version 1.0.0"
```

---

### Task 19: Fix documentation inconsistencies

**Files:**
- Modify: `README.md`
- Modify: `INSTALL.md`
- Modify: `HOW-TO-USE.md`
- Verify: `docs/API.md`, `docs/CONFIGURATION.md`, `docs/DEPLOYMENT.md`, `docs/TROUBLESHOOTING.md`

**Step 1: Fix README.md**

- Update Python requirement to 3.12+
- Fix PyPI status: change "coming soon" to consistent messaging
- Update MCP config examples to show only Claude Code, Codex, OpenCode
- Verify CONTRIBUTING.md link works

**Step 2: Fix INSTALL.md**

- Change Python `3.8+` to `3.12+`
- Align install instructions with current state

**Step 3: Fix HOW-TO-USE.md**

- Fix PyPI status consistency
- Update Python version references

**Step 4: Verify docs/ completeness**

Read each doc file, check for truncation or inaccuracies.

**Step 5: Commit**

```bash
git add README.md INSTALL.md HOW-TO-USE.md docs/
git commit -m "docs: Fix version references, PyPI status, and config examples"
```

---

### Task 20: Create Claude Code plugin manifest

**Files:**
- Create: `plugin.json`
- Create: `src/ast_grep_mcp/__main__.py`

**Step 1: Create __main__.py**

```python
"""Allow running ast_grep_mcp as a module: python -m ast_grep_mcp"""

from ast_grep_mcp.server import main_sync

if __name__ == "__main__":
    main_sync()
```

**Step 2: Create plugin.json**

```json
{
  "name": "ast-mcp",
  "description": "AST-powered semantic code analysis for AI coding agents",
  "version": "1.0.0",
  "author": "AndEnd-Collective",
  "license": "MIT",
  "repository": "https://github.com/AndEnd-Collective/ast-mcp",
  "mcp_servers": {
    "ast-mcp": {
      "command": "python",
      "args": ["-m", "ast_grep_mcp"],
      "env": {}
    }
  }
}
```

**Step 3: Update README.md with plugin configs**

Add a section with config examples for Claude Code, Codex, and OpenCode.

**Step 4: Test the entry point**

Run: `cd /Users/Naor.Penso/code/ast-mcp && python -m ast_grep_mcp --help` or verify it starts the stdio server.

**Step 5: Commit**

```bash
git add plugin.json src/ast_grep_mcp/__main__.py README.md
git commit -m "feat: Add Claude Code plugin manifest and __main__.py entry point"
```

---

### Task 21: Run full verification

**Step 1: Run full test suite**

```bash
cd /Users/Naor.Penso/code/ast-mcp
python -m pytest tests/ -v --tb=short
```

Expected: All tests pass.

**Step 2: Run linters**

```bash
python -m black --check src/ tests/
python -m isort --check src/ tests/
python -m flake8 src/ tests/
python -m mypy src/
```

**Step 3: Verify server starts**

```bash
python -m ast_grep_mcp
```

Expected: Server starts on stdio (will hang waiting for input — Ctrl+C to exit).

**Step 4: Verify no sensitive info**

```bash
grep -r "pplx-" src/ tests/ docs/ *.md *.json
grep -r "sk-ant-" src/ tests/ docs/ *.md *.json
```

Expected: No matches.

**Step 5: Final commit if any fixes needed**

```bash
git add -A
git commit -m "fix: Final verification cleanup for public release"
```
