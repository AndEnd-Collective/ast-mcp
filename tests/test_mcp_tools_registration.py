"""Tests for MCP tools registration and tool input model validation."""

import asyncio
import sys
import os
import json
import pytest
from pathlib import Path
from pydantic import ValidationError

# Add src to path so we can import modules
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))


@pytest.mark.asyncio
async def test_mcp_tools_registration():
    """Test that MCP tools are properly registered and functional."""
    from ast_grep_mcp.server import create_server, ServerConfig

    # Create server with config
    config = ServerConfig()
    server_instance = create_server(config)

    assert server_instance is not None

    # Initialize server
    await server_instance.initialize()

    # Access the MCP server directly
    mcp_server = server_instance.server
    assert mcp_server is not None

    # Check that the server has the expected MCP methods
    expected_methods = ['list_tools', 'call_tool', 'list_resources', 'read_resource']
    for method in expected_methods:
        assert hasattr(mcp_server, method), f"Server missing method: {method}"

    # Cleanup
    try:
        await server_instance.cleanup()
    except Exception:
        pass


class TestSearchToolInputValidation:
    """Test SearchToolInput validation."""

    def test_valid_search_input(self):
        """Test creating a valid SearchToolInput."""
        from ast_grep_mcp.tools import SearchToolInput
        inp = SearchToolInput(
            pattern="console.log($MSG)",
            language="javascript",
            path="/tmp"
        )
        assert inp.pattern == "console.log($MSG)"
        assert inp.language == "javascript"
        assert inp.recursive is True
        assert inp.output_format == "json"

    def test_search_input_empty_pattern_rejected(self):
        """Test that empty pattern is rejected."""
        from ast_grep_mcp.tools import SearchToolInput
        with pytest.raises(ValidationError):
            SearchToolInput(
                pattern="   ",
                language="javascript",
                path="/tmp"
            )

    def test_search_input_dangerous_chars_rejected(self):
        """Test that dangerous characters in pattern are rejected."""
        from ast_grep_mcp.tools import SearchToolInput
        with pytest.raises(ValidationError):
            SearchToolInput(
                pattern="console.log(`evil`)",
                language="javascript",
                path="/tmp"
            )

    def test_search_input_semicolon_rejected(self):
        """Test that semicolon in pattern is rejected."""
        from ast_grep_mcp.tools import SearchToolInput
        with pytest.raises(ValidationError):
            SearchToolInput(
                pattern="a; rm -rf /",
                language="javascript",
                path="/tmp"
            )

    def test_search_input_shell_operators_rejected(self):
        """Test that shell operators && and || are rejected."""
        from ast_grep_mcp.tools import SearchToolInput
        with pytest.raises(ValidationError):
            SearchToolInput(
                pattern="a && b",
                language="javascript",
                path="/tmp"
            )

        with pytest.raises(ValidationError):
            SearchToolInput(
                pattern="a || b",
                language="javascript",
                path="/tmp"
            )

    def test_search_input_invalid_meta_variable(self):
        """Test that numeric meta-variables are rejected."""
        from ast_grep_mcp.tools import SearchToolInput
        with pytest.raises(ValidationError):
            SearchToolInput(
                pattern="func($123)",
                language="javascript",
                path="/tmp"
            )

    def test_search_input_invalid_output_format(self):
        """Test that invalid output format is rejected."""
        from ast_grep_mcp.tools import SearchToolInput
        with pytest.raises(ValidationError):
            SearchToolInput(
                pattern="$FUNC",
                language="javascript",
                path="/tmp",
                output_format="xml"
            )

    def test_search_input_text_output_format(self):
        """Test that text output format is accepted."""
        from ast_grep_mcp.tools import SearchToolInput
        inp = SearchToolInput(
            pattern="$FUNC",
            language="javascript",
            path="/tmp",
            output_format="text"
        )
        assert inp.output_format == "text"

    def test_search_input_with_include_globs(self):
        """Test search input with valid include globs."""
        from ast_grep_mcp.tools import SearchToolInput
        inp = SearchToolInput(
            pattern="$FUNC",
            language="javascript",
            path="/tmp",
            include_globs=["*.js", "*.ts"]
        )
        assert inp.include_globs == ["*.js", "*.ts"]

    def test_search_input_too_broad_include_glob_rejected(self):
        """Test that overly broad include glob is rejected."""
        from ast_grep_mcp.tools import SearchToolInput
        with pytest.raises(ValidationError):
            SearchToolInput(
                pattern="$FUNC",
                language="javascript",
                path="/tmp",
                include_globs=["*"]
            )

    def test_search_input_dangerous_include_glob_rejected(self):
        """Test that dangerous chars in include glob are rejected."""
        from ast_grep_mcp.tools import SearchToolInput
        with pytest.raises(ValidationError):
            SearchToolInput(
                pattern="$FUNC",
                language="javascript",
                path="/tmp",
                include_globs=["*.js; rm -rf /"]
            )

    def test_search_input_empty_include_globs_becomes_none(self):
        """Test that empty include globs list becomes None."""
        from ast_grep_mcp.tools import SearchToolInput
        inp = SearchToolInput(
            pattern="$FUNC",
            language="javascript",
            path="/tmp",
            include_globs=[]
        )
        assert inp.include_globs is None

    def test_search_input_unmatched_brackets_in_glob_rejected(self):
        """Test that unmatched brackets in glob patterns are rejected."""
        from ast_grep_mcp.tools import SearchToolInput
        with pytest.raises(ValidationError):
            SearchToolInput(
                pattern="$FUNC",
                language="javascript",
                path="/tmp",
                include_globs=["[*.js"]
            )


