"""Comprehensive tests for the monitoring module."""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ast_grep_mcp.monitoring import (
    MemoryAlert,
    MemoryConfig,
    MemoryMonitor,
    MemorySnapshot,
    get_memory_monitor,
    set_memory_monitor,
)


# ---------------------------------------------------------------------------
# MemoryConfig tests
# ---------------------------------------------------------------------------

class TestMemoryConfig:
    """Tests for MemoryConfig dataclass."""

    def test_default_values(self):
        config = MemoryConfig()
        assert config.enable_detailed_monitoring is True
        assert config.enable_leak_detection is True
        assert config.enable_tracemalloc is False
        assert config.tracemalloc_limit == 10
        assert config.warning_threshold_mb == 512
        assert config.critical_threshold_mb == 1024
        assert config.max_memory_mb == 2048
        assert config.monitoring_interval == 60
        assert config.leak_check_interval == 600
        assert config.gc_optimization_interval == 120
        assert config.enable_aggressive_gc is False
        assert config.gc_threshold_adjustment is True
        assert config.enable_memory_alerts is True
        assert config.alert_cooldown == 300

    def test_custom_values(self):
        config = MemoryConfig(
            enable_detailed_monitoring=False,
            enable_leak_detection=False,
            enable_tracemalloc=True,
            tracemalloc_limit=25,
            warning_threshold_mb=256,
            critical_threshold_mb=512,
            max_memory_mb=1024,
            monitoring_interval=30,
            leak_check_interval=300,
            gc_optimization_interval=60,
            enable_aggressive_gc=True,
            gc_threshold_adjustment=False,
            enable_memory_alerts=False,
            alert_cooldown=120,
        )
        assert config.enable_detailed_monitoring is False
        assert config.enable_leak_detection is False
        assert config.enable_tracemalloc is True
        assert config.tracemalloc_limit == 25
        assert config.warning_threshold_mb == 256
        assert config.critical_threshold_mb == 512
        assert config.max_memory_mb == 1024
        assert config.monitoring_interval == 30
        assert config.leak_check_interval == 300
        assert config.gc_optimization_interval == 60
        assert config.enable_aggressive_gc is True
        assert config.gc_threshold_adjustment is False
        assert config.enable_memory_alerts is False
        assert config.alert_cooldown == 120


# ---------------------------------------------------------------------------
# MemorySnapshot tests
# ---------------------------------------------------------------------------

class TestMemorySnapshot:
    """Tests for MemorySnapshot dataclass."""

    def _make_snapshot(self, **overrides):
        defaults = dict(
            timestamp=1000.0,
            rss_mb=100.5,
            vms_mb=200.0,
            percent=5.2,
            available_mb=8000.0,
            python_objects=50000,
            gc_counts=(700, 10, 5),
            num_threads=4,
            num_fds=12,
        )
        defaults.update(overrides)
        return MemorySnapshot(**defaults)

    def test_field_presence(self):
        snap = self._make_snapshot()
        assert snap.timestamp == 1000.0
        assert snap.rss_mb == 100.5
        assert snap.vms_mb == 200.0
        assert snap.percent == 5.2
        assert snap.available_mb == 8000.0
        assert snap.python_objects == 50000
        assert snap.gc_counts == (700, 10, 5)
        assert snap.num_threads == 4
        assert snap.num_fds == 12
        assert snap.growth_rate_mb_per_min is None

    def test_growth_rate_optional(self):
        snap = self._make_snapshot(growth_rate_mb_per_min=3.5)
        assert snap.growth_rate_mb_per_min == 3.5

    def test_to_dict_keys(self):
        snap = self._make_snapshot()
        d = snap.to_dict()
        expected_keys = {
            'timestamp', 'rss_mb', 'vms_mb', 'percent', 'available_mb',
            'python_objects', 'gc_counts', 'num_threads', 'num_fds',
            'growth_rate_mb_per_min',
        }
        assert set(d.keys()) == expected_keys

    def test_to_dict_values(self):
        snap = self._make_snapshot(growth_rate_mb_per_min=1.2)
        d = snap.to_dict()
        assert d['timestamp'] == 1000.0
        assert d['rss_mb'] == 100.5
        assert d['vms_mb'] == 200.0
        assert d['percent'] == 5.2
        assert d['available_mb'] == 8000.0
        assert d['python_objects'] == 50000
        assert d['gc_counts'] == [700, 10, 5]  # tuple converted to list
        assert d['num_threads'] == 4
        assert d['num_fds'] == 12
        assert d['growth_rate_mb_per_min'] == 1.2

    def test_to_dict_gc_counts_is_list(self):
        snap = self._make_snapshot()
        d = snap.to_dict()
        assert isinstance(d['gc_counts'], list)


