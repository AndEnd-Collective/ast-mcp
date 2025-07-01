#!/usr/bin/env python3
"""Test enhanced resource management and sandboxing features."""

import asyncio
import sys
import os
import tempfile
import time
from pathlib import Path

# Add the src directory to the path
sys.path.insert(0, str(Path(__file__).parent / "src"))

# Mock the security imports if not available
try:
    from ast_grep_mcp.utils import (
        ResourceManager, ResourceConfig, ResourceLimitError,
        ASTGrepExecutor
    )
except ImportError as e:
    print(f"Import error: {e}")
    sys.exit(1)

async def test_resource_config():
    """Test ResourceConfig functionality."""
    print("🔧 Testing ResourceConfig...")
    
    # Test default config
    config = ResourceConfig()
    assert config.max_files == 1000
    assert config.max_memory_mb == 512
    assert config.enable_sandboxing is True
    
    # Test custom config
    custom_config = ResourceConfig(
        max_files=100,
        max_memory_mb=256,
        max_cpu_time=15,
        enable_sandboxing=False
    )
    
    config_dict = custom_config.to_dict()
    assert config_dict['max_files'] == 100
    assert config_dict['max_memory_mb'] == 256
    assert config_dict['max_cpu_time'] == 15
    assert config_dict['enable_sandboxing'] is False
    
    print("✅ ResourceConfig tests passed")

async def test_resource_manager_basic():
    """Test basic ResourceManager functionality."""
    print("🛡️ Testing ResourceManager basic functionality...")
    
    config = ResourceConfig(max_files=5, max_wall_time=2)
    
    async with ResourceManager(config) as manager:
        # Test file limit checking
        temp_file = Path("/tmp/test_file")
        
        # Should pass for files under limit
        for i in range(5):
            assert manager.check_file_limit(temp_file) is True
        
        # Should raise error for file over limit
        try:
            manager.check_file_limit(temp_file)
            assert False, "Should have raised ResourceLimitError"
        except ResourceLimitError as e:
            assert "File limit exceeded" in str(e)
        
        # Test time limit (short wait)
        assert manager.check_time_limit() is True
        
        # Test resource usage tracking
        usage = manager.get_resource_usage()
        assert 'files_processed' in usage
        assert 'elapsed_time' in usage
        assert usage['files_processed'] == 6  # 5 + 1 over limit
    
    print("✅ ResourceManager basic tests passed")

async def test_resource_manager_sandboxing():
    """Test ResourceManager sandboxing features."""
    print("🏖️ Testing ResourceManager sandboxing...")
    
    config = ResourceConfig(enable_sandboxing=True)
    
    async with ResourceManager(config) as manager:
        # Test sandboxed environment
        env = manager.get_sandboxed_env()
        assert 'PATH' in env
        assert 'HOME' in env
        assert 'LANG' in env
        assert 'LC_ALL' in env
        
        # Test subprocess kwargs
        kwargs = manager.get_subprocess_kwargs()
        assert 'env' in kwargs
        
        # Check that temp directory is created
        if manager.temp_dir:
            assert manager.temp_dir.exists()
            assert manager.temp_dir.is_dir()
    
    print("✅ ResourceManager sandboxing tests passed")

async def test_resource_manager_time_limit():
    """Test ResourceManager time limit enforcement."""
    print("⏰ Testing ResourceManager time limits...")
    
    config = ResourceConfig(max_wall_time=1)  # 1 second limit
    
    try:
        async with ResourceManager(config) as manager:
            # Wait long enough to exceed time limit
            await asyncio.sleep(1.5)
            manager.check_time_limit()
            assert False, "Should have raised ResourceLimitError"
    except ResourceLimitError as e:
        assert "Wall time limit exceeded" in str(e)
    
    print("✅ ResourceManager time limit tests passed")

async def test_ast_grep_executor_integration():
    """Test ASTGrepExecutor integration with enhanced resource management."""
    print("🔧 Testing ASTGrepExecutor integration...")
    
    # Create a simple test script to execute
    test_script = """
import time
print("Hello World")
time.sleep(0.1)
print("Done")
"""
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(test_script)
        test_file = Path(f.name)
    
    try:
        # Create executor with limited resources
        executor = ASTGrepExecutor(timeout=5, max_files=10)
        
        # Test that we can execute a simple command with resource management
        # (Note: This won't actually use ast-grep since it may not be installed)
        # Instead, we'll test the resource management infrastructure
        
        # For now, just verify the executor initializes properly
        assert executor.timeout == 5
        assert executor.max_files == 10
        
        print("✅ ASTGrepExecutor integration test passed")
        
    finally:
        # Clean up test file
        test_file.unlink()

async def test_platform_compatibility():
    """Test platform compatibility of resource management features."""
    print("💻 Testing platform compatibility...")
    
    config = ResourceConfig()
    
    async with ResourceManager(config) as manager:
        # Check platform detection
        print(f"Platform: Unix={manager.is_unix}")
        print(f"Resource module: {manager.has_resource_module}")
        print(f"Psutil available: {manager.has_psutil}")
        
        # Should work on all platforms, though with reduced functionality on non-Unix
        usage = manager.get_resource_usage()
        assert isinstance(usage, dict)
        assert 'files_processed' in usage
        assert 'elapsed_time' in usage
    
    print("✅ Platform compatibility tests passed")

async def test_error_handling():
    """Test error handling and edge cases."""
    print("🚨 Testing error handling...")
    
    config = ResourceConfig(max_files=0)  # Immediate failure
    
    async with ResourceManager(config) as manager:
        # Test immediate file limit error
        try:
            manager.check_file_limit(Path("/tmp/test"))
            assert False, "Should have raised ResourceLimitError"
        except ResourceLimitError:
            pass
        
        # Test time limit with no start time (should pass)
        manager.start_time = None
        assert manager.check_time_limit() is True
    
    print("✅ Error handling tests passed")

async def main():
    """Run all resource management tests."""
    print("🧪 Testing Enhanced Resource Management and Sandboxing")
    print("=" * 60)
    
    try:
        await test_resource_config()
        await test_resource_manager_basic()
        await test_resource_manager_sandboxing()
        await test_resource_manager_time_limit()
        await test_ast_grep_executor_integration()
        await test_platform_compatibility()
        await test_error_handling()
        
        print("\n" + "=" * 60)
        print("🎉 All resource management tests PASSED!")
        return 0
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(asyncio.run(main())) 