class TestScanToolInputValidation:
    """Test ScanToolInput validation."""

    def test_valid_scan_input(self):
        """Test creating a valid ScanToolInput."""
        from ast_grep_mcp.tools import ScanToolInput
        inp = ScanToolInput(path="/tmp")
        assert inp.output_format == "json"

    def test_scan_input_empty_path_rejected(self):
        """Test that empty path is rejected."""
        from ast_grep_mcp.tools import ScanToolInput
        with pytest.raises(ValidationError):
            ScanToolInput(path="   ")

    def test_scan_input_with_rules_config(self):
        """Test scan input with rules_config path."""
        from ast_grep_mcp.tools import ScanToolInput
        inp = ScanToolInput(path="/tmp", rules_config="/tmp/sgconfig.yml")
        assert inp.rules_config is not None

    def test_scan_input_empty_rules_config_becomes_none(self):
        """Test that empty rules_config string becomes None."""
        from ast_grep_mcp.tools import ScanToolInput
        inp = ScanToolInput(path="/tmp", rules_config="   ")
        assert inp.rules_config is None

    def test_scan_input_invalid_output_format(self):
        """Test that invalid output format is rejected."""
        from ast_grep_mcp.tools import ScanToolInput
        with pytest.raises(ValidationError):
            ScanToolInput(path="/tmp", output_format="csv")

    def test_scan_input_text_output_format(self):
        """Test that text output format is accepted."""
        from ast_grep_mcp.tools import ScanToolInput
        inp = ScanToolInput(path="/tmp", output_format="text")
        assert inp.output_format == "text"

    def test_scan_input_json_output_format(self):
        """Test that json output format is accepted."""
        from ast_grep_mcp.tools import ScanToolInput
        inp = ScanToolInput(path="/tmp", output_format="json")
        assert inp.output_format == "json"

    def test_scan_input_output_format_case_normalization(self):
        """Test that output format is normalized to lowercase."""
        from ast_grep_mcp.tools import ScanToolInput
        inp = ScanToolInput(path="/tmp", output_format="JSON")
        assert inp.output_format == "json"


