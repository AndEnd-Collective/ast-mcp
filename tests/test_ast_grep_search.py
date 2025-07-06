"""Comprehensive test suite for ast_grep_search tool functionality."""

import pytest
import json
import tempfile
import shutil
import sys
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch
from typing import Dict, Any, List

# Add src to Python path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ast_grep_mcp.tools import (
    SearchToolInput, 
    ast_grep_search_impl,
    _build_search_args,
    _format_search_results_json,
    _format_search_results_text
)
from ast_grep_mcp.utils import ASTGrepError


class TestSearchToolInput:
    """Test SearchToolInput validation and processing."""
    
    @patch('src.ast_grep_mcp.tools.get_language_manager')
    def test_valid_input_basic(self, mock_get_manager):
        """Test basic valid input parameters."""
        # Mock language manager
        mock_manager = Mock()
        mock_manager.validate_language_identifier.return_value = "javascript"
        mock_get_manager.return_value = mock_manager
        
        input_data = SearchToolInput(
            pattern="console.log($MSG)",
            language="javascript",
            path="./src"
        )
        assert input_data.pattern == "console.log($MSG)"
        assert input_data.language == "javascript"
        # Path will be converted to absolute path by sanitize_path
        assert input_data.path.endswith("ast-mcp/src")
        assert input_data.recursive is True
        assert input_data.output_format == "json"
    
    @patch('src.ast_grep_mcp.tools.get_language_manager')
    def test_valid_input_with_globs(self, mock_get_manager):
        """Test input with custom glob patterns."""
        # Mock language manager
        mock_manager = Mock()
        mock_manager.validate_language_identifier.return_value = "typescript"
        mock_get_manager.return_value = mock_manager
        
        input_data = SearchToolInput(
            pattern="function $NAME($ARGS)",
            language="typescript",
            path="./src",
            include_globs=["*.test.ts", "*.spec.ts"],
            exclude_globs=["node_modules/**", "dist/**"]
        )
        assert input_data.include_globs == ["*.test.ts", "*.spec.ts"]
        assert input_data.exclude_globs == ["node_modules/**", "dist/**"]
    
    @patch('src.ast_grep_mcp.tools.get_language_manager')
    def test_pattern_validation_empty(self, mock_get_manager):
        """Test pattern validation rejects empty patterns."""
        # Mock language manager
        mock_manager = Mock()
        mock_manager.validate_language_identifier.return_value = "python"
        mock_get_manager.return_value = mock_manager
        
        from pydantic import ValidationError
        with pytest.raises(ValidationError, match="String should have at least 1 character"):
            SearchToolInput(
                pattern="",
                language="python",
                path="./src"
            )
    
    @patch('src.ast_grep_mcp.tools.get_language_manager')
    def test_pattern_validation_dangerous_chars(self, mock_get_manager):
        """Test pattern validation rejects dangerous characters."""
        # Mock language manager
        mock_manager = Mock()
        mock_manager.validate_language_identifier.return_value = "javascript"
        mock_get_manager.return_value = mock_manager
        
        dangerous_patterns = [
            "console.log(`danger`)",      # backtick is always dangerous
            "pattern; malicious",         # semicolon is always dangerous
            "pattern && malicious",       # double ampersand is dangerous
            "pattern || malicious",       # double pipe is dangerous
        ]
        
        from pydantic import ValidationError
        for pattern in dangerous_patterns:
            with pytest.raises(ValidationError, match="Potentially dangerous character"):
                SearchToolInput(
                    pattern=pattern,
                    language="javascript",
                    path="./src"
                )
    
    @patch('src.ast_grep_mcp.tools.get_language_manager')
    def test_language_validation_valid_languages(self, mock_get_manager):
        """Test language validation accepts valid language identifiers."""
        valid_languages = [
            "javascript", "js", "typescript", "ts", "python", "py",
            "rust", "rs", "go", "java", "c", "cpp", "csharp", "cs"
        ]
        
        # Mock language manager
        mock_manager = Mock()
        mock_manager.validate_language_identifier.side_effect = lambda x, **kwargs: x
        mock_get_manager.return_value = mock_manager
        
        for lang in valid_languages:
            input_data = SearchToolInput(
                pattern="test",
                language=lang,
                path="./src"
            )
            # Language should be normalized by the validator
            assert input_data.language is not None
    
    @patch('src.ast_grep_mcp.tools.get_language_manager')
    def test_language_validation_invalid_language(self, mock_get_manager):
        """Test language validation rejects invalid languages."""
        # Mock language manager to raise error for invalid language
        mock_manager = Mock()
        mock_manager.validate_language_identifier.side_effect = ValueError("Unsupported language")
        mock_manager.suggest_similar_languages.return_value = []
        mock_get_manager.return_value = mock_manager
        
        with pytest.raises(ValueError, match="Unsupported language"):
            SearchToolInput(
                pattern="test",
                language="invalid_language",
                path="./src"
            )
    
    @patch('src.ast_grep_mcp.tools.get_language_manager')
    def test_path_validation_empty(self, mock_get_manager):
        """Test path validation rejects empty paths."""
        # Mock language manager
        mock_manager = Mock()
        mock_manager.validate_language_identifier.return_value = "python"
        mock_get_manager.return_value = mock_manager
        
        from pydantic import ValidationError
        with pytest.raises(ValidationError, match="String should have at least 1 character"):
            SearchToolInput(
                pattern="test",
                language="python",
                path=""
            )
    
    @patch('src.ast_grep_mcp.tools.get_language_manager')
    def test_output_format_validation(self, mock_get_manager):
        """Test output format validation."""
        # Mock language manager
        mock_manager = Mock()
        mock_manager.validate_language_identifier.return_value = "python"
        mock_get_manager.return_value = mock_manager
        
        # Valid formats (case-sensitive)
        for fmt in ["json", "text"]:
            input_data = SearchToolInput(
                pattern="test",
                language="python",
                path="./src",
                output_format=fmt
            )
            assert input_data.output_format == fmt
        
        # Invalid format (case-sensitive validation in SearchToolInput)
        from pydantic import ValidationError
        with pytest.raises(ValidationError, match="Output format must be 'json' or 'text'"):
            SearchToolInput(
                pattern="test",
                language="python",
                path="./src",
                output_format="JSON"  # Uppercase not allowed
            )
    
    @patch('src.ast_grep_mcp.tools.get_language_manager')
    def test_glob_validation_dangerous_patterns(self, mock_get_manager):
        """Test glob validation rejects dangerous patterns."""
        # Mock language manager
        mock_manager = Mock()
        mock_manager.validate_language_identifier.return_value = "javascript"
        mock_get_manager.return_value = mock_manager
        
        dangerous_globs = [
            "*.js && rm -rf /",
            "*.py | cat /etc/passwd",
            "*.rs; malicious_command",
            "*.ts `evil_script`",
            "*.go $(whoami)"
        ]
        
        for glob_pattern in dangerous_globs:
            with pytest.raises(ValueError, match="potentially dangerous character"):
                SearchToolInput(
                    pattern="test",
                    language="javascript",
                    path="./src",
                    include_globs=[glob_pattern]
                )


