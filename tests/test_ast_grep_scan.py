class TestErrorHandling:
    """Test error handling and structured responses."""
    
    def test_validation_error_response(self):
        """Test validation error response structure."""
        from src.ast_grep_mcp.utils import handle_validation_error
        
        error = ValueError("Invalid language 'invalid_lang'")
        result = handle_validation_error(error, "Language validation", "/test/path")
        
        assert result["status"] == "error"
        assert result["error"] == "Validation Error"
        assert "Language validation" in result["message"]
        assert result["path"] == "/test/path"
        assert "timestamp" in result
    
    def test_configuration_error_response(self):
        """Test configuration error response structure."""
        from src.ast_grep_mcp.utils import handle_configuration_error
        
        error = ValueError("Missing ruleDirs field")
        result = handle_configuration_error(error, "/test/sgconfig.yml")
        
        assert result["status"] == "error"
        assert result["error"] == "Configuration Error"
        assert result["path"] == "/test/sgconfig.yml"
        assert "suggestions" in result
        assert len(result["suggestions"]) > 0
    
    def test_execution_error_response(self):
        """Test execution error response structure."""
        from src.ast_grep_mcp.utils import handle_execution_error, ASTGrepNotFoundError
        
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
        from src.ast_grep_mcp.utils import create_success_response
        
        data = {"matches": [], "total": 0}
        result = create_success_response(data, "Scan completed successfully")
        
        assert result["status"] == "success"
        assert result["data"] == data
        assert result["message"] == "Scan completed successfully"
        assert "timestamp" in result
    
    def test_format_tool_response_json(self):
        """Test tool response formatting for JSON output."""
        from src.ast_grep_mcp.utils import format_tool_response
        
        data = {"violations": [], "summary": {"total": 0}}
        result = format_tool_response(data, "json", True, "Scan completed")
        
        assert len(result) == 1
        assert result[0].type == "text"
        
        # Parse the JSON to verify structure
        import json
        parsed = json.loads(result[0].text)
        assert parsed["status"] == "success"
        assert parsed["data"] == data
    
    def test_format_tool_response_text_error(self):
        """Test tool response formatting for text output with error."""
        from src.ast_grep_mcp.utils import format_tool_response, create_error_response
        
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