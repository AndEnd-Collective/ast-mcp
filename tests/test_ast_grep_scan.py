"""Tests for AST-grep scan error handling, response formatting, and utility functions."""

import sys
import json
from pathlib import Path

# Add src to Python path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


class TestErrorHandling:
    """Test error handling and structured responses."""

    def test_validation_error_response(self):
        """Test validation error response structure."""
        from ast_grep_mcp.utils import handle_validation_error

        error = ValueError("Invalid language 'invalid_lang'")
        result = handle_validation_error(error, "Language validation", "/test/path")

        assert result["status"] == "error"
        assert result["error"] == "Validation Error"
        assert "Language validation" in result["message"]
        assert result["path"] == "/test/path"
        assert "timestamp" in result

    def test_configuration_error_response(self):
        """Test configuration error response structure."""
        from ast_grep_mcp.utils import handle_configuration_error

        error = ValueError("Missing ruleDirs field")
        result = handle_configuration_error(error, "/test/sgconfig.yml")

        assert result["status"] == "error"
        assert result["error"] == "Configuration Error"
        assert result["path"] == "/test/sgconfig.yml"
        assert "suggestions" in result
        assert len(result["suggestions"]) > 0

    def test_execution_error_response(self):
        """Test execution error response structure."""
        from ast_grep_mcp.utils import handle_execution_error, ASTGrepNotFoundError

        error = ASTGrepNotFoundError("ast-grep binary not found")
        result = handle_execution_error(error, command=["sg", "search"], path="/test/path")

        assert result["status"] == "error"
        assert result["error"] == "Execution Error"
        assert result["path"] == "/test/path"
        assert "details" in result
        assert "command" in result["details"]
        assert "suggestions" in result
        assert any("install" in s.lower() for s in result["suggestions"])

    def test_success_response_structure(self):
        """Test success response structure."""
        from ast_grep_mcp.utils import create_success_response

        data = {"matches": [], "total": 0}
        result = create_success_response(data, "Scan completed successfully")

        assert result["status"] == "success"
        assert result["data"] == data
        assert result["message"] == "Scan completed successfully"
        assert "timestamp" in result

    def test_format_tool_response_json(self):
        """Test tool response formatting for JSON output."""
        from ast_grep_mcp.utils import format_tool_response

        data = {"violations": [], "summary": {"total": 0}}
        result = format_tool_response(data, "json", True, "Scan completed")

        assert len(result) == 1
        assert result[0].type == "text"

        # Parse the JSON to verify structure
        parsed = json.loads(result[0].text)
        assert parsed["status"] == "success"
        assert parsed["data"] == data

    def test_format_tool_response_text_error(self):
        """Test tool response formatting for text output with error."""
        from ast_grep_mcp.utils import format_tool_response, create_error_response

        error_info = create_error_response(
            "Test Error",
            "This is a test error",
            suggestions=["Try this", "Or this"]
        )

        result = format_tool_response(
            data=None,
            output_format="text",
            success=False,
            error_info=error_info
        )

        assert len(result) == 1
        assert result[0].type == "text"
        assert "Error: This is a test error" in result[0].text
        assert "Suggestions:" in result[0].text
        assert "Try this" in result[0].text


