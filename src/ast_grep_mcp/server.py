"""MCP Server implementation for AST-Grep wrapper with comprehensive integration."""

import asyncio
import logging
import signal
import sys
import os
from typing import Dict, Any, Optional, List
from pathlib import Path
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
import psutil
import time
import shutil
import subprocess
import json
import platform
import traceback
import warnings
from collections import defaultdict

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Resource, Tool, TextContent, ImageContent, EmbeddedResource
from mcp.server.models import InitializationOptions
from pydantic import AnyUrl

from .tools import register_tools
from .resources import register_resources
from .utils import setup_logging, validate_ast_grep_installation, ASTGrepError
from .logging_config import (
    setup_enhanced_logging, shutdown_logging, LoggingConfig,
    get_logging_manager, with_correlation_id, log_function_call
)
from .performance import (
    EnhancedPerformanceManager,
    MemoryMonitor, 
    PerformanceMetricsCollector
)
from .tools import (
    initialize_performance_system,
    shutdown_performance_system,
    get_comprehensive_performance_metrics,
    get_performance_dashboard_data
)
from .security import (
    SecurityManager,
    initialize_security,
    get_security_manager,
    ValidationConfig,
    EnhancedAuditLogger,
    get_audit_logger
)
from .config import ASTGrepConfig

# Suppress deprecation warnings for datetime
warnings.filterwarnings("ignore", category=DeprecationWarning, message=".*datetime.datetime.utcnow.*")

# Initialize logging first
logger = setup_logging(__name__)


class ServerConfig:
    """Configuration for the AST-Grep MCP server."""
    
    def __init__(self):
        self.name = os.getenv("AST_GREP_MCP_NAME", "ast-grep-mcp")
        self.version = os.getenv("AST_GREP_MCP_VERSION", "1.0.0")
        
        # Performance settings
        self.enable_performance = os.getenv("AST_GREP_ENABLE_PERFORMANCE", "true").lower() == "true"
        self.enable_security = os.getenv("AST_GREP_ENABLE_SECURITY", "true").lower() == "true"
        self.enable_monitoring = os.getenv("AST_GREP_ENABLE_MONITORING", "true").lower() == "true"
        
        # Enhanced monitoring settings
        self.health_check_interval = int(os.getenv("AST_GREP_HEALTH_CHECK_INTERVAL", "30"))  # seconds
        self.max_health_history = int(os.getenv("AST_GREP_MAX_HEALTH_HISTORY", "100"))
        self.system_monitoring_enabled = os.getenv("AST_GREP_SYSTEM_MONITORING", "true").lower() == "true"
        self.dependency_check_enabled = os.getenv("AST_GREP_DEPENDENCY_CHECK", "true").lower() == "true"
        self.alerting_enabled = os.getenv("AST_GREP_ALERTING", "true").lower() == "true"
        self.detailed_diagnostics = os.getenv("AST_GREP_DETAILED_DIAGNOSTICS", "true").lower() == "true"
        
        # System resource monitoring thresholds
        self.cpu_warning_threshold = float(os.getenv("AST_GREP_CPU_WARNING", "80.0"))
        self.cpu_critical_threshold = float(os.getenv("AST_GREP_CPU_CRITICAL", "95.0"))
        self.memory_warning_threshold = float(os.getenv("AST_GREP_MEMORY_WARNING", "85.0"))
        self.memory_critical_threshold = float(os.getenv("AST_GREP_MEMORY_CRITICAL", "95.0"))
        
        # Rate limiting
        self.rate_limit_enabled = os.getenv("AST_GREP_RATE_LIMIT", "true").lower() == "true"
        self.rate_limit_requests = int(os.getenv("AST_GREP_RATE_LIMIT_REQUESTS", "100"))
        self.rate_limit_window = int(os.getenv("AST_GREP_RATE_LIMIT_WINDOW", "60"))
        
        # Enhanced logging settings
        self.enable_enhanced_logging = os.getenv("AST_GREP_ENHANCED_LOGGING", "true").lower() == "true"
        self.log_level = os.getenv("AST_GREP_LOG_LEVEL", "INFO").upper()
        self.log_format = os.getenv("AST_GREP_LOG_FORMAT", "structured").lower()
        self.log_correlation_ids = os.getenv("AST_GREP_LOG_CORRELATION_IDS", "true").lower() == "true"

    def validate(self) -> Dict[str, Any]:
        """Validate configuration and return validation results."""
        issues = []
        
        # Validate basic settings
        if self.health_check_interval <= 0:
            issues.append("Health check interval must be positive")
        
        if self.max_health_history <= 0:
            issues.append("Max health history must be positive")
            
        if self.rate_limit_requests <= 0:
            issues.append("Rate limit requests must be positive")
            
        if self.rate_limit_window <= 0:
            issues.append("Rate limit window must be positive")
        
        # Validate threshold ranges
        if not (0 <= self.cpu_warning_threshold <= 100):
            issues.append("CPU warning threshold must be between 0 and 100")
            
        if not (0 <= self.cpu_critical_threshold <= 100):
            issues.append("CPU critical threshold must be between 0 and 100")
            
        if self.cpu_warning_threshold >= self.cpu_critical_threshold:
            issues.append("CPU warning threshold must be less than critical threshold")
            
        if not (0 <= self.memory_warning_threshold <= 100):
            issues.append("Memory warning threshold must be between 0 and 100")
            
        if not (0 <= self.memory_critical_threshold <= 100):
            issues.append("Memory critical threshold must be between 0 and 100")
            
        if self.memory_warning_threshold >= self.memory_critical_threshold:
            issues.append("Memory warning threshold must be less than critical threshold")
        
        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "config": {
                "name": self.name,
                "version": self.version,
                "performance_enabled": self.enable_performance,
                "security_enabled": self.enable_security,
                "monitoring_enabled": self.enable_monitoring,
                "system_monitoring_enabled": self.system_monitoring_enabled,
                "alerting_enabled": self.alerting_enabled
            }
        }


class InitializationState:
    """Track initialization state of server components."""
    
    def __init__(self):
        self.components = {
            "enhanced_logging": False,
            "config_validation": False,
            "ast_grep": False,
            "performance_system": False,
            "security_system": False,
            "mcp_components": False,
            "health_monitoring": False
        }
        self.failed_components = []
        self.partial_failures = []
    
    def mark_completed(self, component: str) -> None:
        """Mark a component as successfully initialized."""
        if component in self.components:
            self.components[component] = True
    
    def mark_failed(self, component: str, error: str) -> None:
        """Mark a component as failed during initialization."""
        self.failed_components.append({"component": component, "error": error})
    
    def mark_partial_failure(self, component: str, error: str) -> None:
        """Mark a component as partially failed but still functional."""
        self.partial_failures.append({"component": component, "error": error})
    
    def is_component_initialized(self, component: str) -> bool:
        """Check if a component was successfully initialized."""
        return self.components.get(component, False)
    
    def get_initialized_components(self) -> List[str]:
        """Get list of successfully initialized components."""
        return [comp for comp, status in self.components.items() if status]
    
    def get_failed_components(self) -> List[Dict[str, str]]:
        """Get list of components that failed to initialize."""
        return self.failed_components
    
    def has_critical_failures(self) -> bool:
        """Check if there are critical failures that prevent server startup."""
        critical_components = ["config_validation", "ast_grep"]
        return any(comp["component"] in critical_components for comp in self.failed_components)