# ---------------------------------------------------------------------------
# MemoryAlert tests
# ---------------------------------------------------------------------------

class TestMemoryAlert:
    """Tests for MemoryAlert dataclass."""

    def _make_alert(self, **overrides):
        defaults = dict(
            alert_type='warning',
            timestamp=1000.0,
            current_usage_mb=600.0,
            threshold_mb=512.0,
            message='High memory usage',
            suggested_actions=['Clear caches', 'Force GC'],
        )
        defaults.update(overrides)
        return MemoryAlert(**defaults)

    def test_field_presence(self):
        alert = self._make_alert()
        assert alert.alert_type == 'warning'
        assert alert.timestamp == 1000.0
        assert alert.current_usage_mb == 600.0
        assert alert.threshold_mb == 512.0
        assert alert.message == 'High memory usage'
        assert alert.suggested_actions == ['Clear caches', 'Force GC']

    def test_to_dict_keys(self):
        alert = self._make_alert()
        d = alert.to_dict()
        expected_keys = {
            'alert_type', 'timestamp', 'current_usage_mb',
            'threshold_mb', 'message', 'suggested_actions',
        }
        assert set(d.keys()) == expected_keys

    def test_to_dict_values(self):
        alert = self._make_alert(alert_type='critical', current_usage_mb=1200.0)
        d = alert.to_dict()
        assert d['alert_type'] == 'critical'
        assert d['current_usage_mb'] == 1200.0
        assert d['threshold_mb'] == 512.0
        assert d['message'] == 'High memory usage'
        assert isinstance(d['suggested_actions'], list)


# ---------------------------------------------------------------------------
# MemoryMonitor tests
# ---------------------------------------------------------------------------

class TestMemoryMonitorInit:
    """Tests for MemoryMonitor initialization."""

    def test_init_with_default_config(self):
        config = MemoryConfig()
        monitor = MemoryMonitor(config)
        assert monitor.config is config
        assert monitor._snapshots == []
        assert monitor._alerts == []
        assert monitor._baseline_memory is None
        assert monitor._peak_memory == 0.0
        assert monitor._monitoring_task is None
        assert monitor._leak_detection_task is None
        assert monitor._gc_optimization_task is None

    def test_init_tracemalloc_disabled_by_default(self):
        config = MemoryConfig(enable_tracemalloc=False)
        monitor = MemoryMonitor(config)
        assert monitor.config.enable_tracemalloc is False

    def test_init_max_limits(self):
        config = MemoryConfig()
        monitor = MemoryMonitor(config)
        assert monitor._max_snapshots == 20
        assert monitor._max_alerts == 10
        assert monitor._max_leak_candidates == 20