class TestScanResultFormatting:
    """Test scan result formatting for JSON and text output."""

    def test_format_tool_response_json_success_with_metadata(self):
        """Test JSON format includes metadata when provided."""
        from ast_grep_mcp.utils import format_tool_response

        data = {"violations": [{"rule": "no-console", "file": "test.js"}]}
        metadata = {"scan_duration_ms": 150, "files_scanned": 42}
        result = format_tool_response(
            data, "json", True, "Scan completed", metadata=metadata
        )

        assert len(result) == 1
        parsed = json.loads(result[0].text)
        assert parsed["status"] == "success"
        assert parsed["data"] == data
        assert parsed["metadata"] == metadata

    def test_format_tool_response_json_success_no_message(self):
        """Test JSON format works without optional message."""
        from ast_grep_mcp.utils import format_tool_response

        data = {"results": []}
        result = format_tool_response(data, "json", True)

        assert len(result) == 1
        parsed = json.loads(result[0].text)
        assert parsed["status"] == "success"
        assert parsed["data"] == data
        # message is optional
        assert "message" not in parsed or parsed.get("message") is None

    def test_format_tool_response_text_success(self):
        """Test text format for successful result."""
        from ast_grep_mcp.utils import format_tool_response

        data = {"violations": [], "summary": {"total": 0}}
        result = format_tool_response(data, "text", True, "No violations found")

        assert len(result) == 1
        assert result[0].type == "text"
        # Text mode should still produce readable output
        text = result[0].text
        assert len(text) > 0

    def test_format_tool_response_json_error(self):
        """Test JSON format for error response."""
        from ast_grep_mcp.utils import format_tool_response, create_error_response

        error_info = create_error_response(
            "Scan Error",
            "Failed to read configuration file",
            path="/project/sgconfig.yml",
            suggestions=["Check file permissions", "Verify YAML syntax"]
        )

        result = format_tool_response(
            data=None, output_format="json", success=False, error_info=error_info
        )

        assert len(result) == 1
        parsed = json.loads(result[0].text)
        assert parsed["status"] == "error"

    def test_format_tool_response_text_error_without_suggestions(self):
        """Test text format for error without suggestions."""
        from ast_grep_mcp.utils import format_tool_response, create_error_response

        error_info = create_error_response(
            "Parse Error",
            "Syntax error in pattern",
        )

        result = format_tool_response(
            data=None, output_format="text", success=False, error_info=error_info
        )

        assert len(result) == 1
        assert "Syntax error in pattern" in result[0].text


class TestScanInputValidationEdgeCases:
    """Test scan input validation edge cases."""

    def test_validation_error_for_ast_grep_validation_error(self):
        """Test handling of ASTGrepValidationError with language suggestions."""
        from ast_grep_mcp.utils import handle_validation_error, ASTGrepValidationError

        error = ASTGrepValidationError("Similar languages: python, py")
        result = handle_validation_error(error, "Language validation", "/test/path")

        assert result["status"] == "error"
        assert result["error"] == "AST-Grep Validation Error"
        assert "suggestions" in result
        assert any("supported languages" in s.lower() for s in result["suggestions"])

    def test_validation_error_for_pattern_errors(self):
        """Test handling of pattern-related validation errors."""
        from ast_grep_mcp.utils import handle_validation_error

        error = ValueError("Invalid pattern syntax")
        result = handle_validation_error(error, "Pattern validation")

        assert result["status"] == "error"
        assert "suggestions" in result

    def test_validation_error_without_path(self):
        """Test validation error response without path."""
        from ast_grep_mcp.utils import handle_validation_error

        error = ValueError("Something wrong")
        result = handle_validation_error(error, "General validation")

        assert result["status"] == "error"
        # path should be None or absent when not provided
        assert result.get("path") is None

    def test_configuration_error_with_rule_dirs_suggestion(self):
        """Test configuration error includes ruleDirs-specific suggestions."""
        from ast_grep_mcp.utils import handle_configuration_error

        error = ValueError("Missing ruleDirs field in config")
        result = handle_configuration_error(error, "/project/sgconfig.yml")

        assert result["status"] == "error"
        assert any("ruleDirs" in s or "rule" in s.lower() for s in result["suggestions"])

    def test_configuration_error_general(self):
        """Test general configuration error without ruleDirs."""
        from ast_grep_mcp.utils import handle_configuration_error

        error = ValueError("Invalid YAML syntax")
        result = handle_configuration_error(error, "/project/sgconfig.yml")

        assert result["status"] == "error"
        assert len(result["suggestions"]) > 0
        assert any("YAML" in s or "yaml" in s.lower() for s in result["suggestions"])

    def test_configuration_error_without_path(self):
        """Test configuration error without config path."""
        from ast_grep_mcp.utils import handle_configuration_error

        error = ValueError("Config error")
        result = handle_configuration_error(error)

        assert result["status"] == "error"
        assert result.get("path") is None


