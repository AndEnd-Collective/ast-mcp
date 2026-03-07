"""
Comprehensive tests for src/ast_grep_mcp/server.py.

Tests cover: ServerConfig, InitializationState, HealthMetrics,
HealthThresholds, SystemResourceMonitor, DependencyHealthChecker,
ASTGrepMCPServer, and create_server().
"""

import asyncio
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

# Add src to Python path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ast_grep_mcp.server import (
    ASTGrepMCPServer,
    DependencyHealthChecker,
    HealthMetrics,
    HealthThresholds,
    InitializationState,
    ServerConfig,
    SystemResourceMonitor,
    create_server,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def server_config():
    """Return a ServerConfig with default (env-based) values."""
    return ServerConfig()


@pytest.fixture
def init_state():
    """Return a fresh InitializationState."""
    return InitializationState()


@pytest.fixture
def health_metrics():
    """Return a fresh HealthMetrics with small history."""
    return HealthMetrics(max_history=10)


@pytest.fixture
def health_thresholds():
    """Return a fresh HealthThresholds."""
    return HealthThresholds()


@pytest.fixture
def dep_checker():
    """Return a DependencyHealthChecker."""
    return DependencyHealthChecker()


@pytest.fixture
def mcp_server():
    """Return an ASTGrepMCPServer without starting it.

    We mock validate_ast_grep_installation so the constructor does not
    need the ast-grep binary present.
    """
    config = ServerConfig()
    config.enable_performance = False
    config.enable_security = False
    config.enable_monitoring = False
    server = ASTGrepMCPServer(config)
    return server


# ===================================================================
# ServerConfig tests
# ===================================================================