class TestMemoryMonitorSnapshot:
    """Tests for MemoryMonitor._take_snapshot()."""

    @pytest.mark.asyncio
    async def test_take_snapshot_returns_memory_snapshot(self):
        config = MemoryConfig(
            enable_detailed_monitoring=True,
            enable_tracemalloc=False,
        )
        monitor = MemoryMonitor(config)
        snapshot = await monitor._take_snapshot()

        assert isinstance(snapshot, MemorySnapshot)
        assert snapshot.rss_mb > 0
        assert snapshot.vms_mb > 0
        assert snapshot.timestamp > 0
        assert snapshot.num_threads >= 1

    @pytest.mark.asyncio
    async def test_take_snapshot_records_in_history(self):
        config = MemoryConfig(enable_tracemalloc=False)
        monitor = MemoryMonitor(config)

        await monitor._take_snapshot()
        assert len(monitor._snapshots) == 1

        await monitor._take_snapshot()
        assert len(monitor._snapshots) == 2

    @pytest.mark.asyncio
    async def test_take_snapshot_updates_peak_memory(self):
        config = MemoryConfig(enable_tracemalloc=False)
        monitor = MemoryMonitor(config)

        snapshot = await monitor._take_snapshot()
        assert monitor._peak_memory == snapshot.rss_mb

    @pytest.mark.asyncio
    async def test_take_snapshot_calculates_growth_rate(self):
        config = MemoryConfig(enable_tracemalloc=False)
        monitor = MemoryMonitor(config)

        await monitor._take_snapshot()
        snapshot2 = await monitor._take_snapshot()
        # growth_rate_mb_per_min should be set since we have a prior snapshot
        assert snapshot2.growth_rate_mb_per_min is not None

    @pytest.mark.asyncio
    async def test_snapshot_limit_enforced(self):
        config = MemoryConfig(enable_tracemalloc=False)
        monitor = MemoryMonitor(config)
        monitor._max_snapshots = 5

        for _ in range(10):
            await monitor._take_snapshot()

        assert len(monitor._snapshots) <= 5

    @pytest.mark.asyncio
    async def test_take_snapshot_without_detailed_monitoring(self):
        config = MemoryConfig(
            enable_detailed_monitoring=False,
            enable_tracemalloc=False,
        )
        monitor = MemoryMonitor(config)
        snapshot = await monitor._take_snapshot()

        assert snapshot.python_objects == 0
        assert snapshot.gc_counts == (0, 0, 0)


class TestMemoryMonitorGetters:
    """Tests for MemoryMonitor getter methods."""

    @pytest.mark.asyncio
    async def test_get_current_usage_none_when_empty(self):
        config = MemoryConfig(enable_tracemalloc=False)
        monitor = MemoryMonitor(config)
        assert monitor.get_current_usage() is None

    @pytest.mark.asyncio
    async def test_get_current_usage_returns_latest(self):
        config = MemoryConfig(enable_tracemalloc=False)
        monitor = MemoryMonitor(config)
        await monitor._take_snapshot()
        usage = monitor.get_current_usage()
        assert isinstance(usage, MemorySnapshot)
        assert usage.rss_mb > 0

    @pytest.mark.asyncio
    async def test_get_memory_history_empty(self):
        config = MemoryConfig(enable_tracemalloc=False)
        monitor = MemoryMonitor(config)
        history = monitor.get_memory_history()
        assert history == []

    @pytest.mark.asyncio
    async def test_get_memory_history_with_limit(self):
        config = MemoryConfig(enable_tracemalloc=False)
        monitor = MemoryMonitor(config)
        for _ in range(5):
            await monitor._take_snapshot()

        history = monitor.get_memory_history(limit=3)
        assert len(history) == 3

    @pytest.mark.asyncio
    async def test_get_recent_alerts_empty(self):
        config = MemoryConfig(enable_tracemalloc=False)
        monitor = MemoryMonitor(config)
        alerts = monitor.get_recent_alerts()
        assert alerts == []

    @pytest.mark.asyncio
    async def test_get_memory_stats_empty(self):
        config = MemoryConfig(enable_tracemalloc=False)
        monitor = MemoryMonitor(config)
        stats = monitor.get_memory_stats()
        assert stats == {}

    @pytest.mark.asyncio
    async def test_get_memory_stats_with_data(self):
        config = MemoryConfig(enable_tracemalloc=False)
        monitor = MemoryMonitor(config)
        await monitor._take_snapshot()

        stats = monitor.get_memory_stats()
        assert 'current_usage_mb' in stats
        assert 'peak_usage_mb' in stats
        assert 'baseline_usage_mb' in stats
        assert 'average_usage_mb' in stats
        assert 'memory_pressure' in stats
        assert stats['memory_pressure'] == 'normal'  # should be normal in tests


