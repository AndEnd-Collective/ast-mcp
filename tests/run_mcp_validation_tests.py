#!/usr/bin/env python3
"""Comprehensive MCP Validation Test Runner.

This script runs all MCP validation tests in a coordinated manner and provides
comprehensive reporting on MCP protocol compliance, performance, and reliability.
"""

import asyncio
import json
import sys
import os
import time
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional
from concurrent.futures import ThreadPoolExecutor
import statistics

# Add src to Python path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

try:
    from ast_grep_mcp.utils import find_ast_grep_binary
except ImportError as e:
    print(f"Import error: {e}")
    print("Please install dependencies: pip install -e .")
    sys.exit(1)


class MCPValidationTestRunner:
    """Comprehensive MCP validation test runner and reporter."""
    
    def __init__(self):
        self.test_modules = [
            ("Client-Server Integration", "test_mcp_client_integration"),
            ("Protocol Message Validation", "test_mcp_protocol_messages"),
            ("Schema Compliance", "test_mcp_schema_compliance"),
            ("Transport Layer", "test_mcp_transport"),
            ("Performance & Load", "test_mcp_performance"),
            ("Structured Output", "test_mcp_structured_output")
        ]
        
        self.results = {}
        self.overall_metrics = {}
        self.start_time = None
        self.end_time = None
        
    def print_header(self):
        """Print test suite header."""
        print("=" * 80)
        print("🧪 COMPREHENSIVE MCP VALIDATION TEST SUITE")
        print("=" * 80)
        print("Testing MCP Protocol Compliance, Performance, and Reliability")
        print("Based on MCP Python SDK patterns and best practices")
        print("=" * 80)
        print()
    
    async def check_prerequisites(self):
        """Check test prerequisites."""
        print("🔍 Checking Prerequisites...")
        
        prerequisites_met = True
        
        # Check Python version
        python_version = sys.version_info
        if python_version >= (3, 10):
            print(f"✅ Python version: {python_version.major}.{python_version.minor}.{python_version.micro}")
        else:
            print(f"❌ Python version: {python_version.major}.{python_version.minor}.{python_version.micro} (requires >= 3.10)")
            prerequisites_met = False
        
        # Check ast-grep availability
        try:
            ast_grep_path = await find_ast_grep_binary()
            if ast_grep_path:
                print(f"✅ ast-grep binary: {ast_grep_path}")
            else:
                print("⚠️  ast-grep binary: Not found (some tests may be limited)")
        except Exception as e:
            print(f"⚠️  ast-grep binary: Error checking ({e})")
        
        # Check required packages
        required_packages = [
            "mcp", "pydantic", "psutil", "jsonschema", "aiofiles"
        ]
        
        for package in required_packages:
            try:
                __import__(package)
                print(f"✅ Package {package}: Available")
            except ImportError:
                print(f"❌ Package {package}: Missing")
                prerequisites_met = False
        
        # Check test files exist
        test_dir = Path(__file__).parent
        missing_tests = []
        
        for test_name, test_module in self.test_modules:
            test_file = test_dir / f"{test_module}.py"
            if test_file.exists():
                print(f"✅ Test module {test_module}: Found")
            else:
                print(f"❌ Test module {test_module}: Missing")
                missing_tests.append(test_module)
                prerequisites_met = False
        
        if missing_tests:
            print(f"\nMissing test modules: {missing_tests}")
        
        print()
        return prerequisites_met
    
    async def run_test_module(self, test_name: str, test_module: str) -> Dict[str, Any]:
        """Run a single test module."""
        print(f"🧪 Running {test_name} Tests...")
        
        test_file = Path(__file__).parent / f"{test_module}.py"
        start_time = time.time()
        
        try:
            # Run test module as subprocess
            result = subprocess.run(
                [sys.executable, str(test_file)],
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout per test module
            )
            
            end_time = time.time()
            duration = end_time - start_time
            
            # Parse output for results
            output_lines = result.stdout.strip().split('\n') if result.stdout else []
            error_lines = result.stderr.strip().split('\n') if result.stderr else []
            
            # Count test results from output
            passed_tests = 0
            failed_tests = 0
            total_tests = 0
            
            for line in output_lines:
                if "✅ PASS" in line:
                    passed_tests += 1
                    total_tests += 1
                elif "❌ FAIL" in line:
                    failed_tests += 1
                    total_tests += 1
            
            # Determine overall success
            success = result.returncode == 0 and failed_tests == 0
            
            test_result = {
                "name": test_name,
                "module": test_module,
                "success": success,
                "duration": duration,
                "return_code": result.returncode,
                "total_tests": total_tests,
                "passed_tests": passed_tests,
                "failed_tests": failed_tests,
                "success_rate": (passed_tests / total_tests * 100) if total_tests > 0 else 0,
                "output": result.stdout,
                "errors": result.stderr
            }
            
            # Print summary
            if success:
                print(f"✅ {test_name}: PASSED ({total_tests} tests, {duration:.1f}s)")
            else:
                print(f"❌ {test_name}: FAILED ({passed_tests}/{total_tests} passed, {duration:.1f}s)")
                if result.stderr:
                    print(f"   Error: {result.stderr.split(chr(10))[0]}")  # First line of error
            
            return test_result
            
        except subprocess.TimeoutExpired:
            end_time = time.time()
            duration = end_time - start_time
            
            print(f"⏰ {test_name}: TIMEOUT ({duration:.1f}s)")
            
            return {
                "name": test_name,
                "module": test_module,
                "success": False,
                "duration": duration,
                "return_code": -1,
                "total_tests": 0,
                "passed_tests": 0,
                "failed_tests": 0,
                "success_rate": 0,
                "output": "",
                "errors": "Test timed out"
            }
            
        except Exception as e:
            end_time = time.time()
            duration = end_time - start_time
            
            print(f"💥 {test_name}: ERROR ({e})")
            
            return {
                "name": test_name,
                "module": test_module,
                "success": False,
                "duration": duration,
                "return_code": -2,
                "total_tests": 0,
                "passed_tests": 0,
                "failed_tests": 0,
                "success_rate": 0,
                "output": "",
                "errors": str(e)
            }
    
    async def run_all_tests(self, parallel: bool = False):
        """Run all test modules."""
        print("🚀 Starting MCP Validation Test Suite...")
        print()
        
        self.start_time = time.time()
        
        if parallel:
            print("Running tests in parallel...")
            tasks = []
            for test_name, test_module in self.test_modules:
                task = asyncio.create_task(self.run_test_module(test_name, test_module))
                tasks.append(task)
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    test_name, test_module = self.test_modules[i]
                    result = {
                        "name": test_name,
                        "module": test_module,
                        "success": False,
                        "duration": 0,
                        "return_code": -3,
                        "total_tests": 0,
                        "passed_tests": 0,
                        "failed_tests": 0,
                        "success_rate": 0,
                        "output": "",
                        "errors": str(result)
                    }
                
                self.results[result["module"]] = result
        else:
            print("Running tests sequentially...")
            for test_name, test_module in self.test_modules:
                result = await self.run_test_module(test_name, test_module)
                self.results[test_module] = result
                print()  # Space between tests
        
        self.end_time = time.time()
    
    def calculate_overall_metrics(self):
        """Calculate overall metrics across all tests."""
        if not self.results:
            return
        
        total_duration = self.end_time - self.start_time if self.start_time and self.end_time else 0
        
        # Test module metrics
        total_modules = len(self.results)
        successful_modules = sum(1 for result in self.results.values() if result["success"])
        failed_modules = total_modules - successful_modules
        
        # Individual test metrics
        total_tests = sum(result["total_tests"] for result in self.results.values())
        total_passed = sum(result["passed_tests"] for result in self.results.values())
        total_failed = sum(result["failed_tests"] for result in self.results.values())
        
        # Duration metrics
        durations = [result["duration"] for result in self.results.values()]
        avg_duration = statistics.mean(durations) if durations else 0
        max_duration = max(durations) if durations else 0
        min_duration = min(durations) if durations else 0
        
        # Success rates
        success_rates = [result["success_rate"] for result in self.results.values() if result["total_tests"] > 0]
        avg_success_rate = statistics.mean(success_rates) if success_rates else 0
        
        self.overall_metrics = {
            "total_duration": total_duration,
            "modules": {
                "total": total_modules,
                "successful": successful_modules,
                "failed": failed_modules,
                "success_rate": (successful_modules / total_modules * 100) if total_modules > 0 else 0
            },
            "tests": {
                "total": total_tests,
                "passed": total_passed,
                "failed": total_failed,
                "success_rate": (total_passed / total_tests * 100) if total_tests > 0 else 0
            },
            "performance": {
                "avg_duration": avg_duration,
                "max_duration": max_duration,
                "min_duration": min_duration,
                "avg_success_rate": avg_success_rate
            }
        }
    
    def print_detailed_results(self):
        """Print detailed test results."""
        print("=" * 80)
        print("📊 DETAILED TEST RESULTS")
        print("=" * 80)
        
        for module, result in self.results.items():
            print(f"\n🧪 {result['name']}")
            print(f"   Module: {result['module']}")
            print(f"   Status: {'✅ PASSED' if result['success'] else '❌ FAILED'}")
            print(f"   Duration: {result['duration']:.2f}s")
            print(f"   Tests: {result['passed_tests']}/{result['total_tests']} passed ({result['success_rate']:.1f}%)")
            
            if not result['success']:
                print(f"   Return Code: {result['return_code']}")
                if result['errors']:
                    error_lines = result['errors'].split('\n')[:3]  # First 3 lines
                    for line in error_lines:
                        if line.strip():
                            print(f"   Error: {line.strip()}")
    
    def print_summary(self):
        """Print test summary."""
        print("\n" + "=" * 80)
        print("📈 COMPREHENSIVE TEST SUMMARY")
        print("=" * 80)
        
        metrics = self.overall_metrics
        
        print(f"Total Duration: {metrics['total_duration']:.2f}s")
        print()
        
        print("Module Results:")
        print(f"  Total Modules: {metrics['modules']['total']}")
        print(f"  Successful: {metrics['modules']['successful']}")
        print(f"  Failed: {metrics['modules']['failed']}")
        print(f"  Module Success Rate: {metrics['modules']['success_rate']:.1f}%")
        print()
        
        print("Individual Test Results:")
        print(f"  Total Tests: {metrics['tests']['total']}")
        print(f"  Passed: {metrics['tests']['passed']}")
        print(f"  Failed: {metrics['tests']['failed']}")
        print(f"  Test Success Rate: {metrics['tests']['success_rate']:.1f}%")
        print()
        
        print("Performance Metrics:")
        print(f"  Average Module Duration: {metrics['performance']['avg_duration']:.2f}s")
        print(f"  Fastest Module: {metrics['performance']['min_duration']:.2f}s")
        print(f"  Slowest Module: {metrics['performance']['max_duration']:.2f}s")
        print(f"  Average Success Rate: {metrics['performance']['avg_success_rate']:.1f}%")
        print()
        
        # Overall assessment
        overall_success = (
            metrics['modules']['success_rate'] >= 90 and
            metrics['tests']['success_rate'] >= 95
        )
        
        if overall_success:
            print("🎉 OVERALL ASSESSMENT: EXCELLENT")
            print("   MCP server demonstrates strong protocol compliance and reliability")
        elif metrics['tests']['success_rate'] >= 80:
            print("✅ OVERALL ASSESSMENT: GOOD")
            print("   MCP server is functional with some areas for improvement")
        elif metrics['tests']['success_rate'] >= 60:
            print("⚠️  OVERALL ASSESSMENT: NEEDS IMPROVEMENT")
            print("   MCP server has significant issues that should be addressed")
        else:
            print("❌ OVERALL ASSESSMENT: POOR")
            print("   MCP server has critical issues preventing proper operation")
        
        return overall_success
    
    def save_results_json(self, filename: str = "mcp_validation_results.json"):
        """Save results to JSON file."""
        try:
            output_data = {
                "timestamp": time.time(),
                "overall_metrics": self.overall_metrics,
                "test_results": self.results,
                "summary": {
                    "total_duration": self.overall_metrics["total_duration"],
                    "modules_passed": self.overall_metrics["modules"]["successful"],
                    "modules_total": self.overall_metrics["modules"]["total"],
                    "tests_passed": self.overall_metrics["tests"]["passed"],
                    "tests_total": self.overall_metrics["tests"]["total"],
                    "overall_success_rate": self.overall_metrics["tests"]["success_rate"]
                }
            }
            
            output_path = Path(__file__).parent / filename
            with open(output_path, 'w') as f:
                json.dump(output_data, f, indent=2)
            
            print(f"📁 Results saved to: {output_path}")
            return True
            
        except Exception as e:
            print(f"❌ Failed to save results: {e}")
            return False
    
    def print_recommendations(self):
        """Print recommendations based on test results."""
        print("\n" + "=" * 80)
        print("💡 RECOMMENDATIONS")
        print("=" * 80)
        
        failed_modules = [
            result for result in self.results.values() 
            if not result["success"]
        ]
        
        if not failed_modules:
            print("🎯 All test modules passed! Your MCP server demonstrates excellent compliance.")
            print("   Continue monitoring performance under production loads.")
            return
        
        print("Based on test results, consider the following improvements:")
        print()
        
        for result in failed_modules:
            print(f"📌 {result['name']} Module:")
            
            if "integration" in result["module"]:
                print("   - Check server initialization and communication protocols")
                print("   - Verify JSON-RPC message handling")
                print("   - Test with different MCP clients")
            
            elif "protocol" in result["module"]:
                print("   - Review JSON-RPC 2.0 compliance")
                print("   - Validate message format handling")
                print("   - Check error response formats")
            
            elif "schema" in result["module"]:
                print("   - Ensure Pydantic models follow MCP patterns")
                print("   - Validate JSON schema generation")
                print("   - Check type annotation completeness")
            
            elif "transport" in result["module"]:
                print("   - Test stdio transport reliability")
                print("   - Check message framing and parsing")
                print("   - Improve error handling in transport layer")
            
            elif "performance" in result["module"]:
                print("   - Optimize concurrent request handling")
                print("   - Monitor memory usage patterns")
                print("   - Implement proper rate limiting")
            
            elif "structured" in result["module"]:
                print("   - Enhance Pydantic model validation")
                print("   - Improve structured output compliance")
                print("   - Add proper type annotations")
            
            print()