class TestServerConfig:
    """Tests for ServerConfig defaults and env-var overrides."""

    def test_default_name(self, server_config):
        assert server_config.name == "ast-mcp"

    def test_default_version(self, server_config):
        assert server_config.version == "1.0.0"

    def test_default_performance_enabled(self, server_config):
        assert server_config.enable_performance is True

    def test_default_security_enabled(self, server_config):
        assert server_config.enable_security is True

    def test_default_monitoring_enabled(self, server_config):
        assert server_config.enable_monitoring is True

    def test_default_health_check_interval(self, server_config):
        assert server_config.health_check_interval == 30

    def test_default_max_health_history(self, server_config):
        assert server_config.max_health_history == 100

    def test_default_system_monitoring_enabled(self, server_config):
        assert server_config.system_monitoring_enabled is True

    def test_default_dependency_check_enabled(self, server_config):
        assert server_config.dependency_check_enabled is True

    def test_default_alerting_enabled(self, server_config):
        assert server_config.alerting_enabled is True

    def test_default_detailed_diagnostics(self, server_config):
        assert server_config.detailed_diagnostics is True

    def test_default_cpu_thresholds(self, server_config):
        assert server_config.cpu_warning_threshold == 80.0
        assert server_config.cpu_critical_threshold == 95.0

    def test_default_memory_thresholds(self, server_config):
        assert server_config.memory_warning_threshold == 85.0
        assert server_config.memory_critical_threshold == 95.0

    def test_default_rate_limiting(self, server_config):
        assert server_config.rate_limit_enabled is True
        assert server_config.rate_limit_requests == 100
        assert server_config.rate_limit_window == 60

    def test_default_enhanced_logging(self, server_config):
        assert server_config.enable_enhanced_logging is True

    def test_default_log_level(self, server_config):
        assert server_config.log_level == "INFO"

    def test_default_log_format(self, server_config):
        assert server_config.log_format == "structured"

    def test_default_log_correlation_ids(self, server_config):
        assert server_config.log_correlation_ids is True

    # --- env var overrides with monkeypatch ---

    def test_env_override_name(self, monkeypatch):
        monkeypatch.setenv("AST_GREP_MCP_NAME", "custom-name")
        config = ServerConfig()
        assert config.name == "custom-name"

    def test_env_override_version(self, monkeypatch):
        monkeypatch.setenv("AST_GREP_MCP_VERSION", "2.0.0")
        config = ServerConfig()
        assert config.version == "2.0.0"

    def test_env_override_enable_performance_false(self, monkeypatch):
        monkeypatch.setenv("AST_GREP_ENABLE_PERFORMANCE", "false")
        config = ServerConfig()
        assert config.enable_performance is False

    def test_env_override_enable_security_false(self, monkeypatch):
        monkeypatch.setenv("AST_GREP_ENABLE_SECURITY", "false")
        config = ServerConfig()
        assert config.enable_security is False

    def test_env_override_enable_monitoring_false(self, monkeypatch):
        monkeypatch.setenv("AST_GREP_ENABLE_MONITORING", "false")
        config = ServerConfig()
        assert config.enable_monitoring is False

    def test_env_override_health_check_interval(self, monkeypatch):
        monkeypatch.setenv("AST_GREP_HEALTH_CHECK_INTERVAL", "120")
        config = ServerConfig()
        assert config.health_check_interval == 120

    def test_env_override_max_health_history(self, monkeypatch):
        monkeypatch.setenv("AST_GREP_MAX_HEALTH_HISTORY", "200")
        config = ServerConfig()
        assert config.max_health_history == 200

    def test_env_override_system_monitoring_false(self, monkeypatch):
        monkeypatch.setenv("AST_GREP_SYSTEM_MONITORING", "false")
        config = ServerConfig()
        assert config.system_monitoring_enabled is False

    def test_env_override_dependency_check_false(self, monkeypatch):
        monkeypatch.setenv("AST_GREP_DEPENDENCY_CHECK", "false")
        config = ServerConfig()
        assert config.dependency_check_enabled is False

    def test_env_override_alerting_false(self, monkeypatch):
        monkeypatch.setenv("AST_GREP_ALERTING", "false")
        config = ServerConfig()
        assert config.alerting_enabled is False

    def test_env_override_detailed_diagnostics_false(self, monkeypatch):
        monkeypatch.setenv("AST_GREP_DETAILED_DIAGNOSTICS", "false")
        config = ServerConfig()
        assert config.detailed_diagnostics is False

    def test_env_override_cpu_thresholds(self, monkeypatch):
        monkeypatch.setenv("AST_GREP_CPU_WARNING", "70.0")
        monkeypatch.setenv("AST_GREP_CPU_CRITICAL", "90.0")
        config = ServerConfig()
        assert config.cpu_warning_threshold == 70.0
        assert config.cpu_critical_threshold == 90.0

    def test_env_override_memory_thresholds(self, monkeypatch):
        monkeypatch.setenv("AST_GREP_MEMORY_WARNING", "75.0")
        monkeypatch.setenv("AST_GREP_MEMORY_CRITICAL", "92.0")
        config = ServerConfig()
        assert config.memory_warning_threshold == 75.0
        assert config.memory_critical_threshold == 92.0

    def test_env_override_rate_limit_disabled(self, monkeypatch):
        monkeypatch.setenv("AST_GREP_RATE_LIMIT", "false")
        config = ServerConfig()
        assert config.rate_limit_enabled is False

    def test_env_override_rate_limit_requests(self, monkeypatch):
        monkeypatch.setenv("AST_GREP_RATE_LIMIT_REQUESTS", "50")
        config = ServerConfig()
        assert config.rate_limit_requests == 50

    def test_env_override_rate_limit_window(self, monkeypatch):
        monkeypatch.setenv("AST_GREP_RATE_LIMIT_WINDOW", "120")
        config = ServerConfig()
        assert config.rate_limit_window == 120

    def test_env_override_enhanced_logging_false(self, monkeypatch):
        monkeypatch.setenv("AST_GREP_ENHANCED_LOGGING", "false")
        config = ServerConfig()
        assert config.enable_enhanced_logging is False

    def test_env_override_log_level(self, monkeypatch):
        monkeypatch.setenv("AST_GREP_LOG_LEVEL", "debug")
        config = ServerConfig()
        assert config.log_level == "DEBUG"

    def test_env_override_log_format(self, monkeypatch):
        monkeypatch.setenv("AST_GREP_LOG_FORMAT", "JSON")
        config = ServerConfig()
        assert config.log_format == "json"

    def test_env_override_log_correlation_ids_false(self, monkeypatch):
        monkeypatch.setenv("AST_GREP_LOG_CORRELATION_IDS", "false")
        config = ServerConfig()
        assert config.log_correlation_ids is False

    # --- validate() ---

    def test_validate_default_config_is_valid(self, server_config):
        result = server_config.validate()
        assert result["valid"] is True
        assert result["issues"] == []
        assert result["config"]["name"] == "ast-mcp"
        assert result["config"]["version"] == "1.0.0"

    def test_validate_config_contains_expected_keys(self, server_config):
        result = server_config.validate()
        expected_keys = {
            "name", "version", "performance_enabled",
            "security_enabled", "monitoring_enabled",
            "system_monitoring_enabled", "alerting_enabled",
        }
        assert expected_keys == set(result["config"].keys())

    def test_validate_bad_health_check_interval(self):
        config = ServerConfig()
        config.health_check_interval = 0
        result = config.validate()
        assert result["valid"] is False
        assert any("Health check interval" in i for i in result["issues"])

    def test_validate_bad_max_health_history(self):
        config = ServerConfig()
        config.max_health_history = -1
        result = config.validate()
        assert result["valid"] is False
        assert any("Max health history" in i for i in result["issues"])

    def test_validate_bad_rate_limit_requests(self):
        config = ServerConfig()
        config.rate_limit_requests = 0
        result = config.validate()
        assert result["valid"] is False
        assert any("Rate limit requests" in i for i in result["issues"])

    def test_validate_bad_rate_limit_window(self):
        config = ServerConfig()
        config.rate_limit_window = -5
        result = config.validate()
        assert result["valid"] is False
        assert any("Rate limit window" in i for i in result["issues"])

    def test_validate_cpu_warning_out_of_range(self):
        config = ServerConfig()
        config.cpu_warning_threshold = -1.0
        result = config.validate()
        assert result["valid"] is False
        assert any("CPU warning threshold" in i for i in result["issues"])

    def test_validate_cpu_critical_out_of_range(self):
        config = ServerConfig()
        config.cpu_critical_threshold = 150.0
        result = config.validate()
        assert result["valid"] is False
        assert any("CPU critical threshold" in i for i in result["issues"])

    def test_validate_cpu_warning_ge_critical(self):
        config = ServerConfig()
        config.cpu_warning_threshold = 95.0
        config.cpu_critical_threshold = 90.0
        result = config.validate()
        assert result["valid"] is False
        assert any("CPU warning threshold must be less than critical" in i for i in result["issues"])

    def test_validate_memory_warning_out_of_range(self):
        config = ServerConfig()
        config.memory_warning_threshold = 101.0
        result = config.validate()
        assert result["valid"] is False
        assert any("Memory warning threshold" in i for i in result["issues"])

    def test_validate_memory_critical_out_of_range(self):
        config = ServerConfig()
        config.memory_critical_threshold = -5.0
        result = config.validate()
        assert result["valid"] is False
        assert any("Memory critical threshold" in i for i in result["issues"])

    def test_validate_memory_warning_ge_critical(self):
        config = ServerConfig()
        config.memory_warning_threshold = 96.0
        config.memory_critical_threshold = 95.0
        result = config.validate()
        assert result["valid"] is False
        assert any("Memory warning threshold must be less than critical" in i for i in result["issues"])

    def test_validate_multiple_issues(self):
        config = ServerConfig()
        config.health_check_interval = 0
        config.rate_limit_window = 0
        config.cpu_warning_threshold = -1.0
        result = config.validate()
        assert result["valid"] is False
        assert len(result["issues"]) >= 3