class TestMemoryMonitorThresholds:
    """Tests for memory threshold checking."""

    @pytest.mark.asyncio
    async def test_warning_threshold_triggers_alert(self):
        config = MemoryConfig(
            enable_tracemalloc=False,
            warning_threshold_mb=1,  # extremely low so it triggers
            critical_threshold_mb=9999999,
            alert_cooldown=0,
        )
        monitor = MemoryMonitor(config)

        # Create a snapshot with high memory usage
        snapshot = MemorySnapshot(
            timestamp=time.time(),
            rss_mb=100.0,  # will exceed warning_threshold_mb=1
            vms_mb=200.0,
            percent=5.0,
            available_mb=8000.0,
            python_objects=1000,
            gc_counts=(0, 0, 0),
            num_threads=1,
            num_fds=0,
        )

        await monitor._check_memory_thresholds(snapshot)
        assert len(monitor._alerts) == 1
        assert monitor._alerts[0].alert_type == 'warning'

    @pytest.mark.asyncio
    async def test_critical_threshold_triggers_alert(self):
        config = MemoryConfig(
            enable_tracemalloc=False,
            warning_threshold_mb=1,
            critical_threshold_mb=2,  # extremely low so it triggers
            alert_cooldown=0,
        )
        monitor = MemoryMonitor(config)

        snapshot = MemorySnapshot(
            timestamp=time.time(),
            rss_mb=100.0,  # exceeds critical_threshold_mb=2
            vms_mb=200.0,
            percent=5.0,
            available_mb=8000.0,
            python_objects=1000,
            gc_counts=(0, 0, 0),
            num_threads=1,
            num_fds=0,
        )

        # Patch _emergency_memory_cleanup to avoid side effects
        monitor._emergency_memory_cleanup = AsyncMock()

        await monitor._check_memory_thresholds(snapshot)
        assert len(monitor._alerts) == 1
        assert monitor._alerts[0].alert_type == 'critical'

    @pytest.mark.asyncio
    async def test_alert_cooldown_suppresses_duplicate(self):
        config = MemoryConfig(
            enable_tracemalloc=False,
            warning_threshold_mb=1,
            critical_threshold_mb=9999999,
            alert_cooldown=9999,  # very long cooldown
        )
        monitor = MemoryMonitor(config)

        snapshot = MemorySnapshot(
            timestamp=time.time(),
            rss_mb=100.0,
            vms_mb=200.0,
            percent=5.0,
            available_mb=8000.0,
            python_objects=1000,
            gc_counts=(0, 0, 0),
            num_threads=1,
            num_fds=0,
        )

        await monitor._check_memory_thresholds(snapshot)
        await monitor._check_memory_thresholds(snapshot)

        # Only one alert because cooldown has not elapsed
        assert len(monitor._alerts) == 1


class TestMemoryMonitorGrowth:
    """Tests for memory growth detection."""

    @pytest.mark.asyncio
    async def test_no_alert_when_growth_is_none(self):
        config = MemoryConfig(enable_tracemalloc=False, alert_cooldown=0)
        monitor = MemoryMonitor(config)

        snapshot = MemorySnapshot(
            timestamp=time.time(),
            rss_mb=100.0,
            vms_mb=200.0,
            percent=5.0,
            available_mb=8000.0,
            python_objects=1000,
            gc_counts=(0, 0, 0),
            num_threads=1,
            num_fds=0,
            growth_rate_mb_per_min=None,
        )

        await monitor._check_memory_growth(snapshot)
        assert len(monitor._alerts) == 0

    @pytest.mark.asyncio
    async def test_rapid_growth_triggers_alert(self):
        config = MemoryConfig(enable_tracemalloc=False, alert_cooldown=0)
        monitor = MemoryMonitor(config)

        snapshot = MemorySnapshot(
            timestamp=time.time(),
            rss_mb=100.0,
            vms_mb=200.0,
            percent=5.0,
            available_mb=8000.0,
            python_objects=1000,
            gc_counts=(0, 0, 0),
            num_threads=1,
            num_fds=0,
            growth_rate_mb_per_min=60.0,  # exceeds 50 MB/min threshold
        )

        await monitor._check_memory_growth(snapshot)
        assert len(monitor._alerts) == 1
        assert monitor._alerts[0].alert_type == 'rapid_growth'


