"""Comprehensive tests for the metrics module."""

import time

import pytest

from ast_grep_mcp.metrics import (
    MetricsConfig,
    OperationMetrics,
    PerformanceMetricsCollector,
    get_metrics_collector,
    set_metrics_collector,
)


# ---------------------------------------------------------------------------
# MetricsConfig tests
# ---------------------------------------------------------------------------

class TestMetricsConfig:
    """Tests for MetricsConfig dataclass."""

    def test_default_values(self):
        config = MetricsConfig()
        assert config.enable_detailed_metrics is True
        assert config.enable_adaptive_timeouts is True
        assert config.metrics_window_size == 1000
        assert config.percentile_calculation_interval == 60
        assert config.latency_buckets == [1, 5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000]
        assert config.track_percentiles == [50, 90, 95, 99]
        assert config.base_timeout_ms == 10000
        assert config.min_timeout_ms == 1000
        assert config.max_timeout_ms == 60000
        assert config.timeout_percentile == 95
        assert config.timeout_safety_factor == 1.5
        assert config.enable_load_aware_timeouts is True
        assert config.cpu_threshold_high == 80.0
        assert config.memory_threshold_high == 85.0
        assert config.load_factor_high == 0.8
        assert config.load_factor_low == 1.2
        assert config.throughput_window_seconds == 60
        assert config.error_rate_window_seconds == 300

    def test_custom_values(self):
        config = MetricsConfig(
            enable_detailed_metrics=False,
            enable_adaptive_timeouts=False,
            metrics_window_size=500,
            percentile_calculation_interval=30,
            latency_buckets=[10, 50, 100],
            track_percentiles=[50, 99],
            base_timeout_ms=5000,
            min_timeout_ms=500,
            max_timeout_ms=30000,
            timeout_percentile=99,
            timeout_safety_factor=2.0,
            enable_load_aware_timeouts=False,
            cpu_threshold_high=90.0,
            memory_threshold_high=95.0,
            load_factor_high=0.5,
            load_factor_low=1.5,
            throughput_window_seconds=120,
            error_rate_window_seconds=600,
        )
        assert config.enable_detailed_metrics is False
        assert config.enable_adaptive_timeouts is False
        assert config.metrics_window_size == 500
        assert config.percentile_calculation_interval == 30
        assert config.latency_buckets == [10, 50, 100]
        assert config.track_percentiles == [50, 99]
        assert config.base_timeout_ms == 5000
        assert config.min_timeout_ms == 500
        assert config.max_timeout_ms == 30000
        assert config.timeout_percentile == 99
        assert config.timeout_safety_factor == 2.0
        assert config.enable_load_aware_timeouts is False
        assert config.cpu_threshold_high == 90.0
        assert config.memory_threshold_high == 95.0
        assert config.load_factor_high == 0.5
        assert config.load_factor_low == 1.5
        assert config.throughput_window_seconds == 120
        assert config.error_rate_window_seconds == 600

    def test_latency_buckets_are_independent_instances(self):
        """Each MetricsConfig instance should have its own latency_buckets list."""
        config_a = MetricsConfig()
        config_b = MetricsConfig()
        config_a.latency_buckets.append(99999)
        assert 99999 not in config_b.latency_buckets


# ---------------------------------------------------------------------------
# OperationMetrics tests
# ---------------------------------------------------------------------------