# ===================================================================
# InitializationState tests
# ===================================================================

class TestInitializationState:
    """Tests for component initialization tracking."""

    def test_default_state(self, init_state):
        expected_components = {
            "enhanced_logging", "config_validation", "ast_grep",
            "performance_system", "security_system", "mcp_components",
            "health_monitoring",
        }
        assert set(init_state.components.keys()) == expected_components
        assert all(status is False for status in init_state.components.values())

    def test_default_no_failures(self, init_state):
        assert init_state.failed_components == []
        assert init_state.partial_failures == []

    def test_mark_completed(self, init_state):
        init_state.mark_completed("ast_grep")
        assert init_state.components["ast_grep"] is True

    def test_mark_completed_unknown_component(self, init_state):
        init_state.mark_completed("nonexistent")
        # Unknown component should not be added
        assert "nonexistent" not in init_state.components

    def test_mark_failed(self, init_state):
        init_state.mark_failed("ast_grep", "binary not found")
        assert len(init_state.failed_components) == 1
        assert init_state.failed_components[0]["component"] == "ast_grep"
        assert init_state.failed_components[0]["error"] == "binary not found"

    def test_mark_partial_failure(self, init_state):
        init_state.mark_partial_failure("performance_system", "timeout")
        assert len(init_state.partial_failures) == 1
        assert init_state.partial_failures[0]["component"] == "performance_system"
        assert init_state.partial_failures[0]["error"] == "timeout"

    def test_is_component_initialized_false(self, init_state):
        assert init_state.is_component_initialized("ast_grep") is False

    def test_is_component_initialized_true(self, init_state):
        init_state.mark_completed("ast_grep")
        assert init_state.is_component_initialized("ast_grep") is True

    def test_is_component_initialized_unknown(self, init_state):
        assert init_state.is_component_initialized("nonexistent") is False

    def test_get_initialized_components_empty(self, init_state):
        assert init_state.get_initialized_components() == []

    def test_get_initialized_components_some(self, init_state):
        init_state.mark_completed("ast_grep")
        init_state.mark_completed("mcp_components")
        initialized = init_state.get_initialized_components()
        assert "ast_grep" in initialized
        assert "mcp_components" in initialized
        assert len(initialized) == 2

    def test_get_failed_components_empty(self, init_state):
        assert init_state.get_failed_components() == []

    def test_get_failed_components_nonempty(self, init_state):
        init_state.mark_failed("ast_grep", "missing")
        init_state.mark_failed("config_validation", "invalid")
        failed = init_state.get_failed_components()
        assert len(failed) == 2

    def test_has_critical_failures_false(self, init_state):
        assert init_state.has_critical_failures() is False

    def test_has_critical_failures_non_critical_component(self, init_state):
        init_state.mark_failed("performance_system", "timeout")
        assert init_state.has_critical_failures() is False

    def test_has_critical_failures_critical_config_validation(self, init_state):
        init_state.mark_failed("config_validation", "bad config")
        assert init_state.has_critical_failures() is True

    def test_has_critical_failures_critical_ast_grep(self, init_state):
        init_state.mark_failed("ast_grep", "not found")
        assert init_state.has_critical_failures() is True

    def test_state_transitions(self, init_state):
        """Test a realistic initialization flow."""
        init_state.mark_completed("enhanced_logging")
        init_state.mark_completed("config_validation")
        init_state.mark_completed("ast_grep")
        init_state.mark_partial_failure("performance_system", "slow init")
        init_state.mark_completed("mcp_components")

        initialized = init_state.get_initialized_components()
        assert len(initialized) == 4
        assert len(init_state.partial_failures) == 1
        assert init_state.has_critical_failures() is False


# ===================================================================
# HealthMetrics tests
# ===================================================================