class TestMemoryMonitorPeakTracking:
    """Tests for peak memory tracking."""

    @pytest.mark.asyncio
    async def test_peak_memory_updated(self):
        config = MemoryConfig(enable_tracemalloc=False)
        monitor = MemoryMonitor(config)

        snap1 = await monitor._take_snapshot()
        peak_after_first = monitor._peak_memory

        # The peak should be at least as large as the first snapshot
        assert peak_after_first >= snap1.rss_mb

    @pytest.mark.asyncio
    async def test_peak_memory_never_decreases(self):
        config = MemoryConfig(enable_tracemalloc=False)
        monitor = MemoryMonitor(config)

        await monitor._take_snapshot()
        peak1 = monitor._peak_memory

        await monitor._take_snapshot()
        peak2 = monitor._peak_memory

        assert peak2 >= peak1


class TestMemoryMonitorLifecycle:
    """Tests for start/stop lifecycle."""

    @pytest.mark.asyncio
    async def test_start_creates_tasks_and_baseline(self):
        config = MemoryConfig(
            enable_tracemalloc=False,
            enable_detailed_monitoring=True,
            enable_leak_detection=True,
            gc_threshold_adjustment=True,
            monitoring_interval=3600,  # long interval so loop does not fire
            leak_check_interval=3600,
            gc_optimization_interval=3600,
        )
        monitor = MemoryMonitor(config)

        await monitor.start()

        try:
            assert monitor._monitoring_task is not None
            assert monitor._leak_detection_task is not None
            assert monitor._gc_optimization_task is not None
            assert monitor._baseline_memory is not None
            assert len(monitor._snapshots) >= 1
        finally:
            await monitor.stop()

    @pytest.mark.asyncio
    async def test_stop_cancels_tasks(self):
        config = MemoryConfig(
            enable_tracemalloc=False,
            enable_detailed_monitoring=True,
            enable_leak_detection=True,
            gc_threshold_adjustment=True,
            monitoring_interval=3600,
            leak_check_interval=3600,
            gc_optimization_interval=3600,
        )
        monitor = MemoryMonitor(config)

        await monitor.start()
        await monitor.stop()

        assert monitor._monitoring_task.done()
        assert monitor._leak_detection_task.done()
        assert monitor._gc_optimization_task.done()

    @pytest.mark.asyncio
    async def test_start_without_optional_features(self):
        config = MemoryConfig(
            enable_tracemalloc=False,
            enable_detailed_monitoring=False,
            enable_leak_detection=False,
            gc_threshold_adjustment=False,
        )
        monitor = MemoryMonitor(config)

        await monitor.start()

        try:
            assert monitor._monitoring_task is None
            assert monitor._leak_detection_task is None
            assert monitor._gc_optimization_task is None
            # Baseline should still be set from _take_snapshot
            assert monitor._baseline_memory is not None
        finally:
            await monitor.stop()


class TestMemoryMonitorForceCleanup:
    """Tests for force_cleanup method."""

    @pytest.mark.asyncio
    async def test_force_cleanup_returns_results(self):
        config = MemoryConfig(enable_tracemalloc=False)
        monitor = MemoryMonitor(config)

        results = await monitor.force_cleanup()

        assert 'objects_collected' in results
        assert 'memory_before_mb' in results
        assert 'memory_after_mb' in results
        assert 'memory_freed_mb' in results
        assert 'timestamp' in results
        assert isinstance(results['objects_collected'], int)
        assert results['memory_before_mb'] > 0


