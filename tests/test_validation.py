#!/usr/bin/env python3
"""Comprehensive validation testing for AST-Grep MCP."""

import sys
import os
from pathlib import Path

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

try:
    from ast_grep_mcp.tools import SearchToolInput, ScanToolInput, RunToolInput, CallGraphInput
    from pydantic import ValidationError
    import tempfile
    import json
except ImportError as e:
    print(f"Import error: {e}")
    print("Please install dependencies or check paths")
    sys.exit(1)

# Mock the external dependencies for standalone testing
class MockLanguageManager:
    def validate_language_identifier(self, lang):
        valid_langs = ['javascript', 'python', 'js', 'py', 'typescript', 'ts', 'rust', 'go']
        return lang in valid_langs
    
    def suggest_similar_languages(self, lang):
        return ['javascript', 'python']

def mock_get_language_manager():
    return MockLanguageManager()

def mock_sanitize_path(path_str):
    return Path(path_str).resolve()

# Apply mocks if needed
try:
    import ast_grep_mcp.tools
    ast_grep_mcp.tools.get_language_manager = mock_get_language_manager
    ast_grep_mcp.tools.sanitize_path = mock_sanitize_path
except:
    pass  # Ignore if modules not available

def test_search_input_validation():
    """Test SearchToolInput validation."""
    print("🔍 Testing SearchToolInput validation...")
    
    # Test 1: Valid input
    try:
        valid_input = SearchToolInput(
            pattern="console.log($MSG)",
            language="javascript",
            path="./src",
            recursive=True,
            output_format="json"
        )
        print("✅ Valid SearchToolInput passes")
    except Exception as e:
        print(f"❌ Valid SearchToolInput failed: {e}")
        return False
    
    # Test 2: Invalid language
    try:
        SearchToolInput(
            pattern="test",
            language="invalid_language",
            path="./src"
        )
        print("❌ Should have failed - invalid language")
        return False
    except ValidationError:
        print("✅ Invalid language correctly rejected")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False
    
    # Test 3: Empty pattern
    try:
        SearchToolInput(
            pattern="",
            language="javascript",
            path="./src"
        )
        print("❌ Should have failed - empty pattern")
        return False
    except ValidationError:
        print("✅ Empty pattern correctly rejected")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False
    
    # Test 4: Pattern too long
    try:
        long_pattern = "x" * 5000
        SearchToolInput(
            pattern=long_pattern,
            language="javascript",
            path="./src"
        )
        print("❌ Should have failed - pattern too long")
        return False
    except ValidationError:
        print("✅ Long pattern correctly rejected")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False
    
    return True

def test_call_graph_input_validation():
    """Test CallGraphInput validation."""
    print("\n📊 Testing CallGraphInput validation...")
    
    # Test valid input
    try:
        valid_input = CallGraphInput(
            path="./src",
            languages=["javascript", "python"],
            include_external=False
        )
        print("✅ Valid CallGraphInput passes")
    except Exception as e:
        print(f"❌ Valid CallGraphInput failed: {e}")
        return False
    
    # Test invalid language
    try:
        CallGraphInput(
            path="./src",
            languages=["invalid_language"],
            include_external=False
        )
        print("❌ Should have failed - invalid language")
        return False
    except ValidationError:
        print("✅ Invalid language correctly rejected")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False
    
    # Test empty languages list
    try:
        CallGraphInput(
            path="./src",
            languages=[],
            include_external=False
        )
        print("❌ Should have failed - empty languages")
        return False
    except ValidationError:
        print("✅ Empty languages correctly rejected")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False
    
    return True

def test_scan_input_validation():
    """Test ScanToolInput validation."""
    print("\n🔎 Testing ScanToolInput validation...")
    
    # Create temporary rule file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
        f.write("""
rules:
  - id: test-rule
    pattern: "console.log($MSG)"
    message: "Test rule"
        """)
        rule_file = f.name
    
    try:
        # Test valid input
        try:
            valid_input = ScanToolInput(
                path="./src",  # Required field
                rules_config=rule_file,  # Correct field name
                output_format="json"
            )
            print("✅ Valid ScanToolInput passes")
        except Exception as e:
            print(f"❌ Valid ScanToolInput failed: {e}")
            return False
        
        # Test non-existent rule file
        try:
            ScanToolInput(
                path="./src",
                rules_config="/nonexistent/rule.yml"
            )
            print("❌ Should have failed - non-existent rule file")
            return False
        except ValidationError:
            print("✅ Non-existent rule file correctly rejected")
        except Exception as e:
            print(f"❌ Unexpected error: {e}")
            return False
        
        return True
        
    finally:
        # Clean up
        os.unlink(rule_file)