class HealthMetrics:
    """Collect and manage health metrics over time."""
    
    def __init__(self, max_history: int = 50):  # Reduced from 100 to 50
        self.max_history = max_history
        self.health_history: List[Dict[str, Any]] = []
        self.system_metrics_history: List[Dict[str, Any]] = []
        self.component_health_history: Dict[str, List[Dict[str, Any]]] = {}
        self.alert_history: List[Dict[str, Any]] = []
        self._max_components = 20  # Limit number of components tracked
        
    def add_health_check(self, health_data: Dict[str, Any]) -> None:
        """Add a health check result to history."""
        health_data["timestamp"] = datetime.now(timezone.utc).isoformat()
        self.health_history.append(health_data)
        
        # Keep only recent history
        if len(self.health_history) > self.max_history:
            self.health_history = self.health_history[-self.max_history:]
    
    def add_system_metrics(self, metrics: Dict[str, Any]) -> None:
        """Add system metrics to history."""
        metrics["timestamp"] = datetime.now(timezone.utc).isoformat()
        self.system_metrics_history.append(metrics)
        
        if len(self.system_metrics_history) > self.max_history:
            self.system_metrics_history = self.system_metrics_history[-self.max_history:]
    
    def add_component_health(self, component: str, health_data: Dict[str, Any]) -> None:
        """Add component-specific health data."""
        # Limit number of components to prevent unbounded growth
        if component not in self.component_health_history:
            if len(self.component_health_history) >= self._max_components:
                # Remove oldest component if limit reached
                oldest_component = min(
                    self.component_health_history.keys(),
                    key=lambda c: self.component_health_history[c][-1].get('timestamp', '')
                )
                del self.component_health_history[oldest_component]
            
            self.component_health_history[component] = []
        
        health_data["timestamp"] = datetime.now(timezone.utc).isoformat()
        self.component_health_history[component].append(health_data)
        
        # Keep only recent history per component
        if len(self.component_health_history[component]) > self.max_history:
            self.component_health_history[component] = self.component_health_history[component][-self.max_history:]
    
    def add_alert(self, alert_type: str, message: str, severity: str = "warning") -> None:
        """Add an alert to history."""
        alert = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": alert_type,
            "message": message,
            "severity": severity
        }
        self.alert_history.append(alert)
        
        # Keep only recent alerts
        if len(self.alert_history) > self.max_history:
            self.alert_history = self.alert_history[-self.max_history:]
    
    def get_health_trends(self, time_window_minutes: int = 60) -> Dict[str, Any]:
        """Get health trends over a time window."""
        cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=time_window_minutes)
        
        recent_health = [
            h for h in self.health_history 
            if datetime.fromisoformat(h["timestamp"]) > cutoff_time
        ]
        
        if not recent_health:
            return {"error": "No health data in time window"}
        
        # Calculate trends
        health_statuses = [h.get("overall_status", "unknown") for h in recent_health]
        healthy_count = health_statuses.count("healthy")
        degraded_count = health_statuses.count("degraded")
        unhealthy_count = health_statuses.count("unhealthy")
        
        return {
            "time_window_minutes": time_window_minutes,
            "total_checks": len(recent_health),
            "health_distribution": {
                "healthy": healthy_count,
                "degraded": degraded_count,
                "unhealthy": unhealthy_count,
                "healthy_percentage": (healthy_count / len(recent_health)) * 100
            },
            "recent_alerts": [
                a for a in self.alert_history
                if datetime.fromisoformat(a["timestamp"]) > cutoff_time
            ]
        }

    def get_alert_summary(self) -> Dict[str, Any]:
        """Get summary of recent alerts."""
        if not self.alert_history:
            return {"total_alerts": 0, "recent_critical": 0, "recent_warnings": 0}
        
        # Count alerts by severity
        critical_count = len([a for a in self.alert_history[-10:] if a.get('severity') == 'critical'])
        warning_count = len([a for a in self.alert_history[-10:] if a.get('severity') == 'warning'])
        
        return {
            "total_alerts": len(self.alert_history),
            "recent_critical": critical_count,
            "recent_warnings": warning_count,
            "last_alert": self.alert_history[-1] if self.alert_history else None
        }
    
    def cleanup_old_data(self) -> None:
        """Clean up old health data to prevent memory growth."""
        try:
            # Keep only recent health history (half of max)
            target_size = self.max_history // 2
            if len(self.health_history) > target_size:
                self.health_history = self.health_history[-target_size:]
            
            # Limit system metrics history
            if len(self.system_metrics_history) > target_size:
                self.system_metrics_history = self.system_metrics_history[-target_size:]
            
            # Limit component health history per component
            for component in self.component_health:
                if len(self.component_health[component]) > target_size:
                    self.component_health[component] = self.component_health[component][-target_size:]
            
            # Limit alert history 
            if len(self.alert_history) > target_size:
                self.alert_history = self.alert_history[-target_size:]
                
            logger.debug(f"Cleaned up health metrics data, keeping {target_size} entries per category")
            
        except Exception as e:
            logger.error(f"Error cleaning up health metrics data: {e}")


class HealthThresholds:
    """Define health thresholds for alerting."""
    
    def __init__(self):
        # System resource thresholds
        self.cpu_usage_warning = 80.0  # %
        self.cpu_usage_critical = 95.0  # %
        self.memory_usage_warning = 85.0  # %
        self.memory_usage_critical = 95.0  # %
        self.disk_usage_warning = 85.0  # %
        self.disk_usage_critical = 95.0  # %
        
        # Response time thresholds (seconds)
        self.ast_grep_response_warning = 5.0
        self.ast_grep_response_critical = 10.0
        
        # Error rate thresholds (per minute)
        self.error_rate_warning = 10
        self.error_rate_critical = 50
        
        # Component availability thresholds
        self.component_availability_warning = 95.0  # %
        self.component_availability_critical = 85.0  # %