class TestBuildSearchArgs:
    """Test _build_search_args function."""
    
    @patch('src.ast_grep_mcp.tools.get_language_manager')
    def test_basic_args(self, mock_get_manager):
        """Test basic argument building."""
        # Mock language manager for input validation
        mock_manager = Mock()
        mock_manager.validate_language_identifier.return_value = "javascript"
        mock_manager.get_language_info.return_value = {"extensions": [".js"]}
        mock_get_manager.return_value = mock_manager
        
        input_data = SearchToolInput(
            pattern="test",
            language="javascript",
            path="./src"
        )
        args = _build_search_args(input_data)
        
        assert "--json" in args
        assert "--no-recurse" not in args  # recursive=True by default
    
    @patch('src.ast_grep_mcp.tools.get_language_manager')
    def test_non_recursive_args(self, mock_get_manager):
        """Test non-recursive argument building."""
        # Mock language manager for input validation
        mock_manager = Mock()
        mock_manager.validate_language_identifier.return_value = "javascript"
        mock_manager.get_language_info.return_value = {"extensions": [".js"]}
        mock_get_manager.return_value = mock_manager
        
        input_data = SearchToolInput(
            pattern="test",
            language="javascript",
            path="./src",
            recursive=False
        )
        args = _build_search_args(input_data)
        
        assert "--json" in args
        assert "--no-recurse" in args
    
    @patch('src.ast_grep_mcp.tools.get_language_manager')
    def test_custom_include_globs(self, mock_get_manager):
        """Test custom include glob patterns."""
        # Mock language manager for input validation
        mock_manager = Mock()
        mock_manager.validate_language_identifier.return_value = "javascript"
        mock_get_manager.return_value = mock_manager
        
        input_data = SearchToolInput(
            pattern="test",
            language="javascript",
            path="./src",
            include_globs=["*.test.js", "*.spec.js"]
        )
        args = _build_search_args(input_data)
        
        assert "--include" in args
        assert "*.test.js" in args
        assert "*.spec.js" in args
    
    @patch('src.ast_grep_mcp.tools.get_language_manager')
    def test_exclude_globs(self, mock_get_manager):
        """Test exclude glob patterns."""
        # Mock language manager for input validation
        mock_manager = Mock()
        mock_manager.validate_language_identifier.return_value = "javascript"
        mock_manager.get_language_info.return_value = {"extensions": [".js"]}
        mock_get_manager.return_value = mock_manager
        
        input_data = SearchToolInput(
            pattern="test",
            language="javascript",
            path="./src",
            exclude_globs=["node_modules/**", "*.min.js"]
        )
        args = _build_search_args(input_data)
        
        assert "--exclude" in args
        assert "node_modules/**" in args
        assert "*.min.js" in args
    
    @patch('src.ast_grep_mcp.tools.get_language_manager')
    def test_language_based_include_patterns(self, mock_get_manager):
        """Test language-based file extension patterns as fallback."""
        # Mock language manager
        mock_manager = Mock()
        mock_manager.get_language_info.return_value = {
            "extensions": [".js", ".jsx", ".mjs"]
        }
        mock_manager.validate_language_identifier.return_value = "javascript"
        mock_get_manager.return_value = mock_manager
        
        input_data = SearchToolInput(
            pattern="test",
            language="javascript",
            path="./src"
        )
        args = _build_search_args(input_data)
        
        # Should include language-based patterns when no custom globs provided
        assert "--include" in args
        assert "*.js" in args
        assert "*.jsx" in args
        assert "*.mjs" in args


