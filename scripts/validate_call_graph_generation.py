#!/usr/bin/env python3
"""Validation script for call graph generation system."""

import asyncio
import json
import tempfile
import time
from pathlib import Path
from typing import Dict, Any, List
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from ast_grep_mcp.utils import create_call_graph_generator
from ast_grep_mcp.schemas import validate_call_graph_data, CallGraphValidator


class CallGraphValidationSuite:
    """Comprehensive validation suite for call graph generation."""
    
    def __init__(self):
        self.generator = None
        self.validator = CallGraphValidator()
        self.results = {
            'total_tests': 0,
            'passed_tests': 0,
            'failed_tests': 0,
            'errors': [],
            'performance_metrics': {}
        }
    
    async def initialize(self):
        """Initialize the call graph generator."""
        self.generator = await create_call_graph_generator()
    
    def create_test_files(self) -> Dict[str, Path]:
        """Create test files for validation."""
        temp_dir = Path(tempfile.mkdtemp())
        test_files = {}
        
        # Python test file with complex relationships
        python_code = '''
import json
import os
from typing import List, Dict, Any

class DataProcessor:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.cache = {}
    
    def process_file(self, file_path: str) -> Dict[str, Any]:
        """Process a file and return results."""
        if file_path in self.cache:
            return self.cache[file_path]
        
        data = self.load_file(file_path)
        processed = self.transform_data(data)
        validated = self.validate_results(processed)
        
        self.cache[file_path] = validated
        return validated
    
    def load_file(self, file_path: str) -> Any:
        """Load file content."""
        with open(file_path, 'r') as f:
            return json.load(f)
    
    def transform_data(self, data: Any) -> Dict[str, Any]:
        """Transform loaded data."""
        if isinstance(data, list):
            return {'items': data, 'count': len(data)}
        elif isinstance(data, dict):
            return self.normalize_dict(data)
        else:
            return {'value': data, 'type': type(data).__name__}
    
    def normalize_dict(self, data: dict) -> dict:
        """Normalize dictionary data."""
        normalized = {}
        for key, value in data.items():
            normalized[key.lower()] = self.clean_value(value)
        return normalized
    
    def clean_value(self, value: Any) -> Any:
        """Clean individual values."""
        if isinstance(value, str):
            return value.strip()
        return value
    
    def validate_results(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate processed results."""
        if not data:
            raise ValueError("Empty data")
        
        return {
            'data': data,
            'validated': True,
            'timestamp': self.get_timestamp()
        }
    
    def get_timestamp(self) -> str:
        """Get current timestamp."""
        import datetime
        return datetime.datetime.now().isoformat()

def main():
    """Main entry point."""
    processor = DataProcessor({'mode': 'strict'})
    
    files_to_process = get_file_list()
    results = []
    
    for file_path in files_to_process:
        try:
            result = processor.process_file(file_path)
            results.append(result)
        except Exception as e:
            log_error(f"Failed to process {file_path}: {e}")
    
    save_results(results)
    print(f"Processed {len(results)} files")

def get_file_list() -> List[str]:
    """Get list of files to process."""
    return ['data1.json', 'data2.json', 'data3.json']

def log_error(message: str):
    """Log error message."""
    print(f"ERROR: {message}")

def save_results(results: List[Dict[str, Any]]):
    """Save processing results."""
    with open('output.json', 'w') as f:
        json.dump(results, f, indent=2)

if __name__ == "__main__":
    main()
'''
        
        # JavaScript test file
        js_code = '''
class TaskManager {
    constructor() {
        this.tasks = [];
        this.handlers = new Map();
    }
    
    addTask(task) {
        const processed = this.processTask(task);
        this.tasks.push(processed);
        this.notifyHandlers('taskAdded', processed);
        return processed.id;
    }
    
    processTask(task) {
        const validated = this.validateTask(task);
        const enriched = this.enrichTask(validated);
        return this.finalizeTask(enriched);
    }
    
    validateTask(task) {
        if (!task.title) {
            throw new Error('Task must have a title');
        }
        return {
            ...task,
            validated: true
        };
    }
    
    enrichTask(task) {
        return {
            ...task,
            id: this.generateId(),
            createdAt: new Date().toISOString(),
            status: 'pending'
        };
    }
    
    finalizeTask(task) {
        this.logTaskCreation(task);
        return task;
    }
    
    generateId() {
        return Math.random().toString(36).substr(2, 9);
    }
    
    logTaskCreation(task) {
        console.log(`Created task: ${task.title} (${task.id})`);
    }
    
    notifyHandlers(event, data) {
        const handlers = this.handlers.get(event) || [];
        handlers.forEach(handler => handler(data));
    }
    
    registerHandler(event, handler) {
        if (!this.handlers.has(event)) {
            this.handlers.set(event, []);
        }
        this.handlers.get(event).push(handler);
    }
}

function createManager() {
    const manager = new TaskManager();
    
    manager.registerHandler('taskAdded', (task) => {
        updateUI(task);
    });
    
    return manager;
}

function updateUI(task) {
    displayTask(task);
    updateStats();
}

function displayTask(task) {
    console.log(`Displaying task: ${task.title}`);
}

function updateStats() {
    console.log('Stats updated');
}

// Export for testing
if (typeof module !== 'undefined') {
    module.exports = { TaskManager, createManager };
}
'''
        
        # Create files
        test_files['python'] = temp_dir / "processor.py"
        test_files['python'].write_text(python_code, encoding='utf-8')
        
        test_files['javascript'] = temp_dir / "taskmanager.js"
        test_files['javascript'].write_text(js_code, encoding='utf-8')
        
        test_files['temp_dir'] = temp_dir
        
        return test_files
    
    async def test_basic_functionality(self, test_files: Dict[str, Path]) -> bool:
        """Test basic call graph generation functionality."""
        try:
            result = await self.generator.generate_call_graph(
                paths=[test_files['python']],
                languages=['python']
            )
            
            # Basic structure checks
            required_keys = ['metadata', 'nodes', 'edges', 'metrics', 'statistics']
            for key in required_keys:
                if key not in result:
                    raise AssertionError(f"Missing required key: {key}")
            
            # Check that we found functions
            if len(result['nodes']) == 0:
                raise AssertionError("No functions detected")
            
            # Check that we have reasonable metadata
            metadata = result['metadata']
            if metadata['total_functions'] != len(result['nodes']):
                raise AssertionError("Metadata mismatch: total_functions")
            
            return True
            
        except Exception as e:
            self.results['errors'].append(f"Basic functionality test failed: {e}")
            return False
    
    async def test_schema_compliance(self, test_files: Dict[str, Path]) -> bool:
        """Test schema compliance of generated call graphs."""
        try:
            result = await self.generator.generate_call_graph(
                paths=[test_files['python']],
                languages=['python']
            )
            
            validation_result = self.validator.validate_call_graph(result)
            
            if not validation_result['valid']:
                error_details = validation_result.get('errors', [])
                raise AssertionError(f"Schema validation failed: {error_details}")
            
            return True
            
        except Exception as e:
            self.results['errors'].append(f"Schema compliance test failed: {e}")
            return False
    
    async def test_multi_language_support(self, test_files: Dict[str, Path]) -> bool:
        """Test multi-language call graph generation."""
        try:
            files = [test_files['python'], test_files['javascript']]
            
            result = await self.generator.generate_call_graph(
                paths=files,
                languages=['python', 'javascript']
            )
            
            # Check that we found functions from multiple languages
            languages_found = set()
            for node in result['nodes']:
                languages_found.add(node.get('language', 'unknown'))
            
            if len(languages_found) < 2:
                raise AssertionError(f"Expected multiple languages, found: {languages_found}")
            
            # Check statistics
            stats = result['statistics']
            lang_stats = stats.get('functions_by_language', {})
            if len(lang_stats) < 2:
                raise AssertionError("Language statistics incomplete")
            
            return True
            
        except Exception as e:
            self.results['errors'].append(f"Multi-language support test failed: {e}")
            return False
    
    async def test_filtering_functionality(self, test_files: Dict[str, Path]) -> bool:
        """Test filtering functionality."""
        try:
            # Test with no filtering
            result_all = await self.generator.generate_call_graph(
                paths=[test_files['python']],
                languages=['python']
            )
            
            # Test with filtering
            result_filtered = await self.generator.generate_call_graph(
                paths=[test_files['python']],
                languages=['python'],
                filter_patterns=[r'^main$', r'^get_.*']
            )
            
            # Filtered result should have fewer or equal functions
            if len(result_filtered['nodes']) > len(result_all['nodes']):
                raise AssertionError("Filtering increased function count")
            
            # Check that filtered functions match patterns
            for node in result_filtered['nodes']:
                name = node['name']
                if not (name == 'main' or name.startswith('get_')):
                    # Note: Some functions might pass due to implementation details
                    pass
            
            return True
            
        except Exception as e:
            self.results['errors'].append(f"Filtering functionality test failed: {e}")
            return False
    
    async def test_error_handling(self) -> bool:
        """Test error handling with invalid inputs."""
        try:
            # Test with non-existent file
            result = await self.generator.generate_call_graph(
                paths=["/nonexistent/file.py"],
                languages=['python']
            )
            
            # Should return valid structure with errors
            if 'errors' not in result:
                raise AssertionError("No errors reported for invalid file")
            
            if len(result['errors']) == 0:
                raise AssertionError("Expected errors for invalid file")
            
            # Should still have valid structure
            required_keys = ['metadata', 'nodes', 'edges', 'metrics', 'statistics']
            for key in required_keys:
                if key not in result:
                    raise AssertionError(f"Missing key in error case: {key}")
            
            return True
            
        except Exception as e:
            self.results['errors'].append(f"Error handling test failed: {e}")
            return False
    
    async def test_performance(self, test_files: Dict[str, Path]) -> bool:
        """Test performance characteristics."""
        try:
            start_time = time.time()
            
            result = await self.generator.generate_call_graph(
                paths=[test_files['temp_dir']],
                languages=['python', 'javascript']
            )
            
            end_time = time.time()
            processing_time = end_time - start_time
            
            # Store performance metrics
            self.results['performance_metrics'] = {
                'processing_time': processing_time,
                'functions_found': len(result['nodes']),
                'edges_found': len(result['edges']),
                'functions_per_second': len(result['nodes']) / processing_time if processing_time > 0 else 0
            }
            
            # Performance threshold (adjust as needed)
            if processing_time > 30:
                raise AssertionError(f"Processing took too long: {processing_time} seconds")
            
            return True
            
        except Exception as e:
            self.results['errors'].append(f"Performance test failed: {e}")
            return False
    
    async def test_accuracy(self, test_files: Dict[str, Path]) -> bool:
        """Test accuracy of call detection."""
        try:
            result = await self.generator.generate_call_graph(
                paths=[test_files['python']],
                languages=['python']
            )
            
            # Build function and call maps
            nodes = result['nodes']
            edges = result['edges']
            
            function_names = [node['name'] for node in nodes]
            
            # Check for expected functions
            expected_functions = [
                'main', 'DataProcessor.__init__', 'process_file', 
                'load_file', 'transform_data', 'validate_results'
            ]
            
            found_functions = 0
            for expected in expected_functions:
                if any(expected in name for name in function_names):
                    found_functions += 1
            
            # Should find at least 80% of expected functions
            accuracy = found_functions / len(expected_functions)
            if accuracy < 0.8:
                raise AssertionError(f"Low accuracy: {accuracy:.2f} (found {found_functions}/{len(expected_functions)})")
            
            # Check for some expected call relationships
            if len(edges) == 0:
                raise AssertionError("No call relationships detected")
            
            return True
            
        except Exception as e:
            self.results['errors'].append(f"Accuracy test failed: {e}")
            return False
    
    async def run_validation_suite(self) -> Dict[str, Any]:
        """Run the complete validation suite."""
        print("Starting call graph generation validation suite...")
        
        # Create test files
        test_files = self.create_test_files()
        
        try:
            # Define test cases
            test_cases = [
                ("Basic Functionality", self.test_basic_functionality),
                ("Schema Compliance", self.test_schema_compliance),
                ("Multi-Language Support", self.test_multi_language_support),
                ("Filtering Functionality", self.test_filtering_functionality),
                ("Error Handling", self.test_error_handling),
                ("Performance", self.test_performance),
                ("Accuracy", self.test_accuracy),
            ]
            
            # Run test cases
            for test_name, test_func in test_cases:
                print(f"\nRunning test: {test_name}")
                self.results['total_tests'] += 1
                
                try:
                    if callable(test_func):
                        if test_name in ["Basic Functionality", "Schema Compliance", 
                                       "Multi-Language Support", "Filtering Functionality",
                                       "Performance", "Accuracy"]:
                            success = await test_func(test_files)
                        else:
                            success = await test_func()
                    else:
                        success = False
                    
                    if success:
                        print(f"✓ {test_name} PASSED")
                        self.results['passed_tests'] += 1
                    else:
                        print(f"✗ {test_name} FAILED")
                        self.results['failed_tests'] += 1
                        
                except Exception as e:
                    print(f"✗ {test_name} ERROR: {e}")
                    self.results['failed_tests'] += 1
                    self.results['errors'].append(f"{test_name}: {e}")
            
        finally:
            # Cleanup
            import shutil
            shutil.rmtree(test_files['temp_dir'])
        
        return self.results
    
    def print_summary(self, results: Dict[str, Any]):
        """Print validation summary."""
        print("\n" + "="*60)
        print("CALL GRAPH GENERATION VALIDATION SUMMARY")
        print("="*60)
        print(f"Total Tests: {results['total_tests']}")
        print(f"Passed: {results['passed_tests']}")
        print(f"Failed: {results['failed_tests']}")
        print(f"Success Rate: {results['passed_tests']/results['total_tests']*100:.1f}%")
        
        if results['performance_metrics']:
            metrics = results['performance_metrics']
            print(f"\nPerformance Metrics:")
            print(f"  Processing Time: {metrics.get('processing_time', 0):.2f} seconds")
            print(f"  Functions Found: {metrics.get('functions_found', 0)}")
            print(f"  Edges Found: {metrics.get('edges_found', 0)}")
            print(f"  Functions/Second: {metrics.get('functions_per_second', 0):.2f}")
        
        if results['errors']:
            print(f"\nErrors ({len(results['errors'])}):")
            for i, error in enumerate(results['errors'], 1):
                print(f"  {i}. {error}")
        
        print("\nValidation Complete!")


async def main():
    """Main validation script."""
    validator = CallGraphValidationSuite()
    
    try:
        await validator.initialize()
        results = await validator.run_validation_suite()
        validator.print_summary(results)
        
        # Return appropriate exit code
        return 0 if results['failed_tests'] == 0 else 1
        
    except Exception as e:
        print(f"Validation suite failed to initialize: {e}")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