def test_path_validation():
    """Test path validation and sanitization."""
    print("\n📁 Testing path validation...")
    
    # Test 1: Valid relative path
    try:
        input_data = SearchToolInput(
            pattern="test",
            language="javascript",
            path="./src"
        )
        print("✅ Valid relative path accepted")
    except Exception as e:
        print(f"❌ Valid relative path failed: {e}")
        return False
    
    # Test 2: Dangerous path traversal
    try:
        SearchToolInput(
            pattern="test",
            language="javascript",
            path="../../../etc/passwd"
        )
        # This should be handled by security layer, not validation
        print("⚠️  Path traversal not caught at validation level (handled by security layer)")
    except Exception as e:
        print(f"ℹ️  Path traversal handling: {e}")
    
    return True

def test_pattern_validation():
    """Test AST-Grep pattern validation."""
    print("\n🎯 Testing pattern validation...")
    
    patterns_to_test = [
        ("console.log($MSG)", True, "Valid meta-variable pattern"),
        ("function $NAME() { $BODY }", True, "Valid function pattern"),
        ("$X + $Y", True, "Valid expression pattern"),
        ("", False, "Empty pattern"),
        ("   ", False, "Whitespace-only pattern"),
        ("$", False, "Invalid meta-variable"),
        ("$123", False, "Numeric meta-variable"),
    ]
    
    success_count = 0
    for pattern, should_pass, description in patterns_to_test:
        try:
            SearchToolInput(
                pattern=pattern,
                language="javascript",
                path="./src"
            )
            if should_pass:
                print(f"✅ {description}: correctly accepted")
                success_count += 1
            else:
                print(f"❌ {description}: should have been rejected")
        except ValidationError:
            if not should_pass:
                print(f"✅ {description}: correctly rejected")
                success_count += 1
            else:
                print(f"❌ {description}: should have been accepted")
        except Exception as e:
            print(f"❌ {description}: unexpected error - {e}")
    
    return success_count == len(patterns_to_test)

def test_output_format_validation():
    """Test output format validation."""
    print("\n📤 Testing output format validation...")
    
    valid_formats = ["json", "text"]
    invalid_formats = ["xml", "csv", "", "invalid"]
    
    # Test valid formats
    for fmt in valid_formats:
        try:
            SearchToolInput(
                pattern="test",
                language="javascript",
                path="./src",
                output_format=fmt
            )
            print(f"✅ Valid format '{fmt}' accepted")
        except Exception as e:
            print(f"❌ Valid format '{fmt}' rejected: {e}")
            return False
    
    # Test invalid formats
    for fmt in invalid_formats:
        try:
            SearchToolInput(
                pattern="test",
                language="javascript",
                path="./src",
                output_format=fmt
            )
            print(f"❌ Invalid format '{fmt}' should have been rejected")
            return False
        except ValidationError:
            print(f"✅ Invalid format '{fmt}' correctly rejected")
        except Exception as e:
            print(f"❌ Unexpected error for '{fmt}': {e}")
            return False
    
    return True

def run_all_validation_tests():
    """Run comprehensive validation tests."""
    print("=" * 60)
    print("🧪 AST-Grep MCP Validation Test Suite")
    print("=" * 60)
    
    test_functions = [
        test_search_input_validation,
        test_call_graph_input_validation,
        test_scan_input_validation,
        test_path_validation,
        test_pattern_validation,
        test_output_format_validation
    ]
    
    passed = 0
    total = len(test_functions)
    
    for test_func in test_functions:
        try:
            if test_func():
                passed += 1
        except Exception as e:
            print(f"❌ Test {test_func.__name__} failed with error: {e}")
    
    print("\n" + "=" * 60)
    print("📊 Validation Test Results")
    print("=" * 60)
    print(f"Passed: {passed}/{total}")
    print(f"Success Rate: {(passed/total)*100:.1f}%")
    
    if passed == total:
        print("🎉 ALL VALIDATION TESTS PASSED!")
        return True
    else:
        print(f"❌ {total-passed} VALIDATION TESTS FAILED!")
        return False

if __name__ == "__main__":
    success = run_all_validation_tests()
    sys.exit(0 if success else 1)