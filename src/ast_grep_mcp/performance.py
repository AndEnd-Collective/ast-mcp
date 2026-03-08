"""Performance management orchestrator for AST-Grep MCP Server.

This module provides the PerformanceManager and EnhancedPerformanceManager
classes that orchestrate caching, metrics, monitoring, concurrency, and
streaming sub-systems.

Sub-module symbols are re-exported for backward compatibility.
"""

import asyncio
import hashlib
import json
import logging
import time
from functools import wraps
from typing import Any, AsyncIterator, Callable, Dict, List, Optional, TypeVar

import psutil

# Re-export sub-module symbols for backward compatibility
from .cache import (  # noqa: F401
    CacheConfig,
    CacheEntry,
    CacheKey,
    CacheStatistics,
    CacheValue,
    AsyncLRUCache,
)
from .metrics import (  # noqa: F401
    MetricsConfig,
    OperationMetrics,
    PerformanceMetricsCollector,
    get_metrics_collector,
    set_metrics_collector,
)
from .monitoring import (  # noqa: F401
    MemoryConfig,
    MemorySnapshot,
    MemoryAlert,
    MemoryMonitor,
    get_memory_monitor,
    set_memory_monitor,
)
from .concurrency import (  # noqa: F401
    ConcurrencyConfig,
    RequestPriority,
    QueuedRequest,
    DistributedLock,
    ConcurrentRequestManager,
)
from .streaming import (  # noqa: F401
    StreamingConfig,
    StreamingManager,
    get_streaming_manager,
    set_streaming_manager,
)

T = TypeVar('T')

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# PerformanceManager
# ---------------------------------------------------------------------------