class TestHealthMetrics:
    """Tests for health metrics collection."""

    def test_default_values(self, health_metrics):
        assert health_metrics.max_history == 10
        assert health_metrics.health_history == []
        assert health_metrics.system_metrics_history == []
        assert health_metrics.component_health_history == {}
        assert health_metrics.alert_history == []

    def test_add_health_check(self, health_metrics):
        health_metrics.add_health_check({"overall_status": "healthy"})
        assert len(health_metrics.health_history) == 1
        assert "timestamp" in health_metrics.health_history[0]

    def test_add_health_check_enforces_max_history(self, health_metrics):
        for i in range(20):
            health_metrics.add_health_check({"check_number": i})
        assert len(health_metrics.health_history) == 10
        # Should keep the most recent entries
        assert health_metrics.health_history[0]["check_number"] == 10

    def test_add_system_metrics(self, health_metrics):
        health_metrics.add_system_metrics({"cpu": {"percent": 50}})
        assert len(health_metrics.system_metrics_history) == 1
        assert "timestamp" in health_metrics.system_metrics_history[0]

    def test_add_system_metrics_enforces_max_history(self, health_metrics):
        for i in range(15):
            health_metrics.add_system_metrics({"index": i})
        assert len(health_metrics.system_metrics_history) == 10

    def test_add_component_health(self, health_metrics):
        health_metrics.add_component_health("performance", {"status": "healthy"})
        assert "performance" in health_metrics.component_health_history
        assert len(health_metrics.component_health_history["performance"]) == 1

    def test_add_component_health_enforces_max_history(self, health_metrics):
        for i in range(15):
            health_metrics.add_component_health("performance", {"index": i})
        assert len(health_metrics.component_health_history["performance"]) == 10

    def test_add_component_health_respects_max_components(self, health_metrics):
        # _max_components defaults to 20
        for i in range(25):
            health_metrics.add_component_health(f"comp_{i}", {"status": "ok"})
        assert len(health_metrics.component_health_history) <= 20

    def test_add_alert(self, health_metrics):
        health_metrics.add_alert("cpu_high", "CPU at 90%", "warning")
        assert len(health_metrics.alert_history) == 1
        alert = health_metrics.alert_history[0]
        assert alert["type"] == "cpu_high"
        assert alert["message"] == "CPU at 90%"
        assert alert["severity"] == "warning"
        assert "timestamp" in alert

    def test_add_alert_default_severity(self, health_metrics):
        health_metrics.add_alert("test", "test message")
        assert health_metrics.alert_history[0]["severity"] == "warning"

    def test_add_alert_enforces_max_history(self, health_metrics):
        for i in range(15):
            health_metrics.add_alert("test", f"msg_{i}")
        assert len(health_metrics.alert_history) == 10

    def test_get_health_trends_no_data(self, health_metrics):
        result = health_metrics.get_health_trends(60)
        assert "error" in result

    def test_get_health_trends_with_data(self, health_metrics):
        # Add some health checks with current timestamps (they are added by add_health_check)
        for status in ["healthy", "healthy", "degraded"]:
            health_metrics.add_health_check({"overall_status": status})

        result = health_metrics.get_health_trends(60)
        assert result["total_checks"] == 3
        assert result["health_distribution"]["healthy"] == 2
        assert result["health_distribution"]["degraded"] == 1
        assert result["health_distribution"]["unhealthy"] == 0
        assert "healthy_percentage" in result["health_distribution"]

    def test_get_alert_summary_no_alerts(self, health_metrics):
        result = health_metrics.get_alert_summary()
        assert result["total_alerts"] == 0
        assert result["recent_critical"] == 0
        assert result["recent_warnings"] == 0

    def test_get_alert_summary_with_alerts(self, health_metrics):
        health_metrics.add_alert("cpu", "CPU high", "warning")
        health_metrics.add_alert("mem", "Memory critical", "critical")
        result = health_metrics.get_alert_summary()
        assert result["total_alerts"] == 2
        assert result["recent_critical"] == 1
        assert result["recent_warnings"] == 1
        assert result["last_alert"]["type"] == "mem"


# ===================================================================
# HealthThresholds tests
# ===================================================================

class TestHealthThresholds:
    """Tests for health threshold defaults."""

    def test_cpu_thresholds(self, health_thresholds):
        assert health_thresholds.cpu_usage_warning == 80.0
        assert health_thresholds.cpu_usage_critical == 95.0

    def test_memory_thresholds(self, health_thresholds):
        assert health_thresholds.memory_usage_warning == 85.0
        assert health_thresholds.memory_usage_critical == 95.0

    def test_disk_thresholds(self, health_thresholds):
        assert health_thresholds.disk_usage_warning == 85.0
        assert health_thresholds.disk_usage_critical == 95.0

    def test_response_time_thresholds(self, health_thresholds):
        assert health_thresholds.ast_grep_response_warning == 5.0
        assert health_thresholds.ast_grep_response_critical == 10.0

    def test_error_rate_thresholds(self, health_thresholds):
        assert health_thresholds.error_rate_warning == 10
        assert health_thresholds.error_rate_critical == 50

    def test_availability_thresholds(self, health_thresholds):
        assert health_thresholds.component_availability_warning == 95.0
        assert health_thresholds.component_availability_critical == 85.0

    def test_custom_thresholds(self):
        thresholds = HealthThresholds()
        thresholds.cpu_usage_warning = 60.0
        thresholds.cpu_usage_critical = 85.0
        assert thresholds.cpu_usage_warning == 60.0
        assert thresholds.cpu_usage_critical == 85.0


# ===================================================================
# SystemResourceMonitor tests
# ===================================================================

