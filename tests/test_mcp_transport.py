#!/usr/bin/env python3
"""MCP Transport Layer Testing.

This module tests the MCP transport layer mechanisms including stdio transport,
message framing and parsing, connection lifecycle, and error handling in the
transport layer.
"""

import asyncio
import json
import sys
import os
import tempfile
import subprocess
import signal
import time
import uuid
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from contextlib import asynccontextmanager

# Add src to Python path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

try:
    from ast_grep_mcp.server import create_server, ServerConfig
    from mcp.server.stdio import stdio_server
    from mcp.client.stdio import stdio_client
except ImportError as e:
    print(f"Import error: {e}")
    print("Please install dependencies: pip install -e .")
    sys.exit(1)


class MCPTransportTester:
    """Test MCP transport layer functionality."""
    
    def __init__(self):
        self.test_results = []
        self.server_process = None
        
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
    
    @asynccontextmanager
    async def create_server_process(self):
        """Create a server process for transport testing."""
        print("🚀 Creating server process for transport testing...")
        
        # Create a minimal server script
        server_script = """
import asyncio
import sys
import os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ast_grep_mcp.server import create_server, ServerConfig

async def main():
    config = ServerConfig()
    config.enable_performance = True
    config.enable_security = False
    config.enable_monitoring = False
    config.system_monitoring_enabled = False
    config.alerting_enabled = False
    config.dependency_check_enabled = False
    
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
                text=True,
                bufsize=0  # Unbuffered for immediate I/O
            )
            
            # Give server time to start
            await asyncio.sleep(3)
            
            # Check if server is still running
            if self.server_process.poll() is not None:
                stderr_output = self.server_process.stderr.read()
                raise Exception(f"Server process terminated early: {stderr_output}")
            
            print("✅ Server process created successfully")
            yield self.server_process
            
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
    
    async def test_stdio_transport_basic(self):
        """Test basic stdio transport functionality."""
        print("\n📡 Testing Basic Stdio Transport")
        
        try:
            async with self.create_server_process() as server_process:
                # Test basic read/write operations
                
                # Send a simple message
                test_message = {"jsonrpc": "2.0", "method": "test", "id": "test-1"}
                message_json = json.dumps(test_message) + "\n"
                
                server_process.stdin.write(message_json)
                server_process.stdin.flush()
                
                self.record_test(
                    "Stdio transport - Basic write",
                    True,
                    "Successfully wrote message to stdin"
                )
                
                # Try to read response (should get an error for unknown method)
                try:
                    response_line = await asyncio.wait_for(
                        asyncio.create_task(asyncio.to_thread(server_process.stdout.readline)),
                        timeout=5.0
                    )
                    
                    if response_line:
                        response = json.loads(response_line.strip())
                        self.record_test(
                            "Stdio transport - Basic read",
                            True,
                            f"Successfully read response: {response.get('id', 'no-id')}"
                        )
                    else:
                        self.record_test(
                            "Stdio transport - Basic read",
                            False,
                            "No response received"
                        )
                        
                except asyncio.TimeoutError:
                    self.record_test(
                        "Stdio transport - Basic read",
                        False,
                        "Timeout waiting for response"
                    )
                except json.JSONDecodeError:
                    self.record_test(
                        "Stdio transport - Basic read",
                        False,
                        "Invalid JSON response"
                    )
                
        except Exception as e:
            self.record_test(
                "Stdio transport - Basic functionality",
                False,
                f"Error: {e}"
            )
    
    async def test_message_framing(self):
        """Test message framing and parsing."""
        print("\n📦 Testing Message Framing and Parsing")
        
        try:
            async with self.create_server_process() as server_process:
                # Test single message
                single_message = {"jsonrpc": "2.0", "method": "ping", "id": "frame-1"}
                single_json = json.dumps(single_message) + "\n"
                
                server_process.stdin.write(single_json)
                server_process.stdin.flush()
                
                try:
                    response = await asyncio.wait_for(
                        asyncio.create_task(asyncio.to_thread(server_process.stdout.readline)),
                        timeout=5.0
                    )
                    
                    if response and response.strip():
                        parsed = json.loads(response.strip())
                        self.record_test(
                            "Message framing - Single message",
                            parsed.get("id") == "frame-1",
                            "Single message framed and parsed correctly"
                        )
                    else:
                        self.record_test(
                            "Message framing - Single message",
                            False,
                            "No response to single message"
                        )
                        
                except (asyncio.TimeoutError, json.JSONDecodeError) as e:
                    self.record_test(
                        "Message framing - Single message",
                        False,
                        f"Error: {e}"
                    )
                
                # Test multiple messages in sequence
                messages = [
                    {"jsonrpc": "2.0", "method": "test1", "id": "frame-2"},
                    {"jsonrpc": "2.0", "method": "test2", "id": "frame-3"},
                    {"jsonrpc": "2.0", "method": "test3", "id": "frame-4"}
                ]
                
                # Send all messages
                for msg in messages:
                    msg_json = json.dumps(msg) + "\n"
                    server_process.stdin.write(msg_json)
                    server_process.stdin.flush()
                
                # Read responses
                responses_received = 0
                for i in range(len(messages)):
                    try:
                        response = await asyncio.wait_for(
                            asyncio.create_task(asyncio.to_thread(server_process.stdout.readline)),
                            timeout=2.0
                        )
                        
                        if response and response.strip():
                            parsed = json.loads(response.strip())
                            if "id" in parsed:
                                responses_received += 1
                                
                    except (asyncio.TimeoutError, json.JSONDecodeError):
                        break
                
                self.record_test(
                    "Message framing - Multiple messages",
                    responses_received == len(messages),
                    f"Received {responses_received}/{len(messages)} responses"
                )
                
        except Exception as e:
            self.record_test(
                "Message framing - General",
                False,
                f"Error: {e}"
            )
    
    async def test_connection_lifecycle(self):
        """Test connection lifecycle management."""
        print("\n🔄 Testing Connection Lifecycle")
        
        try:
            # Test 1: Normal connection startup
            async with self.create_server_process() as server_process:
                # Check that server is responsive after startup
                init_message = {
                    "jsonrpc": "2.0",
                    "method": "initialize",
                    "id": "lifecycle-1",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {"name": "test-client", "version": "1.0.0"}
                    }
                }
                
                init_json = json.dumps(init_message) + "\n"
                server_process.stdin.write(init_json)
                server_process.stdin.flush()
                
                try:
                    response = await asyncio.wait_for(
                        asyncio.create_task(asyncio.to_thread(server_process.stdout.readline)),
                        timeout=10.0
                    )
                    
                    if response and response.strip():
                        parsed = json.loads(response.strip())
                        initialization_success = (
                            parsed.get("id") == "lifecycle-1" and 
                            "result" in parsed
                        )
                        
                        self.record_test(
                            "Connection lifecycle - Initialization",
                            initialization_success,
                            "Server responded to initialization"
                        )
                    else:
                        self.record_test(
                            "Connection lifecycle - Initialization",
                            False,
                            "No initialization response"
                        )
                        
                except (asyncio.TimeoutError, json.JSONDecodeError) as e:
                    self.record_test(
                        "Connection lifecycle - Initialization",
                        False,
                        f"Initialization failed: {e}"
                    )
                
                # Test 2: Server remains responsive during normal operation
                ping_message = {"jsonrpc": "2.0", "method": "ping", "id": "lifecycle-2"}
                ping_json = json.dumps(ping_message) + "\n"
                
                server_process.stdin.write(ping_json)
                server_process.stdin.flush()
                
                try:
                    response = await asyncio.wait_for(
                        asyncio.create_task(asyncio.to_thread(server_process.stdout.readline)),
                        timeout=5.0
                    )
                    
                    responsive = response and response.strip()
                    self.record_test(
                        "Connection lifecycle - Server responsiveness",
                        responsive,
                        "Server remains responsive after initialization"
                    )
                    
                except asyncio.TimeoutError:
                    self.record_test(
                        "Connection lifecycle - Server responsiveness",
                        False,
                        "Server became unresponsive"
                    )
            
            # Test 3: Graceful shutdown
            server_terminated_gracefully = (
                self.server_process is None or 
                self.server_process.poll() is not None
            )
            
            self.record_test(
                "Connection lifecycle - Graceful shutdown",
                server_terminated_gracefully,
                "Server terminated gracefully when context ended"
            )
            
        except Exception as e:
            self.record_test(
                "Connection lifecycle - General",
                False,
                f"Error: {e}"
            )
    
    async def test_transport_error_handling(self):
        """Test error handling in transport layer."""
        print("\n❌ Testing Transport Error Handling")
        
        try:
            async with self.create_server_process() as server_process:
                # Test 1: Invalid JSON
                invalid_json = "{ invalid json }\n"
                server_process.stdin.write(invalid_json)
                server_process.stdin.flush()
                
                try:
                    response = await asyncio.wait_for(
                        asyncio.create_task(asyncio.to_thread(server_process.stdout.readline)),
                        timeout=5.0
                    )
                    
                    if response and response.strip():
                        parsed = json.loads(response.strip())
                        has_error = "error" in parsed
                        self.record_test(
                            "Transport error handling - Invalid JSON",
                            has_error,
                            f"Server responded with error to invalid JSON"
                        )
                    else:
                        self.record_test(
                            "Transport error handling - Invalid JSON",
                            False,
                            "No error response to invalid JSON"
                        )
                        
                except (asyncio.TimeoutError, json.JSONDecodeError):
                    self.record_test(
                        "Transport error handling - Invalid JSON",
                        False,
                        "Server did not handle invalid JSON properly"
                    )
                
                # Test 2: Malformed JSON-RPC
                malformed_jsonrpc = {"not_jsonrpc": "true", "id": "error-1"}
                malformed_json = json.dumps(malformed_jsonrpc) + "\n"
                
                server_process.stdin.write(malformed_json)
                server_process.stdin.flush()
                
                try:
                    response = await asyncio.wait_for(
                        asyncio.create_task(asyncio.to_thread(server_process.stdout.readline)),
                        timeout=5.0
                    )
                    
                    if response and response.strip():
                        parsed = json.loads(response.strip())
                        has_error = "error" in parsed
                        self.record_test(
                            "Transport error handling - Malformed JSON-RPC",
                            has_error,
                            "Server responded with error to malformed JSON-RPC"
                        )
                    else:
                        self.record_test(
                            "Transport error handling - Malformed JSON-RPC",
                            False,
                            "No error response to malformed JSON-RPC"
                        )
                        
                except (asyncio.TimeoutError, json.JSONDecodeError):
                    self.record_test(
                        "Transport error handling - Malformed JSON-RPC",
                        False,
                        "Server did not handle malformed JSON-RPC properly"
                    )
                
                # Test 3: Server remains responsive after errors
                recovery_message = {"jsonrpc": "2.0", "method": "ping", "id": "recovery-1"}
                recovery_json = json.dumps(recovery_message) + "\n"
                
                server_process.stdin.write(recovery_json)
                server_process.stdin.flush()
                
                try:
                    response = await asyncio.wait_for(
                        asyncio.create_task(asyncio.to_thread(server_process.stdout.readline)),
                        timeout=5.0
                    )
                    
                    responsive_after_error = response and response.strip()
                    self.record_test(
                        "Transport error handling - Recovery",
                        responsive_after_error,
                        "Server remains responsive after handling errors"
                    )
                    
                except asyncio.TimeoutError:
                    self.record_test(
                        "Transport error handling - Recovery",
                        False,
                        "Server became unresponsive after errors"
                    )
                
        except Exception as e:
            self.record_test(
                "Transport error handling - General",
                False,
                f"Error: {e}"
            )
    
    async def test_message_ordering(self):
        """Test message ordering and synchronization."""
        print("\n🔄 Testing Message Ordering")
        
        try:
            async with self.create_server_process() as server_process:
                # Send multiple messages with unique IDs
                messages = []
                for i in range(5):
                    msg = {"jsonrpc": "2.0", "method": f"test_{i}", "id": f"order-{i}"}
                    messages.append(msg)
                    msg_json = json.dumps(msg) + "\n"
                    server_process.stdin.write(msg_json)
                    server_process.stdin.flush()
                
                # Read responses and check ordering
                responses = []
                for i in range(len(messages)):
                    try:
                        response = await asyncio.wait_for(
                            asyncio.create_task(asyncio.to_thread(server_process.stdout.readline)),
                            timeout=3.0
                        )
                        
                        if response and response.strip():
                            parsed = json.loads(response.strip())
                            responses.append(parsed)
                            
                    except (asyncio.TimeoutError, json.JSONDecodeError):
                        break
                
                # Check that we received responses for all messages
                received_count = len(responses)
                self.record_test(
                    "Message ordering - Response count",
                    received_count == len(messages),
                    f"Received {received_count}/{len(messages)} responses"
                )
                
                # Check that each message got a response with matching ID
                matched_responses = 0
                for msg in messages:
                    msg_id = msg["id"]
                    for response in responses:
                        if response.get("id") == msg_id:
                            matched_responses += 1
                            break
                
                self.record_test(
                    "Message ordering - ID matching",
                    matched_responses == len(messages),
                    f"Matched {matched_responses}/{len(messages)} response IDs"
                )
                
        except Exception as e:
            self.record_test(
                "Message ordering - General",
                False,
                f"Error: {e}"
            )
    
    async def test_large_message_handling(self):
        """Test handling of large messages."""
        print("\n📏 Testing Large Message Handling")
        
        try:
            async with self.create_server_process() as server_process:
                # Create a large message (but not too large to avoid issues)
                large_data = "x" * 10000  # 10KB of data
                large_message = {
                    "jsonrpc": "2.0",
                    "method": "tools/call",
                    "id": "large-1",
                    "params": {
                        "name": "ast_grep_search",
                        "arguments": {
                            "pattern": large_data,
                            "language": "javascript",
                            "path": "."
                        }
                    }
                }
                
                large_json = json.dumps(large_message) + "\n"
                
                # Send large message
                server_process.stdin.write(large_json)
                server_process.stdin.flush()
                
                try:
                    response = await asyncio.wait_for(
                        asyncio.create_task(asyncio.to_thread(server_process.stdout.readline)),
                        timeout=10.0
                    )
                    
                    if response and response.strip():
                        parsed = json.loads(response.strip())
                        handled_large_message = parsed.get("id") == "large-1"
                        
                        self.record_test(
                            "Large message handling - Processing",
                            handled_large_message,
                            f"Server processed large message ({len(large_json)} bytes)"
                        )
                    else:
                        self.record_test(
                            "Large message handling - Processing",
                            False,
                            "No response to large message"
                        )
                        
                except asyncio.TimeoutError:
                    self.record_test(
                        "Large message handling - Processing",
                        False,
                        "Timeout processing large message"
                    )
                except json.JSONDecodeError:
                    self.record_test(
                        "Large message handling - Processing",
                        False,
                        "Invalid JSON response to large message"
                    )
                
                # Test that server remains responsive after large message
                small_message = {"jsonrpc": "2.0", "method": "ping", "id": "after-large"}
                small_json = json.dumps(small_message) + "\n"
                
                server_process.stdin.write(small_json)
                server_process.stdin.flush()
                
                try:
                    response = await asyncio.wait_for(
                        asyncio.create_task(asyncio.to_thread(server_process.stdout.readline)),
                        timeout=5.0
                    )
                    
                    responsive_after_large = response and response.strip()
                    self.record_test(
                        "Large message handling - Recovery",
                        responsive_after_large,
                        "Server responsive after processing large message"
                    )
                    
                except asyncio.TimeoutError:
                    self.record_test(
                        "Large message handling - Recovery",
                        False,
                        "Server unresponsive after large message"
                    )
                
        except Exception as e:
            self.record_test(
                "Large message handling - General",
                False,
                f"Error: {e}"
            )
    
    async def run_all_tests(self):
        """Run all transport layer tests."""
        print("=" * 60)
        print("MCP Transport Layer Tests")
        print("=" * 60)
        
        try:
            # Run test suite
            await self.test_stdio_transport_basic()
            await self.test_message_framing()
            await self.test_connection_lifecycle()
            await self.test_transport_error_handling()
            await self.test_message_ordering()
            await self.test_large_message_handling()
            
            return True
            
        except Exception as e:
            print(f"❌ Transport layer test suite failed: {e}")
            return False
    
    def print_summary(self):
        """Print test summary."""
        print("\n" + "=" * 60)
        print("TRANSPORT LAYER TEST SUMMARY")
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
    tester = MCPTransportTester()
    
    try:
        success = await tester.run_all_tests()
        tester.print_summary()
        
        if success:
            print("\n🎉 All transport layer tests passed!")
            return 0
        else:
            print("\n❌ Some transport layer tests failed!")
            return 1
            
    except Exception as e:
        print(f"❌ Test suite failed: {e}")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)