class TestErrorResponseCreation:
    """Test error response creation with various inputs."""

    def test_create_error_response_basic(self):
        """Test basic error response creation."""
        from ast_grep_mcp.utils import create_error_response

        result = create_error_response("TestError", "Something went wrong")

        assert result["error"] == "TestError"
        assert result["message"] == "Something went wrong"
        assert result["status"] == "error"
        assert "timestamp" in result

    def test_create_error_response_with_details(self):
        """Test error response with details dict."""
        from ast_grep_mcp.utils import create_error_response

        details = {"line": 42, "column": 10, "file": "test.py"}
        result = create_error_response(
            "ParseError", "Parse failed", details=details
        )

        assert result["details"] == details

    def test_create_error_response_with_path(self):
        """Test error response with path."""
        from ast_grep_mcp.utils import create_error_response

        result = create_error_response(
            "FileError", "File not found", path="/missing/file.py"
        )

        assert result["path"] == "/missing/file.py"

    def test_create_error_response_with_suggestions(self):
        """Test error response with suggestions list."""
        from ast_grep_mcp.utils import create_error_response

        suggestions = ["Check the file path", "Verify permissions"]
        result = create_error_response(
            "AccessError", "Cannot access file", suggestions=suggestions
        )

        assert result["suggestions"] == suggestions

    def test_create_error_response_with_all_optional_fields(self):
        """Test error response with all optional fields populated."""
        from ast_grep_mcp.utils import create_error_response

        result = create_error_response(
            "FullError",
            "Full error message",
            details={"code": 500},
            path="/some/path",
            suggestions=["fix it"]
        )

        assert result["error"] == "FullError"
        assert result["message"] == "Full error message"
        assert result["details"] == {"code": 500}
        assert result["path"] == "/some/path"
        assert result["suggestions"] == ["fix it"]
        assert result["status"] == "error"
        assert "timestamp" in result

    def test_create_success_response_without_message(self):
        """Test success response without optional message."""
        from ast_grep_mcp.utils import create_success_response

        data = [1, 2, 3]
        result = create_success_response(data)

        assert result["status"] == "success"
        assert result["data"] == data
        assert "message" not in result

    def test_create_success_response_with_metadata(self):
        """Test success response with metadata."""
        from ast_grep_mcp.utils import create_success_response

        data = {"results": []}
        metadata = {"duration_ms": 50}
        result = create_success_response(data, "Done", metadata=metadata)

        assert result["status"] == "success"
        assert result["data"] == data
        assert result["message"] == "Done"
        assert result["metadata"] == metadata

    def test_create_success_response_with_none_data(self):
        """Test success response with None data."""
        from ast_grep_mcp.utils import create_success_response

        result = create_success_response(None, "No results")

        assert result["status"] == "success"
        assert result["data"] is None


class TestExecutionErrorHandling:
    """Test execution error handling for various error types."""

    def test_execution_error_timeout(self):
        """Test execution error with timeout keyword in message triggers suggestions."""
        from ast_grep_mcp.utils import handle_execution_error

        error = TimeoutError("Request timeout exceeded")
        result = handle_execution_error(error, command=["sg", "scan"], path="/project")

        assert result["status"] == "error"
        assert "suggestions" in result
        assert any("scope" in s.lower() or "timeout" in s.lower() for s in result["suggestions"])

    def test_execution_error_without_command(self):
        """Test execution error without command info."""
        from ast_grep_mcp.utils import handle_execution_error

        error = RuntimeError("General execution failure")
        result = handle_execution_error(error)

        assert result["status"] == "error"
        assert result["error"] == "Execution Error"

    def test_execution_error_without_path(self):
        """Test execution error without path info."""
        from ast_grep_mcp.utils import handle_execution_error

        error = RuntimeError("Some error")
        result = handle_execution_error(error, command=["sg", "run"])

        assert result["status"] == "error"
        assert result.get("path") is None

    def test_execution_error_ast_grep_not_found_has_install_suggestions(self):
        """Test ASTGrepNotFoundError includes install suggestions."""
        from ast_grep_mcp.utils import handle_execution_error, ASTGrepNotFoundError

        error = ASTGrepNotFoundError("Binary not found")
        result = handle_execution_error(error)

        assert result["status"] == "error"
        assert any("install" in s.lower() or "npm" in s.lower() for s in result["suggestions"])
        assert any("PATH" in s or "path" in s.lower() for s in result["suggestions"])


