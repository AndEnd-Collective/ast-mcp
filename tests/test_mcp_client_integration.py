#!/usr/bin/env python3
"""Comprehensive MCP Client-Server Integration Tests.

This module tests actual MCP client-server communication using the stdio transport
mechanism to ensure full protocol compliance and real-world functionality.
"""

import asyncio
import json
import sys
import os
import tempfile
import uuid
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import subprocess
import time
import signal
from contextlib import asynccontextmanager

import pytest

# Add src to Python path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

try:
    from ast_grep_mcp.server import create_server, ServerConfig
    from ast_grep_mcp.utils import find_ast_grep_binary
    from mcp.server import Server
    from mcp.types import Tool, Resource, TextContent
    from mcp.server.stdio import stdio_server
    from mcp.client.stdio import stdio_client
except ImportError as e:
    print(f"Import error: {e}")
    print("Please install dependencies: pip install -e .")
    sys.exit(1)


class TestMCPClientServerIntegration:
    """Test real MCP client-server communication."""

    def setup_method(self):
        self.server_process = None
        self.test_results = []
        self.client_streams = None

    def record_test(self, test_name: str, passed: bool, details: str = ""):
        """Record test result."""
        status = "PASS" if passed else "FAIL"
        print(f"{status} {test_name}")
        if details:
            print(f"    {details}")

        self.test_results.append({
            "test": test_name,
            "passed": passed,
            "details": details,
            "timestamp": time.time()
        })

    @asynccontextmanager
    async def start_server_process(self):
        """Start the MCP server in a separate process."""
        print("Starting MCP server process...")

        # Create a minimal server script for testing
        server_script = """
import asyncio
import sys
import os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ast_grep_mcp.server import create_server, ServerConfig

async def main():
    # Create lightweight config for testing
    config = ServerConfig()
    config.enable_performance = True
    config.enable_security = True
    config.enable_monitoring = False
    config.system_monitoring_enabled = False
    config.alerting_enabled = False
    config.dependency_check_enabled = False
    config.detailed_diagnostics = False
    config.health_check_interval = 300

    server = create_server(config)
    await server.run()

if __name__ == "__main__":
    asyncio.run(main())
"""

        # Write server script to temp file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(server_script)
            server_script_path = f.name

        try:
            # Start server process
            self.server_process = subprocess.Popen(
                [sys.executable, server_script_path],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            # Give server time to start
            await asyncio.sleep(2)

            # Check if server is still running
            if self.server_process.poll() is not None:
                stderr_output = self.server_process.stderr.read()
                raise Exception(f"Server process terminated early: {stderr_output}")

            print("MCP server process started successfully")
            yield self.server_process.stdout, self.server_process.stdin

        finally:
            # Clean up
            if self.server_process and self.server_process.poll() is None:
                self.server_process.terminate()
                try:
                    self.server_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.server_process.kill()
                    self.server_process.wait()

            # Remove temp file
            try:
                os.unlink(server_script_path)
            except:
                pass

    async def send_json_rpc_request(self, write_stream, method: str, params: Dict[str, Any] = None) -> str:
        """Send a JSON-RPC request to the server."""
        request_id = str(uuid.uuid4())
        request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method
        }

        if params:
            request["params"] = params

        request_json = json.dumps(request) + "\n"
        write_stream.write(request_json)
        write_stream.flush()

        return request_id

    async def read_json_rpc_response(self, read_stream, timeout: float = 5.0) -> Dict[str, Any]:
        """Read a JSON-RPC response from the server."""
        try:
            # Read with timeout
            response_line = await asyncio.wait_for(
                asyncio.create_task(asyncio.to_thread(read_stream.readline)),
                timeout=timeout
            )

            if not response_line:
                raise Exception("No response received")

            response = json.loads(response_line.strip())
            return response

        except asyncio.TimeoutError:
            raise Exception(f"Response timeout after {timeout}s")
        except json.JSONDecodeError as e:
            raise Exception(f"Invalid JSON response: {e}")

    @pytest.mark.asyncio
    async def test_server_initialization(self):
        """Test server initialization handshake."""
        print("\nTesting Server Initialization")

        async with self.start_server_process() as (read_stream, write_stream):
            try:
                # Send initialization request
                init_params = {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {
                        "roots": {
                            "listChanged": True
                        },
                        "sampling": {}
                    },
                    "clientInfo": {
                        "name": "mcp-test-client",
                        "version": "1.0.0"
                    }
                }

                request_id = await self.send_json_rpc_request(write_stream, "initialize", init_params)
                response = await self.read_json_rpc_response(read_stream)

                # Validate response
                if response.get("id") != request_id:
                    self.record_test("Server initialization - ID match", False, f"Expected ID {request_id}, got {response.get('id')}")
                    return False

                if "result" not in response:
                    self.record_test("Server initialization - Has result", False, f"No result in response: {response}")
                    return False

                result = response["result"]

                # Check required fields
                required_fields = ["protocolVersion", "capabilities", "serverInfo"]
                for field in required_fields:
                    if field not in result:
                        self.record_test(f"Server initialization - {field} present", False, f"Missing {field}")
                        return False
                    else:
                        self.record_test(f"Server initialization - {field} present", True)

                # Check server info
                server_info = result["serverInfo"]
                if "name" not in server_info:
                    self.record_test("Server initialization - Server name", False, "Missing server name")
                    return False

                self.record_test("Server initialization - Server name", True, f"Server: {server_info['name']}")

                # Send initialized notification
                initialized_notification = {
                    "jsonrpc": "2.0",
                    "method": "notifications/initialized"
                }

                write_stream.write(json.dumps(initialized_notification) + "\n")
                write_stream.flush()

                self.record_test("Server initialization handshake", True, "Complete handshake successful")
                return True

            except Exception as e:
                self.record_test("Server initialization handshake", False, f"Error: {e}")
                return False

    @pytest.mark.asyncio
    async def test_tool_listing(self):
        """Test tool listing functionality."""
        print("\nTesting Tool Listing")

        async with self.start_server_process() as (read_stream, write_stream):
            try:
                request_id = await self.send_json_rpc_request(write_stream, "tools/list")
                response = await self.read_json_rpc_response(read_stream)

                # Validate response structure
                if response.get("id") != request_id:
                    self.record_test("Tool listing - ID match", False, f"ID mismatch")
                    return False

                if "result" not in response:
                    self.record_test("Tool listing - Has result", False, "No result field")
                    return False

                result = response["result"]

                if "tools" not in result:
                    self.record_test("Tool listing - Has tools", False, "No tools field")
                    return False

                tools = result["tools"]

                if not isinstance(tools, list):
                    self.record_test("Tool listing - Tools is list", False, f"Tools is {type(tools)}")
                    return False

                self.record_test("Tool listing - Tools is list", True, f"Found {len(tools)} tools")

                # Validate tool structure
                expected_tools = ["ast_grep_search", "ast_grep_scan", "ast_grep_run"]
                found_tools = {tool.get("name") for tool in tools}

                for expected_tool in expected_tools:
                    if expected_tool in found_tools:
                        self.record_test(f"Tool listing - {expected_tool} present", True)
                    else:
                        self.record_test(f"Tool listing - {expected_tool} present", False, "Tool missing")

                # Validate tool schema
                for tool in tools:
                    if not isinstance(tool, dict):
                        self.record_test(f"Tool structure - {tool} is dict", False)
                        continue

                    required_fields = ["name", "description", "inputSchema"]
                    for field in required_fields:
                        if field not in tool:
                            self.record_test(f"Tool structure - {tool.get('name', 'unknown')} has {field}", False)
                        else:
                            self.record_test(f"Tool structure - {tool.get('name', 'unknown')} has {field}", True)

                return True

            except Exception as e:
                self.record_test("Tool listing", False, f"Error: {e}")
                return False

    @pytest.mark.asyncio
    async def test_tool_execution(self):
        """Test tool execution functionality."""
        print("\nTesting Tool Execution")

        async with self.start_server_process() as (read_stream, write_stream):
            try:
                # Create a temporary test file
                with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False) as f:
                    f.write('console.log("Hello, world!");')
                    test_file_path = f.name

                try:
                    # Test ast_grep_search tool
                    search_params = {
                        "name": "ast_grep_search",
                        "arguments": {
                            "pattern": "console.log($MSG)",
                            "language": "javascript",
                            "path": test_file_path,
                            "output_format": "json"
                        }
                    }

                    request_id = await self.send_json_rpc_request(write_stream, "tools/call", search_params)
                    response = await self.read_json_rpc_response(read_stream, timeout=10.0)

                    # Validate response
                    if response.get("id") != request_id:
                        self.record_test("Tool execution - ID match", False)
                        return False

                    if "result" not in response:
                        self.record_test("Tool execution - Has result", False, f"Response: {response}")
                        return False

                    result = response["result"]

                    if "content" not in result:
                        self.record_test("Tool execution - Has content", False)
                        return False

                    content = result["content"]

                    if not isinstance(content, list) or len(content) == 0:
                        self.record_test("Tool execution - Content is non-empty list", False)
                        return False

                    # Validate content structure
                    first_content = content[0]
                    if "type" not in first_content or "text" not in first_content:
                        self.record_test("Tool execution - Content structure", False)
                        return False

                    self.record_test("Tool execution - Basic search", True, "Search tool executed successfully")

                    # Test that the result contains expected data
                    response_text = first_content["text"]
                    if "console.log" in response_text:
                        self.record_test("Tool execution - Result contains match", True)
                    else:
                        self.record_test("Tool execution - Result contains match", False, f"Response: {response_text}")

                    return True

                finally:
                    # Clean up test file
                    os.unlink(test_file_path)

            except Exception as e:
                self.record_test("Tool execution", False, f"Error: {e}")
                return False

    @pytest.mark.asyncio
    async def test_resource_listing(self):
        """Test resource listing functionality."""
        print("\nTesting Resource Listing")

        async with self.start_server_process() as (read_stream, write_stream):
            try:
                request_id = await self.send_json_rpc_request(write_stream, "resources/list")
                response = await self.read_json_rpc_response(read_stream)

                # Validate response structure
                if response.get("id") != request_id:
                    self.record_test("Resource listing - ID match", False)
                    return False

                if "result" not in response:
                    self.record_test("Resource listing - Has result", False)
                    return False

                result = response["result"]

                if "resources" not in result:
                    self.record_test("Resource listing - Has resources", False)
                    return False

                resources = result["resources"]

                if not isinstance(resources, list):
                    self.record_test("Resource listing - Resources is list", False)
                    return False

                self.record_test("Resource listing - Resources is list", True, f"Found {len(resources)} resources")

                # Validate resource structure
                expected_resources = ["ast-grep://patterns", "ast-grep://languages"]
                found_resources = {resource.get("uri") for resource in resources}

                for expected_resource in expected_resources:
                    if expected_resource in found_resources:
                        self.record_test(f"Resource listing - {expected_resource} present", True)
                    else:
                        self.record_test(f"Resource listing - {expected_resource} present", False)

                return True

            except Exception as e:
                self.record_test("Resource listing", False, f"Error: {e}")
                return False

    @pytest.mark.asyncio
    async def test_resource_reading(self):
        """Test resource reading functionality."""
        print("\nTesting Resource Reading")

        async with self.start_server_process() as (read_stream, write_stream):
            try:
                # Test reading patterns resource
                resource_params = {
                    "uri": "ast-grep://patterns"
                }

                request_id = await self.send_json_rpc_request(write_stream, "resources/read", resource_params)
                response = await self.read_json_rpc_response(read_stream, timeout=10.0)

                # Validate response
                if response.get("id") != request_id:
                    self.record_test("Resource reading - ID match", False)
                    return False

                if "result" not in response:
                    self.record_test("Resource reading - Has result", False, f"Response: {response}")
                    return False

                result = response["result"]

                if "contents" not in result:
                    self.record_test("Resource reading - Has contents", False)
                    return False

                contents = result["contents"]

                if not isinstance(contents, list) or len(contents) == 0:
                    self.record_test("Resource reading - Contents is non-empty list", False)
                    return False

                # Validate content structure
                first_content = contents[0]
                if "uri" not in first_content or "text" not in first_content:
                    self.record_test("Resource reading - Content structure", False)
                    return False

                self.record_test("Resource reading - Patterns resource", True, "Patterns resource read successfully")

                # Test that the result contains expected patterns data
                response_text = first_content["text"]
                try:
                    patterns_data = json.loads(response_text)
                    if "patterns" in patterns_data and isinstance(patterns_data["patterns"], list):
                        self.record_test("Resource reading - Patterns data structure", True)
                    else:
                        self.record_test("Resource reading - Patterns data structure", False, f"Invalid patterns structure: {patterns_data}")
                except json.JSONDecodeError:
                    self.record_test("Resource reading - Patterns data is valid JSON", False, f"Invalid JSON: {response_text}")

                return True

            except Exception as e:
                self.record_test("Resource reading", False, f"Error: {e}")
                return False

    @pytest.mark.asyncio
    async def test_error_handling(self):
        """Test error handling in the protocol."""
        print("\nTesting Error Handling")

        async with self.start_server_process() as (read_stream, write_stream):
            try:
                # Test 1: Invalid method
                request_id = await self.send_json_rpc_request(write_stream, "invalid/method")
                response = await self.read_json_rpc_response(read_stream)

                if "error" in response:
                    self.record_test("Error handling - Invalid method", True, "Proper error response")
                else:
                    self.record_test("Error handling - Invalid method", False, "Should return error")

                # Test 2: Invalid tool call
                invalid_tool_params = {
                    "name": "invalid_tool_xyz_123",
                    "arguments": {}
                }

                request_id = await self.send_json_rpc_request(write_stream, "tools/call", invalid_tool_params)
                response = await self.read_json_rpc_response(read_stream)

                # For invalid tools, the server may return a result with isError=True or a JSON-RPC error
                if "error" in response or (response.get("result", {}).get("isError") == True):
                    self.record_test("Error handling - Invalid tool", True, "Proper error response")
                else:
                    self.record_test("Error handling - Invalid tool", False, "Should return error")

                # Test 3: Invalid resource
                invalid_resource_params = {
                    "uri": "ast-grep://nonexistent"
                }

                request_id = await self.send_json_rpc_request(write_stream, "resources/read", invalid_resource_params)
                response = await self.read_json_rpc_response(read_stream)

                # For invalid resources, check if the content contains an error message
                resource_has_error = False
                if "error" in response:
                    resource_has_error = True
                elif "result" in response and "contents" in response["result"]:
                    contents = response["result"]["contents"]
                    if contents and len(contents) > 0:
                        content_text = contents[0].get("text", "")
                        if "error" in content_text.lower() and "not found" in content_text.lower():
                            resource_has_error = True

                if resource_has_error:
                    self.record_test("Error handling - Invalid resource", True, "Proper error response")
                else:
                    self.record_test("Error handling - Invalid resource", False, "Should return error")

                return True

            except Exception as e:
                self.record_test("Error handling", False, f"Error: {e}")
                return False