class TestResultFormatting:
    """Test result formatting functions."""
    
    def test_format_json_results_with_matches(self):
        """Test JSON formatting with match results."""
        mock_result = {
            "matches": [
                {
                    "file": "src/test.js",
                    "text": "console.log('hello')",
                    "range": {
                        "start": {"line": 5, "column": 0},
                        "end": {"line": 5, "column": 20}
                    },
                    "metaVariables": {"MSG": "'hello'"}
                }
            ],
            "returncode": 0,
            "execution_time": 0.123,
            "command": ["ast-grep", "search", "--json"]
        }
        
        input_data = SearchToolInput(
            pattern="console.log($MSG)",
            language="javascript",
            path="./src"
        )
        
        result = _format_search_results_json(mock_result, input_data)
        
        assert result["totalMatches"] == 1
        assert result["status"] == "success"
        assert result["pattern"] == "console.log($MSG)"
        assert result["language"] == "javascript"
        assert len(result["matches"]) == 1
        
        match = result["matches"][0]
        assert match["file"] == "src/test.js"
        assert match["text"] == "console.log('hello')"
        assert match["range"]["start"]["line"] == 5
        assert match["metaVariables"]["MSG"] == "'hello'"
        assert match["detectedLanguage"] == "javascript"
    
    def test_format_json_results_no_matches(self):
        """Test JSON formatting with no matches."""
        mock_result = {
            "matches": [],
            "returncode": 0,
            "execution_time": 0.050
        }
        
        input_data = SearchToolInput(
            pattern="non_existent_pattern",
            language="python",
            path="./src"
        )
        
        result = _format_search_results_json(mock_result, input_data)
        
        assert result["totalMatches"] == 0
        assert result["status"] == "success"
        assert len(result["matches"]) == 0
    
    @patch('src.ast_grep_mcp.tools.get_language_manager')
    def test_format_text_results_with_matches(self, mock_get_manager):
        """Test text formatting with match results."""
        # Mock language manager for input validation
        mock_manager = Mock()
        mock_manager.validate_language_identifier.return_value = "python"
        mock_get_manager.return_value = mock_manager
        
        mock_result = {
            "matches": [
                {
                    "file": "src/test.py",
                    "text": "print('hello world')",
                    "range": {
                        "start": {"line": 10, "column": 4},
                        "end": {"line": 10, "column": 23}
                    },
                    "metaVariables": {"MSG": "'hello world'"}
                }
            ],
            "returncode": 0,
            "execution_time": 0.089
        }
        
        input_data = SearchToolInput(
            pattern="print($MSG)",
            language="python",
            path="./src",
            recursive=True
        )
        
        result = _format_search_results_text(mock_result, input_data)
        
        assert "AST-Grep Search Results" in result
        assert "Pattern: print($MSG)" in result
        assert "Language: python" in result
        assert "Path:" in result  # Just check that path is included, not exact value
        assert "Recursive: True" in result
        assert "Found 1 matches:" in result
        assert "File: src/test.py" in result
        assert "Line: 10" in result
        assert "Text: print('hello world')" in result
        assert "Variables: {'MSG': \"'hello world'\"}" in result
        assert "Status: Success" in result
        assert "Execution time: 0.089s" in result
    
    @patch('src.ast_grep_mcp.tools.get_language_manager')
    def test_format_text_results_no_matches(self, mock_get_manager):
        """Test text formatting with no matches."""
        # Mock language manager for input validation
        mock_manager = Mock()
        mock_manager.validate_language_identifier.return_value = "rust"
        mock_get_manager.return_value = mock_manager
        
        mock_result = {
            "matches": [],
            "returncode": 0,
            "execution_time": 0.025
        }
        
        input_data = SearchToolInput(
            pattern="non_existent",
            language="rust",
            path="./src"
        )
        
        result = _format_search_results_text(mock_result, input_data)
        
        assert "No matches found." in result
        assert "Status: Success" in result