class TestOperationMetrics:
    """Tests for OperationMetrics dataclass."""

    def test_default_counters(self):
        metrics = OperationMetrics()
        assert metrics.total_requests == 0
        assert metrics.successful_requests == 0
        assert metrics.failed_requests == 0
        assert metrics.timeout_requests == 0
        assert metrics.average_latency_ms == 0.0
        assert metrics.current_throughput_rps == 0.0
        assert metrics.current_error_rate == 0.0
        assert metrics.current_timeout_ms == 10000
        assert len(metrics.latency_measurements) == 0
        assert len(metrics.latency_buckets) == 0
        assert len(metrics.current_percentiles) == 0
        assert len(metrics.request_timestamps) == 0

    def test_add_latency_bucket_new_bucket(self):
        metrics = OperationMetrics()
        metrics.add_latency_bucket(10.0)
        assert 10.0 in metrics.latency_buckets
        assert metrics.latency_buckets[10.0] == 1

    def test_add_latency_bucket_existing_bucket_increments(self):
        metrics = OperationMetrics()
        metrics.add_latency_bucket(10.0)
        metrics.add_latency_bucket(10.0)
        metrics.add_latency_bucket(10.0)
        assert metrics.latency_buckets[10.0] == 3

    def test_add_latency_bucket_enforces_max_limit(self):
        metrics = OperationMetrics()
        # Fill to max capacity (50 buckets)
        for i in range(50):
            metrics.add_latency_bucket(float(i))

        assert len(metrics.latency_buckets) == 50

        # Adding one more bucket should remove the largest existing one
        metrics.add_latency_bucket(999.0)
        assert len(metrics.latency_buckets) == 50
        assert 999.0 in metrics.latency_buckets
        # The largest bucket (49.0) should have been removed
        assert 49.0 not in metrics.latency_buckets

    def test_add_latency_bucket_at_max_removes_largest(self):
        """When at max capacity, adding a new bucket removes the one with the largest key."""
        metrics = OperationMetrics()
        for i in range(50):
            metrics.add_latency_bucket(float(i + 100))

        # Largest key is 149.0
        assert 149.0 in metrics.latency_buckets
        metrics.add_latency_bucket(50.0)
        assert 50.0 in metrics.latency_buckets
        assert 149.0 not in metrics.latency_buckets

    def test_cleanup_old_data_removes_old_timestamps(self):
        metrics = OperationMetrics()
        # Set last_cleanup to the past so cleanup actually runs
        metrics.last_cleanup = 0.0

        old_timestamp = time.time() - 7200  # 2 hours ago
        recent_timestamp = time.time() - 60  # 1 minute ago
        metrics.request_timestamps.append(old_timestamp)
        metrics.request_timestamps.append(recent_timestamp)

        metrics.cleanup_old_data()

        assert old_timestamp not in metrics.request_timestamps
        assert recent_timestamp in metrics.request_timestamps

    def test_cleanup_old_data_skips_when_recent(self):
        """cleanup_old_data should skip if called within 5 minutes of last cleanup."""
        metrics = OperationMetrics()
        # last_cleanup defaults to time.time(), so a recent call should skip
        old_timestamp = time.time() - 7200
        metrics.request_timestamps.append(old_timestamp)

        metrics.cleanup_old_data()

        # Should NOT have cleaned because last_cleanup is too recent
        assert old_timestamp in metrics.request_timestamps

    def test_cleanup_old_data_trims_excess_buckets(self):
        metrics = OperationMetrics()
        metrics.last_cleanup = 0.0

        # Add more than max buckets
        for i in range(60):
            metrics.latency_buckets[float(i)] = i + 1  # count = i+1

        assert len(metrics.latency_buckets) > 50

        metrics.cleanup_old_data()

        # Should keep only top 50 by count
        assert len(metrics.latency_buckets) <= 50

    def test_to_dict_serialization(self):
        metrics = OperationMetrics()
        metrics.total_requests = 100
        metrics.successful_requests = 95
        metrics.failed_requests = 5
        metrics.timeout_requests = 2
        metrics.current_percentiles = {50: 10.0, 95: 50.0, 99: 100.0}
        metrics.current_timeout_ms = 5000
        metrics.average_latency_ms = 25.0
        metrics.current_throughput_rps = 3.5
        metrics.current_error_rate = 0.05
        metrics.latency_buckets = {10.0: 40, 50.0: 30, 100.0: 25}

        result = metrics.to_dict()

        assert result['total_requests'] == 100
        assert result['successful_requests'] == 95
        assert result['failed_requests'] == 5
        assert result['timeout_requests'] == 2
        assert result['current_percentiles'] == {50: 10.0, 95: 50.0, 99: 100.0}
        assert result['current_timeout_ms'] == 5000
        assert result['average_latency_ms'] == 25.0
        assert result['current_throughput_rps'] == 3.5
        assert result['current_error_rate'] == 0.05
        assert result['latency_buckets'] == {10.0: 40, 50.0: 30, 100.0: 25}

    def test_to_dict_limits_latency_buckets_output(self):
        """to_dict should only include up to 20 latency buckets in its output."""
        metrics = OperationMetrics()
        for i in range(30):
            metrics.latency_buckets[float(i)] = i

        result = metrics.to_dict()
        assert len(result['latency_buckets']) <= 20


# ---------------------------------------------------------------------------
# PerformanceMetricsCollector tests
# ---------------------------------------------------------------------------