class TestRunToolInputValidation:
    """Test RunToolInput validation."""

    def test_valid_run_input(self):
        """Test creating a valid RunToolInput."""
        from ast_grep_mcp.tools import RunToolInput
        inp = RunToolInput(
            pattern="console.log($MSG)",
            language="javascript",
            path="/tmp"
        )
        assert inp.pattern == "console.log($MSG)"
        assert inp.dry_run is True
        assert inp.rewrite is None

    def test_run_input_with_rewrite(self):
        """Test run input with rewrite pattern."""
        from ast_grep_mcp.tools import RunToolInput
        inp = RunToolInput(
            pattern="console.log($MSG)",
            rewrite="logger.info($MSG)",
            language="javascript",
            path="/tmp"
        )
        assert inp.rewrite == "logger.info($MSG)"

    def test_run_input_empty_pattern_rejected(self):
        """Test that empty pattern is rejected."""
        from ast_grep_mcp.tools import RunToolInput
        with pytest.raises(ValidationError):
            RunToolInput(
                pattern="   ",
                language="javascript",
                path="/tmp"
            )

    def test_run_input_dangerous_pattern_rejected(self):
        """Test that dangerous pattern with semicolon is rejected."""
        from ast_grep_mcp.tools import RunToolInput
        with pytest.raises(ValidationError):
            RunToolInput(
                pattern="a; rm -rf /",
                language="javascript",
                path="/tmp"
            )

    def test_run_input_dangerous_rewrite_rejected(self):
        """Test that dangerous rewrite pattern is rejected."""
        from ast_grep_mcp.tools import RunToolInput
        with pytest.raises(ValidationError):
            RunToolInput(
                pattern="console.log($MSG)",
                rewrite="evil; drop",
                language="javascript",
                path="/tmp"
            )

    def test_run_input_empty_rewrite_becomes_none(self):
        """Test that empty rewrite string becomes None."""
        from ast_grep_mcp.tools import RunToolInput
        inp = RunToolInput(
            pattern="$FUNC",
            rewrite="   ",
            language="javascript",
            path="/tmp"
        )
        assert inp.rewrite is None

    def test_run_input_dry_run_false(self):
        """Test run input with dry_run set to False."""
        from ast_grep_mcp.tools import RunToolInput
        inp = RunToolInput(
            pattern="$FUNC",
            language="javascript",
            path="/tmp",
            dry_run=False
        )
        assert inp.dry_run is False

    def test_run_input_invalid_output_format(self):
        """Test that invalid output format is rejected."""
        from ast_grep_mcp.tools import RunToolInput
        with pytest.raises(ValidationError):
            RunToolInput(
                pattern="$FUNC",
                language="javascript",
                path="/tmp",
                output_format="html"
            )

    def test_run_input_backtick_in_pattern_rejected(self):
        """Test that backtick in pattern is rejected."""
        from ast_grep_mcp.tools import RunToolInput
        with pytest.raises(ValidationError):
            RunToolInput(
                pattern="`command`",
                language="javascript",
                path="/tmp"
            )

    def test_run_input_dollar_paren_in_pattern_rejected(self):
        """Test that $( in pattern is rejected as shell injection."""
        from ast_grep_mcp.tools import RunToolInput
        with pytest.raises(ValidationError):
            RunToolInput(
                pattern="$(whoami)",
                language="javascript",
                path="/tmp"
            )