class TestASTGrepSearchIntegration:
    """Test ast_grep_search function integration."""
    
    @pytest.mark.asyncio
    @patch('src.ast_grep_mcp.tools.create_ast_grep_executor')
    @patch('src.ast_grep_mcp.tools.get_language_manager')
    async def test_successful_search_json_output(self, mock_get_manager, mock_create_executor):
        """Test successful search with JSON output."""
        # Mock language manager
        mock_manager = Mock()
        mock_manager.validate_language_identifier.return_value = "javascript"
        mock_manager.map_to_ast_grep_language.return_value = "js"
        mock_manager.get_language_info.return_value = {
            "extensions": [".js", ".jsx", ".mjs"]
        }
        mock_get_manager.return_value = mock_manager
        
        # Mock executor
        mock_executor = AsyncMock()
        mock_executor.search.return_value = {
            "parsed_output": [
                {
                    "file": "test.js",
                    "text": "console.log('test')",
                    "range": {
                        "start": {"line": 1, "column": 0},
                        "end": {"line": 1, "column": 18}
                    },
                    "metaVariables": {}
                }
            ],
            "returncode": 0,
            "execution_time": 0.123,
            "command": ["ast-grep", "search"]
        }
        mock_create_executor.return_value = mock_executor
        
        input_data = SearchToolInput(
            pattern="console.log($MSG)",
            language="javascript",
            path="./test.js",
            output_format="json"
        )
        
        result = await ast_grep_search_impl(input_data, Path("/usr/bin/ast-grep"))
        
        assert len(result) == 1
        assert result[0].type == "text"
        
        # Parse the JSON result
        parsed_result = json.loads(result[0].text)
        assert parsed_result["totalMatches"] == 1
        assert parsed_result["status"] == "success"
        assert len(parsed_result["matches"]) == 1
    
    @pytest.mark.asyncio
    @patch('src.ast_grep_mcp.tools.create_ast_grep_executor')
    @patch('src.ast_grep_mcp.tools.get_language_manager')
    async def test_successful_search_text_output(self, mock_get_manager, mock_create_executor):
        """Test successful search with text output."""
        # Mock language manager
        mock_manager = Mock()
        mock_manager.validate_language_identifier.return_value = "python"
        mock_manager.map_to_ast_grep_language.return_value = "py"
        mock_manager.get_language_info.return_value = {
            "extensions": [".py", ".pyi", ".pyw"]
        }
        mock_get_manager.return_value = mock_manager
        
        # Mock executor
        mock_executor = AsyncMock()
        mock_executor.search.return_value = {
            "parsed_output": [
                {
                    "file": "test.py",
                    "text": "def hello():",
                    "range": {
                        "start": {"line": 1, "column": 0},
                        "end": {"line": 1, "column": 12}
                    },
                    "metaVariables": {}
                }
            ],
            "returncode": 0,
            "execution_time": 0.089
        }
        mock_create_executor.return_value = mock_executor
        
        input_data = SearchToolInput(
            pattern="def $NAME():",
            language="python",
            path="./test.py",
            output_format="text"
        )
        
        result = await ast_grep_search_impl(input_data, Path("/usr/bin/ast-grep"))
        
        assert len(result) == 1
        assert result[0].type == "text"
        assert "AST-Grep Search Results" in result[0].text
    
    @pytest.mark.asyncio
    @patch('src.ast_grep_mcp.tools.create_ast_grep_executor')
    @patch('src.ast_grep_mcp.tools.get_language_manager')
    async def test_search_with_ast_grep_error(self, mock_get_manager, mock_create_executor):
        """Test search handling AST-Grep errors."""
        # Mock language manager
        mock_manager = Mock()
        mock_manager.validate_language_identifier.return_value = "javascript"
        mock_manager.map_to_ast_grep_language.return_value = "js"
        mock_manager.get_language_info.return_value = {
            "extensions": [".js", ".jsx", ".mjs"]
        }
        mock_get_manager.return_value = mock_manager
        
        # Mock executor to raise ASTGrepError
        mock_executor = AsyncMock()
        mock_executor.search.side_effect = ASTGrepError("Invalid pattern syntax")
        mock_create_executor.return_value = mock_executor
        
        input_data = SearchToolInput(
            pattern="invalid_pattern[",
            language="javascript",
            path="./src"
        )
        
        result = await ast_grep_search_impl(input_data, Path("/usr/bin/ast-grep"))
        
        assert len(result) == 1
        assert result[0].type == "text"
        
        # Parse the error result
        parsed_result = json.loads(result[0].text)
        assert parsed_result["error"] == "AST-Grep execution failed"
        assert "Invalid pattern syntax" in parsed_result["message"]
        assert parsed_result["pattern"] == "invalid_pattern["
    
    @pytest.mark.asyncio
    @patch('src.ast_grep_mcp.tools.create_ast_grep_executor')
    @patch('src.ast_grep_mcp.tools.get_language_manager')
    async def test_search_with_unexpected_error(self, mock_get_manager, mock_create_executor):
        """Test search handling unexpected errors."""
        # Mock language manager
        mock_manager = Mock()
        mock_manager.validate_language_identifier.return_value = "go"
        mock_manager.map_to_ast_grep_language.return_value = "go"
        mock_manager.get_language_info.return_value = {
            "extensions": [".go"]
        }
        mock_get_manager.return_value = mock_manager
        
        # Mock executor to raise unexpected error
        mock_executor = AsyncMock()
        mock_executor.search.side_effect = RuntimeError("Unexpected runtime error")
        mock_create_executor.return_value = mock_executor
        
        input_data = SearchToolInput(
            pattern="func $NAME($ARGS)",
            language="go",
            path="./src"
        )
        
        result = await ast_grep_search_impl(input_data, Path("/usr/bin/ast-grep"))
        
        assert len(result) == 1
        assert result[0].type == "text"
        
        # Parse the error result
        parsed_result = json.loads(result[0].text)
        assert parsed_result["error"] == "Unexpected error during search"
        assert "Unexpected runtime error" in parsed_result["message"]


