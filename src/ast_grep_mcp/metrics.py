"""Performance metrics collection with adaptive timeout strategies."""

import logging
import statistics
import time
from collections import deque
from dataclasses import dataclass, field
from threading import RLock
from typing import Any, Dict, List, Optional


logger = logging.getLogger(__name__)


@dataclass
class MetricsConfig:
    """Configuration for performance metrics collection and adaptive timeouts."""

    # Metrics collection settings
    enable_detailed_metrics: bool = True
    enable_adaptive_timeouts: bool = True
    metrics_window_size: int = 1000           # Number of recent measurements to keep
    percentile_calculation_interval: int = 60  # Recalculate percentiles every N seconds

    # Latency tracking settings
    latency_buckets: List[float] = field(default_factory=lambda: [1, 5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000])  # ms
    track_percentiles: List[int] = field(default_factory=lambda: [50, 90, 95, 99])

    # Timeout adaptation settings
    base_timeout_ms: float = 10000            # Base timeout (10 seconds)
    min_timeout_ms: float = 1000              # Minimum timeout (1 second)
    max_timeout_ms: float = 60000             # Maximum timeout (60 seconds)
    timeout_percentile: int = 95              # Use P95 latency for timeout calculation
    timeout_safety_factor: float = 1.5       # Multiply P95 by this factor

    # System load adaptation settings
    enable_load_aware_timeouts: bool = True
    cpu_threshold_high: float = 80.0          # High CPU usage threshold (%)
    memory_threshold_high: float = 85.0       # High memory usage threshold (%)
    load_factor_high: float = 0.8             # Reduce timeout by this factor under high load
    load_factor_low: float = 1.2              # Increase timeout by this factor under low load

    # Throughput monitoring settings
    throughput_window_seconds: int = 60       # Calculate throughput over this window
    error_rate_window_seconds: int = 300      # Calculate error rate over this window