class TestMemoryMonitorShouldSendAlert:
    """Tests for _should_send_alert."""

    def test_returns_false_when_alerts_disabled(self):
        config = MemoryConfig(
            enable_tracemalloc=False,
            enable_memory_alerts=False,
        )
        monitor = MemoryMonitor(config)
        assert monitor._should_send_alert('warning', time.time()) is False

    def test_returns_true_first_time(self):
        config = MemoryConfig(
            enable_tracemalloc=False,
            enable_memory_alerts=True,
            alert_cooldown=300,
        )
        monitor = MemoryMonitor(config)
        assert monitor._should_send_alert('warning', time.time()) is True

    def test_returns_false_within_cooldown(self):
        config = MemoryConfig(
            enable_tracemalloc=False,
            enable_memory_alerts=True,
            alert_cooldown=300,
        )
        monitor = MemoryMonitor(config)
        now = time.time()
        monitor._should_send_alert('warning', now)
        assert monitor._should_send_alert('warning', now + 1) is False

    def test_returns_true_after_cooldown(self):
        config = MemoryConfig(
            enable_tracemalloc=False,
            enable_memory_alerts=True,
            alert_cooldown=10,
        )
        monitor = MemoryMonitor(config)
        now = time.time()
        monitor._should_send_alert('warning', now)
        assert monitor._should_send_alert('warning', now + 11) is True

    def test_different_alert_types_independent(self):
        config = MemoryConfig(
            enable_tracemalloc=False,
            enable_memory_alerts=True,
            alert_cooldown=9999,
        )
        monitor = MemoryMonitor(config)
        now = time.time()

        assert monitor._should_send_alert('warning', now) is True
        assert monitor._should_send_alert('critical', now) is True
        # But repeating warning should be suppressed
        assert monitor._should_send_alert('warning', now + 1) is False


class TestMemoryMonitorCheckMemoryAlerts:
    """Tests for the synchronous _check_memory_alerts method."""

    def test_critical_alert_generated(self):
        config = MemoryConfig(
            enable_tracemalloc=False,
            critical_threshold_mb=50,
            warning_threshold_mb=10,
            alert_cooldown=0,
        )
        monitor = MemoryMonitor(config)

        snapshot = MemorySnapshot(
            timestamp=time.time(),
            rss_mb=100.0,
            vms_mb=200.0,
            percent=5.0,
            available_mb=8000.0,
            python_objects=1000,
            gc_counts=(0, 0, 0),
            num_threads=1,
            num_fds=0,
        )

        monitor._check_memory_alerts(snapshot)
        assert len(monitor._alerts) == 1
        assert monitor._alerts[0].alert_type == 'critical_memory'

    def test_warning_alert_generated(self):
        config = MemoryConfig(
            enable_tracemalloc=False,
            critical_threshold_mb=9999999,
            warning_threshold_mb=10,
            alert_cooldown=0,
        )
        monitor = MemoryMonitor(config)

        snapshot = MemorySnapshot(
            timestamp=time.time(),
            rss_mb=100.0,
            vms_mb=200.0,
            percent=5.0,
            available_mb=8000.0,
            python_objects=1000,
            gc_counts=(0, 0, 0),
            num_threads=1,
            num_fds=0,
        )

        monitor._check_memory_alerts(snapshot)
        assert len(monitor._alerts) == 1
        assert monitor._alerts[0].alert_type == 'high_memory'

    def test_rapid_growth_alert(self):
        config = MemoryConfig(
            enable_tracemalloc=False,
            critical_threshold_mb=9999999,
            warning_threshold_mb=9999999,
            alert_cooldown=0,
        )
        monitor = MemoryMonitor(config)

        snapshot = MemorySnapshot(
            timestamp=time.time(),
            rss_mb=100.0,
            vms_mb=200.0,
            percent=5.0,
            available_mb=8000.0,
            python_objects=1000,
            gc_counts=(0, 0, 0),
            num_threads=1,
            num_fds=0,
            growth_rate_mb_per_min=150.0,  # exceeds 100 MB/min threshold
        )

        monitor._check_memory_alerts(snapshot)
        assert len(monitor._alerts) == 1
        assert monitor._alerts[0].alert_type == 'rapid_growth'

    def test_alert_limit_enforced(self):
        config = MemoryConfig(
            enable_tracemalloc=False,
            critical_threshold_mb=9999999,
            warning_threshold_mb=1,
            alert_cooldown=0,
        )
        monitor = MemoryMonitor(config)
        monitor._max_alerts = 3

        for i in range(10):
            snapshot = MemorySnapshot(
                timestamp=time.time() + i,
                rss_mb=100.0,
                vms_mb=200.0,
                percent=5.0,
                available_mb=8000.0,
                python_objects=1000,
                gc_counts=(0, 0, 0),
                num_threads=1,
                num_fds=0,
            )
            monitor._check_memory_alerts(snapshot)

        assert len(monitor._alerts) <= 3


