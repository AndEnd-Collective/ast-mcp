#!/usr/bin/env python3
"""MCP Protocol Message Validation Tests.

This module tests raw JSON-RPC 2.0 message format compliance and MCP-specific
message structure validation to ensure protocol-level correctness.
"""

import asyncio
import json
import sys
import os
import uuid
import time
from pathlib import Path
from typing import Dict, Any, List, Optional, Union

# Add src to Python path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

try:
    from ast_grep_mcp.server import create_server, ServerConfig
    from ast_grep_mcp.utils import find_ast_grep_binary
except ImportError as e:
    print(f"Import error: {e}")
    print("Please install dependencies: pip install -e .")
    sys.exit(1)


class MCPProtocolMessageValidator:
    """Validate MCP protocol messages for JSON-RPC and MCP compliance."""
    
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
        """Set up MCP server for testing."""
        print("🔧 Setting up MCP server for protocol testing...")
        
        try:
            config = ServerConfig()
            config.enable_performance = True
            config.enable_security = True
            config.enable_monitoring = False
            config.system_monitoring_enabled = False
            config.alerting_enabled = False
            config.dependency_check_enabled = False
            config.detailed_diagnostics = False
            
            server_wrapper = create_server(config)
            await server_wrapper.initialize()
            self.server = server_wrapper.server
            
            print("✅ MCP server initialized for protocol testing")
            return True
            
        except Exception as e:
            print(f"❌ Server setup failed: {e}")
            return False
    
    def validate_json_rpc_request(self, message: Dict[str, Any]) -> bool:
        """Validate JSON-RPC 2.0 request format."""
        try:
            # Required fields for JSON-RPC 2.0 request
            if message.get("jsonrpc") != "2.0":
                return False
            
            if "method" not in message:
                return False
            
            if not isinstance(message["method"], str):
                return False
            
            # ID is optional for notifications, required for requests
            if "id" in message:
                if not isinstance(message["id"], (str, int, type(None))):
                    return False
            
            # Params is optional
            if "params" in message:
                if not isinstance(message["params"], (dict, list)):
                    return False
            
            return True
            
        except Exception:
            return False
    
    def validate_json_rpc_response(self, message: Dict[str, Any]) -> bool:
        """Validate JSON-RPC 2.0 response format."""
        try:
            # Required fields for JSON-RPC 2.0 response
            if message.get("jsonrpc") != "2.0":
                return False
            
            if "id" not in message:
                return False
            
            # Must have either result OR error, but not both
            has_result = "result" in message
            has_error = "error" in message
            
            if not (has_result ^ has_error):  # XOR - exactly one must be true
                return False
            
            # Validate error format if present
            if has_error:
                error = message["error"]
                if not isinstance(error, dict):
                    return False
                
                if "code" not in error or not isinstance(error["code"], int):
                    return False
                
                if "message" not in error or not isinstance(error["message"], str):
                    return False
            
            return True
            
        except Exception:
            return False
    
    def validate_mcp_initialize_request(self, message: Dict[str, Any]) -> bool:
        """Validate MCP initialize request format."""
        try:
            if not self.validate_json_rpc_request(message):
                return False
            
            if message.get("method") != "initialize":
                return False
            
            params = message.get("params", {})
            
            # Required MCP initialize parameters
            required_fields = ["protocolVersion", "capabilities", "clientInfo"]
            for field in required_fields:
                if field not in params:
                    return False
            
            # Validate protocol version format
            protocol_version = params["protocolVersion"]
            if not isinstance(protocol_version, str):
                return False
            
            # Validate capabilities structure
            capabilities = params["capabilities"]
            if not isinstance(capabilities, dict):
                return False
            
            # Validate client info structure
            client_info = params["clientInfo"]
            if not isinstance(client_info, dict):
                return False
            
            if "name" not in client_info:
                return False
            
            return True
            
        except Exception:
            return False
    
    def validate_mcp_initialize_response(self, message: Dict[str, Any]) -> bool:
        """Validate MCP initialize response format."""
        try:
            if not self.validate_json_rpc_response(message):
                return False
            
            if "result" not in message:
                return False
            
            result = message["result"]
            
            # Required MCP initialize response fields
            required_fields = ["protocolVersion", "capabilities", "serverInfo"]
            for field in required_fields:
                if field not in result:
                    return False
            
            # Validate server info structure
            server_info = result["serverInfo"]
            if not isinstance(server_info, dict):
                return False
            
            if "name" not in server_info:
                return False
            
            return True
            
        except Exception:
            return False
    
    def validate_mcp_tools_list_request(self, message: Dict[str, Any]) -> bool:
        """Validate MCP tools/list request format."""
        try:
            if not self.validate_json_rpc_request(message):
                return False
            
            if message.get("method") != "tools/list":
                return False
            
            # tools/list should not have params
            if "params" in message and message["params"] is not None:
                return False
            
            return True
            
        except Exception:
            return False
    
    def validate_mcp_tools_list_response(self, message: Dict[str, Any]) -> bool:
        """Validate MCP tools/list response format."""
        try:
            if not self.validate_json_rpc_response(message):
                return False
            
            if "result" not in message:
                return False
            
            result = message["result"]
            
            if "tools" not in result:
                return False
            
            tools = result["tools"]
            if not isinstance(tools, list):
                return False
            
            # Validate each tool structure
            for tool in tools:
                if not isinstance(tool, dict):
                    return False
                
                required_tool_fields = ["name", "description", "inputSchema"]
                for field in required_tool_fields:
                    if field not in tool:
                        return False
                
                # Validate input schema is a valid JSON schema
                input_schema = tool["inputSchema"]
                if not isinstance(input_schema, dict):
                    return False
                
                if "type" not in input_schema:
                    return False
            
            return True
            
        except Exception:
            return False
    
    def validate_mcp_tools_call_request(self, message: Dict[str, Any]) -> bool:
        """Validate MCP tools/call request format."""
        try:
            if not self.validate_json_rpc_request(message):
                return False
            
            if message.get("method") != "tools/call":
                return False
            
            params = message.get("params", {})
            
            # Required fields for tools/call
            if "name" not in params:
                return False
            
            if not isinstance(params["name"], str):
                return False
            
            # Arguments should be a dict if present
            if "arguments" in params:
                if not isinstance(params["arguments"], dict):
                    return False
            
            return True
            
        except Exception:
            return False
    
    def validate_mcp_tools_call_response(self, message: Dict[str, Any]) -> bool:
        """Validate MCP tools/call response format."""
        try:
            if not self.validate_json_rpc_response(message):
                return False
            
            if "result" not in message:
                return False
            
            result = message["result"]
            
            if "content" not in result:
                return False
            
            content = result["content"]
            if not isinstance(content, list):
                return False
            
            # Validate each content item
            for item in content:
                if not isinstance(item, dict):
                    return False
                
                if "type" not in item:
                    return False
                
                # Based on type, validate required fields
                item_type = item["type"]
                if item_type == "text":
                    if "text" not in item:
                        return False
                elif item_type == "image":
                    if "data" not in item or "mimeType" not in item:
                        return False
                elif item_type == "resource":
                    if "resource" not in item:
                        return False
            
            return True
            
        except Exception:
            return False
    
    def validate_mcp_resources_list_request(self, message: Dict[str, Any]) -> bool:
        """Validate MCP resources/list request format."""
        try:
            if not self.validate_json_rpc_request(message):
                return False
            
            if message.get("method") != "resources/list":
                return False
            
            # resources/list should not have params
            if "params" in message and message["params"] is not None:
                return False
            
            return True
            
        except Exception:
            return False
    
    def validate_mcp_resources_list_response(self, message: Dict[str, Any]) -> bool:
        """Validate MCP resources/list response format."""
        try:
            if not self.validate_json_rpc_response(message):
                return False
            
            if "result" not in message:
                return False
            
            result = message["result"]
            
            if "resources" not in result:
                return False
            
            resources = result["resources"]
            if not isinstance(resources, list):
                return False
            
            # Validate each resource structure
            for resource in resources:
                if not isinstance(resource, dict):
                    return False
                
                required_resource_fields = ["uri", "name"]
                for field in required_resource_fields:
                    if field not in resource:
                        return False
                
                # URI should be a string
                if not isinstance(resource["uri"], str):
                    return False
                
                # Name should be a string
                if not isinstance(resource["name"], str):
                    return False
            
            return True
            
        except Exception:
            return False
    
    def validate_mcp_resources_read_request(self, message: Dict[str, Any]) -> bool:
        """Validate MCP resources/read request format."""
        try:
            if not self.validate_json_rpc_request(message):
                return False
            
            if message.get("method") != "resources/read":
                return False
            
            params = message.get("params", {})
            
            # Required field for resources/read
            if "uri" not in params:
                return False
            
            if not isinstance(params["uri"], str):
                return False
            
            return True
            
        except Exception:
            return False
    
    def validate_mcp_resources_read_response(self, message: Dict[str, Any]) -> bool:
        """Validate MCP resources/read response format."""
        try:
            if not self.validate_json_rpc_response(message):
                return False
            
            if "result" not in message:
                return False
            
            result = message["result"]
            
            if "contents" not in result:
                return False
            
            contents = result["contents"]
            if not isinstance(contents, list):
                return False
            
            # Validate each content item
            for item in contents:
                if not isinstance(item, dict):
                    return False
                
                if "type" not in item:
                    return False
                
                # Based on type, validate required fields
                item_type = item["type"]
                if item_type == "text":
                    if "text" not in item:
                        return False
                elif item_type == "blob":
                    if "blob" not in item or "mimeType" not in item:
                        return False
            
            return True
            
        except Exception:
            return False
    
    def validate_mcp_error_response(self, message: Dict[str, Any]) -> bool:
        """Validate MCP error response format."""
        try:
            if not self.validate_json_rpc_response(message):
                return False
            
            if "error" not in message:
                return False
            
            error = message["error"]
            
            # JSON-RPC error codes
            valid_codes = [
                -32700,  # Parse error
                -32600,  # Invalid Request
                -32601,  # Method not found
                -32602,  # Invalid params
                -32603,  # Internal error
                -32000,  # Server error (MCP-specific errors can use this range)
            ]
            
            # MCP also allows server-defined error codes in the -32000 to -32099 range
            code = error["code"]
            if code not in valid_codes and not (-32099 <= code <= -32000):
                return False
            
            return True
            
        except Exception:
            return False
    
    async def test_json_rpc_message_validation(self):
        """Test JSON-RPC 2.0 message format validation."""
        print("\n📋 Testing JSON-RPC 2.0 Message Format Validation")
        
        # Test valid JSON-RPC request
        valid_request = {
            "jsonrpc": "2.0",
            "method": "test_method",
            "params": {"arg": "value"},
            "id": "test-id"
        }
        
        self.record_test(
            "JSON-RPC request validation - Valid request",
            self.validate_json_rpc_request(valid_request)
        )
        
        # Test invalid JSON-RPC requests
        invalid_requests = [
            {"method": "test"},  # Missing jsonrpc
            {"jsonrpc": "1.0", "method": "test", "id": 1},  # Wrong version
            {"jsonrpc": "2.0", "id": 1},  # Missing method
            {"jsonrpc": "2.0", "method": 123, "id": 1},  # Method not string
            {"jsonrpc": "2.0", "method": "test", "params": "invalid", "id": 1},  # Invalid params type
        ]
        
        for i, invalid_request in enumerate(invalid_requests):
            self.record_test(
                f"JSON-RPC request validation - Invalid request {i+1}",
                not self.validate_json_rpc_request(invalid_request)
            )
        
        # Test valid JSON-RPC response
        valid_response = {
            "jsonrpc": "2.0",
            "result": {"data": "value"},
            "id": "test-id"
        }
        
        self.record_test(
            "JSON-RPC response validation - Valid response",
            self.validate_json_rpc_response(valid_response)
        )
        
        # Test valid JSON-RPC error response
        valid_error_response = {
            "jsonrpc": "2.0",
            "error": {
                "code": -32601,
                "message": "Method not found"
            },
            "id": "test-id"
        }
        
        self.record_test(
            "JSON-RPC response validation - Valid error response",
            self.validate_json_rpc_response(valid_error_response)
        )
        
        # Test invalid JSON-RPC responses
        invalid_responses = [
            {"result": "test"},  # Missing jsonrpc and id
            {"jsonrpc": "2.0", "result": "test"},  # Missing id
            {"jsonrpc": "2.0", "id": 1},  # Missing result and error
            {"jsonrpc": "2.0", "result": "test", "error": {"code": -1, "message": "error"}, "id": 1},  # Both result and error
        ]
        
        for i, invalid_response in enumerate(invalid_responses):
            self.record_test(
                f"JSON-RPC response validation - Invalid response {i+1}",
                not self.validate_json_rpc_response(invalid_response)
            )
    
    async def test_mcp_initialize_messages(self):
        """Test MCP initialize message validation."""
        print("\n🤝 Testing MCP Initialize Message Validation")
        
        # Valid initialize request
        valid_init_request = {
            "jsonrpc": "2.0",
            "id": "init-1",
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "roots": {"listChanged": True}
                },
                "clientInfo": {
                    "name": "test-client",
                    "version": "1.0.0"
                }
            }
        }
        
        self.record_test(
            "MCP initialize request validation - Valid request",
            self.validate_mcp_initialize_request(valid_init_request)
        )
        
        # Valid initialize response
        valid_init_response = {
            "jsonrpc": "2.0",
            "id": "init-1",
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "logging": {},
                    "tools": {"listChanged": True}
                },
                "serverInfo": {
                    "name": "ast-mcp",
                    "version": "1.0.0"
                }
            }
        }
        
        self.record_test(
            "MCP initialize response validation - Valid response",
            self.validate_mcp_initialize_response(valid_init_response)
        )
        
        # Invalid initialize requests
        invalid_init_requests = [
            {  # Missing protocolVersion
                "jsonrpc": "2.0",
                "id": "init-1",
                "method": "initialize",
                "params": {
                    "capabilities": {},
                    "clientInfo": {"name": "test"}
                }
            },
            {  # Missing clientInfo
                "jsonrpc": "2.0", 
                "id": "init-1",
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {}
                }
            }
        ]
        
        for i, invalid_request in enumerate(invalid_init_requests):
            self.record_test(
                f"MCP initialize request validation - Invalid request {i+1}",
                not self.validate_mcp_initialize_request(invalid_request)
            )
    
    async def test_mcp_tools_messages(self):
        """Test MCP tools message validation."""
        print("\n🛠️ Testing MCP Tools Message Validation")
        
        # Valid tools/list request
        valid_tools_list_request = {
            "jsonrpc": "2.0",
            "id": "tools-1",
            "method": "tools/list"
        }
        
        self.record_test(
            "MCP tools/list request validation - Valid request",
            self.validate_mcp_tools_list_request(valid_tools_list_request)
        )
        
        # Valid tools/list response
        valid_tools_list_response = {
            "jsonrpc": "2.0",
            "id": "tools-1",
            "result": {
                "tools": [
                    {
                        "name": "test_tool",
                        "description": "A test tool",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "arg": {"type": "string"}
                            }
                        }
                    }
                ]
            }
        }
        
        self.record_test(
            "MCP tools/list response validation - Valid response",
            self.validate_mcp_tools_list_response(valid_tools_list_response)
        )
        
        # Valid tools/call request
        valid_tools_call_request = {
            "jsonrpc": "2.0",
            "id": "call-1",
            "method": "tools/call",
            "params": {
                "name": "test_tool",
                "arguments": {
                    "arg": "value"
                }
            }
        }
        
        self.record_test(
            "MCP tools/call request validation - Valid request",
            self.validate_mcp_tools_call_request(valid_tools_call_request)
        )
        
        # Valid tools/call response
        valid_tools_call_response = {
            "jsonrpc": "2.0",
            "id": "call-1",
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": "Tool result"
                    }
                ]
            }
        }
        
        self.record_test(
            "MCP tools/call response validation - Valid response",
            self.validate_mcp_tools_call_response(valid_tools_call_response)
        )
    
    async def test_mcp_resources_messages(self):
        """Test MCP resources message validation."""
        print("\n📚 Testing MCP Resources Message Validation")
        
        # Valid resources/list request
        valid_resources_list_request = {
            "jsonrpc": "2.0",
            "id": "res-1",
            "method": "resources/list"
        }
        
        self.record_test(
            "MCP resources/list request validation - Valid request",
            self.validate_mcp_resources_list_request(valid_resources_list_request)
        )
        
        # Valid resources/list response
        valid_resources_list_response = {
            "jsonrpc": "2.0",
            "id": "res-1",
            "result": {
                "resources": [
                    {
                        "uri": "ast-grep://health",
                        "name": "Health Status",
                        "description": "Server health information"
                    }
                ]
            }
        }
        
        self.record_test(
            "MCP resources/list response validation - Valid response",
            self.validate_mcp_resources_list_response(valid_resources_list_response)
        )
        
        # Valid resources/read request
        valid_resources_read_request = {
            "jsonrpc": "2.0",
            "id": "read-1",
            "method": "resources/read",
            "params": {
                "uri": "ast-grep://health"
            }
        }
        
        self.record_test(
            "MCP resources/read request validation - Valid request",
            self.validate_mcp_resources_read_request(valid_resources_read_request)
        )
        
        # Valid resources/read response
        valid_resources_read_response = {
            "jsonrpc": "2.0",
            "id": "read-1",
            "result": {
                "contents": [
                    {
                        "type": "text",
                        "text": '{"status": "healthy"}'
                    }
                ]
            }
        }
        
        self.record_test(
            "MCP resources/read response validation - Valid response",
            self.validate_mcp_resources_read_response(valid_resources_read_response)
        )
    
    async def test_mcp_error_messages(self):
        """Test MCP error message validation."""
        print("\n❌ Testing MCP Error Message Validation")
        
        # Standard JSON-RPC errors
        standard_errors = [
            {"code": -32700, "message": "Parse error"},
            {"code": -32600, "message": "Invalid Request"},
            {"code": -32601, "message": "Method not found"},
            {"code": -32602, "message": "Invalid params"},
            {"code": -32603, "message": "Internal error"},
        ]
        
        for error_info in standard_errors:
            error_response = {
                "jsonrpc": "2.0",
                "id": "error-test",
                "error": error_info
            }
            
            self.record_test(
                f"MCP error validation - Code {error_info['code']}",
                self.validate_mcp_error_response(error_response)
            )
        
        # MCP-specific server errors
        mcp_server_errors = [
            {"code": -32000, "message": "Server error"},
            {"code": -32050, "message": "Tool execution failed"},
            {"code": -32099, "message": "Custom server error"},
        ]
        
        for error_info in mcp_server_errors:
            error_response = {
                "jsonrpc": "2.0",
                "id": "error-test",
                "error": error_info
            }
            
            self.record_test(
                f"MCP server error validation - Code {error_info['code']}",
                self.validate_mcp_error_response(error_response)
            )
        
        # Invalid error codes
        invalid_error_codes = [-1, 0, 1000, -33000]
        for code in invalid_error_codes:
            error_response = {
                "jsonrpc": "2.0",
                "id": "error-test",
                "error": {"code": code, "message": "Invalid error"}
            }
            
            self.record_test(
                f"MCP error validation - Invalid code {code}",
                not self.validate_mcp_error_response(error_response)
            )
    
    async def run_all_tests(self):
        """Run all protocol message validation tests."""
        print("=" * 60)
        print("MCP Protocol Message Validation Tests")
        print("=" * 60)
        
        try:
            # Setup server
            if not await self.setup_server():
                return False
            
            # Run test suite
            await self.test_json_rpc_message_validation()
            await self.test_mcp_initialize_messages()
            await self.test_mcp_tools_messages()
            await self.test_mcp_resources_messages()
            await self.test_mcp_error_messages()
            
            return True
            
        except Exception as e:
            print(f"❌ Protocol message validation test suite failed: {e}")
            return False
    
    def print_summary(self):
        """Print test summary."""
        print("\n" + "=" * 60)
        print("PROTOCOL MESSAGE VALIDATION TEST SUMMARY")
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
    validator = MCPProtocolMessageValidator()
    
    try:
        success = await validator.run_all_tests()
        validator.print_summary()
        
        if success:
            print("\n🎉 All protocol message validation tests passed!")
            return 0
        else:
            print("\n❌ Some protocol message validation tests failed!")
            return 1
            
    except Exception as e:
        print(f"❌ Test suite failed: {e}")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)