class SystemResourceMonitor:
    """Monitor system resources (CPU, memory, disk, network)."""
    
    def __init__(self):
        self.process = psutil.Process()
        self.start_time = time.time()
        self._last_network_io = None
        self._last_disk_io = None
        
    async def get_system_metrics(self) -> Dict[str, Any]:
        """Get comprehensive system resource metrics."""
        try:
            # CPU metrics
            cpu_percent = psutil.cpu_percent(interval=0.1)
            cpu_count = psutil.cpu_count()
            cpu_freq = psutil.cpu_freq()
            
            # Memory metrics
            memory = psutil.virtual_memory()
            swap = psutil.swap_memory()
            
            # Disk metrics
            disk_usage = psutil.disk_usage('/')
            disk_io = psutil.disk_io_counters()
            
            # Network metrics
            network_io = psutil.net_io_counters()
            
            # Process-specific metrics
            process_info = {
                "pid": self.process.pid,
                "cpu_percent": self.process.cpu_percent(),
                "memory_info": self.process.memory_info()._asdict(),
                "memory_percent": self.process.memory_percent(),
                "num_threads": self.process.num_threads(),
                "num_fds": self.process.num_fds() if hasattr(self.process, 'num_fds') else None,
                "create_time": self.process.create_time(),
                "uptime_seconds": time.time() - self.start_time
            }
            
            # Calculate rates if we have previous data
            network_rates = self._calculate_network_rates(network_io)
            disk_rates = self._calculate_disk_rates(disk_io)
            
            return {
                "cpu": {
                    "percent": cpu_percent,
                    "count": cpu_count,
                    "frequency": cpu_freq._asdict() if cpu_freq else None
                },
                "memory": {
                    "total": memory.total,
                    "available": memory.available,
                    "percent": memory.percent,
                    "used": memory.used,
                    "free": memory.free,
                    "buffers": memory.buffers if hasattr(memory, 'buffers') else None,
                    "cached": memory.cached if hasattr(memory, 'cached') else None
                },
                "swap": {
                    "total": swap.total,
                    "used": swap.used,
                    "free": swap.free,
                    "percent": swap.percent
                },
                "disk": {
                    "total": disk_usage.total,
                    "used": disk_usage.used,
                    "free": disk_usage.free,
                    "percent": (disk_usage.used / disk_usage.total) * 100,
                    "io": disk_io._asdict() if disk_io else None,
                    "io_rates": disk_rates
                },
                "network": {
                    "io": network_io._asdict() if network_io else None,
                    "io_rates": network_rates
                },
                "process": process_info,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error collecting system metrics: {e}")
            return {"error": str(e), "timestamp": datetime.now(timezone.utc).isoformat()}
    
    def _calculate_network_rates(self, current_io) -> Dict[str, float]:
        """Calculate network I/O rates."""
        if self._last_network_io is None:
            self._last_network_io = (current_io, time.time())
            return {"bytes_sent_per_sec": 0.0, "bytes_recv_per_sec": 0.0}
        
        last_io, last_time = self._last_network_io
        current_time = time.time()
        time_delta = current_time - last_time
        
        if time_delta <= 0:
            return {"bytes_sent_per_sec": 0.0, "bytes_recv_per_sec": 0.0}
        
        bytes_sent_rate = (current_io.bytes_sent - last_io.bytes_sent) / time_delta
        bytes_recv_rate = (current_io.bytes_recv - last_io.bytes_recv) / time_delta
        
        self._last_network_io = (current_io, current_time)
        
        return {
            "bytes_sent_per_sec": bytes_sent_rate,
            "bytes_recv_per_sec": bytes_recv_rate,
            "packets_sent_per_sec": (current_io.packets_sent - last_io.packets_sent) / time_delta,
            "packets_recv_per_sec": (current_io.packets_recv - last_io.packets_recv) / time_delta
        }
    
    def _calculate_disk_rates(self, current_io) -> Dict[str, float]:
        """Calculate disk I/O rates."""
        if current_io is None:
            return {"read_bytes_per_sec": 0.0, "write_bytes_per_sec": 0.0}
            
        if self._last_disk_io is None:
            self._last_disk_io = (current_io, time.time())
            return {"read_bytes_per_sec": 0.0, "write_bytes_per_sec": 0.0}
        
        last_io, last_time = self._last_disk_io
        current_time = time.time()
        time_delta = current_time - last_time
        
        if time_delta <= 0:
            return {"read_bytes_per_sec": 0.0, "write_bytes_per_sec": 0.0}
        
        read_rate = (current_io.read_bytes - last_io.read_bytes) / time_delta
        write_rate = (current_io.write_bytes - last_io.write_bytes) / time_delta
        
        self._last_disk_io = (current_io, current_time)
        
        return {
            "read_bytes_per_sec": read_rate,
            "write_bytes_per_sec": write_rate,
            "read_count_per_sec": (current_io.read_count - last_io.read_count) / time_delta,
            "write_count_per_sec": (current_io.write_count - last_io.write_count) / time_delta
        }


class DependencyHealthChecker:
    """Check health of external dependencies."""
    
    def __init__(self):
        self.last_check_time = None
        self.cached_results = {}
        self.cache_duration = 300  # 5 minutes
        
    async def check_all_dependencies(self) -> Dict[str, Any]:
        """Check health of all external dependencies."""
        current_time = time.time()
        
        # Use cache if recent
        if (self.last_check_time and 
            current_time - self.last_check_time < self.cache_duration and
            self.cached_results):
            return self.cached_results
        
        results = {
            "ast_grep": await self._check_ast_grep_health(),
            "python_dependencies": await self._check_python_dependencies(),
            "system_dependencies": await self._check_system_dependencies(),
            "network_connectivity": await self._check_network_connectivity(),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        self.last_check_time = current_time
        self.cached_results = results
        
        return results
    
    async def _check_ast_grep_health(self) -> Dict[str, Any]:
        """Check AST-Grep binary health and responsiveness."""
        try:
            # Check if binary exists and is executable
            ast_grep_path = await validate_ast_grep_installation()
            
            if not ast_grep_path or not ast_grep_path.exists():
                return {
                    "status": "unhealthy",
                    "error": "AST-Grep binary not found",
                    "path": str(ast_grep_path) if ast_grep_path else None
                }
            
            # Test responsiveness with a simple command
            start_time = time.time()
            try:
                result = subprocess.run([
                    str(ast_grep_path), "--version"
                ], capture_output=True, text=True, timeout=10)
                
                response_time = time.time() - start_time
                
                if result.returncode == 0:
                    return {
                        "status": "healthy",
                        "path": str(ast_grep_path),
                        "version": result.stdout.strip(),
                        "response_time_seconds": response_time
                    }
                else:
                    return {
                        "status": "unhealthy",
                        "error": f"AST-Grep command failed: {result.stderr}",
                        "path": str(ast_grep_path),
                        "return_code": result.returncode
                    }
                    
            except subprocess.TimeoutExpired:
                return {
                    "status": "unhealthy",
                    "error": "AST-Grep command timed out",
                    "path": str(ast_grep_path),
                    "timeout_seconds": 10
                }
                
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": f"Failed to check AST-Grep: {e}"
            }
    
    async def _check_python_dependencies(self) -> Dict[str, Any]:
        """Check Python package dependencies health with graceful error handling."""
        try:
            # Try to import pkg_resources, but handle gracefully if not available
            dependencies = {}
            missing_deps = []
            version_issues = []
            
            try:
                import pkg_resources
                
                # Check critical dependencies
                critical_packages = [
                    'mcp', 'psutil', 'pydantic', 'asyncio', 'typing_extensions'
                ]
                
                for package in critical_packages:
                    try:
                        version = pkg_resources.get_distribution(package).version
                        dependencies[package] = {
                            'status': 'available',
                            'version': version,
                            'critical': True
                        }
                    except pkg_resources.DistributionNotFound:
                        missing_deps.append(package)
                        dependencies[package] = {
                            'status': 'missing',
                            'version': None,
                            'critical': True
                        }
                    except Exception as e:
                        version_issues.append({'package': package, 'error': str(e)})
                        dependencies[package] = {
                            'status': 'error',
                            'version': None,
                            'error': str(e),
                            'critical': True
                        }
                        
            except ImportError:
                # pkg_resources not available - this is common in some environments
                logger.info("pkg_resources not available, using basic dependency check")
                
                # Basic check without pkg_resources
                basic_packages = ['psutil', 'pydantic']
                for package in basic_packages:
                    try:
                        __import__(package)
                        dependencies[package] = {
                            'status': 'available',
                            'version': 'unknown (pkg_resources unavailable)',
                            'critical': True
                        }
                    except ImportError:
                        missing_deps.append(package)
                        dependencies[package] = {
                            'status': 'missing',
                            'version': None,
                            'critical': True
                        }
                        
                # Add note about pkg_resources
                dependencies['pkg_resources'] = {
                    'status': 'unavailable',
                    'version': None,
                    'critical': False,
                    'note': 'Not available in this environment (this is normal for some setups)'
                }
            
            # Determine overall status
            if missing_deps:
                status = 'critical'
            elif version_issues:
                status = 'warning' 
            else:
                status = 'healthy'
            
            return {
                'status': status,
                'dependencies': dependencies,
                'missing_critical': missing_deps,
                'version_issues': version_issues,
                'total_checked': len(dependencies),
                'available_count': len([d for d in dependencies.values() if d['status'] == 'available'])
            }
            
        except Exception as e:
            logger.error(f"Error checking Python dependencies: {e}")
            return {
                'status': 'error',
                'error': str(e),
                'dependencies': {},
                'missing_critical': [],
                'version_issues': []
            }
    
    async def _check_system_dependencies(self) -> Dict[str, Any]:
        """Check system-level dependencies."""
        try:
            dependencies = {}
            
            # Check if common system tools are available
            system_tools = ['git', 'grep', 'find']
            
            for tool in system_tools:
                tool_path = shutil.which(tool)
                if tool_path:
                    dependencies[tool] = {
                        "status": "healthy",
                        "path": tool_path
                    }
                else:
                    dependencies[tool] = {
                        "status": "missing",
                        "error": f"{tool} not found in PATH"
                    }
            
            return {
                "status": "healthy",
                "dependencies": dependencies
            }
            
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": f"Failed to check system dependencies: {e}"
            }
    
    async def _check_network_connectivity(self) -> Dict[str, Any]:
        """Check basic network connectivity."""
        try:
            # Basic check - this is optional for AST-Grep MCP
            # Just verify we can resolve common hostnames
            import socket
            
            test_hosts = ['github.com', 'pypi.org']
            connectivity_results = {}
            
            for host in test_hosts:
                try:
                    socket.getaddrinfo(host, 80, timeout=5)
                    connectivity_results[host] = {"status": "reachable"}
                except Exception as e:
                    connectivity_results[host] = {
                        "status": "unreachable", 
                        "error": str(e)
                    }
            
            return {
                "status": "healthy",  # Network is optional for AST-Grep
                "connectivity": connectivity_results
            }
            
        except Exception as e:
            return {
                "status": "healthy",  # Don't fail on network issues
                "error": f"Network check failed: {e}"
            }