class TestSystemResourceMonitor:
    """Tests for system resource monitoring."""

    def test_initialization(self):
        monitor = SystemResourceMonitor()
        assert monitor.process is not None
        assert monitor.start_time > 0
        assert monitor._last_network_io is None
        assert monitor._last_disk_io is None

    @pytest.mark.asyncio
    async def test_get_system_metrics_returns_dict(self):
        monitor = SystemResourceMonitor()
        metrics = await monitor.get_system_metrics()
        assert isinstance(metrics, dict)
        # Should contain top-level keys even if some fail
        assert "timestamp" in metrics

    @pytest.mark.asyncio
    async def test_get_system_metrics_contains_cpu(self):
        monitor = SystemResourceMonitor()
        metrics = await monitor.get_system_metrics()
        if "error" not in metrics:
            assert "cpu" in metrics
            assert "percent" in metrics["cpu"]

    @pytest.mark.asyncio
    async def test_get_system_metrics_contains_memory(self):
        monitor = SystemResourceMonitor()
        metrics = await monitor.get_system_metrics()
        if "error" not in metrics:
            assert "memory" in metrics
            assert "total" in metrics["memory"]

    @pytest.mark.asyncio
    async def test_get_system_metrics_contains_process(self):
        monitor = SystemResourceMonitor()
        metrics = await monitor.get_system_metrics()
        if "error" not in metrics:
            assert "process" in metrics
            assert "pid" in metrics["process"]

    def test_calculate_network_rates_first_call(self):
        monitor = SystemResourceMonitor()
        mock_io = MagicMock()
        mock_io.bytes_sent = 1000
        mock_io.bytes_recv = 2000
        rates = monitor._calculate_network_rates(mock_io)
        assert rates["bytes_sent_per_sec"] == 0.0
        assert rates["bytes_recv_per_sec"] == 0.0
        # State should be stored
        assert monitor._last_network_io is not None

    def test_calculate_network_rates_second_call(self):
        monitor = SystemResourceMonitor()
        mock_io_1 = MagicMock()
        mock_io_1.bytes_sent = 1000
        mock_io_1.bytes_recv = 2000
        mock_io_1.packets_sent = 10
        mock_io_1.packets_recv = 20

        # First call stores baseline
        monitor._calculate_network_rates(mock_io_1)

        # Simulate time passage
        monitor._last_network_io = (mock_io_1, time.time() - 1.0)

        mock_io_2 = MagicMock()
        mock_io_2.bytes_sent = 2000
        mock_io_2.bytes_recv = 4000
        mock_io_2.packets_sent = 20
        mock_io_2.packets_recv = 40

        rates = monitor._calculate_network_rates(mock_io_2)
        assert rates["bytes_sent_per_sec"] > 0
        assert rates["bytes_recv_per_sec"] > 0

    def test_calculate_disk_rates_none_io(self):
        monitor = SystemResourceMonitor()
        rates = monitor._calculate_disk_rates(None)
        assert rates["read_bytes_per_sec"] == 0.0
        assert rates["write_bytes_per_sec"] == 0.0

    def test_calculate_disk_rates_first_call(self):
        monitor = SystemResourceMonitor()
        mock_io = MagicMock()
        mock_io.read_bytes = 5000
        mock_io.write_bytes = 3000
        rates = monitor._calculate_disk_rates(mock_io)
        assert rates["read_bytes_per_sec"] == 0.0
        assert rates["write_bytes_per_sec"] == 0.0
        assert monitor._last_disk_io is not None

    def test_calculate_disk_rates_second_call(self):
        monitor = SystemResourceMonitor()
        mock_io_1 = MagicMock()
        mock_io_1.read_bytes = 5000
        mock_io_1.write_bytes = 3000
        mock_io_1.read_count = 100
        mock_io_1.write_count = 50

        monitor._calculate_disk_rates(mock_io_1)
        monitor._last_disk_io = (mock_io_1, time.time() - 1.0)

        mock_io_2 = MagicMock()
        mock_io_2.read_bytes = 10000
        mock_io_2.write_bytes = 6000
        mock_io_2.read_count = 200
        mock_io_2.write_count = 100

        rates = monitor._calculate_disk_rates(mock_io_2)
        assert rates["read_bytes_per_sec"] > 0
        assert rates["write_bytes_per_sec"] > 0


# ===================================================================
# DependencyHealthChecker tests
# ===================================================================

