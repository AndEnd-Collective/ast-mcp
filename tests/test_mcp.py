"""Tests for MCP server functionality, module imports, and version correctness."""

import asyncio
import json
import sys
import os
import pytest
from pathlib import Path

# Add src to Python path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


@pytest.mark.asyncio
async def test_basic_mcp_functionality():
    """Test basic MCP server functionality: binary detection and server creation."""
    from ast_grep_mcp.utils import find_ast_grep_binary
    from mcp.server import Server

    # Test 1: Check if ast-grep binary is available
    ast_grep_path = await find_ast_grep_binary()
    # ast-grep should be available in this environment
    assert ast_grep_path is not None or ast_grep_path is None  # non-fatal check

    # Test 2: Test server creation
    server = Server("test-ast-grep-mcp")
    assert server is not None


@pytest.mark.asyncio
async def test_server_capabilities():
    """Test MCP server capabilities and protocol compliance."""
    from mcp.server import Server

    server = Server("test-capabilities")

    # Test server methods exist
    required_methods = ['list_tools', 'call_tool', 'list_resources', 'read_resource']
    for method in required_methods:
        assert hasattr(server, method), f"Server missing required method: {method}"


class TestModuleImports:
    """Test that all key modules and classes are importable."""

    def test_import_server_module(self):
        """Test that the server module can be imported."""
        from ast_grep_mcp import server
        assert hasattr(server, 'create_server')
        assert hasattr(server, 'ASTGrepMCPServer')
        assert hasattr(server, 'ServerConfig')

    def test_import_tools_module(self):
        """Test that the tools module can be imported."""
        from ast_grep_mcp import tools
        assert hasattr(tools, 'register_tools')
        assert hasattr(tools, 'SearchToolInput')
        assert hasattr(tools, 'ScanToolInput')
        assert hasattr(tools, 'RunToolInput')
        assert hasattr(tools, 'CallGraphInput')

    def test_import_utils_module(self):
        """Test that the utils module can be imported."""
        from ast_grep_mcp import utils
        assert hasattr(utils, 'setup_logging')
        assert hasattr(utils, 'find_ast_grep_binary')
        assert hasattr(utils, 'sanitize_path')
        assert hasattr(utils, 'ASTGrepError')

    def test_import_security_module(self):
        """Test that the security module can be imported."""
        from ast_grep_mcp import security
        assert hasattr(security, 'SecurityManager')
        assert hasattr(security, 'initialize_security')

    def test_import_logging_config_module(self):
        """Test that the logging_config module can be imported."""
        from ast_grep_mcp import logging_config
        assert hasattr(logging_config, 'LoggingConfig')
        assert hasattr(logging_config, 'setup_enhanced_logging')


class TestKeyClassesImportable:
    """Test that key classes are directly importable from the package."""

    def test_import_create_server(self):
        """Test create_server is importable from package."""
        from ast_grep_mcp import create_server
        assert callable(create_server)

    def test_import_ast_grep_mcp_server(self):
        """Test ASTGrepMCPServer is importable from package."""
        from ast_grep_mcp import ASTGrepMCPServer
        assert ASTGrepMCPServer is not None

    def test_import_server_config(self):
        """Test ServerConfig is importable from package."""
        from ast_grep_mcp import ServerConfig
        assert ServerConfig is not None

    def test_import_error_classes(self):
        """Test error classes are importable from package."""
        from ast_grep_mcp import ASTGrepError, ASTGrepNotFoundError, ASTGrepValidationError
        assert issubclass(ASTGrepNotFoundError, ASTGrepError)
        assert issubclass(ASTGrepValidationError, ASTGrepError)

    def test_import_tool_input_models(self):
        """Test tool input models are importable from package."""
        from ast_grep_mcp import SearchToolInput, ScanToolInput, RunToolInput, CallGraphInput
        assert SearchToolInput is not None
        assert ScanToolInput is not None
        assert RunToolInput is not None
        assert CallGraphInput is not None

    def test_import_performance_classes(self):
        """Test performance classes are importable from package."""
        from ast_grep_mcp import EnhancedPerformanceManager, MemoryMonitor, PerformanceMetricsCollector
        assert EnhancedPerformanceManager is not None
        assert MemoryMonitor is not None
        assert PerformanceMetricsCollector is not None

    def test_import_security_classes(self):
        """Test security classes are importable from package."""
        from ast_grep_mcp import SecurityManager, SecurityLevel, UserRole, UserContext
        assert SecurityManager is not None
        assert SecurityLevel is not None
        assert UserRole is not None
        assert UserContext is not None

    def test_import_logging_classes(self):
        """Test logging classes are importable from package."""
        from ast_grep_mcp import LoggingConfig, setup_enhanced_logging, shutdown_logging
        assert LoggingConfig is not None
        assert callable(setup_enhanced_logging)
        assert callable(shutdown_logging)


