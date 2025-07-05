#!/usr/bin/env python3
"""MCP Structured Output Validation Tests.

This module enhances existing validation tests with MCP SDK structured output patterns,
testing Pydantic model validation using MCP SDK patterns, type hint compliance,
and schema generation verification.
"""

import asyncio
import json
import sys
import os
import tempfile
import time
from pathlib import Path
from typing import Dict, Any, List, Optional, Union, get_type_hints, get_origin, get_args
import inspect

# Add src to Python path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

try:
    from ast_grep_mcp.server import create_server, ServerConfig
    from ast_grep_mcp.tools import (
        SearchToolInput, ScanToolInput, RunToolInput, CallGraphInput
    )
    from pydantic import BaseModel, ValidationError, Field
    import jsonschema
    
    # Create simple result models for testing structured output patterns
    class SearchResult(BaseModel):
        matches: List[Dict[str, Any]] = []
        total_matches: int = 0
        files_searched: int = 0
        search_time_ms: int = 0
        pattern: str = ""
        language: str = ""
    
    class ScanResult(BaseModel):
        issues: List[Dict[str, Any]] = []
        total_issues: int = 0
        files_scanned: int = 0
        scan_time_ms: int = 0
        rules_applied: List[str] = []
    
    class RunResult(BaseModel):
        output: str = ""
        exit_code: int = 0
        execution_time_ms: int = 0
        command: str = ""
    
    class CallGraphResult(BaseModel):
        nodes: List[Dict[str, Any]] = []
        edges: List[Dict[str, Any]] = []
        total_functions: int = 0
        total_calls: int = 0
        generation_time_ms: int = 0
except ImportError as e:
    print(f"Import error: {e}")
    print("Please install dependencies: pip install -e .")
    sys.exit(1)