class TestMultiLanguageSupport:
    """Test search functionality across different programming languages."""
    
    @pytest.mark.parametrize("language,pattern,expected_ast_grep_lang", [
        ("javascript", "console.log($MSG)", "js"),
        ("typescript", "function $NAME($ARGS): $TYPE", "ts"),
        ("python", "def $NAME($ARGS):", "py"),
        ("rust", "fn $NAME($ARGS) -> $TYPE", "rs"),
        ("go", "func $NAME($ARGS) $TYPE", "go"),
        ("java", "public class $NAME", "java"),
        ("c", "int $NAME($ARGS)", "c"),
        ("cpp", "class $NAME", "cpp"),
        ("csharp", "public class $NAME", "cs"),
        ("php", "function $NAME($ARGS)", "php"),
        ("ruby", "def $NAME($ARGS)", "rb"),
        ("swift", "func $NAME($ARGS) -> $TYPE", "swift"),
        ("kotlin", "fun $NAME($ARGS): $TYPE", "kt"),
        ("scala", "def $NAME($ARGS): $TYPE", "scala")
    ])
    @pytest.mark.asyncio
    @patch('src.ast_grep_mcp.tools.create_ast_grep_executor')
    @patch('src.ast_grep_mcp.tools.get_language_manager')
    async def test_language_specific_patterns(self, mock_get_manager, mock_create_executor, 
                                             language, pattern, expected_ast_grep_lang):
        """Test language-specific pattern matching."""
        # Define language-specific extensions for comprehensive mock setup
        language_extensions = {
            "javascript": [".js", ".jsx", ".mjs"],
            "typescript": [".ts", ".tsx"],
            "python": [".py", ".pyi", ".pyw"],
            "rust": [".rs"],
            "go": [".go"],
            "java": [".java"],
            "c": [".c", ".h"],
            "cpp": [".cpp", ".cxx", ".cc", ".hpp"],
            "csharp": [".cs"],
            "php": [".php"],
            "ruby": [".rb"],
            "swift": [".swift"],
            "kotlin": [".kt", ".kts"],
            "scala": [".scala", ".sc"]
        }
        
        # Mock language manager
        mock_manager = Mock()
        mock_manager.validate_language_identifier.return_value = language
        mock_manager.map_to_ast_grep_language.return_value = expected_ast_grep_lang
        mock_manager.get_language_info.return_value = {
            "extensions": language_extensions.get(language, [f".{language}"])
        }
        mock_get_manager.return_value = mock_manager
        
        # Mock executor
        mock_executor = AsyncMock()
        mock_executor.search.return_value = {
            "parsed_output": [],
            "returncode": 0,
            "execution_time": 0.050
        }
        mock_create_executor.return_value = mock_executor
        
        input_data = SearchToolInput(
            pattern=pattern,
            language=language,
            path="./src"
        )
        
        result = await ast_grep_search_impl(input_data, Path("/usr/bin/ast-grep"))
        
        # Verify the executor was called with correct language mapping
        mock_executor.search.assert_called_once()
        call_args = mock_executor.search.call_args
        assert call_args[1]["language"] == expected_ast_grep_lang
        assert call_args[1]["pattern"] == pattern