class TestCallGraphInputValidation:
    """Test CallGraphInput validation."""

    def test_valid_call_graph_input(self):
        """Test creating a valid CallGraphInput."""
        from ast_grep_mcp.tools import CallGraphInput
        inp = CallGraphInput(path="/tmp")
        assert inp.include_external is False
        assert inp.languages is None

    def test_call_graph_input_with_languages(self):
        """Test call graph input with language list."""
        from ast_grep_mcp.tools import CallGraphInput
        inp = CallGraphInput(path="/tmp", languages=["python", "javascript"])
        assert "python" in inp.languages
        assert "javascript" in inp.languages

    def test_call_graph_input_empty_path_rejected(self):
        """Test that empty path is rejected."""
        from ast_grep_mcp.tools import CallGraphInput
        with pytest.raises(ValidationError):
            CallGraphInput(path="   ")

    def test_call_graph_input_empty_languages_list_rejected(self):
        """Test that empty languages list is rejected."""
        from ast_grep_mcp.tools import CallGraphInput
        with pytest.raises(ValidationError):
            CallGraphInput(path="/tmp", languages=[])

    def test_call_graph_input_too_many_languages_rejected(self):
        """Test that more than 20 languages are rejected."""
        from ast_grep_mcp.tools import CallGraphInput
        too_many = [f"lang{i}" for i in range(25)]
        with pytest.raises(ValidationError):
            CallGraphInput(path="/tmp", languages=too_many)

    def test_call_graph_input_include_external_true(self):
        """Test call graph input with include_external set to True."""
        from ast_grep_mcp.tools import CallGraphInput
        inp = CallGraphInput(path="/tmp", include_external=True)
        assert inp.include_external is True

    def test_call_graph_input_none_languages_accepted(self):
        """Test that None languages (auto-detect) is accepted."""
        from ast_grep_mcp.tools import CallGraphInput
        inp = CallGraphInput(path="/tmp", languages=None)
        assert inp.languages is None


class TestToolInputModelTypes:
    """Test that tool input models have the expected base class and structure."""

    def test_search_tool_input_is_base_model(self):
        """Test SearchToolInput extends BaseModel."""
        from ast_grep_mcp.tools import SearchToolInput
        from pydantic import BaseModel
        assert issubclass(SearchToolInput, BaseModel)

    def test_scan_tool_input_is_base_model(self):
        """Test ScanToolInput extends BaseModel."""
        from ast_grep_mcp.tools import ScanToolInput
        from pydantic import BaseModel
        assert issubclass(ScanToolInput, BaseModel)

    def test_run_tool_input_is_base_model(self):
        """Test RunToolInput extends BaseModel."""
        from ast_grep_mcp.tools import RunToolInput
        from pydantic import BaseModel
        assert issubclass(RunToolInput, BaseModel)

    def test_call_graph_input_is_base_model(self):
        """Test CallGraphInput extends BaseModel."""
        from ast_grep_mcp.tools import CallGraphInput
        from pydantic import BaseModel
        assert issubclass(CallGraphInput, BaseModel)

    def test_search_tool_input_schema_has_required_fields(self):
        """Test SearchToolInput schema lists required fields."""
        from ast_grep_mcp.tools import SearchToolInput
        schema = SearchToolInput.model_json_schema()
        required = schema.get('required', [])
        assert 'pattern' in required
        assert 'language' in required
        assert 'path' in required

    def test_scan_tool_input_schema_has_required_fields(self):
        """Test ScanToolInput schema lists required fields."""
        from ast_grep_mcp.tools import ScanToolInput
        schema = ScanToolInput.model_json_schema()
        required = schema.get('required', [])
        assert 'path' in required

    def test_run_tool_input_schema_has_required_fields(self):
        """Test RunToolInput schema lists required fields."""
        from ast_grep_mcp.tools import RunToolInput
        schema = RunToolInput.model_json_schema()
        required = schema.get('required', [])
        assert 'pattern' in required
        assert 'language' in required
        assert 'path' in required

    def test_call_graph_input_schema_has_required_fields(self):
        """Test CallGraphInput schema lists required fields."""
        from ast_grep_mcp.tools import CallGraphInput
        schema = CallGraphInput.model_json_schema()
        required = schema.get('required', [])
        assert 'path' in required


if __name__ == "__main__":
    asyncio.run(test_mcp_tools_registration())