async def main():
    """Main test runner function."""
    runner = MCPValidationTestRunner()
    
    # Print header
    runner.print_header()
    
    # Check prerequisites
    if not await runner.check_prerequisites():
        print("❌ Prerequisites not met. Please install required dependencies.")
        return 1
    
    # Parse command line arguments
    parallel = "--parallel" in sys.argv
    save_json = "--save-json" in sys.argv
    verbose = "--verbose" in sys.argv
    
    try:
        # Run all tests
        await runner.run_all_tests(parallel=parallel)
        
        # Calculate metrics
        runner.calculate_overall_metrics()
        
        # Print results
        if verbose:
            runner.print_detailed_results()
        
        runner.print_summary()
        
        # Save results if requested
        if save_json:
            runner.save_results_json()
        
        # Print recommendations
        runner.print_recommendations()
        
        # Return exit code based on overall success
        overall_success = runner.overall_metrics["tests"]["success_rate"] >= 95
        return 0 if overall_success else 1
        
    except KeyboardInterrupt:
        print("\n⏹️  Test run interrupted by user")
        return 1
    except Exception as e:
        print(f"\n💥 Test runner failed: {e}")
        return 1


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in ["--help", "-h"]:
        print("MCP Validation Test Runner")
        print()
        print("Usage: python run_mcp_validation_tests.py [options]")
        print()
        print("Options:")
        print("  --parallel    Run test modules in parallel")
        print("  --save-json   Save results to JSON file")
        print("  --verbose     Show detailed results")
        print("  --help, -h    Show this help message")
        sys.exit(0)
    
    exit_code = asyncio.run(main())
    sys.exit(exit_code)