class TestMemoryMonitorLeakHelpers:
    """Tests for leak detection helper methods."""

    def test_cleanup_leak_candidates_removes_old(self):
        config = MemoryConfig(enable_tracemalloc=False)
        monitor = MemoryMonitor(config)

        now = time.time()
        monitor._leak_candidates = {
            'old_key': {'last_seen': now - 7200, 'count': 1, 'size_mb': 5.0},
            'new_key': {'last_seen': now, 'count': 1, 'size_mb': 5.0},
        }

        monitor._cleanup_leak_candidates(now)
        assert 'old_key' not in monitor._leak_candidates
        assert 'new_key' in monitor._leak_candidates

    def test_evict_oldest_leak_candidate(self):
        config = MemoryConfig(enable_tracemalloc=False)
        monitor = MemoryMonitor(config)

        now = time.time()
        monitor._leak_candidates = {
            'oldest': {'last_seen': now - 100, 'count': 1, 'size_mb': 5.0},
            'newer': {'last_seen': now - 50, 'count': 1, 'size_mb': 5.0},
            'newest': {'last_seen': now, 'count': 1, 'size_mb': 5.0},
        }

        monitor._evict_oldest_leak_candidate()
        assert 'oldest' not in monitor._leak_candidates
        assert len(monitor._leak_candidates) == 2

    def test_evict_oldest_leak_candidate_empty(self):
        config = MemoryConfig(enable_tracemalloc=False)
        monitor = MemoryMonitor(config)
        monitor._leak_candidates = {}
        # Should not raise
        monitor._evict_oldest_leak_candidate()


# ---------------------------------------------------------------------------
# Global accessor tests
# ---------------------------------------------------------------------------

class TestGlobalAccessors:
    """Tests for get_memory_monitor / set_memory_monitor."""

    def test_get_set_round_trip(self):
        import ast_grep_mcp.monitoring as mod

        original = mod._memory_monitor
        try:
            config = MemoryConfig(enable_tracemalloc=False)
            monitor = MemoryMonitor(config)

            set_memory_monitor(monitor)
            assert get_memory_monitor() is monitor
        finally:
            mod._memory_monitor = original

    def test_initial_value_is_none(self):
        import ast_grep_mcp.monitoring as mod

        original = mod._memory_monitor
        try:
            mod._memory_monitor = None
            assert get_memory_monitor() is None
        finally:
            mod._memory_monitor = original

    def test_set_overwrites_previous(self):
        import ast_grep_mcp.monitoring as mod

        original = mod._memory_monitor
        try:
            config = MemoryConfig(enable_tracemalloc=False)
            m1 = MemoryMonitor(config)
            m2 = MemoryMonitor(config)

            set_memory_monitor(m1)
            assert get_memory_monitor() is m1

            set_memory_monitor(m2)
            assert get_memory_monitor() is m2
        finally:
            mod._memory_monitor = original
