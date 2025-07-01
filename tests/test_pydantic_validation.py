#!/usr/bin/env python3
"""Standalone test for Pydantic validation enhancements."""

import sys
import os
from pathlib import Path

# Add the src directory to the path
sys.path.insert(0, str(Path(__file__).parent / "src"))

# Mock the external dependencies that are not available
class MockLanguageManager:
    def validate_language_identifier(self, lang):
        valid_langs = ['javascript', 'python', 'js', 'py', 'typescript', 'ts']
        return lang in valid_langs
    
    def suggest_similar_languages(self, lang):
        return ['javascript', 'python']

def mock_get_language_manager():
    return MockLanguageManager()

def mock_sanitize_path(path_str):
    # Simple mock that just returns the absolute path
    return Path(path_str).resolve()

# Patch the imports
import ast_grep_mcp.tools
ast_grep_mcp.tools.get_language_manager = mock_get_language_manager
ast_grep_mcp.tools.sanitize_path = mock_sanitize_path

# Now import the models
from ast_grep_mcp.tools import CallGraphInput, SearchToolInput

def test_call_graph_input_validation():
    """Test CallGraphInput validation enhancements."""
    print("Testing CallGraphInput validation...")
    
    # Test valid input
    try:
        valid_input = CallGraphInput(
            path="./src",
            languages=["javascript", "python"],
            include_external=False
        )
        print("✅ Valid CallGraphInput passes")
    except Exception as e:
        print(f"❌ Valid input failed: {e}")
        return False
    
    # Test too many languages
    try:
        too_many_langs = ["js"] * 25
        CallGraphInput(
            path="./src",
            languages=too_many_langs,
            include_external=False
        )
        print("❌ Should have failed - too many languages")
        return False
    except ValueError as e:
        print(f"✅ Correctly rejected too many languages: {str(e)[:100]}...")
    
    # Test dangerous characters in language
    try:
        CallGraphInput(
            path="./src",
            languages=["javascript; rm -rf /"],
            include_external=False
        )
        print("❌ Should have failed - dangerous characters")
        return False
    except ValueError as e:
        print(f"✅ Correctly rejected dangerous characters: {str(e)[:100]}...")
    
    # Test duplicate languages
    try:
        CallGraphInput(
            path="./src",
            languages=["javascript", "js", "javascript"],
            include_external=False
        )
        print("❌ Should have failed - duplicate languages")
        return False
    except ValueError as e:
        print(f"✅ Correctly rejected duplicate languages: {str(e)[:100]}...")
    
    return True

def test_search_tool_input_validation():
    """Test SearchToolInput glob validation enhancements."""
    print("\nTesting SearchToolInput glob validation...")
    
    # Test valid globs
    try:
        valid_input = SearchToolInput(
            pattern="console.log($MSG)",
            language="javascript", 
            path="./src",
            include_globs=["*.js", "*.ts"],
            exclude_globs=["node_modules/**"]
        )
        print("✅ Valid SearchToolInput with globs passes")
    except Exception as e:
        print(f"❌ Valid globs failed: {e}")
        return False
    
    # Test dangerous characters in globs
    try:
        SearchToolInput(
            pattern="test",
            language="javascript",
            path="./src",
            include_globs=["*.js && rm -rf /"]
        )
        print("❌ Should have failed - dangerous glob")
        return False
    except ValueError as e:
        print(f"✅ Correctly rejected dangerous glob: {str(e)[:100]}...")
    
    # Test overly broad patterns
    try:
        SearchToolInput(
            pattern="test",
            language="javascript",
            path="./src",
            include_globs=["*"]
        )
        print("❌ Should have failed - overly broad pattern")
        return False
    except ValueError as e:
        print(f"✅ Correctly rejected broad pattern: {str(e)[:100]}...")
    
    # Test unmatched brackets
    try:
        SearchToolInput(
            pattern="test",
            language="javascript",
            path="./src",
            include_globs=["*.js[abc"]
        )
        print("❌ Should have failed - unmatched brackets")
        return False
    except ValueError as e:
        print(f"✅ Correctly rejected unmatched brackets: {str(e)[:100]}...")
    
    return True

def main():
    """Run all validation tests."""
    print("🧪 Testing Pydantic Validation Enhancements")
    print("=" * 50)
    
    success = True
    
    try:
        success &= test_call_graph_input_validation()
        success &= test_search_tool_input_validation()
        
        print("\n" + "=" * 50)
        if success:
            print("🎉 All validation tests PASSED!")
            return 0
        else:
            print("❌ Some validation tests FAILED!")
            return 1
            
    except Exception as e:
        print(f"\n💥 Test execution failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main()) 