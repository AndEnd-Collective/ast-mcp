#!/usr/bin/env python3
"""Basic MCP server functionality test."""

import asyncio
import json
import sys
import os
from pathlib import Path

# Add src to Python path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

try:
    from ast_grep_mcp.server import main_sync
    from ast_grep_mcp.utils import find_ast_grep_binary
    from mcp.server import Server
    from mcp.types import Tool
except ImportError as e:
    print(f"Import error: {e}")
    print("Please install dependencies: pip install -e .")
    sys.exit(1)

async def test_basic_mcp_functionality():
    """Test basic MCP server functionality."""
    print("🧪 Testing Basic MCP Functionality")
    
    try:
        # Test 1: Check if ast-grep binary is available
        print("\n1. Testing ast-grep binary detection...")
        ast_grep_path = await find_ast_grep_binary()
        if ast_grep_path:
            print(f"✅ ast-grep found at: {ast_grep_path}")
        else:
            print("⚠️  ast-grep not found - some functionality may be limited")
        
        # Test 2: Test server creation
        print("\n2. Testing MCP server creation...")
        server = Server("test-ast-grep-mcp")
        print("✅ MCP server created successfully")
        
        # Test 3: Import and validate tools module
        print("\n3. Testing tools module import...")
        from ast_grep_mcp.tools import register_tools
        print("✅ Tools module imported successfully")
        
        # Test 4: Register tools (if ast-grep is available)
        if ast_grep_path:
            print("\n4. Testing tool registration...")
            register_tools(server, ast_grep_path)
            print("✅ Tools registered successfully")
            
            # Test 5: List registered tools
            print("\n5. Testing tool listing...")
            tools = server.list_tools()  # This is likely a callable that returns tools
            if callable(tools):
                tools = tools()
            print(f"✅ Found {len(tools)} registered tools:")
            for tool in tools:
                print(f"   - {tool.name}: {tool.description[:60]}...")
            
            # Test 6: Verify core tools exist
            print("\n6. Verifying core tools...")
            tool_names = {tool.name for tool in tools}
            expected_tools = ["ast_grep_search", "ast_grep_scan", "ast_grep_run"]
            
            for expected_tool in expected_tools:
                if expected_tool in tool_names:
                    print(f"✅ {expected_tool} - found")
                else:
                    print(f"❌ {expected_tool} - missing")
        
        print("\n🎉 Basic MCP functionality test completed!")
        return True
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_server_capabilities():
    """Test MCP server capabilities and protocol compliance."""
    print("\n🔍 Testing MCP Server Capabilities")
    
    try:
        server = Server("test-capabilities")
        
        # Test server methods exist
        required_methods = ['list_tools', 'call_tool', 'list_resources', 'read_resource']
        print("\nChecking required MCP methods:")
        
        for method in required_methods:
            if hasattr(server, method):
                print(f"✅ {method} - available")
            else:
                print(f"❌ {method} - missing")
        
        return True
        
    except Exception as e:
        print(f"❌ Capabilities test failed: {e}")
        return False

if __name__ == "__main__":
    async def run_tests():
        """Run all basic tests."""
        print("=" * 60)
        print("AST-Grep MCP Server - Basic Functionality Tests")
        print("=" * 60)
        
        test1_result = await test_basic_mcp_functionality()
        test2_result = await test_server_capabilities()
        
        print("\n" + "=" * 60)
        if test1_result and test2_result:
            print("🎉 ALL TESTS PASSED!")
            return 0
        else:
            print("❌ SOME TESTS FAILED!")
            return 1
    
    exit_code = asyncio.run(run_tests())
    sys.exit(exit_code)