class ASTGrepMCPServer:
    """Enhanced AST-Grep MCP Server with comprehensive integration."""
    
    def __init__(self, config: Optional[ServerConfig] = None):
        """Initialize the AST-Grep MCP Server with comprehensive monitoring."""
        self.config = config or ServerConfig()
        self.server = Server(self.config.name)
        
        # Core server state
        self._initialized = False
        self._running = False
        self._start_time = time.time()
        self._shutdown_event = asyncio.Event()
        self._shutdown_timeout = 30.0  # Default shutdown timeout
        
        # Initialization tracking
        self._initialization_state = InitializationState()
        
        # Core components
        self._ast_grep_path: Optional[Path] = None
        
        # Performance system components
        self._performance_manager = None
        self._memory_monitor = None
        self._metrics_collector = None
        
        # Security system components
        self._security_manager = None
        self._audit_logger = None
        
        # Enhanced logging system
        self._logging_manager = None
        
        # Health monitoring
        self._health_status = "initializing"
        self._health_task: Optional[asyncio.Task] = None
        self._last_health_check: Dict[str, Any] = {}
        
        # Background tasks tracking
        self._cleanup_tasks: List[asyncio.Task] = []
        
        # Enhanced monitoring components
        self._health_metrics = HealthMetrics(max_history=self.config.max_health_history)
        self._health_thresholds = HealthThresholds()
        self._system_monitor = SystemResourceMonitor()
        self._dependency_checker = DependencyHealthChecker()
        
    async def initialize(self) -> None:
        """Initialize the server and all subsystems with comprehensive error handling."""
        if self._initialized:
            logger.warning("Server already initialized")
            return
            
        logger.info(f"Initializing {self.config.name} v{self.config.version}")
        
        try:
            # Step 0: Initialize enhanced logging (critical)
            if self.config.enable_enhanced_logging:
                await self._initialize_step("enhanced_logging", self._initialize_enhanced_logging, critical=True)
            
            # Step 1: Validate configuration (critical)
            await self._initialize_step("config_validation", self._validate_configuration, critical=True)
            
            # Step 2: Initialize core AST-Grep (critical)
            await self._initialize_step("ast_grep", self._initialize_ast_grep, critical=True)
            
            # Step 3: Initialize optional subsystems with graceful degradation
            if self.config.enable_performance:
                await self._initialize_step("performance_system", self._initialize_performance_system, critical=False)
            
            if self.config.enable_security:
                await self._initialize_step("security_system", self._initialize_security_system, critical=False)
            
            # Step 4: Register MCP tools and resources (critical)
            await self._initialize_step("mcp_components", self._register_mcp_components, critical=True)
            
            # Step 5: Setup health monitoring (optional)
            if self.config.enable_monitoring:
                await self._initialize_step("health_monitoring", self._initialize_health_monitoring, critical=False)
            
            # Check for critical failures
            if self._initialization_state.has_critical_failures():
                await self._handle_critical_initialization_failure()
                return
            
            # Validate initialization
            await self._validate_initialization()
            
            self._initialized = True
            self._health_status = "healthy" if not self._initialization_state.partial_failures else "degraded"
            
            await self._log_initialization_summary()
            
        except Exception as e:
            logger.error(f"Server initialization failed: {e}")
            await self._handle_initialization_failure(e)
            raise
    
    async def _initialize_step(self, component: str, initializer_func, critical: bool = False) -> None:
        """Initialize a single component with error handling.
        
        Args:
            component: Name of the component being initialized
            initializer_func: Async function to perform the initialization
            critical: Whether this component is critical for server operation
        """
        try:
            logger.info(f"Initializing {component}")
            await initializer_func()
            self._initialization_state.mark_completed(component)
            logger.info(f"Successfully initialized {component}")
            
        except Exception as e:
            error_msg = f"Failed to initialize {component}: {e}"
            logger.error(error_msg)
            
            if critical:
                self._initialization_state.mark_failed(component, str(e))
                raise ASTGrepError(error_msg) from e
            else:
                self._initialization_state.mark_partial_failure(component, str(e))
                logger.warning(f"Continuing with {component} disabled due to initialization failure")
    
    async def _validate_configuration(self) -> None:
        """Validate server configuration."""
        config_validation = self.config.validate()
        if not config_validation["valid"]:
            raise ASTGrepError(f"Invalid configuration: {config_validation['issues']}")
        logger.info(f"Configuration validated: {config_validation['config']}")
    
    async def _validate_initialization(self) -> None:
        """Validate that initialization completed successfully."""
        initialized_components = self._initialization_state.get_initialized_components()
        logger.info(f"Initialized components: {initialized_components}")
        
        # Check that critical components are initialized
        critical_components = ["config_validation", "ast_grep", "mcp_components"]
        missing_critical = [comp for comp in critical_components 
                          if not self._initialization_state.is_component_initialized(comp)]
        
        if missing_critical:
            raise ASTGrepError(f"Critical components not initialized: {missing_critical}")
        
        # Test basic functionality
        if self._ast_grep_path and not self._ast_grep_path.exists():
            raise ASTGrepError("AST-Grep binary path validation failed")
    
    async def _handle_critical_initialization_failure(self) -> None:
        """Handle critical initialization failures."""
        failed_components = self._initialization_state.get_failed_components()
        error_msg = f"Critical components failed to initialize: {failed_components}"
        logger.error(error_msg)
        
        # Attempt cleanup of any partially initialized components
        await self._emergency_cleanup()
        
        raise ASTGrepError(error_msg)
    
    async def _handle_initialization_failure(self, error: Exception) -> None:
        """Handle general initialization failure."""
        logger.error(f"Initialization failed with error: {error}")
        
        # Attempt to clean up any partially initialized state
        await self._emergency_cleanup()
        
        # Reset initialization state
        self._initialization_state = InitializationState()
        self._initialized = False
        self._health_status = "failed"
    
    async def _emergency_cleanup(self) -> None:
        """Emergency cleanup of partially initialized components."""
        logger.info("Performing emergency cleanup of partially initialized components")
        
        try:
            # Stop health monitoring if it was started
            if self._health_task and not self._health_task.done():
                self._health_task.cancel()
                try:
                    await asyncio.wait_for(self._health_task, timeout=5.0)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass
            
            # Shutdown performance system if initialized
            if self._initialization_state.is_component_initialized("performance_system"):
                try:
                    await shutdown_performance_system()
                except Exception as e:
                    logger.warning(f"Error during emergency performance system cleanup: {e}")
            
            # Shutdown enhanced logging system if initialized (do this last)
            if self._initialization_state.is_component_initialized("enhanced_logging"):
                try:
                    shutdown_logging()
                except Exception as e:
                    print(f"Error during emergency logging system cleanup: {e}", file=sys.stderr)
            
            logger.info("Emergency cleanup completed")
            
        except Exception as e:
            logger.error(f"Error during emergency cleanup: {e}")
    
    async def _log_initialization_summary(self) -> None:
        """Log a summary of the initialization process."""
        initialized = self._initialization_state.get_initialized_components()
        failed = self._initialization_state.get_failed_components()
        partial = self._initialization_state.partial_failures
        
        logger.info("=== INITIALIZATION SUMMARY ===")
        logger.info(f"Successfully initialized: {initialized}")
        
        if partial:
            logger.warning(f"Partial failures (degraded mode): {[p['component'] for p in partial]}")
            for failure in partial:
                logger.warning(f"  - {failure['component']}: {failure['error']}")
        
        if failed:
            logger.error(f"Failed components: {[f['component'] for f in failed]}")
            for failure in failed:
                logger.error(f"  - {failure['component']}: {failure['error']}")
        
        logger.info(f"Server status: {self._health_status}")
        logger.info("=== INITIALIZATION COMPLETE ===")
        
        # Store initialization metrics for health checks
        self._last_health_check = {
            "initialization_summary": {
                "initialized_components": initialized,
                "failed_components": failed,
                "partial_failures": partial,
                "status": self._health_status
            }
        }
    
    async def _initialize_enhanced_logging(self) -> None:
        """Initialize the enhanced logging system."""
        logger.info("Initializing enhanced logging system")
        
        # Create logging configuration
        logging_config = LoggingConfig(
            level=self.config.log_level,
            format_type=self.config.log_format,
            enable_correlation_ids=self.config.log_correlation_ids,
        )
        
        # Setup enhanced logging
        self._logging_manager = setup_enhanced_logging(logging_config)
        
        logger.info("Enhanced logging system initialized successfully")
    
    async def _initialize_ast_grep(self) -> None:
        """Initialize AST-Grep binary validation."""
        logger.info("Validating ast-grep installation")
        self._ast_grep_path = await validate_ast_grep_installation()
        logger.info(f"AST-Grep binary found at: {self._ast_grep_path}")
    
    async def _initialize_performance_system(self) -> None:
        """Initialize the performance optimization system."""
        logger.info("Initializing performance system")
        
        # Initialize the global performance system
        await initialize_performance_system()
        
        # Get component references (these are now initialized globally)
        from .performance import (
            get_performance_manager,
            get_metrics_collector
        )
        from .tools import get_memory_manager
        
        self._performance_manager = get_performance_manager()
        self._memory_monitor = get_memory_manager()
        self._metrics_collector = get_metrics_collector()
        
        logger.info("Performance system initialized successfully")
    
    async def _initialize_security_system(self) -> None:
        """Initialize the security system."""
        logger.info("Initializing security system")
        
        # Create security configuration
        security_config = ValidationConfig(
            max_depth=10,
            max_pattern_length=8192,
            allowed_paths=[],  # Will be configured based on usage
            blocked_paths=["/etc", "/proc", "/sys"],
            max_file_size=50 * 1024 * 1024,  # 50MB
            rate_limit_requests=self.config.rate_limit_requests,
            rate_limit_window_seconds=self.config.rate_limit_window
        )
        
        # Initialize global security
        self._security_manager = initialize_security(security_config)
        self._audit_logger = get_audit_logger()
        
        logger.info("Security system initialized successfully")
    
    async def _register_mcp_components(self) -> None:
        """Register MCP tools and resources."""
        logger.info("Registering MCP components")
        
        # Register tools and resources
        register_tools(self.server, self._ast_grep_path)
        register_resources(self.server)
        
        # Register health check endpoints
        await self._register_health_endpoints()
        
        logger.info("MCP components registered successfully")
    
    async def _register_health_endpoints(self) -> None:
        """Register health monitoring resources."""
        
        @self.server.read_resource()
        async def read_health_resource(uri: str) -> str:
            """Read health monitoring resources."""
            if uri == "ast-grep://health":
                return await self._get_health_status()
            elif uri == "ast-grep://metrics":
                return await self._get_metrics_status()
            elif uri == "ast-grep://performance":
                return await self._get_performance_status()
            elif uri == "ast-grep://security":
                return await self._get_security_status()
            elif uri == "ast-grep://health/trends":
                return await self._get_health_trends()
            elif uri == "ast-grep://health/alerts":
                return await self._get_alerts_status()
            elif uri == "ast-grep://health/system":
                return await self._get_system_resources_status()
            elif uri == "ast-grep://health/dependencies":
                return await self._get_dependencies_status()
            elif uri == "ast-grep://health/diagnostics":
                return await self._get_diagnostics_status()
            else:
                raise ValueError(f"Unknown health resource: {uri}")

        @self.server.list_resources()
        async def list_health_resources() -> List[Resource]:
            """List available health monitoring resources."""
            resources = [
                Resource(
                    uri="ast-grep://health",
                    name="Server Health Status",
                    description="Current health status of the AST-Grep MCP server including component status and configuration",
                    mimeType="application/json"
                ),
                Resource(
                    uri="ast-grep://metrics",
                    name="Performance Metrics",
                    description="Performance metrics and statistics from the performance monitoring system",
                    mimeType="application/json"
                ),
                Resource(
                    uri="ast-grep://performance",
                    name="Performance Dashboard",
                    description="Detailed performance dashboard data including caching, concurrency, and memory metrics",
                    mimeType="application/json"
                ),
                Resource(
                    uri="ast-grep://security",
                    name="Security Status",
                    description="Security system status including audit logging and rate limiting information",
                    mimeType="application/json"
                )
            ]
            
            # Add enhanced monitoring resources if enabled
            if self.config.enable_monitoring:
                resources.extend([
                    Resource(
                        uri="ast-grep://health/trends",
                        name="Health Trends",
                        description="Historical health trends and metrics over different time windows",
                        mimeType="application/json"
                    ),
                    Resource(
                        uri="ast-grep://health/alerts",
                        name="Health Alerts",
                        description="Current health alerts and alert history with severity levels",
                        mimeType="application/json"
                    )
                ])
            
            if self.config.system_monitoring_enabled:
                resources.append(
                    Resource(
                        uri="ast-grep://health/system",
                        name="System Resources",
                        description="Detailed system resource monitoring including CPU, memory, disk, and network metrics",
                        mimeType="application/json"
                    )
                )
            
            if self.config.dependency_check_enabled:
                resources.append(
                    Resource(
                        uri="ast-grep://health/dependencies",
                        name="Dependencies Status",
                        description="Health status of external dependencies including AST-Grep binary and system tools",
                        mimeType="application/json"
                    )
                )
            
            if self.config.detailed_diagnostics:
                resources.append(
                    Resource(
                        uri="ast-grep://health/diagnostics",
                        name="System Diagnostics",
                        description="Comprehensive system diagnostics and configuration information",
                        mimeType="application/json"
                    )
                )
            
            return resources
    
    async def _initialize_health_monitoring(self) -> None:
        """Initialize health monitoring background task."""
        logger.info("Starting health monitoring")
        self._health_task = asyncio.create_task(self._health_monitoring_loop())
    
    async def _health_monitoring_loop(self) -> None:
        """Main health monitoring loop with reduced frequency to conserve memory."""
        logger.info("Starting health monitoring loop")
        
        # Use longer intervals to reduce memory pressure
        health_check_interval = max(self.config.health_check_interval, 60)  # Minimum 60 seconds
        consecutive_errors = 0
        max_consecutive_errors = 5
        
        while not self._shutdown_event.is_set():
            try:
                await self._perform_health_check()
                consecutive_errors = 0  # Reset on successful check
                
                # Trigger periodic cleanup of health metrics to prevent memory growth
                if len(self.health_metrics.health_history) > self.health_metrics.max_history * 0.8:
                    self.health_metrics.cleanup_old_data()
                
            except asyncio.CancelledError:
                logger.info("Health monitoring loop cancelled")
                break
            except Exception as e:
                consecutive_errors += 1
                logger.error(f"Health monitoring error #{consecutive_errors}: {e}")
                
                if consecutive_errors >= max_consecutive_errors:
                    logger.critical(f"Health monitoring failed {max_consecutive_errors} times, stopping health monitoring")
                    break
            
            try:
                await asyncio.wait_for(
                    self._shutdown_event.wait(), 
                    timeout=health_check_interval
                )
                break  # Shutdown event was set
            except asyncio.TimeoutError:
                continue  # Normal timeout, continue monitoring
        
        logger.info("Health monitoring loop stopped")
    
    async def _perform_health_check(self) -> None:
        """Perform comprehensive health check with enhanced monitoring."""
        try:
            start_time = time.time()
            
            # Basic health data
            health_data = {
                "overall_status": "healthy",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "check_duration_seconds": 0,
                "components": {},
                "alerts": [],
                "system_resources": {},
                "dependencies": {}
            }
            
            # Check core components
            await self._check_core_components(health_data)
            
            # Check system resources if enabled
            if self.config.system_monitoring_enabled:
                await self._check_system_resources(health_data)
            
            # Check dependencies if enabled
            if self.config.dependency_check_enabled:
                await self._check_dependencies(health_data)
            
            # Evaluate alerts if enabled
            if self.config.alerting_enabled:
                await self._evaluate_health_alerts(health_data)
            
            # Determine overall status
            health_data["overall_status"] = self._determine_overall_health_status(health_data)
            health_data["check_duration_seconds"] = time.time() - start_time
            
            # Store health data
            self._last_health_check = health_data
            self._health_status = health_data["overall_status"]
            
            # Add to health metrics history
            self._health_metrics.add_health_check(health_data)
            
            logger.debug(f"Health check completed: {health_data['overall_status']} in {health_data['check_duration_seconds']:.3f}s")
            
        except Exception as e:
            logger.error(f"Health check error: {e}")
            error_health_data = {
                "overall_status": "unhealthy",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "error": str(e),
                "check_duration_seconds": time.time() - start_time if 'start_time' in locals() else 0
            }
            self._last_health_check = error_health_data
            self._health_status = "unhealthy"
            self._health_metrics.add_health_check(error_health_data)
    
    async def _check_core_components(self, health_data: Dict[str, Any]) -> None:
        """Check core component health."""
        components = health_data["components"]
        
        # Check AST-Grep availability
        components["ast_grep"] = {
            "status": "healthy" if (self._ast_grep_path and self._ast_grep_path.exists()) else "unhealthy",
            "path": str(self._ast_grep_path) if self._ast_grep_path else None
        }
        
        # Check performance system
        if self.config.enable_performance:
            try:
                if self._performance_manager and self._memory_monitor and self._metrics_collector:
                    # Test performance system responsiveness
                    memory_stats = await self._memory_monitor.get_memory_usage()
                    components["performance"] = {
                        "status": "healthy",
                        "memory_monitoring": "active",
                        "last_memory_check": memory_stats
                    }
                    
                    # Add to component health history
                    self._health_metrics.add_component_health("performance", {
                        "status": "healthy",
                        "memory_stats": memory_stats
                    })
                else:
                    components["performance"] = {"status": "unhealthy", "error": "Components not initialized"}
            except Exception as e:
                components["performance"] = {"status": "unhealthy", "error": str(e)}
        else:
            components["performance"] = {"status": "disabled"}
        
        # Check security system  
        if self.config.enable_security:
            try:
                if self._security_manager and self._audit_logger:
                    components["security"] = {
                        "status": "healthy",
                        "audit_logging": "active",
                        "rate_limiting": "active" if self.config.rate_limit_enabled else "disabled"
                    }
                    
                    # Add to component health history
                    self._health_metrics.add_component_health("security", {
                        "status": "healthy",
                        "rate_limiting_enabled": self.config.rate_limit_enabled
                    })
                else:
                    components["security"] = {"status": "unhealthy", "error": "Components not initialized"}
            except Exception as e:
                components["security"] = {"status": "unhealthy", "error": str(e)}
        else:
            components["security"] = {"status": "disabled"}
        
        # Check initialization state
        components["initialization"] = {
            "status": "healthy" if self._initialized else "unhealthy",
            "initialized_components": self._initialization_state.get_initialized_components(),
            "failed_components": self._initialization_state.get_failed_components(),
            "partial_failures": len(self._initialization_state.partial_failures) > 0
        }
        
        # Check health monitoring itself
        components["health_monitoring"] = {
            "status": "healthy" if (self._health_task and not self._health_task.done()) else "unhealthy",
            "monitoring_enabled": self.config.enable_monitoring,
            "check_interval": self.config.health_check_interval
        }
    
    async def _check_system_resources(self, health_data: Dict[str, Any]) -> None:
        """Check system resource health."""
        try:
            system_metrics = await self._system_monitor.get_system_metrics()
            health_data["system_resources"] = system_metrics
            
            # Add to system metrics history
            self._health_metrics.add_system_metrics(system_metrics)
            
            # Check resource thresholds for alerts
            if "cpu" in system_metrics and "percent" in system_metrics["cpu"]:
                cpu_usage = system_metrics["cpu"]["percent"]
                if cpu_usage >= self.config.cpu_critical_threshold:
                    health_data["alerts"].append({
                        "type": "system_resource",
                        "severity": "critical",
                        "message": f"CPU usage critical: {cpu_usage:.1f}% >= {self.config.cpu_critical_threshold}%"
                    })
                elif cpu_usage >= self.config.cpu_warning_threshold:
                    health_data["alerts"].append({
                        "type": "system_resource",
                        "severity": "warning",
                        "message": f"CPU usage high: {cpu_usage:.1f}% >= {self.config.cpu_warning_threshold}%"
                    })
            
            if "memory" in system_metrics and "percent" in system_metrics["memory"]:
                memory_usage = system_metrics["memory"]["percent"]
                if memory_usage >= self.config.memory_critical_threshold:
                    health_data["alerts"].append({
                        "type": "system_resource",
                        "severity": "critical",
                        "message": f"Memory usage critical: {memory_usage:.1f}% >= {self.config.memory_critical_threshold}%"
                    })
                elif memory_usage >= self.config.memory_warning_threshold:
                    health_data["alerts"].append({
                        "type": "system_resource",
                        "severity": "warning",
                        "message": f"Memory usage high: {memory_usage:.1f}% >= {self.config.memory_warning_threshold}%"
                    })
                    
        except Exception as e:
            logger.error(f"Error checking system resources: {e}")
            health_data["system_resources"] = {"error": str(e)}
            health_data["alerts"].append({
                "type": "system_monitoring",
                "severity": "warning",
                "message": f"System resource monitoring failed: {e}"
            })
    
    async def _check_dependencies(self, health_data: Dict[str, Any]) -> None:
        """Check dependency health."""
        try:
            dependencies = await self._dependency_checker.check_all_dependencies()
            health_data["dependencies"] = dependencies
            
            # Check for unhealthy dependencies
            for dep_name, dep_info in dependencies.items():
                if dep_name == "timestamp":
                    continue
                    
                if isinstance(dep_info, dict) and dep_info.get("status") == "unhealthy":
                    health_data["alerts"].append({
                        "type": "dependency",
                        "severity": "critical" if dep_name == "ast_grep" else "warning",
                        "message": f"Dependency unhealthy: {dep_name} - {dep_info.get('error', 'Unknown error')}"
                    })
                elif isinstance(dep_info, dict) and dep_info.get("status") == "degraded":
                    health_data["alerts"].append({
                        "type": "dependency",
                        "severity": "warning", 
                        "message": f"Dependency degraded: {dep_name}"
                    })
                    
        except Exception as e:
            logger.error(f"Error checking dependencies: {e}")
            health_data["dependencies"] = {"error": str(e)}
            health_data["alerts"].append({
                "type": "dependency_check",
                "severity": "warning",
                "message": f"Dependency checking failed: {e}"
            })
    
    async def _evaluate_health_alerts(self, health_data: Dict[str, Any]) -> None:
        """Evaluate and process health alerts."""
        try:
            # Add alerts to metrics history
            for alert in health_data.get("alerts", []):
                self._health_metrics.add_alert(
                    alert_type=alert["type"],
                    message=alert["message"],
                    severity=alert["severity"]
                )
            
            # Log critical alerts
            for alert in health_data.get("alerts", []):
                if alert["severity"] == "critical":
                    logger.error(f"CRITICAL HEALTH ALERT: {alert['message']}")
                elif alert["severity"] == "warning":
                    logger.warning(f"Health warning: {alert['message']}")
                    
        except Exception as e:
            logger.error(f"Error evaluating health alerts: {e}")
    
    def _determine_overall_health_status(self, health_data: Dict[str, Any]) -> str:
        """Determine overall health status based on all checks."""
        # Check for critical alerts
        critical_alerts = [a for a in health_data.get("alerts", []) if a["severity"] == "critical"]
        if critical_alerts:
            return "unhealthy"
        
        # Check component health
        components = health_data.get("components", {})
        unhealthy_components = [
            name for name, info in components.items() 
            if isinstance(info, dict) and info.get("status") == "unhealthy"
        ]
        
        # Core components must be healthy
        core_components = ["ast_grep", "initialization"]
        if any(comp in unhealthy_components for comp in core_components):
            return "unhealthy"
        
        # Check for any warnings or degraded state
        warning_alerts = [a for a in health_data.get("alerts", []) if a["severity"] == "warning"]
        if warning_alerts or unhealthy_components:
            return "degraded"
        
        return "healthy"
    
    async def _get_health_status(self) -> str:
        """Get current health status as comprehensive JSON."""
        import json
        
        status = {
            "status": self._health_status,
            "server": {
                "name": self.config.name,
                "version": self.config.version,
                "initialized": self._initialized,
                "running": self._running,
                "uptime_seconds": time.time() - self._start_time
            },
            "last_check": self._last_health_check,
            "components": {
                "ast_grep": self._ast_grep_path is not None,
                "performance": self._performance_manager is not None,
                "security": self._security_manager is not None,
                "monitoring": self._health_task is not None,
                "system_monitoring": self.config.system_monitoring_enabled,
                "dependency_checking": self.config.dependency_check_enabled,
                "alerting": self.config.alerting_enabled
            },
            "configuration": {
                "health_check_interval": self.config.health_check_interval,
                "max_health_history": self.config.max_health_history,
                "cpu_thresholds": {
                    "warning": self.config.cpu_warning_threshold,
                    "critical": self.config.cpu_critical_threshold
                },
                "memory_thresholds": {
                    "warning": self.config.memory_warning_threshold,
                    "critical": self.config.memory_critical_threshold
                }
            }
        }
        
        return json.dumps(status, indent=2)
    
    async def _get_metrics_status(self) -> str:
        """Get performance metrics as JSON."""
        import json
        
        if self._metrics_collector:
            metrics = await self._metrics_collector.get_performance_summary()
        else:
            metrics = {"error": "Performance system not enabled"}
            
        return json.dumps(metrics, indent=2)
    
    async def _get_performance_status(self) -> str:
        """Get detailed performance status as JSON."""
        import json
        
        if self.config.enable_performance:
            performance_data = await get_performance_dashboard_data()
        else:
            performance_data = {"error": "Performance system not enabled"}
            
        return json.dumps(performance_data, indent=2)
    
    async def _get_security_status(self) -> str:
        """Get security system status as JSON."""
        import json
        
        if self._security_manager and self._audit_logger:
            # Get security statistics
            security_data = {
                "security_manager": "active",
                "audit_logger": "active",
                "rate_limiting": {
                    "enabled": True,
                    "requests_per_window": self.config.rate_limit_requests,
                    "window_seconds": self.config.rate_limit_window
                }
            }
        else:
            security_data = {"error": "Security system not enabled"}
            
        return json.dumps(security_data, indent=2)
    
    async def _get_health_trends(self) -> str:
        """Get health trends and historical data."""
        import json
        
        try:
            # Get trends for different time windows
            trends = {
                "last_hour": self._health_metrics.get_health_trends(60),
                "last_6_hours": self._health_metrics.get_health_trends(360),
                "last_24_hours": self._health_metrics.get_health_trends(1440),
                "recent_health_checks": self._health_metrics.health_history[-10:],  # Last 10 checks
                "system_metrics_summary": self._get_system_metrics_summary(),
                "component_health_summary": self._get_component_health_summary()
            }
            
            return json.dumps(trends, indent=2)
            
        except Exception as e:
            logger.error(f"Error getting health trends: {e}")
            return json.dumps({"error": str(e)}, indent=2)
    
    def _get_system_metrics_summary(self) -> Dict[str, Any]:
        """Get summary of recent system metrics."""
        if not self._health_metrics.system_metrics_history:
            return {"error": "No system metrics history available"}
        
        recent_metrics = self._health_metrics.system_metrics_history[-5:]  # Last 5 measurements
        
        # Calculate averages
        cpu_values = [m.get("cpu", {}).get("percent", 0) for m in recent_metrics if "cpu" in m]
        memory_values = [m.get("memory", {}).get("percent", 0) for m in recent_metrics if "memory" in m]
        
        return {
            "recent_measurements": len(recent_metrics),
            "cpu_usage": {
                "current": cpu_values[-1] if cpu_values else 0,
                "average": sum(cpu_values) / len(cpu_values) if cpu_values else 0,
                "max": max(cpu_values) if cpu_values else 0
            },
            "memory_usage": {
                "current": memory_values[-1] if memory_values else 0,
                "average": sum(memory_values) / len(memory_values) if memory_values else 0,
                "max": max(memory_values) if memory_values else 0
            }
        }
    
    def _get_component_health_summary(self) -> Dict[str, Any]:
        """Get summary of component health over time."""
        summary = {}
        
        for component, history in self._health_metrics.component_health_history.items():
            if history:
                recent_checks = history[-10:]  # Last 10 checks
                healthy_count = sum(1 for check in recent_checks if check.get("status") == "healthy")
                
                summary[component] = {
                    "total_checks": len(recent_checks),
                    "healthy_checks": healthy_count,
                    "availability_percentage": (healthy_count / len(recent_checks)) * 100 if recent_checks else 0,
                    "last_status": recent_checks[-1].get("status", "unknown") if recent_checks else "unknown",
                    "last_check_time": recent_checks[-1].get("timestamp") if recent_checks else None
                }
        
        return summary

    async def _get_alerts_status(self) -> str:
        """Get current alerts and alert history."""
        import json
        
        try:
            alerts_data = {
                "current_alerts": [],
                "recent_alerts": self._health_metrics.alert_history[-20:],  # Last 20 alerts
                "alert_summary": {
                    "total_alerts": len(self._health_metrics.alert_history),
                    "critical_alerts": len([a for a in self._health_metrics.alert_history if a["severity"] == "critical"]),
                    "warning_alerts": len([a for a in self._health_metrics.alert_history if a["severity"] == "warning"])
                }
            }
            
            # Get current alerts from last health check
            if self._last_health_check and "alerts" in self._last_health_check:
                alerts_data["current_alerts"] = self._last_health_check["alerts"]
            
            return json.dumps(alerts_data, indent=2)
            
        except Exception as e:
            logger.error(f"Error getting alerts status: {e}")
            return json.dumps({"error": str(e)}, indent=2)

    async def _get_system_resources_status(self) -> str:
        """Get detailed system resources status."""
        import json
        
        try:
            if self.config.system_monitoring_enabled:
                system_metrics = await self._system_monitor.get_system_metrics()
                
                # Add threshold information
                system_metrics["thresholds"] = {
                    "cpu": {
                        "warning": self.config.cpu_warning_threshold,
                        "critical": self.config.cpu_critical_threshold
                    },
                    "memory": {
                        "warning": self.config.memory_warning_threshold,
                        "critical": self.config.memory_critical_threshold
                    }
                }
                
                # Add status indicators
                if "cpu" in system_metrics and "percent" in system_metrics["cpu"]:
                    cpu_usage = system_metrics["cpu"]["percent"]
                    if cpu_usage >= self.config.cpu_critical_threshold:
                        system_metrics["cpu"]["status"] = "critical"
                    elif cpu_usage >= self.config.cpu_warning_threshold:
                        system_metrics["cpu"]["status"] = "warning"
                    else:
                        system_metrics["cpu"]["status"] = "normal"
                
                if "memory" in system_metrics and "percent" in system_metrics["memory"]:
                    memory_usage = system_metrics["memory"]["percent"]
                    if memory_usage >= self.config.memory_critical_threshold:
                        system_metrics["memory"]["status"] = "critical"
                    elif memory_usage >= self.config.memory_warning_threshold:
                        system_metrics["memory"]["status"] = "warning"
                    else:
                        system_metrics["memory"]["status"] = "normal"
                
                return json.dumps(system_metrics, indent=2)
            else:
                return json.dumps({"error": "System monitoring not enabled"}, indent=2)
                
        except Exception as e:
            logger.error(f"Error getting system resources: {e}")
            return json.dumps({"error": str(e)}, indent=2)

    async def _get_dependencies_status(self) -> str:
        """Get detailed dependencies status."""
        import json
        
        try:
            if self.config.dependency_check_enabled:
                dependencies = await self._dependency_checker.check_all_dependencies()
                
                # Add summary information
                dependencies["summary"] = {
                    "total_dependencies": len([k for k in dependencies.keys() if k != "timestamp"]),
                    "healthy": len([v for k, v in dependencies.items() 
                                  if k != "timestamp" and isinstance(v, dict) and v.get("status") == "healthy"]),
                    "unhealthy": len([v for k, v in dependencies.items() 
                                   if k != "timestamp" and isinstance(v, dict) and v.get("status") == "unhealthy"]),
                    "degraded": len([v for k, v in dependencies.items() 
                                  if k != "timestamp" and isinstance(v, dict) and v.get("status") == "degraded"])
                }
                
                return json.dumps(dependencies, indent=2)
            else:
                return json.dumps({"error": "Dependency checking not enabled"}, indent=2)
                
        except Exception as e:
            logger.error(f"Error getting dependencies status: {e}")
            return json.dumps({"error": str(e)}, indent=2)

    async def _get_diagnostics_status(self) -> str:
        """Get comprehensive diagnostics information."""
        import json
        
        try:
            diagnostics = {
                "server_info": {
                    "name": self.config.name,
                    "version": self.config.version,
                    "start_time": self._start_time,
                    "uptime_seconds": time.time() - self._start_time,
                    "process_id": os.getpid(),
                    "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
                },
                "configuration": {
                    "performance_enabled": self.config.enable_performance,
                    "security_enabled": self.config.enable_security,
                    "monitoring_enabled": self.config.enable_monitoring,
                    "system_monitoring": self.config.system_monitoring_enabled,
                    "dependency_checking": self.config.dependency_check_enabled,
                    "alerting": self.config.alerting_enabled,
                    "health_check_interval": self.config.health_check_interval,
                    "max_health_history": self.config.max_health_history
                },
                "initialization_state": {
                    "initialized": self._initialized,
                    "initialized_components": self._initialization_state.get_initialized_components(),
                    "failed_components": self._initialization_state.get_failed_components(),
                    "partial_failures": self._initialization_state.partial_failures
                },
                "health_monitoring": {
                    "status": self._health_status,
                    "monitoring_task_running": self._health_task is not None and not self._health_task.done(),
                    "last_check_time": self._last_health_check.get("timestamp") if self._last_health_check else None,
                    "total_health_checks": len(self._health_metrics.health_history),
                    "total_alerts": len(self._health_metrics.alert_history)
                }
            }
            
            # Add AST-Grep information
            if self._ast_grep_path:
                diagnostics["ast_grep"] = {
                    "path": str(self._ast_grep_path),
                    "exists": self._ast_grep_path.exists(),
                    "executable": os.access(self._ast_grep_path, os.X_OK) if self._ast_grep_path.exists() else False
                }
            
            return json.dumps(diagnostics, indent=2)
            
        except Exception as e:
            logger.error(f"Error getting diagnostics: {e}")
            return json.dumps({"error": str(e)}, indent=2)
    
    async def run(self) -> None:
        """Run the MCP server with comprehensive error handling."""
        if not self._initialized:
            await self.initialize()
        
        self._running = True
        self._start_time = time.time()  # Reset start time when actually running
        logger.info(f"Starting {self.config.name} MCP server")
        
        # Setup signal handlers for graceful shutdown
        if hasattr(signal, 'SIGTERM'):
            signal.signal(signal.SIGTERM, self._signal_handler)
        if hasattr(signal, 'SIGINT'):
            signal.signal(signal.SIGINT, self._signal_handler)
        
        try:
            # Run the server with stdio transport
            async with stdio_server() as streams:
                await self.server.run(
                    streams[0], streams[1], self.server.create_initialization_options()
                )
        except KeyboardInterrupt:
            logger.info("Server interrupted by user")
        except Exception as e:
            logger.error(f"Server runtime error: {e}")
            raise
        finally:
            # Always ensure graceful shutdown
            if self._running or self._initialized:
                logger.info("Ensuring graceful shutdown")
                await self.shutdown_gracefully()
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, initiating graceful shutdown")
        self._shutdown_event.set()
        
        # Schedule graceful shutdown in the event loop
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Create cleanup task and track it
            cleanup_task = loop.create_task(self.shutdown_gracefully())
            self._cleanup_tasks.append(cleanup_task)
    
    async def cleanup(self) -> None:
        """Clean up server resources with comprehensive shutdown procedures."""
        if not self._running and not self._initialized:
            logger.debug("Server not running or initialized, skipping cleanup")
            return
            
        logger.info("Starting server cleanup")
        self._running = False
        self._shutdown_event.set()
        
        # Track cleanup steps
        cleanup_steps = []
        
        try:
            # Step 1: Stop accepting new requests (signal shutdown)
            cleanup_steps.append("signal_shutdown")
            logger.info("Signaling shutdown to all components")
            
            # Step 2: Stop health monitoring with timeout
            if self._health_task and not self._health_task.done():
                cleanup_steps.append("health_monitoring")
                logger.info("Stopping health monitoring")
                await self._stop_task_with_timeout(self._health_task, "health monitoring", 5.0)
            
            # Step 3: Stop any background cleanup tasks
            if self._cleanup_tasks:
                cleanup_steps.append("cleanup_tasks")
                logger.info(f"Stopping {len(self._cleanup_tasks)} background cleanup tasks")
                await self._stop_tasks_with_timeout(self._cleanup_tasks, "cleanup tasks", 10.0)
                self._cleanup_tasks.clear()
            
            # Step 4: Shutdown subsystems in reverse order of initialization
            if self._initialization_state.is_component_initialized("performance_system"):
                cleanup_steps.append("performance_system")
                logger.info("Shutting down performance system")
                try:
                    await asyncio.wait_for(shutdown_performance_system(), timeout=15.0)
                    logger.info("Performance system shutdown complete")
                except asyncio.TimeoutError:
                    logger.warning("Performance system shutdown timed out")
                except Exception as e:
                    logger.error(f"Error shutting down performance system: {e}")
            
            # Step 5: Security system cleanup
            if self._initialization_state.is_component_initialized("security_system"):
                cleanup_steps.append("security_system")
                logger.info("Cleaning up security system")
                try:
                    # Security system doesn't have async shutdown, but log completion
                    logger.info("Security system cleanup complete")
                except Exception as e:
                    logger.error(f"Error during security system cleanup: {e}")
            
            # Step 6: Shutdown enhanced logging system (do this last before state reset)
            if self._initialization_state.is_component_initialized("enhanced_logging"):
                cleanup_steps.append("enhanced_logging")
                logger.info("Shutting down enhanced logging system")
                try:
                    shutdown_logging()
                    # Use print for final logging message since logger may be shutdown
                    print("Enhanced logging system shutdown complete", file=sys.stdout)
                except Exception as e:
                    print(f"Error shutting down enhanced logging system: {e}", file=sys.stderr)
            
            # Step 7: Reset component states
            cleanup_steps.append("reset_state")
            self._ast_grep_path = None
            self._performance_manager = None
            self._memory_monitor = None
            self._metrics_collector = None
            self._security_manager = None
            self._audit_logger = None
            self._logging_manager = None
            self._health_task = None
            
            # Step 7: Reset initialization state
            self._initialization_state = InitializationState()
            self._initialized = False
            self._health_status = "shutdown"
            
            logger.info("=== SHUTDOWN SUMMARY ===")
            logger.info(f"Completed cleanup steps: {cleanup_steps}")
            logger.info("Server cleanup complete")
            logger.info("=== SHUTDOWN COMPLETE ===")
            
        except Exception as e:
            logger.error(f"Error during cleanup (completed steps: {cleanup_steps}): {e}")
            # Force reset state even if cleanup failed
            self._initialized = False
            self._running = False
            self._health_status = "shutdown_error"
            raise
    
    async def _stop_task_with_timeout(self, task: asyncio.Task, task_name: str, timeout: float) -> None:
        """Stop a single task with timeout and proper cancellation handling.
        
        Args:
            task: The task to stop
            task_name: Human-readable name for logging
            timeout: Timeout in seconds
        """
        try:
            # First, try to cancel the task
            task.cancel()
            
            # Wait for it to complete with timeout
            await asyncio.wait_for(task, timeout=timeout)
            logger.info(f"Successfully stopped {task_name}")
            
        except asyncio.CancelledError:
            logger.info(f"{task_name} was cancelled successfully")
        except asyncio.TimeoutError:
            logger.warning(f"{task_name} did not stop within {timeout}s timeout")
        except Exception as e:
            logger.error(f"Error stopping {task_name}: {e}")
    
    async def _stop_tasks_with_timeout(self, tasks: List[asyncio.Task], task_group_name: str, timeout: float) -> None:
        """Stop multiple tasks with timeout.
        
        Args:
            tasks: List of tasks to stop
            task_group_name: Human-readable name for the group
            timeout: Total timeout for all tasks
        """
        if not tasks:
            return
        
        try:
            # Cancel all tasks
            for task in tasks:
                if not task.done():
                    task.cancel()
            
            # Wait for all tasks to complete with timeout
            done, pending = await asyncio.wait(
                tasks, 
                timeout=timeout, 
                return_when=asyncio.ALL_COMPLETED
            )
            
            if pending:
                logger.warning(f"{len(pending)} {task_group_name} did not stop within {timeout}s timeout")
                # Force cancel any remaining tasks
                for task in pending:
                    task.cancel()
            else:
                logger.info(f"Successfully stopped all {task_group_name}")
                
        except Exception as e:
            logger.error(f"Error stopping {task_group_name}: {e}")
    
    async def shutdown_gracefully(self, timeout: Optional[float] = None) -> None:
        """Initiate graceful shutdown with optional timeout.
        
        Args:
            timeout: Maximum time to wait for shutdown (defaults to self._shutdown_timeout)
        """
        shutdown_timeout = timeout or self._shutdown_timeout
        logger.info(f"Initiating graceful shutdown with {shutdown_timeout}s timeout")
        
        try:
            await asyncio.wait_for(self.cleanup(), timeout=shutdown_timeout)
            logger.info("Graceful shutdown completed successfully")
        except asyncio.TimeoutError:
            logger.error(f"Graceful shutdown timed out after {shutdown_timeout}s")
            # Force immediate shutdown
            await self._force_shutdown()
        except Exception as e:
            logger.error(f"Error during graceful shutdown: {e}")
            await self._force_shutdown()
    
    async def _force_shutdown(self) -> None:
        """Force immediate shutdown of all components."""
        logger.warning("Forcing immediate shutdown")
        
        try:
            # Cancel all running tasks aggressively
            if self._health_task and not self._health_task.done():
                self._health_task.cancel()
            
            for task in self._cleanup_tasks:
                if not task.done():
                    task.cancel()
            
            # Reset all state immediately
            self._initialized = False
            self._running = False
            self._health_status = "force_shutdown"
            
            logger.warning("Force shutdown complete")
            
        except Exception as e:
            logger.error(f"Error during force shutdown: {e}")


def create_server(config: Optional[ServerConfig] = None) -> ASTGrepMCPServer:
    """Factory function to create an AST-Grep MCP Server instance.
    
    Args:
        config: Server configuration (defaults to environment-based config)
        
    Returns:
        ASTGrepMCPServer instance
    """
    return ASTGrepMCPServer(config)


async def main() -> None:
    """Main entry point for the server."""
    # Setup logging first
    config = ServerConfig()
    setup_logging(level=config.log_level)
    
    # Create and run server
    server = create_server(config)
    try:
        await server.run()
    except KeyboardInterrupt:
        logger.info("Server interrupted by user")
    except Exception as e:
        logger.error(f"Server failed: {e}")
        sys.exit(1)


def main_sync() -> None:
    """Synchronous entry point for console script."""
    asyncio.run(main())


if __name__ == "__main__":
    main_sync() 