class TestPerformanceMetricsCollector:
    """Tests for PerformanceMetricsCollector."""

    def _make_collector(self, **config_overrides):
        config = MetricsConfig(**config_overrides)
        return PerformanceMetricsCollector(config)

    def test_record_operation_start_returns_context(self):
        collector = self._make_collector()
        ctx = collector.record_operation_start("search", "op-1", query="test")

        assert ctx['operation'] == "search"
        assert ctx['operation_id'] == "op-1"
        assert 'start_time' in ctx
        assert isinstance(ctx['start_time'], float)
        assert ctx['metadata'] == {'query': 'test'}

    def test_record_operation_start_increments_total_requests(self):
        collector = self._make_collector()
        collector.record_operation_start("search", "op-1")
        collector.record_operation_start("search", "op-2")

        metrics = collector.get_operation_metrics("search")
        assert metrics is not None
        assert metrics['total_requests'] == 2

    def test_record_operation_complete_updates_metrics_success(self):
        collector = self._make_collector()
        ctx = collector.record_operation_start("search", "op-1")
        collector.record_operation_end(ctx, success=True)

        metrics = collector.get_operation_metrics("search")
        assert metrics is not None
        assert metrics['successful_requests'] == 1
        assert metrics['failed_requests'] == 0
        assert metrics['average_latency_ms'] >= 0

    def test_record_operation_complete_updates_metrics_failure(self):
        collector = self._make_collector()
        ctx = collector.record_operation_start("search", "op-1")
        collector.record_operation_end(ctx, success=False)

        metrics = collector.get_operation_metrics("search")
        assert metrics is not None
        assert metrics['successful_requests'] == 0
        assert metrics['failed_requests'] == 1

    def test_record_operation_complete_tracks_timeout(self):
        collector = self._make_collector()
        ctx = collector.record_operation_start("search", "op-1")
        collector.record_operation_end(ctx, success=False, error_type='timeout')

        metrics = collector.get_operation_metrics("search")
        assert metrics is not None
        assert metrics['timeout_requests'] == 1
        assert metrics['failed_requests'] == 1

    def test_get_operation_metrics_returns_correct_data(self):
        collector = self._make_collector()
        # Record some operations
        for i in range(5):
            ctx = collector.record_operation_start("scan", f"op-{i}")
            collector.record_operation_end(ctx, success=True)

        result = collector.get_operation_metrics("scan")
        assert result is not None
        assert result['total_requests'] == 5
        assert result['successful_requests'] == 5
        assert result['failed_requests'] == 0
        assert result['timeout_requests'] == 0
        assert result['average_latency_ms'] >= 0
        assert 'current_percentiles' in result
        assert 'latency_buckets' in result

    def test_get_operation_metrics_returns_none_for_unknown(self):
        collector = self._make_collector()
        assert collector.get_operation_metrics("nonexistent") is None

    def test_get_timeout_for_operation_returns_positive(self):
        collector = self._make_collector()
        timeout = collector.get_timeout_for_operation("search")
        assert timeout > 0
        # Default base_timeout_ms is 10000, so timeout in seconds should be 10.0
        assert timeout == 10.0

    def test_get_timeout_for_operation_existing_operation(self):
        collector = self._make_collector()
        ctx = collector.record_operation_start("search", "op-1")
        collector.record_operation_end(ctx, success=True)

        timeout = collector.get_timeout_for_operation("search")
        assert timeout > 0
        assert isinstance(timeout, float)

    def test_update_system_metrics_does_not_raise(self):
        collector = self._make_collector()
        collector.update_system_metrics(
            cpu_usage=55.0,
            memory_usage=70.0,
            active_requests=10,
            queue_length=5
        )
        # Verify system metrics were actually stored
        all_metrics = collector.get_all_metrics()
        assert all_metrics['system_metrics']['cpu_usage'] == 55.0
        assert all_metrics['system_metrics']['memory_usage'] == 70.0
        assert all_metrics['system_metrics']['active_requests'] == 10
        assert all_metrics['system_metrics']['queue_length'] == 5

    def test_cleanup_old_data_works(self):
        collector = self._make_collector()
        # Record an operation so there's data to clean
        ctx = collector.record_operation_start("search", "op-1")
        collector.record_operation_end(ctx, success=True)

        # Force cleanup by setting the last cleanup time far in the past
        collector._last_cleanup_time = 0.0

        # Should not raise
        collector.cleanup_old_data()

    def test_cleanup_old_data_skips_when_recent(self):
        collector = self._make_collector()
        # _last_cleanup_time defaults to time.time(), so this should skip
        collector.cleanup_old_data()
        # No error means it successfully skipped

    def test_get_all_metrics_structure(self):
        collector = self._make_collector()
        ctx = collector.record_operation_start("search", "op-1")
        collector.record_operation_end(ctx, success=True)

        all_metrics = collector.get_all_metrics()
        assert 'timestamp' in all_metrics
        assert 'uptime_seconds' in all_metrics
        assert 'global_metrics' in all_metrics
        assert 'system_metrics' in all_metrics
        assert 'operations' in all_metrics
        assert 'config' in all_metrics

        gm = all_metrics['global_metrics']
        assert gm['total_requests'] == 1
        assert gm['successful_requests'] == 1
        assert gm['failed_requests'] == 0
        assert gm['timeout_requests'] == 0
        assert gm['global_error_rate'] == 0.0
        assert gm['global_timeout_rate'] == 0.0

    def test_get_all_metrics_multiple_operations(self):
        collector = self._make_collector()
        ctx1 = collector.record_operation_start("search", "op-1")
        collector.record_operation_end(ctx1, success=True)
        ctx2 = collector.record_operation_start("scan", "op-2")
        collector.record_operation_end(ctx2, success=False)

        all_metrics = collector.get_all_metrics()
        assert 'search' in all_metrics['operations']
        assert 'scan' in all_metrics['operations']
        assert all_metrics['global_metrics']['total_requests'] == 2
        assert all_metrics['global_metrics']['successful_requests'] == 1
        assert all_metrics['global_metrics']['failed_requests'] == 1

    def test_get_performance_summary_structure(self):
        collector = self._make_collector()
        ctx = collector.record_operation_start("search", "op-1")
        collector.record_operation_end(ctx, success=True)

        summary = collector.get_performance_summary()
        assert 'timestamp' in summary
        assert 'operations' in summary
        assert 'system_load' in summary

        assert 'search' in summary['operations']
        op_summary = summary['operations']['search']
        assert 'requests_per_second' in op_summary
        assert 'error_rate_percent' in op_summary
        assert 'average_latency_ms' in op_summary
        assert 'p95_latency_ms' in op_summary
        assert 'p99_latency_ms' in op_summary
        assert 'current_timeout_ms' in op_summary
        assert 'total_requests' in op_summary

    def test_load_aware_timeout_high_load(self):
        """Under high CPU load, timeouts should be reduced."""
        collector = self._make_collector()
        collector.update_system_metrics(
            cpu_usage=90.0, memory_usage=50.0,
            active_requests=0, queue_length=0
        )

        # Record enough operations to trigger percentile calculation
        for i in range(15):
            ctx = collector.record_operation_start("search", f"op-{i}")
            collector.record_operation_end(ctx, success=True)

        # Force percentile recalculation by resetting the timer
        collector._metrics["search"].last_percentile_calculation = 0.0
        ctx = collector.record_operation_start("search", "op-final")
        collector.record_operation_end(ctx, success=True)

        timeout = collector.get_timeout_for_operation("search")
        assert timeout > 0

    def test_load_aware_timeout_low_load(self):
        """Under low load, timeouts should be increased."""
        collector = self._make_collector()
        collector.update_system_metrics(
            cpu_usage=10.0, memory_usage=20.0,
            active_requests=0, queue_length=0
        )

        timeout = collector.get_timeout_for_operation("search")
        assert timeout > 0

    def test_record_operation_end_for_untracked_operation_is_noop(self):
        """record_operation_end should silently return if the operation is not tracked."""
        collector = self._make_collector()
        context = {
            'operation': 'untracked',
            'operation_id': 'op-1',
            'start_time': time.time(),
            'metadata': {}
        }
        # Should not raise
        collector.record_operation_end(context, success=True)
        assert collector.get_operation_metrics("untracked") is None

    def test_cleanup_scales_down_high_counters(self):
        """Cleanup should scale down counters when they exceed 1M requests."""
        collector = self._make_collector()
        # Manually inject a high-count operation
        ctx = collector.record_operation_start("heavy", "op-1")
        collector.record_operation_end(ctx, success=True)

        metrics_obj = collector._metrics["heavy"]
        metrics_obj.total_requests = 2000000
        metrics_obj.successful_requests = 1900000
        metrics_obj.failed_requests = 100000
        metrics_obj.timeout_requests = 50000

        # Force cleanup
        collector._last_cleanup_time = 0.0
        collector.cleanup_old_data()

        assert metrics_obj.total_requests == 200000
        assert metrics_obj.successful_requests == 190000
        assert metrics_obj.failed_requests == 10000
        assert metrics_obj.timeout_requests == 5000


# ---------------------------------------------------------------------------
# Global accessor tests
# ---------------------------------------------------------------------------

class TestGlobalAccessors:
    """Tests for get_metrics_collector / set_metrics_collector round-trip."""

    def setup_method(self):
        """Reset global state before each test."""
        set_metrics_collector(None)

    def teardown_method(self):
        """Reset global state after each test."""
        set_metrics_collector(None)

    def test_initial_state_is_none(self):
        assert get_metrics_collector() is None

    def test_set_and_get_round_trip(self):
        config = MetricsConfig()
        collector = PerformanceMetricsCollector(config)
        set_metrics_collector(collector)
        assert get_metrics_collector() is collector

    def test_reset_to_none(self):
        config = MetricsConfig()
        collector = PerformanceMetricsCollector(config)
        set_metrics_collector(collector)
        assert get_metrics_collector() is collector

        set_metrics_collector(None)
        assert get_metrics_collector() is None

    def test_replace_collector(self):
        config = MetricsConfig()
        collector_a = PerformanceMetricsCollector(config)
        collector_b = PerformanceMetricsCollector(config)

        set_metrics_collector(collector_a)
        assert get_metrics_collector() is collector_a

        set_metrics_collector(collector_b)
        assert get_metrics_collector() is collector_b