class PerformanceManager:
    """
    Central performance management system for AST-Grep MCP Server.

    Provides:
    - Result caching with configurable policies
    - Cache warming and preloading
    - Performance metrics collection
    - Memory usage optimization
    - Cache invalidation strategies
    """

    def __init__(self, config: Optional[CacheConfig] = None):
        self.config = config or CacheConfig()
        self.cache = AsyncLRUCache(self.config)

        # Performance metrics
        self._operation_times: Dict[str, List[float]] = {}
        self._operation_counts: Dict[str, int] = {}

        # Setup logging
        self.cache.add_event_listener(self._log_cache_events)

        logger.info("PerformanceManager initialized")

    async def initialize(self) -> None:
        """Initialize the performance manager and start background tasks."""
        await self.cache.load_from_disk()
        await self.cache.start_background_tasks()
        logger.info("PerformanceManager started")

    async def shutdown(self) -> None:
        """Shutdown the performance manager and cleanup resources."""
        await self.cache.stop_background_tasks()
        if self.config.enable_persistence:
            await self.cache._save_to_disk()
        logger.info("PerformanceManager shutdown")

    def cache_key(self, operation: str, **kwargs) -> str:
        """Generate a cache key for an operation with parameters.

        Args:
            operation: Operation name
            **kwargs: Operation parameters

        Returns:
            Cache key string
        """
        param_str = json.dumps(kwargs, sort_keys=True, default=str)
        key_data = f"{operation}:{param_str}"
        return hashlib.sha256(key_data.encode()).hexdigest()[:32]

    async def get_or_compute(
        self,
        operation: str,
        compute_func: Callable[[], Any],
        ttl: Optional[int] = None,
        group: Optional[str] = None,
        **kwargs
    ) -> Any:
        """Get result from cache or compute and cache it.

        Args:
            operation: Operation name for cache key generation
            compute_func: Function to compute result if not cached
            ttl: Cache TTL in seconds
            group: Invalidation group
            **kwargs: Parameters for cache key generation

        Returns:
            Cached or computed result
        """
        the_cache_key = self.cache_key(operation, **kwargs)

        # Try to get from cache first
        result = await self.cache.get(the_cache_key)

        if result is not None:
            return result

        # Compute result and cache it
        start_time = time.time()

        try:
            if asyncio.iscoroutinefunction(compute_func):
                result = await compute_func()
            else:
                result = compute_func()

            # Record performance metrics
            duration = time.time() - start_time
            self._record_operation_time(operation, duration)

            # Cache the result
            await self.cache.set(the_cache_key, result, ttl=ttl, group=group)

            return result

        except Exception:
            # Record failed operation
            duration = time.time() - start_time
            self._record_operation_time(f"{operation}_failed", duration)
            raise

    async def invalidate_pattern(self, pattern: str) -> int:
        """Invalidate cache entries matching a pattern.

        Args:
            pattern: Pattern to match against cache keys

        Returns:
            Number of entries invalidated
        """
        count = 0
        keys_to_remove = []

        with self.cache._lock:
            for key in self.cache._cache.keys():
                if pattern in key:
                    keys_to_remove.append(key)

        for key in keys_to_remove:
            if await self.cache.delete(key):
                count += 1

        return count

    def get_performance_metrics(self) -> Dict[str, Any]:
        """Get comprehensive performance metrics."""
        cache_stats = self.cache.get_statistics()

        # Calculate operation statistics
        operation_stats = {}
        for operation, times in self._operation_times.items():
            if times:
                operation_stats[operation] = {
                    "count": len(times),
                    "avg_time_ms": sum(times) * 1000 / len(times),
                    "min_time_ms": min(times) * 1000,
                    "max_time_ms": max(times) * 1000,
                    "total_time_ms": sum(times) * 1000
                }

        return {
            "cache": {
                "hits": cache_stats.hits,
                "misses": cache_stats.misses,
                "hit_rate": cache_stats.hit_rate,
                "total_entries": cache_stats.total_entries,
                "memory_mb": cache_stats.total_memory_bytes / 1024 / 1024,
                "evictions": cache_stats.evictions,
                "expired_evictions": cache_stats.expired_evictions
            },
            "operations": operation_stats,
            "system": {
                "memory_usage_mb": psutil.Process().memory_info().rss / 1024 / 1024,
                "cpu_percent": psutil.Process().cpu_percent()
            }
        }

    def get_performance_stats(self) -> Dict[str, Any]:
        """Get performance statistics (alias for get_performance_metrics)."""
        return self.get_performance_metrics()

    def _record_operation_time(self, operation: str, duration: float) -> None:
        """Record execution time for an operation."""
        if operation not in self._operation_times:
            self._operation_times[operation] = []
            self._operation_counts[operation] = 0

        self._operation_times[operation].append(duration)
        self._operation_counts[operation] += 1

        # Keep only last 100 measurements per operation to prevent memory growth
        if len(self._operation_times[operation]) > 100:
            self._operation_times[operation] = self._operation_times[operation][-50:]

    async def _log_cache_events(self, event_type: str, data: Any) -> None:
        """Log cache events for monitoring."""
        if event_type in ["cache_hit", "cache_miss"]:
            logger.debug(f"Cache {event_type}: {data}")
        else:
            logger.info(f"Cache {event_type}: {data}")


# ---------------------------------------------------------------------------
# cached decorator (PerformanceManager-aware version)
# ---------------------------------------------------------------------------