@dataclass
class OperationMetrics:
    """Metrics for a specific operation type."""

    # Counters
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    timeout_requests: int = 0

    # Latency tracking (reduced sizes to save memory)
    latency_measurements: deque = field(default_factory=lambda: deque(maxlen=100))  # Reduced from 500
    latency_buckets: Dict[float, int] = field(default_factory=dict)
    _max_latency_buckets: int = field(default=50, init=False)  # Limit bucket size

    # Computed metrics
    current_percentiles: Dict[int, float] = field(default_factory=dict)
    current_timeout_ms: float = 10000
    average_latency_ms: float = 0.0

    # Throughput tracking (reduced size to save memory)
    request_timestamps: deque = field(default_factory=lambda: deque(maxlen=200))  # Reduced from 1000
    current_throughput_rps: float = 0.0
    current_error_rate: float = 0.0

    # Timing and cleanup
    last_percentile_calculation: float = 0.0
    last_cleanup: float = field(default_factory=time.time, init=False)

    def add_latency_bucket(self, bucket: float) -> None:
        """Add to latency bucket with size limit enforcement."""
        if bucket not in self.latency_buckets:
            # If we're at max buckets, remove the largest bucket
            if len(self.latency_buckets) >= self._max_latency_buckets:
                largest_bucket = max(self.latency_buckets.keys())
                del self.latency_buckets[largest_bucket]
            self.latency_buckets[bucket] = 0
        self.latency_buckets[bucket] += 1

    def cleanup_old_data(self) -> None:
        """Clean up old data to prevent memory growth."""
        current_time = time.time()

        # Only cleanup every 5 minutes to avoid overhead
        if current_time - self.last_cleanup < 300:
            return

        # Clean old request timestamps (keep only last hour)
        cutoff_time = current_time - 3600  # 1 hour
        while self.request_timestamps and self.request_timestamps[0] < cutoff_time:
            self.request_timestamps.popleft()

        # Reset buckets if they get too large
        if len(self.latency_buckets) > self._max_latency_buckets:
            # Keep only the most frequently used buckets
            sorted_buckets = sorted(self.latency_buckets.items(), key=lambda x: x[1], reverse=True)
            self.latency_buckets = dict(sorted_buckets[:self._max_latency_buckets])

        self.last_cleanup = current_time

    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary."""
        return {
            'total_requests': self.total_requests,
            'successful_requests': self.successful_requests,
            'failed_requests': self.failed_requests,
            'timeout_requests': self.timeout_requests,
            'current_percentiles': self.current_percentiles,
            'current_timeout_ms': self.current_timeout_ms,
            'average_latency_ms': self.average_latency_ms,
            'current_throughput_rps': self.current_throughput_rps,
            'current_error_rate': self.current_error_rate,
            'latency_buckets': dict(list(self.latency_buckets.items())[:20])  # Limit output size
        }


class PerformanceMetricsCollector:
    """
    Advanced performance metrics collector with adaptive timeout strategies.

    Features:
    - Latency tracking with percentile calculations
    - Throughput monitoring and error rate analysis
    - Dynamic timeout adaptation based on historical performance
    - System load awareness for adaptive behavior
    - Per-operation metrics with histogram buckets
    """

    def __init__(self, config: MetricsConfig) -> None:
        self.config = config
        self._metrics: Dict[str, OperationMetrics] = {}
        self._lock = RLock()

        # System metrics
        self._system_metrics: Dict[str, float] = {
            'cpu_usage': 0.0,
            'memory_usage': 0.0,
            'active_requests': 0,
            'queue_length': 0
        }

        # Global metrics
        self._global_start_time = time.time()
        self._last_cleanup_time = time.time()

        logger.info(f"PerformanceMetricsCollector initialized with config: {config}")

    def record_operation_start(self, operation: str, operation_id: str, **metadata: Any) -> Dict[str, Any]:
        """Record the start of an operation and return context for tracking."""
        with self._lock:
            if operation not in self._metrics:
                self._metrics[operation] = OperationMetrics()

            metrics = self._metrics[operation]
            metrics.total_requests += 1

            # Add request timestamp for throughput calculation
            current_time = time.time()
            metrics.request_timestamps.append(current_time)

            # Return context for the operation
            return {
                'operation': operation,
                'operation_id': operation_id,
                'start_time': current_time,
                'metadata': metadata
            }

    def record_operation_end(self, context: Dict[str, Any], success: bool = True,
                             error_type: Optional[str] = None, **result_metadata: Any) -> None:
        """Record the completion of an operation."""
        operation = context['operation']
        start_time = context['start_time']
        end_time = time.time()
        duration_ms = (end_time - start_time) * 1000

        with self._lock:
            if operation not in self._metrics:
                return  # Operation not tracked

            metrics = self._metrics[operation]

            # Update counters
            if success:
                metrics.successful_requests += 1
            else:
                metrics.failed_requests += 1
                if error_type == 'timeout':
                    metrics.timeout_requests += 1

            # Record latency
            metrics.latency_measurements.append(duration_ms)

            # Update latency buckets using the new method with size limits
            for bucket in self.config.latency_buckets:
                if duration_ms <= bucket:
                    metrics.add_latency_bucket(bucket)
                    break

            # Update average latency
            if metrics.latency_measurements:
                metrics.average_latency_ms = statistics.mean(metrics.latency_measurements)

            # Periodically update computed metrics and cleanup
            current_time = time.time()
            if (current_time - metrics.last_percentile_calculation) >= self.config.percentile_calculation_interval:
                self._update_computed_metrics(operation)
                metrics.last_percentile_calculation = current_time

            # Cleanup old data periodically
            metrics.cleanup_old_data()

    def _update_computed_metrics(self, operation: str) -> None:
        """Update computed metrics like percentiles, throughput, and timeouts."""
        metrics = self._metrics[operation]
        current_time = time.time()

        # Calculate percentiles
        if metrics.latency_measurements:
            sorted_latencies = sorted(metrics.latency_measurements)
            for percentile in self.config.track_percentiles:
                index = int((percentile / 100.0) * len(sorted_latencies))
                index = max(0, min(index - 1, len(sorted_latencies) - 1))
                metrics.current_percentiles[percentile] = sorted_latencies[index]

        # Calculate throughput (requests per second)
        throughput_window_start = current_time - self.config.throughput_window_seconds
        recent_requests = [ts for ts in metrics.request_timestamps if ts >= throughput_window_start]
        metrics.current_throughput_rps = len(recent_requests) / self.config.throughput_window_seconds

        # Calculate error rate
        error_window_start = current_time - self.config.error_rate_window_seconds
        recent_total = len([ts for ts in metrics.request_timestamps if ts >= error_window_start])
        recent_errors = metrics.failed_requests  # Simplified - could track per-window
        if recent_total > 0:
            metrics.current_error_rate = recent_errors / recent_total
        else:
            metrics.current_error_rate = 0.0

        # Update adaptive timeout
        if self.config.enable_adaptive_timeouts:
            metrics.current_timeout_ms = self._calculate_adaptive_timeout(operation)

    def _calculate_adaptive_timeout(self, operation: str) -> float:
        """Calculate adaptive timeout based on historical performance and system load."""
        metrics = self._metrics[operation]

        # Start with base timeout
        timeout_ms = self.config.base_timeout_ms

        # Use percentile-based calculation if we have enough data
        if (self.config.timeout_percentile in metrics.current_percentiles and
                len(metrics.latency_measurements) >= 10):

            percentile_latency = metrics.current_percentiles[self.config.timeout_percentile]
            timeout_ms = percentile_latency * self.config.timeout_safety_factor

        # Adjust based on system load
        if self.config.enable_load_aware_timeouts:
            timeout_ms = self._adjust_timeout_for_load(timeout_ms)

        # Apply min/max bounds
        timeout_ms = max(self.config.min_timeout_ms, min(timeout_ms, self.config.max_timeout_ms))

        return timeout_ms

    def _adjust_timeout_for_load(self, base_timeout_ms: float) -> float:
        """Adjust timeout based on current system load."""
        cpu_usage = self._system_metrics.get('cpu_usage', 0.0)
        memory_usage = self._system_metrics.get('memory_usage', 0.0)

        # Under high load, reduce timeouts to fail fast
        if (cpu_usage > self.config.cpu_threshold_high or
                memory_usage > self.config.memory_threshold_high):
            return base_timeout_ms * self.config.load_factor_high

        # Under low load, allow longer timeouts
        elif cpu_usage < 50.0 and memory_usage < 50.0:
            return base_timeout_ms * self.config.load_factor_low

        # Normal load, use base timeout
        return base_timeout_ms

    def update_system_metrics(self, cpu_usage: float, memory_usage: float,
                              active_requests: int, queue_length: int) -> None:
        """Update system-level metrics for load-aware timeout adaptation."""
        with self._lock:
            self._system_metrics.update({
                'cpu_usage': cpu_usage,
                'memory_usage': memory_usage,
                'active_requests': active_requests,
                'queue_length': queue_length
            })

    def get_timeout_for_operation(self, operation: str) -> float:
        """Get the current adaptive timeout for an operation in seconds."""
        with self._lock:
            if operation in self._metrics:
                return self._metrics[operation].current_timeout_ms / 1000.0
            return self.config.base_timeout_ms / 1000.0

    def get_operation_metrics(self, operation: str) -> Optional[Dict[str, Any]]:
        """Get comprehensive metrics for a specific operation."""
        with self._lock:
            if operation in self._metrics:
                return self._metrics[operation].to_dict()
            return None

    def get_all_metrics(self) -> Dict[str, Any]:
        """Get comprehensive metrics for all operations."""
        with self._lock:
            operations_metrics = {}
            for operation, metrics in self._metrics.items():
                operations_metrics[operation] = metrics.to_dict()

            # Calculate global metrics
            total_requests = sum(m.total_requests for m in self._metrics.values())
            total_successful = sum(m.successful_requests for m in self._metrics.values())
            total_failed = sum(m.failed_requests for m in self._metrics.values())
            total_timeouts = sum(m.timeout_requests for m in self._metrics.values())

            global_error_rate = total_failed / total_requests if total_requests > 0 else 0.0
            global_timeout_rate = total_timeouts / total_requests if total_requests > 0 else 0.0

            return {
                'timestamp': time.time(),
                'uptime_seconds': time.time() - self._global_start_time,
                'global_metrics': {
                    'total_requests': total_requests,
                    'successful_requests': total_successful,
                    'failed_requests': total_failed,
                    'timeout_requests': total_timeouts,
                    'global_error_rate': global_error_rate,
                    'global_timeout_rate': global_timeout_rate
                },
                'system_metrics': self._system_metrics.copy(),
                'operations': operations_metrics,
                'config': {
                    'adaptive_timeouts_enabled': self.config.enable_adaptive_timeouts,
                    'load_aware_timeouts_enabled': self.config.enable_load_aware_timeouts,
                    'base_timeout_ms': self.config.base_timeout_ms,
                    'timeout_percentile': self.config.timeout_percentile
                }
            }

    def get_performance_summary(self) -> Dict[str, Any]:
        """Get a concise performance summary suitable for monitoring dashboards."""
        with self._lock:
            operations_summary = {}

            for operation, metrics in self._metrics.items():
                # Get key metrics
                p95_latency = metrics.current_percentiles.get(95, 0)
                p99_latency = metrics.current_percentiles.get(99, 0)

                operations_summary[operation] = {
                    'requests_per_second': metrics.current_throughput_rps,
                    'error_rate_percent': metrics.current_error_rate * 100,
                    'average_latency_ms': metrics.average_latency_ms,
                    'p95_latency_ms': p95_latency,
                    'p99_latency_ms': p99_latency,
                    'current_timeout_ms': metrics.current_timeout_ms,
                    'total_requests': metrics.total_requests
                }

            return {
                'timestamp': time.time(),
                'operations': operations_summary,
                'system_load': {
                    'cpu_usage_percent': self._system_metrics.get('cpu_usage', 0),
                    'memory_usage_percent': self._system_metrics.get('memory_usage', 0),
                    'active_requests': self._system_metrics.get('active_requests', 0),
                    'queue_length': self._system_metrics.get('queue_length', 0)
                }
            }

    def cleanup_old_data(self) -> None:
        """Clean up old metrics data to prevent unbounded memory growth."""
        current_time = time.time()

        # Only run cleanup every 5 minutes to avoid overhead
        if current_time - self._last_cleanup_time < 300:
            return

        with self._lock:
            # Limit total number of operation types tracked (prevent unbounded growth)
            max_operations = 100  # Reasonable limit for operation types
            if len(self._metrics) > max_operations:
                # Remove least recently used operations
                sorted_ops = sorted(
                    self._metrics.items(),
                    key=lambda x: x[1].last_percentile_calculation
                )
                operations_to_remove = sorted_ops[:len(self._metrics) - max_operations]
                for op_name, _ in operations_to_remove:
                    del self._metrics[op_name]
                logger.info(f"Cleaned up {len(operations_to_remove)} old operation metrics")

            # Clean up individual operation metrics
            for operation, metrics in self._metrics.items():
                metrics.cleanup_old_data()

                # Reset excessive counters to prevent overflow
                if metrics.total_requests > 1000000:  # 1M requests
                    # Scale down all counters proportionally
                    scale_factor = 0.1
                    metrics.total_requests = int(metrics.total_requests * scale_factor)
                    metrics.successful_requests = int(metrics.successful_requests * scale_factor)
                    metrics.failed_requests = int(metrics.failed_requests * scale_factor)
                    metrics.timeout_requests = int(metrics.timeout_requests * scale_factor)
                    logger.info(f"Scaled down counters for operation {operation}")

        self._last_cleanup_time = current_time


# Global metrics collector instance
_metrics_collector: Optional[PerformanceMetricsCollector] = None


def get_metrics_collector() -> Optional[PerformanceMetricsCollector]:
    """Get the global metrics collector instance."""
    return _metrics_collector


def set_metrics_collector(collector: Optional[PerformanceMetricsCollector]) -> None:
    """Set the global metrics collector instance."""
    global _metrics_collector
    _metrics_collector = collector