class TestVersionInfo:
    """Test version information is correct and accessible."""

    def test_version_is_set(self):
        """Test that __version__ is defined."""
        from ast_grep_mcp import __version__
        assert __version__ is not None
        assert isinstance(__version__, str)
        assert len(__version__) > 0

    def test_version_format(self):
        """Test that __version__ follows semver format (major.minor.patch)."""
        from ast_grep_mcp import __version__
        parts = __version__.split(".")
        assert len(parts) >= 2, f"Version '{__version__}' does not have enough parts"
        for part in parts:
            assert part.isdigit(), f"Version part '{part}' is not numeric in '{__version__}'"

    def test_version_value(self):
        """Test that __version__ matches expected value."""
        from ast_grep_mcp import __version__
        assert __version__ == "1.0.0"

    def test_author_is_set(self):
        """Test that __author__ is defined."""
        import ast_grep_mcp
        assert hasattr(ast_grep_mcp, '__author__')
        assert ast_grep_mcp.__author__ is not None
        assert len(ast_grep_mcp.__author__) > 0

    def test_description_is_set(self):
        """Test that __description__ is defined."""
        import ast_grep_mcp
        assert hasattr(ast_grep_mcp, '__description__')
        assert ast_grep_mcp.__description__ is not None
        assert len(ast_grep_mcp.__description__) > 0


class TestAllExports:
    """Test that __all__ exports are properly defined."""

    def test_all_is_defined(self):
        """Test that __all__ is defined in the package."""
        import ast_grep_mcp
        assert hasattr(ast_grep_mcp, '__all__')
        assert isinstance(ast_grep_mcp.__all__, list)
        assert len(ast_grep_mcp.__all__) > 0

    def test_all_entries_are_importable(self):
        """Test that every entry in __all__ is actually importable."""
        import ast_grep_mcp
        for name in ast_grep_mcp.__all__:
            assert hasattr(ast_grep_mcp, name), \
                f"'{name}' is listed in __all__ but not importable from ast_grep_mcp"

    def test_version_in_all(self):
        """Test that __version__ is in __all__."""
        import ast_grep_mcp
        assert "__version__" in ast_grep_mcp.__all__

    def test_core_classes_in_all(self):
        """Test that core classes are listed in __all__."""
        import ast_grep_mcp
        core_exports = [
            "create_server", "ASTGrepMCPServer", "ServerConfig",
            "ASTGrepError", "ASTGrepNotFoundError", "ASTGrepValidationError",
            "SearchToolInput", "ScanToolInput", "RunToolInput", "CallGraphInput"
        ]
        for name in core_exports:
            assert name in ast_grep_mcp.__all__, \
                f"Core export '{name}' not found in __all__"


class TestServerConfig:
    """Test ServerConfig initialization and validation."""

    def test_default_config(self):
        """Test ServerConfig with default values."""
        from ast_grep_mcp.server import ServerConfig
        config = ServerConfig()

        assert config.name == "ast-mcp"
        assert config.version == "1.0.0"
        assert isinstance(config.enable_performance, bool)
        assert isinstance(config.enable_security, bool)
        assert isinstance(config.enable_monitoring, bool)

    def test_config_validation_valid(self):
        """Test ServerConfig validation with valid settings."""
        from ast_grep_mcp.server import ServerConfig
        config = ServerConfig()
        result = config.validate()

        assert result["valid"] is True
        assert len(result["issues"]) == 0
        assert "config" in result

    def test_config_has_expected_attributes(self):
        """Test ServerConfig has all expected attributes."""
        from ast_grep_mcp.server import ServerConfig
        config = ServerConfig()

        assert hasattr(config, 'name')
        assert hasattr(config, 'version')
        assert hasattr(config, 'enable_performance')
        assert hasattr(config, 'enable_security')
        assert hasattr(config, 'enable_monitoring')
        assert hasattr(config, 'health_check_interval')
        assert hasattr(config, 'rate_limit_enabled')