def cached(
    ttl: Optional[int] = None,
    group: Optional[str] = None,
    key_func: Optional[Callable[..., str]] = None,
    manager: Optional[PerformanceManager] = None
):
    """Decorator to cache function results.

    Args:
        ttl: Cache TTL in seconds
        group: Invalidation group
        key_func: Custom key generation function
        manager: Performance manager instance (uses global if None)
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def async_wrapper(*args, **kwargs) -> T:
            perf_manager = manager or get_global_performance_manager()

            if key_func:
                the_cache_key = key_func(*args, **kwargs)
            else:
                the_cache_key = perf_manager.cache_key(func.__name__, args=args, kwargs=kwargs)

            # Try cache first
            result = await perf_manager.cache.get(the_cache_key)
            if result is not None:
                return result

            # Compute and cache
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)

            await perf_manager.cache.set(the_cache_key, result, ttl=ttl, group=group)
            return result

        @wraps(func)
        def sync_wrapper(*args, **kwargs) -> T:
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(async_wrapper(*args, **kwargs))

        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper

    return decorator


# ---------------------------------------------------------------------------
# Global PerformanceManager accessors
# ---------------------------------------------------------------------------

_global_performance_manager: Optional[PerformanceManager] = None


def get_global_performance_manager() -> PerformanceManager:
    """Get or create the global performance manager instance."""
    global _global_performance_manager
    if _global_performance_manager is None:
        _global_performance_manager = PerformanceManager()
    return _global_performance_manager


def set_global_performance_manager(manager: PerformanceManager) -> None:
    """Set the global performance manager instance."""
    global _global_performance_manager
    _global_performance_manager = manager


# ---------------------------------------------------------------------------
# EnhancedPerformanceManager
# ---------------------------------------------------------------------------

class EnhancedPerformanceManager(PerformanceManager):
    """Enhanced PerformanceManager with concurrent request handling, rate limiting,
    result streaming, advanced memory monitoring, and comprehensive performance
    metrics collection with adaptive timeouts.
    """

    def __init__(
        self,
        cache_config: CacheConfig,
        concurrency_config: ConcurrencyConfig,
        streaming_config: Optional[StreamingConfig] = None,
        memory_config: Optional[MemoryConfig] = None,
        metrics_config: Optional[MetricsConfig] = None,
    ):
        super().__init__(cache_config)
        self._concurrency_config = concurrency_config
        self._concurrent_manager = ConcurrentRequestManager(concurrency_config)

        # Initialize streaming manager (created in start())
        self._streaming_config = streaming_config or StreamingConfig()
        self._streaming_manager: Optional[StreamingManager] = None

        # Initialize memory monitor (created in start())
        self._memory_config = memory_config or MemoryConfig()
        self._memory_monitor: Optional[MemoryMonitor] = None

        # Initialize performance metrics collector (created in start())
        self._metrics_config = metrics_config or MetricsConfig()
        self._metrics_collector: Optional[PerformanceMetricsCollector] = None

        # Background tasks
        self._monitoring_tasks: List[asyncio.Task] = []
        self._shutdown_event = asyncio.Event()

    async def start(self) -> None:
        """Start all performance management subsystems."""
        if self._streaming_manager is None:
            self._streaming_manager = StreamingManager(self._streaming_config)
            set_streaming_manager(self._streaming_manager)

        if self._memory_monitor is None:
            self._memory_monitor = MemoryMonitor(self._memory_config)
            set_memory_monitor(self._memory_monitor)

        if self._metrics_collector is None:
            self._metrics_collector = PerformanceMetricsCollector(self._metrics_config)
            set_metrics_collector(self._metrics_collector)

        await self._memory_monitor.start()

        # Start system metrics monitoring task
        monitoring_task = asyncio.create_task(self._system_metrics_monitoring_loop())
        self._monitoring_tasks.append(monitoring_task)

        # Start metrics cleanup task
        cleanup_task = asyncio.create_task(self._metrics_cleanup_loop())
        self._monitoring_tasks.append(cleanup_task)

        logger.info("Enhanced performance manager started with all subsystems")

    async def shutdown(self) -> None:
        """Shutdown all performance management subsystems."""
        self._shutdown_event.set()

        # Cancel monitoring tasks
        for task in self._monitoring_tasks:
            task.cancel()

        # Wait for tasks to complete
        if self._monitoring_tasks:
            await asyncio.gather(*self._monitoring_tasks, return_exceptions=True)

        if self._memory_monitor:
            await self._memory_monitor.stop()
        await super().shutdown()

        logger.info("Enhanced performance manager shutdown complete")

    async def _system_metrics_monitoring_loop(self) -> None:
        """Background task to update system metrics for load-aware behavior."""
        try:
            while not self._shutdown_event.is_set():
                try:
                    if not self._memory_monitor or not self._metrics_collector:
                        await asyncio.sleep(30)
                        continue

                    memory_snapshot = self._memory_monitor.get_current_usage()
                    cpu_usage = (
                        memory_snapshot.cpu_percent
                        if hasattr(memory_snapshot, 'cpu_percent')
                        else 0.0
                    )
                    memory_usage = memory_snapshot.percent

                    active_requests = (
                        len(self._concurrent_manager._active_requests)
                        if hasattr(self._concurrent_manager, '_active_requests')
                        else 0
                    )
                    queue_length = (
                        self._concurrent_manager._request_queue.qsize()
                        if hasattr(self._concurrent_manager, '_request_queue')
                        else 0
                    )

                    self._metrics_collector.update_system_metrics(
                        cpu_usage=cpu_usage,
                        memory_usage=memory_usage,
                        active_requests=active_requests,
                        queue_length=queue_length,
                    )

                    await asyncio.sleep(30)

                except Exception as e:
                    logger.error(f"Error in system metrics monitoring: {e}")
                    await asyncio.sleep(30)

        except asyncio.CancelledError:
            logger.info("System metrics monitoring task cancelled")

    async def _metrics_cleanup_loop(self) -> None:
        """Background task to clean up old metrics data."""
        try:
            while not self._shutdown_event.is_set():
                try:
                    if self._metrics_collector:
                        self._metrics_collector.cleanup_old_data()
                    await asyncio.sleep(300)
                except Exception as e:
                    logger.error(f"Error in metrics cleanup: {e}")
                    await asyncio.sleep(300)
        except asyncio.CancelledError:
            logger.info("Metrics cleanup task cancelled")

    async def get_or_compute_concurrent_with_metrics(
        self,
        cache_key: str,
        compute_func: Callable,
        operation: str,
        ttl: Optional[int] = None,
        priority: int = 5,
        timeout: Optional[float] = None,
        user_context: Optional[str] = None,
        **kwargs
    ) -> Any:
        """Enhanced get_or_compute_concurrent with metrics collection and adaptive timeouts."""
        operation_id = f"{operation}_{int(time.time() * 1000)}_{id(cache_key)}"

        metrics_context = self._metrics_collector.record_operation_start(
            operation=operation,
            operation_id=operation_id,
            cache_key=cache_key,
            user_context=user_context,
            priority=priority,
        )

        try:
            if timeout is None:
                timeout = self._metrics_collector.get_timeout_for_operation(operation)

            result = await self.get_or_compute_concurrent(
                cache_key=cache_key,
                compute_func=compute_func,
                ttl=ttl,
                priority=priority,
                timeout=timeout,
                user_context=user_context,
                **kwargs
            )

            self._metrics_collector.record_operation_end(
                context=metrics_context,
                success=True,
                result_size=len(str(result)) if result is not None else 0,
                cache_hit=(
                    cache_key in self._cache._data
                    if hasattr(self, '_cache') and hasattr(self._cache, '_data')
                    else False
                ),
            )

            return result

        except asyncio.TimeoutError as e:
            self._metrics_collector.record_operation_end(
                context=metrics_context,
                success=False,
                error_type='timeout',
            )
            logger.warning(f"Operation {operation} timed out after {timeout}s: {e}")
            raise

        except Exception as e:
            self._metrics_collector.record_operation_end(
                context=metrics_context,
                success=False,
                error_type=type(e).__name__,
            )
            logger.error(f"Operation {operation} failed: {e}")
            raise

    async def stream_large_results_concurrent_with_metrics(
        self,
        data_source: Any,
        operation: str,
        chunk_size: Optional[int] = None,
        user_context: Optional[str] = None,
        **kwargs
    ) -> AsyncIterator[Any]:
        """Enhanced streaming with performance metrics collection."""
        operation_id = f"stream_{operation}_{int(time.time() * 1000)}"

        metrics_context = self._metrics_collector.record_operation_start(
            operation=f"stream_{operation}",
            operation_id=operation_id,
            user_context=user_context,
        )

        chunk_count = 0
        total_items = 0

        try:
            if chunk_size is None:
                system_metrics = self._metrics_collector._system_metrics
                cpu_usage = system_metrics.get('cpu_usage', 0.0)
                memory_usage = system_metrics.get('memory_usage', 0.0)

                if cpu_usage > 80 or memory_usage > 80:
                    chunk_size = max(
                        self._streaming_config.min_chunk_size,
                        self._streaming_config.default_chunk_size // 2,
                    )
                else:
                    chunk_size = self._streaming_config.default_chunk_size

            async for chunk in self.stream_large_results_concurrent(
                data_source=data_source,
                chunk_size=chunk_size,
                user_context=user_context,
                **kwargs
            ):
                chunk_count += 1
                total_items += len(chunk) if hasattr(chunk, '__len__') else 1
                yield chunk

            self._metrics_collector.record_operation_end(
                context=metrics_context,
                success=True,
                chunk_count=chunk_count,
                total_items=total_items,
                final_chunk_size=chunk_size,
            )

        except Exception as e:
            self._metrics_collector.record_operation_end(
                context=metrics_context,
                success=False,
                error_type=type(e).__name__,
                chunk_count=chunk_count,
                total_items=total_items,
            )
            logger.error(f"Streaming operation {operation} failed: {e}")
            raise

    def get_metrics_collector(self) -> Optional[PerformanceMetricsCollector]:
        """Get the performance metrics collector instance."""
        return self._metrics_collector

    def get_memory_monitor(self) -> Optional[MemoryMonitor]:
        """Get the memory monitor instance."""
        return self._memory_monitor

    def get_streaming_manager(self) -> Optional[StreamingManager]:
        """Get the streaming manager instance."""
        return self._streaming_manager

    def get_concurrent_manager(self) -> ConcurrentRequestManager:
        """Get the concurrent request manager instance."""
        return self._concurrent_manager

    async def get_comprehensive_performance_report(self) -> Dict[str, Any]:
        """Get a comprehensive performance report combining all subsystems."""
        metrics_data = self._metrics_collector.get_all_metrics()
        memory_snapshot = self._memory_monitor.get_current_usage()
        cache_stats = self.get_cache_statistics()
        streaming_stats = self._streaming_manager.get_streaming_statistics()

        return {
            'timestamp': time.time(),
            'performance_metrics': metrics_data,
            'memory_monitoring': {
                'current_snapshot': memory_snapshot.to_dict() if memory_snapshot else {},
                'monitoring_enabled': self._memory_config.enable_detailed_monitoring,
                'leak_detection_enabled': self._memory_config.enable_leak_detection,
            },
            'cache_performance': cache_stats,
            'streaming_performance': streaming_stats,
            'concurrency_status': {
                'max_concurrent_requests': self._concurrency_config.max_concurrent_requests,
                'rate_limits': {
                    'global': self._concurrency_config.global_rate_limit,
                    'search': self._concurrency_config.search_rate_limit,
                    'scan': self._concurrency_config.scan_rate_limit,
                },
            },
            'system_health': {
                'memory_pressure': memory_snapshot.percent > 80 if memory_snapshot else False,
                'high_error_rate': (
                    metrics_data.get('global_metrics', {}).get('global_error_rate', 0) > 0.05
                ),
                'high_timeout_rate': (
                    metrics_data.get('global_metrics', {}).get('global_timeout_rate', 0) > 0.02
                ),
            },
            'adaptive_behavior': {
                'adaptive_timeouts_enabled': self._metrics_config.enable_adaptive_timeouts,
                'load_aware_timeouts_enabled': self._metrics_config.enable_load_aware_timeouts,
                'current_adaptive_timeouts': {
                    op: self._metrics_collector.get_timeout_for_operation(op)
                    for op in ['ast_grep_search', 'ast_grep_scan', 'ast_grep_run']
                },
            },
        }

    async def get_performance_dashboard_summary(self) -> Dict[str, Any]:
        """Get a concise performance summary suitable for dashboards."""
        return self._metrics_collector.get_performance_summary()

    async def force_comprehensive_cleanup(self) -> Dict[str, Any]:
        """Force comprehensive cleanup across all performance subsystems."""
        results = {}

        try:
            memory_cleanup = await self.force_memory_cleanup()
            results['memory_cleanup'] = memory_cleanup
        except Exception as e:
            results['memory_cleanup'] = {'error': str(e)}

        try:
            cache_cleanup = await self.force_cache_cleanup()
            results['cache_cleanup'] = cache_cleanup
        except Exception as e:
            results['cache_cleanup'] = {'error': str(e)}

        try:
            self._metrics_collector.cleanup_old_data()
            results['metrics_cleanup'] = {'status': 'completed'}
        except Exception as e:
            results['metrics_cleanup'] = {'error': str(e)}

        try:
            streaming_cleanup = await self._streaming_manager.cleanup_resources()
            results['streaming_cleanup'] = streaming_cleanup
        except Exception as e:
            results['streaming_cleanup'] = {'error': str(e)}

        return {
            'timestamp': time.time(),
            'comprehensive_cleanup_results': results,
            'overall_status': (
                'completed'
                if all('error' not in result for result in results.values())
                else 'partial_errors'
            ),
        }


# ---------------------------------------------------------------------------
# Module-level performance manager accessor (used by tools.py bottom)
# ---------------------------------------------------------------------------

_performance_manager = None


def get_performance_manager():
    """Get the global performance manager instance."""
    global _performance_manager
    return _performance_manager