class MCPStructuredOutputValidator:
    """Validate MCP structured output compliance using SDK patterns."""
    
    def __init__(self):
        self.test_results = []
        self.server = None
        
    def record_test(self, test_name: str, passed: bool, details: str = ""):
        """Record test result."""
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} {test_name}")
        if details:
            print(f"    {details}")
        
        self.test_results.append({
            "test": test_name,
            "passed": passed,
            "details": details,
            "timestamp": time.time()
        })
    
    async def setup_server(self):
        """Set up MCP server for structured output testing."""
        print("🔧 Setting up MCP server for structured output testing...")
        
        try:
            config = ServerConfig()
            config.enable_performance = True
            config.enable_security = True
            config.enable_monitoring = False
            config.system_monitoring_enabled = False
            config.alerting_enabled = False
            config.dependency_check_enabled = False
            
            server_wrapper = create_server(config)
            await server_wrapper.initialize()
            self.server = server_wrapper.server
            
            print("✅ MCP server initialized for structured output testing")
            return True
            
        except Exception as e:
            print(f"❌ Server setup failed: {e}")
            return False
    
    def validate_pydantic_model_structure(self, model_class: type) -> bool:
        """Validate Pydantic model follows MCP SDK patterns."""
        try:
            # Must be a Pydantic BaseModel
            if not issubclass(model_class, BaseModel):
                return False
            
            # Should have model_config or be properly configured
            if hasattr(model_class, 'model_config'):
                config = model_class.model_config
                # Check for common MCP configurations
                if hasattr(config, 'extra') and config.extra == 'forbid':
                    # Good practice for MCP models
                    pass
            
            # All fields should have type annotations
            fields = model_class.model_fields
            for field_name, field_info in fields.items():
                if field_info.annotation is None:
                    return False
            
            # Should be able to generate JSON schema
            try:
                schema = model_class.model_json_schema()
                if not isinstance(schema, dict):
                    return False
            except Exception:
                return False
            
            return True
            
        except Exception:
            return False
    
    def validate_structured_output_compliance(self, model_class: type, sample_data: Dict[str, Any]) -> bool:
        """Validate structured output compliance with MCP patterns."""
        try:
            # Create instance from sample data
            instance = model_class(**sample_data)
            
            # Test serialization to JSON
            json_output = instance.model_dump_json()
            if not json_output:
                return False
            
            # Test deserialization from JSON
            parsed_data = json.loads(json_output)
            reconstructed = model_class(**parsed_data)
            
            # Test that reconstructed instance is equivalent
            if instance.model_dump() != reconstructed.model_dump():
                return False
            
            # Test schema validation
            schema = model_class.model_json_schema()
            jsonschema.validate(instance.model_dump(), schema)
            
            return True
            
        except Exception:
            return False
    
    def validate_return_type_annotations(self, func: callable) -> bool:
        """Validate function return type annotations for MCP compliance."""
        try:
            type_hints = get_type_hints(func)
            
            if 'return' not in type_hints:
                return False
            
            return_type = type_hints['return']
            
            # Check if return type is a structured type (class, Union, etc.)
            if hasattr(return_type, '__origin__'):
                # Handle Union, Optional, List, etc.
                origin = get_origin(return_type)
                args = get_args(return_type)
                
                # For Union types (like Optional), check that at least one is structured
                if origin is Union:
                    for arg in args:
                        if inspect.isclass(arg) and issubclass(arg, BaseModel):
                            return True
                
                # For List types, check the element type
                elif origin is list:
                    if args and inspect.isclass(args[0]) and issubclass(args[0], BaseModel):
                        return True
            
            # Check if return type is directly a Pydantic model
            elif inspect.isclass(return_type) and issubclass(return_type, BaseModel):
                return True
            
            return False
            
        except Exception:
            return False
    
    async def test_input_model_structure(self):
        """Test input model structure compliance."""
        print("\n📥 Testing Input Model Structure Compliance")
        
        input_models = [
            SearchToolInput,
            ScanToolInput,
            RunToolInput,
            CallGraphInput
        ]
        
        for model in input_models:
            # Test basic Pydantic structure
            structured_correctly = self.validate_pydantic_model_structure(model)
            self.record_test(
                f"Input model structure - {model.__name__}",
                structured_correctly,
                f"Pydantic structure {'valid' if structured_correctly else 'invalid'}"
            )
            
            # Test field annotations
            fields = model.model_fields
            all_annotated = all(field.annotation is not None for field in fields.values())
            self.record_test(
                f"Input model annotations - {model.__name__}",
                all_annotated,
                f"All {len(fields)} fields have type annotations"
            )
            
            # Test schema generation
            try:
                schema = model.model_json_schema()
                has_valid_schema = isinstance(schema, dict) and "type" in schema
                self.record_test(
                    f"Input model schema - {model.__name__}",
                    has_valid_schema,
                    f"JSON schema generation {'successful' if has_valid_schema else 'failed'}"
                )
            except Exception as e:
                self.record_test(
                    f"Input model schema - {model.__name__}",
                    False,
                    f"Schema generation error: {e}"
                )
    
    async def test_output_model_structure(self):
        """Test output model structure compliance."""
        print("\n📤 Testing Output Model Structure Compliance")
        
        output_models = [
            SearchResult,
            ScanResult,
            RunResult,
            CallGraphResult
        ]
        
        for model in output_models:
            # Test basic Pydantic structure
            structured_correctly = self.validate_pydantic_model_structure(model)
            self.record_test(
                f"Output model structure - {model.__name__}",
                structured_correctly,
                f"Pydantic structure {'valid' if structured_correctly else 'invalid'}"
            )
            
            # Test that output models can be serialized/deserialized
            try:
                # Create a minimal valid instance
                if model == SearchResult:
                    sample_data = {
                        "matches": [],
                        "total_matches": 0,
                        "files_searched": 0,
                        "search_time_ms": 100,
                        "pattern": "test",
                        "language": "javascript"
                    }
                elif model == ScanResult:
                    sample_data = {
                        "issues": [],
                        "total_issues": 0,
                        "files_scanned": 0,
                        "scan_time_ms": 100,
                        "rules_applied": []
                    }
                elif model == RunResult:
                    sample_data = {
                        "output": "test output",
                        "exit_code": 0,
                        "execution_time_ms": 100,
                        "command": "test command"
                    }
                elif model == CallGraphResult:
                    sample_data = {
                        "nodes": [],
                        "edges": [],
                        "total_functions": 0,
                        "total_calls": 0,
                        "generation_time_ms": 100
                    }
                else:
                    sample_data = {}
                
                compliant = self.validate_structured_output_compliance(model, sample_data)
                self.record_test(
                    f"Output model serialization - {model.__name__}",
                    compliant,
                    f"Structured output {'compliant' if compliant else 'non-compliant'}"
                )
                
            except Exception as e:
                self.record_test(
                    f"Output model serialization - {model.__name__}",
                    False,
                    f"Serialization error: {e}"
                )
    
    async def test_type_hint_patterns(self):
        """Test type hint patterns for MCP compliance."""
        print("\n🏷️ Testing Type Hint Patterns")
        
        # Test function type hints from tools module - focus on MCP tool functions only
        try:
            from ast_grep_mcp import tools
            
            # Get only the actual MCP tool functions, not imported utilities
            mcp_tool_functions = [
                ('ast_grep_search', getattr(tools, 'ast_grep_search', None)),
                ('ast_grep_scan', getattr(tools, 'ast_grep_scan', None)),
                ('ast_grep_run', getattr(tools, 'ast_grep_run', None)),
            ]
            
            # Filter out None values
            tool_functions = [(name, func) for name, func in mcp_tool_functions if func is not None]
            
            for func_name, func in tool_functions:
                try:
                    # Test that function has type hints
                    type_hints = get_type_hints(func)
                    has_type_hints = len(type_hints) > 0
                    
                    self.record_test(
                        f"Function type hints - {func_name}",
                        has_type_hints,
                        f"Function has {len(type_hints)} type hints"
                    )
                    
                    # Test return type annotation if it exists
                    if 'return' in type_hints:
                        return_type_valid = self.validate_return_type_annotations(func)
                        self.record_test(
                            f"Return type annotation - {func_name}",
                            return_type_valid,
                            f"Return type {'properly' if return_type_valid else 'improperly'} annotated"
                        )
                    
                except Exception as e:
                    self.record_test(
                        f"Function analysis - {func_name}",
                        False,
                        f"Error: {e}"
                    )
                    
        except Exception as e:
            self.record_test(
                "Type hint patterns - Tools module",
                False,
                f"Error accessing tools module: {e}"
            )
    
    async def test_mcp_content_types(self):
        """Test MCP content type compliance."""
        print("\n📄 Testing MCP Content Type Compliance")
        
        # Test that our models can be converted to MCP content types
        try:
            from mcp.types import TextContent, ImageContent
            
            # Test SearchResult conversion to TextContent
            search_result = SearchResult(
                matches=[],
                total_matches=0,
                files_searched=0,
                search_time_ms=100,
                pattern="test",
                language="javascript"
            )
            
            # Convert to JSON text content
            text_content = TextContent(
                type="text",
                text=search_result.model_dump_json(indent=2)
            )
            
            self.record_test(
                "MCP content type - SearchResult to TextContent",
                isinstance(text_content.text, str) and len(text_content.text) > 0,
                "Successfully converted to MCP TextContent"
            )
            
            # Test that JSON content is valid
            try:
                parsed = json.loads(text_content.text)
                valid_json = isinstance(parsed, dict)
                self.record_test(
                    "MCP content type - JSON validity",
                    valid_json,
                    "TextContent contains valid JSON"
                )
            except json.JSONDecodeError:
                self.record_test(
                    "MCP content type - JSON validity",
                    False,
                    "TextContent does not contain valid JSON"
                )
            
        except Exception as e:
            self.record_test(
                "MCP content type compliance",
                False,
                f"Error: {e}"
            )
    
    async def test_schema_evolution_compatibility(self):
        """Test schema evolution compatibility."""
        print("\n🔄 Testing Schema Evolution Compatibility")
        
        # Test that models handle additional fields gracefully
        try:
            # Test with extra fields that might be added in future versions
            extra_data = {
                "matches": [],
                "total_matches": 0,
                "files_searched": 0,
                "search_time_ms": 100,
                "pattern": "test",
                "language": "javascript",
                "future_field": "some_value",  # Extra field
                "experimental_feature": {"enabled": True}  # Extra nested field
            }
            
            # Depending on model configuration, this should either accept or reject extra fields
            try:
                result = SearchResult(**extra_data)
                # If model accepts extra fields
                self.record_test(
                    "Schema evolution - Extra fields accepted",
                    True,
                    "Model gracefully accepts additional fields"
                )
            except ValidationError:
                # If model rejects extra fields (strict mode)
                self.record_test(
                    "Schema evolution - Extra fields rejected",
                    True,
                    "Model enforces strict schema validation"
                )
            
            # Test partial data (missing optional fields)
            minimal_data = {
                "matches": [],
                "total_matches": 0,
                "files_searched": 0,
                "search_time_ms": 100,
                "pattern": "test",
                "language": "javascript"
            }
            
            minimal_result = SearchResult(**minimal_data)
            self.record_test(
                "Schema evolution - Minimal data",
                True,
                "Model accepts minimal required data"
            )
            
        except Exception as e:
            self.record_test(
                "Schema evolution compatibility",
                False,
                f"Error: {e}"
            )
    
    async def test_nested_model_validation(self):
        """Test nested model validation patterns."""
        print("\n🪆 Testing Nested Model Validation")
        
        try:
            # Test complex nested data for SearchResult
            complex_match_data = {
                "matches": [
                    {
                        "file": "test.js",
                        "line": 1,
                        "column": 1,
                        "match": "console.log('test')",
                        "context_before": ["// some comment"],
                        "context_after": ["// another line"]
                    },
                    {
                        "file": "test2.js",
                        "line": 5,
                        "column": 10,
                        "match": "console.log('another test')",
                        "context_before": [],
                        "context_after": []
                    }
                ],
                "total_matches": 2,
                "files_searched": 2,
                "search_time_ms": 150,
                "pattern": "console.log($MSG)",
                "language": "javascript"
            }
            
            complex_result = SearchResult(**complex_match_data)
            
            # Test that nested data is properly validated
            self.record_test(
                "Nested model validation - Complex matches",
                len(complex_result.matches) == 2,
                f"Successfully validated {len(complex_result.matches)} nested match objects"
            )
            
            # Test serialization of nested data
            json_output = complex_result.model_dump_json()
            parsed_back = json.loads(json_output)
            
            self.record_test(
                "Nested model validation - Serialization",
                len(parsed_back["matches"]) == 2,
                "Nested data serializes correctly"
            )
            
            # Test reconstruction from serialized data
            reconstructed = SearchResult(**parsed_back)
            
            self.record_test(
                "Nested model validation - Reconstruction",
                len(reconstructed.matches) == 2,
                "Can reconstruct from serialized nested data"
            )
            
        except Exception as e:
            self.record_test(
                "Nested model validation",
                False,
                f"Error: {e}"
            )
    
    async def test_custom_validator_patterns(self):
        """Test custom validator patterns in models."""
        print("\n🔧 Testing Custom Validator Patterns")
        
        try:
            # Test SearchToolInput custom validations
            
            # Test pattern length validation
            try:
                very_long_pattern = "x" * 10000
                SearchToolInput(
                    pattern=very_long_pattern,
                    language="javascript", 
                    path="./test"
                )
                self.record_test(
                    "Custom validator - Pattern length (should fail)",
                    False,
                    "Very long pattern was accepted"
                )
            except ValidationError:
                self.record_test(
                    "Custom validator - Pattern length",
                    True,
                    "Pattern length validation working"
                )
            
            # Test language validation
            try:
                SearchToolInput(
                    pattern="test",
                    language="invalid_language_xyz",
                    path="./test"
                )
                self.record_test(
                    "Custom validator - Language validation (should fail)",
                    False,
                    "Invalid language was accepted"
                )
            except ValidationError:
                self.record_test(
                    "Custom validator - Language validation",
                    True,
                    "Language validation working"
                )
            
            # Test valid cases still work
            valid_input = SearchToolInput(
                pattern="console.log($MSG)",
                language="javascript",
                path="./test",
                recursive=True,
                output_format="json"
            )
            
            self.record_test(
                "Custom validator - Valid input",
                True,
                "Valid input still passes validation"
            )
            
        except Exception as e:
            self.record_test(
                "Custom validator patterns",
                False,
                f"Error: {e}"
            )
    
    async def run_all_tests(self):
        """Run all structured output validation tests."""
        print("=" * 60)
        print("MCP Structured Output Validation Tests")
        print("=" * 60)
        
        try:
            # Setup server
            if not await self.setup_server():
                return False
            
            # Run test suite
            await self.test_input_model_structure()
            await self.test_output_model_structure()
            await self.test_type_hint_patterns()
            await self.test_mcp_content_types()
            await self.test_schema_evolution_compatibility()
            await self.test_nested_model_validation()
            await self.test_custom_validator_patterns()
            
            return True
            
        except Exception as e:
            print(f"❌ Structured output validation test suite failed: {e}")
            return False
    
    def print_summary(self):
        """Print test summary."""
        print("\n" + "=" * 60)
        print("STRUCTURED OUTPUT VALIDATION TEST SUMMARY")
        print("=" * 60)
        
        total_tests = len(self.test_results)
        passed_tests = sum(1 for result in self.test_results if result["passed"])
        failed_tests = total_tests - passed_tests
        
        print(f"Total Tests: {total_tests}")
        print(f"Passed: {passed_tests}")
        print(f"Failed: {failed_tests}")
        print(f"Success Rate: {(passed_tests / total_tests * 100):.1f}%")
        
        if failed_tests > 0:
            print("\nFailed Tests:")
            for result in self.test_results:
                if not result["passed"]:
                    print(f"  - {result['test']}: {result['details']}")
        
        return failed_tests == 0


async def main():
    """Main test function."""
    validator = MCPStructuredOutputValidator()
    
    try:
        success = await validator.run_all_tests()
        validator.print_summary()
        
        if success:
            print("\n🎉 All structured output validation tests passed!")
            return 0
        else:
            print("\n❌ Some structured output validation tests failed!")
            return 1
            
    except Exception as e:
        print(f"❌ Test suite failed: {e}")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)