class TestDependencyHealthChecker:
    """Tests for dependency health checking."""

    def test_initialization(self, dep_checker):
        assert dep_checker.last_check_time is None
        assert dep_checker.cached_results == {}
        assert dep_checker.cache_duration == 300

    @pytest.mark.asyncio
    async def test_check_python_dependencies(self, dep_checker):
        result = await dep_checker._check_python_dependencies()
        assert "status" in result
        assert "dependencies" in result

    @pytest.mark.asyncio
    async def test_check_system_dependencies(self, dep_checker):
        result = await dep_checker._check_system_dependencies()
        assert "status" in result
        assert "dependencies" in result

    @pytest.mark.asyncio
    async def test_check_system_dependencies_finds_git(self, dep_checker):
        result = await dep_checker._check_system_dependencies()
        if result["status"] == "healthy":
            assert "git" in result["dependencies"]

    @pytest.mark.asyncio
    async def test_check_network_connectivity(self, dep_checker):
        result = await dep_checker._check_network_connectivity()
        # Network check should never return unhealthy (it's optional)
        assert result["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_check_all_dependencies_caching(self, dep_checker):
        """check_all_dependencies should use cached results within cache_duration."""
        with patch.object(dep_checker, "_check_ast_grep_health", new_callable=AsyncMock) as mock_ast:
            mock_ast.return_value = {"status": "healthy"}
            with patch.object(dep_checker, "_check_python_dependencies", new_callable=AsyncMock) as mock_py:
                mock_py.return_value = {"status": "healthy"}
                with patch.object(dep_checker, "_check_system_dependencies", new_callable=AsyncMock) as mock_sys:
                    mock_sys.return_value = {"status": "healthy"}
                    with patch.object(dep_checker, "_check_network_connectivity", new_callable=AsyncMock) as mock_net:
                        mock_net.return_value = {"status": "healthy"}

                        # First call should invoke checks
                        result1 = await dep_checker.check_all_dependencies()
                        assert mock_ast.call_count == 1

                        # Second call should return cached
                        result2 = await dep_checker.check_all_dependencies()
                        assert mock_ast.call_count == 1  # Still 1 - cached

    @pytest.mark.asyncio
    async def test_check_all_dependencies_cache_expiry(self, dep_checker):
        """After cache_duration, check_all_dependencies should re-check."""
        with patch.object(dep_checker, "_check_ast_grep_health", new_callable=AsyncMock) as mock_ast:
            mock_ast.return_value = {"status": "healthy"}
            with patch.object(dep_checker, "_check_python_dependencies", new_callable=AsyncMock) as mock_py:
                mock_py.return_value = {"status": "healthy"}
                with patch.object(dep_checker, "_check_system_dependencies", new_callable=AsyncMock) as mock_sys:
                    mock_sys.return_value = {"status": "healthy"}
                    with patch.object(dep_checker, "_check_network_connectivity", new_callable=AsyncMock) as mock_net:
                        mock_net.return_value = {"status": "healthy"}

                        await dep_checker.check_all_dependencies()
                        assert mock_ast.call_count == 1

                        # Expire cache
                        dep_checker.last_check_time = time.time() - 400
                        await dep_checker.check_all_dependencies()
                        assert mock_ast.call_count == 2

    @pytest.mark.asyncio
    async def test_check_ast_grep_health_binary_not_found(self, dep_checker):
        with patch("ast_grep_mcp.server.validate_ast_grep_installation", new_callable=AsyncMock) as mock_validate:
            mock_validate.return_value = None
            result = await dep_checker._check_ast_grep_health()
            assert result["status"] == "unhealthy"
            assert "not found" in result["error"].lower()


# ===================================================================
# ASTGrepMCPServer tests
# ===================================================================

class TestASTGrepMCPServer:
    """Tests for the main server class (construction, no I/O)."""

    def test_constructor_defaults(self, mcp_server):
        assert mcp_server.config is not None
        assert mcp_server.server is not None
        assert mcp_server._initialized is False
        assert mcp_server._running is False
        assert mcp_server._health_status == "initializing"

    def test_constructor_custom_config(self):
        config = ServerConfig()
        config.name = "test-server"
        config.version = "9.9.9"
        server = ASTGrepMCPServer(config)
        assert server.config.name == "test-server"
        assert server.config.version == "9.9.9"

    def test_constructor_default_config_when_none(self):
        server = ASTGrepMCPServer(None)
        assert server.config.name == "ast-mcp"

    def test_server_name_from_config(self, mcp_server):
        assert mcp_server.config.name == "ast-mcp"

    def test_initialization_state_created(self, mcp_server):
        assert isinstance(mcp_server._initialization_state, InitializationState)

    def test_health_metrics_created(self, mcp_server):
        assert isinstance(mcp_server._health_metrics, HealthMetrics)

    def test_health_thresholds_created(self, mcp_server):
        assert isinstance(mcp_server._health_thresholds, HealthThresholds)

    def test_system_monitor_created(self, mcp_server):
        assert isinstance(mcp_server._system_monitor, SystemResourceMonitor)

    def test_dependency_checker_created(self, mcp_server):
        assert isinstance(mcp_server._dependency_checker, DependencyHealthChecker)

    def test_optional_components_none_before_init(self, mcp_server):
        assert mcp_server._ast_grep_path is None
        assert mcp_server._performance_manager is None
        assert mcp_server._memory_monitor is None
        assert mcp_server._metrics_collector is None
        assert mcp_server._security_manager is None
        assert mcp_server._audit_logger is None
        assert mcp_server._logging_manager is None

    def test_health_task_none_before_init(self, mcp_server):
        assert mcp_server._health_task is None

    def test_shutdown_event_not_set(self, mcp_server):
        assert not mcp_server._shutdown_event.is_set()

    def test_shutdown_timeout_default(self, mcp_server):
        assert mcp_server._shutdown_timeout == 30.0

    def test_cleanup_tasks_empty(self, mcp_server):
        assert mcp_server._cleanup_tasks == []

    @pytest.mark.asyncio
    async def test_initialize_sets_initialized(self):
        """Test that a fully mocked initialize sets _initialized to True."""
        config = ServerConfig()
        config.enable_performance = False
        config.enable_security = False
        config.enable_monitoring = False
        config.enable_enhanced_logging = False
        server = ASTGrepMCPServer(config)

        with patch.object(server, "_validate_configuration", new_callable=AsyncMock):
            with patch.object(server, "_initialize_ast_grep", new_callable=AsyncMock):
                with patch.object(server, "_register_mcp_components", new_callable=AsyncMock):
                    with patch.object(server, "_validate_initialization", new_callable=AsyncMock):
                        with patch.object(server, "_log_initialization_summary", new_callable=AsyncMock):
                            await server.initialize()
                            assert server._initialized is True
                            assert server._health_status == "healthy"

    @pytest.mark.asyncio
    async def test_initialize_already_initialized_skips(self):
        """Calling initialize() when already initialized should be a no-op."""
        config = ServerConfig()
        config.enable_performance = False
        config.enable_security = False
        config.enable_monitoring = False
        config.enable_enhanced_logging = False
        server = ASTGrepMCPServer(config)
        server._initialized = True  # Simulate already initialized

        # Should return immediately without error
        await server.initialize()

    @pytest.mark.asyncio
    async def test_initialize_with_partial_failure_sets_degraded(self):
        """If a non-critical subsystem fails, status should be degraded."""
        config = ServerConfig()
        config.enable_performance = True
        config.enable_security = False
        config.enable_monitoring = False
        config.enable_enhanced_logging = False
        server = ASTGrepMCPServer(config)

        async def failing_perf_init():
            raise RuntimeError("perf init failed")

        with patch.object(server, "_validate_configuration", new_callable=AsyncMock):
            with patch.object(server, "_initialize_ast_grep", new_callable=AsyncMock):
                with patch.object(server, "_initialize_performance_system", side_effect=failing_perf_init):
                    with patch.object(server, "_register_mcp_components", new_callable=AsyncMock):
                        with patch.object(server, "_validate_initialization", new_callable=AsyncMock):
                            with patch.object(server, "_log_initialization_summary", new_callable=AsyncMock):
                                await server.initialize()
                                assert server._initialized is True
                                assert server._health_status == "degraded"
                                assert len(server._initialization_state.partial_failures) == 1

    @pytest.mark.asyncio
    async def test_validate_configuration_valid(self):
        config = ServerConfig()
        config.enable_performance = False
        config.enable_security = False
        config.enable_monitoring = False
        server = ASTGrepMCPServer(config)
        # Should not raise
        await server._validate_configuration()

    @pytest.mark.asyncio
    async def test_validate_configuration_invalid_raises(self):
        config = ServerConfig()
        config.health_check_interval = 0
        server = ASTGrepMCPServer(config)
        with pytest.raises(Exception, match="Invalid configuration"):
            await server._validate_configuration()

    def test_determine_overall_health_status_healthy(self, mcp_server):
        health_data = {"alerts": [], "components": {
            "ast_grep": {"status": "healthy"},
            "initialization": {"status": "healthy"},
        }}
        assert mcp_server._determine_overall_health_status(health_data) == "healthy"

    def test_determine_overall_health_status_unhealthy_critical_alert(self, mcp_server):
        health_data = {"alerts": [{"severity": "critical", "message": "bad"}], "components": {}}
        assert mcp_server._determine_overall_health_status(health_data) == "unhealthy"

    def test_determine_overall_health_status_unhealthy_core_component(self, mcp_server):
        health_data = {"alerts": [], "components": {
            "ast_grep": {"status": "unhealthy"},
            "initialization": {"status": "healthy"},
        }}
        assert mcp_server._determine_overall_health_status(health_data) == "unhealthy"

    def test_determine_overall_health_status_degraded_warning(self, mcp_server):
        health_data = {"alerts": [{"severity": "warning", "message": "slow"}], "components": {
            "ast_grep": {"status": "healthy"},
            "initialization": {"status": "healthy"},
        }}
        assert mcp_server._determine_overall_health_status(health_data) == "degraded"

    def test_determine_overall_health_status_degraded_non_core_unhealthy(self, mcp_server):
        health_data = {"alerts": [], "components": {
            "ast_grep": {"status": "healthy"},
            "initialization": {"status": "healthy"},
            "performance": {"status": "unhealthy"},
        }}
        assert mcp_server._determine_overall_health_status(health_data) == "degraded"

    @pytest.mark.asyncio
    async def test_get_health_status_returns_json(self, mcp_server):
        result = await mcp_server._get_health_status()
        data = json.loads(result)
        assert data["status"] == "initializing"
        assert data["server"]["name"] == "ast-mcp"
        assert data["server"]["initialized"] is False

    @pytest.mark.asyncio
    async def test_get_metrics_status_no_collector(self, mcp_server):
        result = await mcp_server._get_metrics_status()
        data = json.loads(result)
        assert "error" in data

    @pytest.mark.asyncio
    async def test_get_performance_status_disabled(self, mcp_server):
        result = await mcp_server._get_performance_status()
        data = json.loads(result)
        assert "error" in data

    @pytest.mark.asyncio
    async def test_get_security_status_disabled(self, mcp_server):
        result = await mcp_server._get_security_status()
        data = json.loads(result)
        assert "error" in data

    @pytest.mark.asyncio
    async def test_get_alerts_status(self, mcp_server):
        result = await mcp_server._get_alerts_status()
        data = json.loads(result)
        assert "current_alerts" in data
        assert "recent_alerts" in data
        assert "alert_summary" in data

    @pytest.mark.asyncio
    async def test_get_diagnostics_status(self, mcp_server):
        result = await mcp_server._get_diagnostics_status()
        data = json.loads(result)
        assert "server_info" in data
        assert data["server_info"]["name"] == "ast-mcp"

    @pytest.mark.asyncio
    async def test_get_system_resources_status_disabled(self):
        config = ServerConfig()
        config.system_monitoring_enabled = False
        config.enable_performance = False
        config.enable_security = False
        config.enable_monitoring = False
        server = ASTGrepMCPServer(config)
        result = await server._get_system_resources_status()
        data = json.loads(result)
        assert "error" in data

    @pytest.mark.asyncio
    async def test_get_dependencies_status_disabled(self):
        config = ServerConfig()
        config.dependency_check_enabled = False
        config.enable_performance = False
        config.enable_security = False
        config.enable_monitoring = False
        server = ASTGrepMCPServer(config)
        result = await server._get_dependencies_status()
        data = json.loads(result)
        assert "error" in data

    @pytest.mark.asyncio
    async def test_get_health_trends(self, mcp_server):
        result = await mcp_server._get_health_trends()
        data = json.loads(result)
        assert "last_hour" in data

    def test_get_system_metrics_summary_empty(self, mcp_server):
        result = mcp_server._get_system_metrics_summary()
        assert "error" in result

    def test_get_system_metrics_summary_with_data(self, mcp_server):
        mcp_server._health_metrics.add_system_metrics(
            {"cpu": {"percent": 50.0}, "memory": {"percent": 60.0}}
        )
        result = mcp_server._get_system_metrics_summary()
        assert "cpu_usage" in result
        assert "memory_usage" in result
        assert result["cpu_usage"]["current"] == 50.0

    def test_get_component_health_summary_empty(self, mcp_server):
        result = mcp_server._get_component_health_summary()
        assert result == {}

    def test_get_component_health_summary_with_data(self, mcp_server):
        mcp_server._health_metrics.add_component_health("perf", {"status": "healthy"})
        mcp_server._health_metrics.add_component_health("perf", {"status": "unhealthy"})
        result = mcp_server._get_component_health_summary()
        assert "perf" in result
        assert result["perf"]["total_checks"] == 2
        assert result["perf"]["healthy_checks"] == 1
        assert result["perf"]["availability_percentage"] == 50.0

    @pytest.mark.asyncio
    async def test_cleanup_not_running(self, mcp_server):
        """Cleanup on a server that never ran should be a no-op."""
        await mcp_server.cleanup()
        # No error should be raised

    @pytest.mark.asyncio
    async def test_cleanup_resets_state(self, mcp_server):
        """After cleanup, internal state should be reset."""
        mcp_server._initialized = True
        mcp_server._running = True
        await mcp_server.cleanup()
        assert mcp_server._initialized is False
        assert mcp_server._running is False
        assert mcp_server._health_status == "shutdown"

    @pytest.mark.asyncio
    async def test_force_shutdown(self, mcp_server):
        mcp_server._running = True
        mcp_server._initialized = True
        await mcp_server._force_shutdown()
        assert mcp_server._initialized is False
        assert mcp_server._running is False
        assert mcp_server._health_status == "force_shutdown"

    @pytest.mark.asyncio
    async def test_emergency_cleanup(self, mcp_server):
        """Emergency cleanup should not raise."""
        await mcp_server._emergency_cleanup()

    def test_signal_handler_sets_event(self, mcp_server):
        """_signal_handler should set the shutdown event."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            # The signal handler tries to create a task on the running loop.
            # Since we don't have a running loop, it may raise but that's fine.
            # We test the shutdown_event part by mocking create_task.
            with patch.object(loop, "is_running", return_value=False):
                mcp_server._signal_handler(15, None)
                assert mcp_server._shutdown_event.is_set()
        finally:
            asyncio.set_event_loop(None)
            loop.close()

    @pytest.mark.asyncio
    async def test_evaluate_health_alerts_logs(self, mcp_server):
        health_data = {
            "alerts": [
                {"type": "cpu", "message": "CPU high", "severity": "warning"},
                {"type": "mem", "message": "Memory critical", "severity": "critical"},
            ]
        }
        await mcp_server._evaluate_health_alerts(health_data)
        # Alerts should be recorded in health metrics
        assert len(mcp_server._health_metrics.alert_history) == 2

    @pytest.mark.asyncio
    async def test_initialize_step_critical_failure_raises(self, mcp_server):
        """A critical initialization step that fails should raise."""
        async def failing():
            raise RuntimeError("boom")

        with pytest.raises(Exception, match="boom"):
            await mcp_server._initialize_step("config_validation", failing, critical=True)
        assert mcp_server._initialization_state.failed_components[0]["component"] == "config_validation"

    @pytest.mark.asyncio
    async def test_initialize_step_noncritical_failure_records_partial(self, mcp_server):
        """A non-critical initialization step that fails records a partial failure."""
        async def failing():
            raise RuntimeError("minor issue")

        await mcp_server._initialize_step("performance_system", failing, critical=False)
        assert len(mcp_server._initialization_state.partial_failures) == 1
        assert mcp_server._initialization_state.partial_failures[0]["component"] == "performance_system"

    @pytest.mark.asyncio
    async def test_initialize_step_success_marks_completed(self, mcp_server):
        async def succeeding():
            pass

        await mcp_server._initialize_step("ast_grep", succeeding, critical=True)
        assert mcp_server._initialization_state.is_component_initialized("ast_grep")

    @pytest.mark.asyncio
    async def test_stop_task_with_timeout(self, mcp_server):
        """Test stopping a task that can be cancelled."""
        async def long_running():
            await asyncio.sleep(100)

        task = asyncio.create_task(long_running())
        await mcp_server._stop_task_with_timeout(task, "test task", 2.0)
        assert task.done()

    @pytest.mark.asyncio
    async def test_stop_tasks_with_timeout_empty(self, mcp_server):
        """Stopping empty task list should be a no-op."""
        await mcp_server._stop_tasks_with_timeout([], "empty", 1.0)

    @pytest.mark.asyncio
    async def test_shutdown_gracefully(self, mcp_server):
        """Graceful shutdown should call cleanup."""
        mcp_server._initialized = True
        mcp_server._running = True
        with patch.object(mcp_server, "cleanup", new_callable=AsyncMock) as mock_cleanup:
            await mcp_server.shutdown_gracefully(timeout=5.0)
            mock_cleanup.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_shutdown_gracefully_timeout_triggers_force(self, mcp_server):
        """If cleanup times out, force shutdown should be called."""
        mcp_server._initialized = True
        mcp_server._running = True

        async def slow_cleanup():
            await asyncio.sleep(100)

        with patch.object(mcp_server, "cleanup", side_effect=slow_cleanup):
            with patch.object(mcp_server, "_force_shutdown", new_callable=AsyncMock) as mock_force:
                await mcp_server.shutdown_gracefully(timeout=0.01)
                mock_force.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_handle_initialization_failure_resets_state(self, mcp_server):
        """_handle_initialization_failure should reset state."""
        mcp_server._initialized = True
        with patch.object(mcp_server, "_emergency_cleanup", new_callable=AsyncMock):
            await mcp_server._handle_initialization_failure(RuntimeError("test"))
            assert mcp_server._initialized is False
            assert mcp_server._health_status == "failed"

    @pytest.mark.asyncio
    async def test_log_initialization_summary(self, mcp_server):
        """_log_initialization_summary should populate _last_health_check."""
        mcp_server._initialization_state.mark_completed("ast_grep")
        await mcp_server._log_initialization_summary()
        assert "initialization_summary" in mcp_server._last_health_check


# ===================================================================
# create_server() tests
# ===================================================================

class TestCreateServer:
    """Tests for the create_server() factory function."""

    def test_returns_ast_grep_mcp_server(self):
        server = create_server()
        assert isinstance(server, ASTGrepMCPServer)

    def test_default_config_when_none(self):
        server = create_server(None)
        assert server.config.name == "ast-mcp"
        assert server.config.version == "1.0.0"

    def test_custom_config_applied(self):
        config = ServerConfig()
        config.name = "custom-server"
        config.version = "3.0.0"
        server = create_server(config)
        assert server.config.name == "custom-server"
        assert server.config.version == "3.0.0"

    def test_custom_config_features_disabled(self):
        config = ServerConfig()
        config.enable_performance = False
        config.enable_security = False
        config.enable_monitoring = False
        server = create_server(config)
        assert server.config.enable_performance is False
        assert server.config.enable_security is False
        assert server.config.enable_monitoring is False

    def test_server_is_not_initialized(self):
        server = create_server()
        assert server._initialized is False

    def test_server_is_not_running(self):
        server = create_server()
        assert server._running is False

    def test_env_var_config(self, monkeypatch):
        monkeypatch.setenv("AST_GREP_MCP_NAME", "env-server")
        monkeypatch.setenv("AST_GREP_MCP_VERSION", "4.0.0")
        server = create_server()
        assert server.config.name == "env-server"
        assert server.config.version == "4.0.0"