class TestEdgeCases:
    """Test edge cases and boundary conditions."""
    
    @pytest.mark.asyncio
    @patch('src.ast_grep_mcp.tools.create_ast_grep_executor')
    @patch('src.ast_grep_mcp.tools.get_language_manager')
    async def test_empty_search_results(self, mock_get_manager, mock_create_executor):
        """Test handling of empty search results."""
        # Mock language manager
        mock_manager = Mock()
        mock_manager.validate_language_identifier.return_value = "javascript"
        mock_manager.map_to_ast_grep_language.return_value = "js"
        mock_manager.get_language_info.return_value = {
            "extensions": [".js", ".jsx", ".mjs"]
        }
        mock_get_manager.return_value = mock_manager
        
        # Mock executor with empty results
        mock_executor = AsyncMock()
        mock_executor.search.return_value = {
            "parsed_output": [],
            "returncode": 0,
            "execution_time": 0.010
        }
        mock_create_executor.return_value = mock_executor
        
        input_data = SearchToolInput(
            pattern="non_existent_pattern",
            language="javascript",
            path="./src"
        )
        
        result = await ast_grep_search_impl(input_data, Path("/usr/bin/ast-grep"))
        
        assert len(result) == 1
        parsed_result = json.loads(result[0].text)
        assert parsed_result["totalMatches"] == 0
        assert parsed_result["status"] == "success"
        assert len(parsed_result["matches"]) == 0
    
    @pytest.mark.asyncio
    @patch('src.ast_grep_mcp.tools.create_ast_grep_executor')
    @patch('src.ast_grep_mcp.tools.get_language_manager')
    async def test_malformed_search_results(self, mock_get_manager, mock_create_executor):
        """Test handling of malformed search results."""
        # Mock language manager
        mock_manager = Mock()
        mock_manager.validate_language_identifier.return_value = "python"
        mock_manager.map_to_ast_grep_language.return_value = "py"
        mock_manager.get_language_info.return_value = {
            "extensions": [".py", ".pyi", ".pyw"]
        }
        mock_get_manager.return_value = mock_manager
        
        # Mock executor with malformed results
        mock_executor = AsyncMock()
        mock_executor.search.return_value = {
            "parsed_output": [
                {
                    # Missing required fields
                    "incomplete": "data"
                }
            ],
            "returncode": 0
        }
        mock_create_executor.return_value = mock_executor
        
        input_data = SearchToolInput(
            pattern="test_pattern",
            language="python",
            path="./src"
        )
        
        result = await ast_grep_search_impl(input_data, Path("/usr/bin/ast-grep"))
        
        # Should handle malformed data gracefully
        assert len(result) == 1
        parsed_result = json.loads(result[0].text)
        assert parsed_result["totalMatches"] == 1
        assert parsed_result["status"] == "success"
        assert len(parsed_result["matches"]) == 1
    
    def test_extremely_long_pattern(self):
        """Test handling of very long patterns."""
        long_pattern = "x" * 10000  # Very long pattern (exceeds 8192 limit)
        
        # Should raise ValidationError due to max_length constraint
        from pydantic import ValidationError
        with pytest.raises(ValidationError, match="String should have at most 8192 characters"):
            SearchToolInput(
                pattern=long_pattern,
                language="javascript",
                path="./src"
            )
    
    def test_unicode_pattern(self):
        """Test handling of Unicode patterns."""
        unicode_pattern = "console.log('🚀 测试 こんにちは')"
        
        input_data = SearchToolInput(
            pattern=unicode_pattern,
            language="javascript",
            path="./src"
        )
        
        assert input_data.pattern == unicode_pattern


if __name__ == "__main__":
    pytest.main([__file__]) 