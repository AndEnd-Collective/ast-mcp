#!/usr/bin/env python3
"""Quick test script to verify enhanced Pydantic validation."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from ast_grep_mcp.tools import SearchToolInput, ScanToolInput, RunToolInput, CallGraphInput
from pydantic import ValidationError

def test_validation():
    """Test the enhanced Pydantic validation."""
    print("Testing enhanced Pydantic validation...\n")
    
    # Test 1: Valid SearchToolInput
    try:
        valid_search = SearchToolInput(
            pattern="console.log($MSG)",
            language="javascript",
            path="./src",
            recursive=True,
            output_format="json"
        )
        print("✅ Valid SearchToolInput: PASSED")
    except Exception as e:
        print(f"❌ Valid SearchToolInput: FAILED - {e}")
    
    # Test 2: Invalid pattern (too long)
    try:
        invalid_search = SearchToolInput(
            pattern="x" * 10000,  # Exceeds max_length=8192
            language="javascript",
            path="./src"
        )
        print("❌ Pattern length validation: FAILED - should have rejected long pattern")
    except ValidationError as e:
        print("✅ Pattern length validation: PASSED - correctly rejected long pattern")
    
    # Test 3: Valid CallGraphInput with languages
    try:
        valid_callgraph = CallGraphInput(
            path="./src",
            languages=["javascript", "python"],
            include_external=False
        )
        print("✅ Valid CallGraphInput: PASSED")
    except Exception as e:
        print(f"❌ Valid CallGraphInput: FAILED - {e}")
    
    # Test 4: Invalid language in CallGraphInput
    try:
        invalid_callgraph = CallGraphInput(
            path="./src",
            languages=["invalid_language_xyz"],
            include_external=False
        )
        print("❌ Language validation: FAILED - should have rejected invalid language")
    except ValidationError as e:
        print("✅ Language validation: PASSED - correctly rejected invalid language")
    
    # Test 5: Valid ScanToolInput with rules_config
    try:
        valid_scan = ScanToolInput(
            path="./src",
            rules_config="./sgconfig.yml",
            output_format="json"
        )
        print("✅ Valid ScanToolInput: PASSED")
    except Exception as e:
        print(f"❌ Valid ScanToolInput: FAILED - {e}")
    
    # Test 6: Invalid glob patterns
    try:
        invalid_globs = SearchToolInput(
            pattern="test",
            language="javascript", 
            path="./src",
            include_globs=["*.js; rm -rf /"]  # Command injection attempt
        )
        print("❌ Dangerous glob validation: FAILED - should have rejected malicious glob")
    except ValidationError as e:
        print("✅ Dangerous glob validation: PASSED - correctly rejected malicious glob")
    
    print("\n🎉 Validation testing complete!")

if __name__ == "__main__":
    test_validation() 