class TestMetaVariableUtilities:
    """Test meta-variable extraction and validation utilities used in scan operations."""

    def test_extract_meta_variables_basic(self):
        """Test basic meta-variable extraction."""
        from ast_grep_mcp.utils import extract_meta_variables

        result = extract_meta_variables("console.log($MESSAGE)")
        assert "$MESSAGE" in result

    def test_extract_meta_variables_multiple(self):
        """Test extraction of multiple meta-variables."""
        from ast_grep_mcp.utils import extract_meta_variables

        result = extract_meta_variables("$FUNC($ARG1, $ARG2)")
        assert "$FUNC" in result
        assert "$ARG1" in result
        assert "$ARG2" in result

    def test_extract_meta_variables_empty_pattern(self):
        """Test extraction from empty pattern."""
        from ast_grep_mcp.utils import extract_meta_variables

        result = extract_meta_variables("")
        assert result == []

    def test_extract_meta_variables_no_variables(self):
        """Test extraction from pattern with no variables."""
        from ast_grep_mcp.utils import extract_meta_variables

        result = extract_meta_variables("console.log('hello')")
        assert result == []

    def test_validate_meta_variable_name_valid(self):
        """Test valid meta-variable names."""
        from ast_grep_mcp.utils import validate_meta_variable_name

        assert validate_meta_variable_name("$FUNC") is True
        assert validate_meta_variable_name("$ARG_NAME") is True
        assert validate_meta_variable_name("$A") is True

    def test_validate_meta_variable_name_invalid(self):
        """Test invalid meta-variable names (lowercase)."""
        from ast_grep_mcp.utils import validate_meta_variable_name

        assert validate_meta_variable_name("$func") is False
        assert validate_meta_variable_name("$mixedCase") is False

    def test_analyze_meta_variable_consistency_matching(self):
        """Test consistency analysis with matching variables."""
        from ast_grep_mcp.utils import analyze_meta_variable_consistency

        result = analyze_meta_variable_consistency(
            "console.log($MSG)", "logger.info($MSG)"
        )
        assert result["consistent"] is True
        assert len(result["missing_in_rewrite"]) == 0
        assert len(result["extra_in_rewrite"]) == 0

    def test_analyze_meta_variable_consistency_mismatch(self):
        """Test consistency analysis with mismatched variables."""
        from ast_grep_mcp.utils import analyze_meta_variable_consistency

        result = analyze_meta_variable_consistency(
            "console.log($MSG)", "logger.info($OTHER)"
        )
        assert result["consistent"] is False
        assert "$MSG" in result["missing_in_rewrite"]
        assert "$OTHER" in result["extra_in_rewrite"]

    def test_create_meta_variable_usage_report(self):
        """Test meta-variable usage report creation."""
        from ast_grep_mcp.utils import create_meta_variable_usage_report

        report = create_meta_variable_usage_report("$FUNC($ARG)")
        assert report["total_variables"] == 2
        assert report["unique_variables"] == 2
        assert "$FUNC" in report["variables"]
        assert "$ARG" in report["variables"]
        assert "naming_compliance" in report

    def test_create_meta_variable_usage_report_with_rewrite(self):
        """Test meta-variable usage report with rewrite pattern."""
        from ast_grep_mcp.utils import create_meta_variable_usage_report

        report = create_meta_variable_usage_report(
            "$FUNC($ARG)", rewrite="$FUNC($ARG, true)"
        )
        assert "rewrite_consistency" in report

    def test_validate_meta_variable_usage_valid(self):
        """Test comprehensive validation with valid usage."""
        from ast_grep_mcp.utils import validate_meta_variable_usage

        result = validate_meta_variable_usage("$FUNC($ARG)")
        assert isinstance(result["errors"], list)
        assert isinstance(result["warnings"], list)

    def test_validate_meta_variable_usage_no_vars_with_rewrite(self):
        """Test validation warning when pattern has no vars but rewrite exists."""
        from ast_grep_mcp.utils import validate_meta_variable_usage

        result = validate_meta_variable_usage("console.log('hello')", "logger.info('hello')")
        # Should produce a warning about no meta-variables with rewrite
        assert len(result["warnings"]) > 0
