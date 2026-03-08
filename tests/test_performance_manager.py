"""Tests for PerformanceManager, EnhancedPerformanceManager, and global accessors.

Covers the orchestrator classes retained in performance.py after the module
was slimmed down.  Sub-module internals (cache, metrics, monitoring, etc.)
are tested in their own test files.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from ast_grep_mcp.performance import (
    # Classes under test
    PerformanceManager,
    EnhancedPerformanceManager,
    # Global accessors
    get_global_performance_manager,
    set_global_performance_manager,
    get_performance_manager,
    # Re-exported sub-module symbols (verify they resolve)
    CacheConfig,
    CacheEntry,
    CacheStatistics,
    AsyncLRUCache,
    CacheKey,
    CacheValue,
    MetricsConfig,
    OperationMetrics,
    PerformanceMetricsCollector,
    get_metrics_collector,
    set_metrics_collector,
    MemoryConfig,
    MemorySnapshot,
    MemoryAlert,
    MemoryMonitor,
    get_memory_monitor,
    set_memory_monitor,
    ConcurrencyConfig,
    RequestPriority,
    QueuedRequest,
    DistributedLock,
    ConcurrentRequestManager,
    StreamingConfig,
    StreamingManager,
    get_streaming_manager,
    set_streaming_manager,
    cached,
)


# ---------------------------------------------------------------------------
# PerformanceManager tests
# ---------------------------------------------------------------------------

class TestPerformanceManager:
    """Tests for the base PerformanceManager class."""

    def test_init_default_config(self):
        """PerformanceManager initialises with default CacheConfig."""
        pm = PerformanceManager()
        assert pm.config is not None
        assert isinstance(pm.config, CacheConfig)
        assert pm.config.max_entries == 1000
        assert pm._operation_times == {}
        assert pm._operation_counts == {}

    def test_init_custom_config(self):
        """PerformanceManager accepts a custom CacheConfig."""
        cfg = CacheConfig(max_entries=50, default_ttl=60)
        pm = PerformanceManager(config=cfg)
        assert pm.config.max_entries == 50
        assert pm.config.default_ttl == 60

    def test_cache_key_deterministic(self):
        """cache_key returns the same hash for the same inputs."""
        pm = PerformanceManager()
        key1 = pm.cache_key("search", pattern="foo", lang="python")
        key2 = pm.cache_key("search", pattern="foo", lang="python")
        assert key1 == key2

    def test_cache_key_differs_for_different_operations(self):
        """cache_key produces different hashes for different operations."""
        pm = PerformanceManager()
        key_search = pm.cache_key("search", pattern="foo")
        key_scan = pm.cache_key("scan", pattern="foo")
        assert key_search != key_scan

    def test_cache_key_differs_for_different_params(self):
        """cache_key produces different hashes for different parameters."""
        pm = PerformanceManager()
        key1 = pm.cache_key("search", pattern="foo")
        key2 = pm.cache_key("search", pattern="bar")
        assert key1 != key2

    def test_cache_key_length(self):
        """cache_key returns a 32-character hex digest."""
        pm = PerformanceManager()
        key = pm.cache_key("op", x=1)
        assert len(key) == 32
        assert all(c in "0123456789abcdef" for c in key)

    @pytest.mark.asyncio
    async def test_get_or_compute_caches_result(self):
        """get_or_compute caches and returns the computed result."""
        pm = PerformanceManager()
        call_count = 0

        def compute():
            nonlocal call_count
            call_count += 1
            return {"result": 42}

        result1 = await pm.get_or_compute("op", compute, pattern="a")
        result2 = await pm.get_or_compute("op", compute, pattern="a")

        assert result1 == {"result": 42}
        assert result2 == {"result": 42}
        assert call_count == 1  # second call should hit cache

    @pytest.mark.asyncio
    async def test_get_or_compute_handles_async_compute(self):
        """get_or_compute works with async compute functions."""
        pm = PerformanceManager()

        async def compute():
            return {"async": True}

        result = await pm.get_or_compute("op_async", compute, x=1)
        assert result == {"async": True}

    @pytest.mark.asyncio
    async def test_get_or_compute_records_failure(self):
        """get_or_compute records timing for failed operations."""
        pm = PerformanceManager()

        def failing_compute():
            raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):
            await pm.get_or_compute("op_fail", failing_compute, x=1)

        assert "op_fail_failed" in pm._operation_times

    def test_record_operation_time_tracks_timing(self):
        """_record_operation_time stores duration and count."""
        pm = PerformanceManager()
        pm._record_operation_time("search", 0.5)
        pm._record_operation_time("search", 0.3)

        assert len(pm._operation_times["search"]) == 2
        assert pm._operation_counts["search"] == 2

    def test_record_operation_time_prunes_history(self):
        """_record_operation_time keeps at most ~100 measurements."""
        pm = PerformanceManager()
        for i in range(150):
            pm._record_operation_time("search", float(i))

        # After 150 inserts the list should have been pruned to 50 at
        # the 101st insert, then grown to 100 by the end.
        assert len(pm._operation_times["search"]) <= 100

    def test_get_performance_stats_returns_expected_keys(self):
        """get_performance_stats returns cache, operations, and system keys."""
        pm = PerformanceManager()
        pm._record_operation_time("search", 0.1)
        stats = pm.get_performance_stats()

        assert "cache" in stats
        assert "operations" in stats
        assert "system" in stats
        assert "hits" in stats["cache"]
        assert "misses" in stats["cache"]
        assert "search" in stats["operations"]
        assert "memory_usage_mb" in stats["system"]

    @pytest.mark.asyncio
    async def test_invalidate_pattern(self):
        """invalidate_pattern removes matching cache entries."""
        pm = PerformanceManager()
        # Populate cache
        await pm.cache.set("abc123", "value1")
        await pm.cache.set("abc456", "value2")
        await pm.cache.set("xyz789", "value3")

        removed = await pm.invalidate_pattern("abc")
        assert removed == 2

    @pytest.mark.asyncio
    async def test_initialize_and_shutdown(self):
        """PerformanceManager initialize/shutdown lifecycle completes."""
        pm = PerformanceManager()
        await pm.initialize()
        await pm.shutdown()


# ---------------------------------------------------------------------------
# EnhancedPerformanceManager tests
# ---------------------------------------------------------------------------

class TestEnhancedPerformanceManager:
    """Tests for the EnhancedPerformanceManager class."""

    def test_init_with_configs(self):
        """EnhancedPerformanceManager accepts all config objects."""
        epm = EnhancedPerformanceManager(
            cache_config=CacheConfig(),
            concurrency_config=ConcurrencyConfig(),
            streaming_config=StreamingConfig(),
            memory_config=MemoryConfig(),
            metrics_config=MetricsConfig(),
        )
        assert isinstance(epm.config, CacheConfig)
        assert isinstance(epm._concurrency_config, ConcurrencyConfig)
        assert isinstance(epm._streaming_config, StreamingConfig)
        assert isinstance(epm._memory_config, MemoryConfig)
        assert isinstance(epm._metrics_config, MetricsConfig)
        # Sub-managers are None until start() is called
        assert epm._streaming_manager is None
        assert epm._memory_monitor is None
        assert epm._metrics_collector is None

    def test_init_default_optional_configs(self):
        """EnhancedPerformanceManager provides defaults for optional configs."""
        epm = EnhancedPerformanceManager(
            cache_config=CacheConfig(),
            concurrency_config=ConcurrencyConfig(),
        )
        assert isinstance(epm._streaming_config, StreamingConfig)
        assert isinstance(epm._memory_config, MemoryConfig)
        assert isinstance(epm._metrics_config, MetricsConfig)

    @pytest.mark.asyncio
    async def test_start_and_shutdown_lifecycle(self):
        """start() initialises sub-managers; shutdown() cleans up."""
        epm = EnhancedPerformanceManager(
            cache_config=CacheConfig(),
            concurrency_config=ConcurrencyConfig(),
            memory_config=MemoryConfig(
                enable_detailed_monitoring=False,
                enable_leak_detection=False,
                enable_tracemalloc=False,
                gc_threshold_adjustment=False,
            ),
        )

        await epm.start()

        # After start, sub-managers should be initialised
        assert epm._streaming_manager is not None
        assert epm._memory_monitor is not None
        assert epm._metrics_collector is not None
        assert len(epm._monitoring_tasks) == 2

        await epm.shutdown()

        # After shutdown all tasks should be done
        for task in epm._monitoring_tasks:
            assert task.done()

    @pytest.mark.asyncio
    async def test_start_sets_global_singletons(self):
        """start() registers sub-managers in global singletons."""
        epm = EnhancedPerformanceManager(
            cache_config=CacheConfig(),
            concurrency_config=ConcurrencyConfig(),
            memory_config=MemoryConfig(
                enable_detailed_monitoring=False,
                enable_leak_detection=False,
                enable_tracemalloc=False,
                gc_threshold_adjustment=False,
            ),
        )

        await epm.start()

        assert get_streaming_manager() is epm._streaming_manager
        assert get_memory_monitor() is epm._memory_monitor
        assert get_metrics_collector() is epm._metrics_collector

        await epm.shutdown()

    def test_is_subclass_of_performance_manager(self):
        """EnhancedPerformanceManager inherits from PerformanceManager."""
        assert issubclass(EnhancedPerformanceManager, PerformanceManager)

    def test_get_concurrent_manager(self):
        """get_concurrent_manager returns the ConcurrentRequestManager."""
        epm = EnhancedPerformanceManager(
            cache_config=CacheConfig(),
            concurrency_config=ConcurrencyConfig(),
        )
        cm = epm.get_concurrent_manager()
        assert isinstance(cm, ConcurrentRequestManager)


# ---------------------------------------------------------------------------
# Global accessor tests
# ---------------------------------------------------------------------------

class TestGlobalAccessors:
    """Tests for module-level get/set functions."""

    def test_get_global_performance_manager_creates_default(self):
        """get_global_performance_manager creates a default instance if None."""
        import ast_grep_mcp.performance as perf_mod

        # Reset global
        original = perf_mod._global_performance_manager
        perf_mod._global_performance_manager = None
        try:
            pm = get_global_performance_manager()
            assert isinstance(pm, PerformanceManager)
            # Subsequent calls return the same instance
            assert get_global_performance_manager() is pm
        finally:
            perf_mod._global_performance_manager = original

    def test_set_global_performance_manager(self):
        """set_global_performance_manager replaces the global instance."""
        import ast_grep_mcp.performance as perf_mod

        original = perf_mod._global_performance_manager
        try:
            custom = PerformanceManager(CacheConfig(max_entries=5))
            set_global_performance_manager(custom)
            assert get_global_performance_manager() is custom
        finally:
            perf_mod._global_performance_manager = original

    def test_get_performance_manager_returns_none_initially(self):
        """get_performance_manager returns None when nothing has been set."""
        import ast_grep_mcp.performance as perf_mod

        original = perf_mod._performance_manager
        perf_mod._performance_manager = None
        try:
            assert get_performance_manager() is None
        finally:
            perf_mod._performance_manager = original


# ---------------------------------------------------------------------------
# Re-export smoke tests
# ---------------------------------------------------------------------------

class TestReExports:
    """Verify that all sub-module symbols are accessible from performance.py."""

    def test_cache_symbols(self):
        assert CacheConfig is not None
        assert CacheEntry is not None
        assert CacheStatistics is not None
        assert AsyncLRUCache is not None

    def test_metrics_symbols(self):
        assert MetricsConfig is not None
        assert OperationMetrics is not None
        assert PerformanceMetricsCollector is not None
        assert callable(get_metrics_collector)
        assert callable(set_metrics_collector)

    def test_monitoring_symbols(self):
        assert MemoryConfig is not None
        assert MemorySnapshot is not None
        assert MemoryAlert is not None
        assert MemoryMonitor is not None
        assert callable(get_memory_monitor)
        assert callable(set_memory_monitor)

    def test_concurrency_symbols(self):
        assert ConcurrencyConfig is not None
        assert RequestPriority is not None
        assert QueuedRequest is not None
        assert DistributedLock is not None
        assert ConcurrentRequestManager is not None

    def test_streaming_symbols(self):
        assert StreamingConfig is not None
        assert StreamingManager is not None
        assert callable(get_streaming_manager)
        assert callable(set_streaming_manager)

    def test_type_aliases(self):
        # CacheKey and CacheValue are simple type aliases
        assert CacheKey is str
