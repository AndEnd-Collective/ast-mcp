#!/usr/bin/env python3
"""Comprehensive test runner for AST-Grep MCP Server."""

import sys
import os
import asyncio
import subprocess
from pathlib import Path

# Add src to Python path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

def run_test_script(test_script: str, description: str):
    """Run a test script and return success status."""
    print(f"\n{'='*60}")
    print(f"🧪 Running {description}")
    print(f"{'='*60}")
    
    try:
        # Run the test script
        result = subprocess.run(
            [sys.executable, test_script],
            cwd=Path(__file__).parent.parent,
            capture_output=False,
            timeout=120  # 2 minute timeout
        )
        
        success = result.returncode == 0
        status = "✅ PASSED" if success else "❌ FAILED"
        print(f"\n{status} {description}")
        return success
        
    except subprocess.TimeoutExpired:
        print(f"❌ TIMEOUT {description} (exceeded 2 minutes)")
        return False
    except Exception as e:
        print(f"❌ ERROR {description}: {e}")
        return False

def check_dependencies():
    """Check if required dependencies are available."""
    print("🔍 Checking Dependencies...")
    
    required_modules = [
        ("mcp", "Model Context Protocol"),
        ("pydantic", "Data validation"),
        ("ast-grep-cli", "AST-Grep binary"),
    ]
    
    missing = []
    for module, description in required_modules:
        try:
            if module == "ast-grep-cli":
                # Special check for ast-grep binary
                import importlib.util
                spec = importlib.util.find_spec("ast_grep_cli")
                if not spec:
                    missing.append((module, description))
            else:
                __import__(module.replace("-", "_"))
            print(f"✅ {description}")
        except ImportError:
            print(f"❌ {description} - MISSING")
            missing.append((module, description))
    
    if missing:
        print(f"\n⚠️  Missing dependencies:")
        for module, description in missing:
            print(f"   pip install {module}")
        print(f"\nTo install all: pip install -e .")
        return False
    
    return True

def main():
    """Main test runner."""
    print("🚀 AST-Grep MCP Server - Comprehensive Test Suite")
    print("=" * 60)
    
    # Check dependencies first
    if not check_dependencies():
        print("\n❌ Dependency check failed. Please install missing dependencies.")
        return 1
    
    # Define test scripts in order of execution
    test_scripts = [
        ("tests/test_validation.py", "Input Validation Tests"),
        ("tests/test_mcp.py", "Basic MCP Functionality Tests"),
        ("tests/test_mcp_protocol.py", "MCP Protocol Compliance Tests"),
    ]
    
    results = []
    total_tests = len(test_scripts)
    
    # Run each test script
    for script_path, description in test_scripts:
        script_full_path = Path(__file__).parent.parent / script_path
        
        if not script_full_path.exists():
            print(f"⚠️  Test script not found: {script_path}")
            results.append(False)
            continue
        
        success = run_test_script(str(script_full_path), description)
        results.append(success)
    
    # Summary
    passed = sum(results)
    failed = total_tests - passed
    pass_rate = (passed / total_tests * 100) if total_tests > 0 else 0
    
    print(f"\n{'='*60}")
    print("📊 COMPREHENSIVE TEST SUMMARY")
    print(f"{'='*60}")
    print(f"Total Test Suites: {total_tests}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Success Rate: {pass_rate:.1f}%")
    
    # Detailed results
    print(f"\n📋 Detailed Results:")
    for i, (script_path, description) in enumerate(test_scripts):
        status = "✅ PASS" if results[i] else "❌ FAIL"
        print(f"   {status} {description}")
    
    # Overall assessment
    if pass_rate == 100:
        print(f"\n🎉 ALL TESTS PASSED - MCP Server is ready for production!")
        return 0
    elif pass_rate >= 80:
        print(f"\n⚠️  Most tests passed - MCP Server is functional with minor issues")
        return 0
    elif pass_rate >= 60:
        print(f"\n⚠️  Some tests failed - MCP Server needs attention")
        return 1
    else:
        print(f"\n❌ Many tests failed - MCP Server has significant issues")
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)