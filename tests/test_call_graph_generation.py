"""Tests for CallGraphGenerator and call graph generation functionality."""

import pytest
import tempfile
import json
from pathlib import Path
from typing import Dict, Any, List

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from ast_grep_mcp.utils import (
    CallGraphGenerator, 
    create_call_graph_generator,
    create_ast_grep_executor
)
from ast_grep_mcp.schemas import validate_call_graph_data, CallGraphValidator


class TestCallGraphGenerator:
    """Test suite for CallGraphGenerator functionality."""

    @pytest.fixture
    async def generator(self):
        """Create a CallGraphGenerator instance for testing."""
        executor = await create_ast_grep_executor()
        generator = await create_call_graph_generator(executor=executor)
        return generator

    @pytest.fixture
    def temp_code_files(self):
        """Create temporary code files for testing."""
        temp_dir = tempfile.mkdtemp()
        test_files = {}
        
        # Python test file with function definitions and calls
        python_code = '''
def main():
    """Main entry point."""
    result = process_data("test")
    helper_function(result)
    return result

def process_data(data):
    """Process input data."""
    if validate_input(data):
        return transform_data(data)
    return None

def validate_input(data):
    """Validate input data."""
    return data is not None and len(data) > 0

def transform_data(data):
    """Transform data."""
    return data.upper()

def helper_function(data):
    """Helper function."""
    log_message(f"Processing: {data}")

def log_message(message):
    """Log a message."""
    print(message)
'''

        # Create test files
        test_files['python'] = Path(temp_dir) / "test.py"
        test_files['python'].write_text(python_code, encoding='utf-8')
        
        test_files['temp_dir'] = Path(temp_dir)
        
        yield test_files
        
        # Cleanup
        import shutil
        shutil.rmtree(temp_dir)

    @pytest.mark.asyncio
    async def test_basic_call_graph_generation(self, generator, temp_code_files):
        """Test basic call graph generation functionality."""
        python_file = temp_code_files['python']
        
        result = await generator.generate_call_graph(
            paths=[python_file],
            languages=['python']
        )
        
        # Basic structure validation
        assert isinstance(result, dict)
        assert 'metadata' in result
        assert 'nodes' in result
        assert 'edges' in result
        assert 'metrics' in result
        assert 'statistics' in result
        
        # Verify nodes contain function information
        nodes = result['nodes']
        assert len(nodes) > 0
        
        # Check for expected functions
        function_names = [node['name'] for node in nodes]
        expected_functions = ['main', 'process_data', 'validate_input', 'transform_data']
        for expected in expected_functions:
            assert expected in function_names, f"Expected function '{expected}' not found in {function_names}"

    @pytest.mark.asyncio
    async def test_schema_validation_integration(self, generator, temp_code_files):
        """Test that generated call graphs pass schema validation."""
        python_file = temp_code_files['python']
        
        result = await generator.generate_call_graph(
            paths=[python_file],
            languages=['python']
        )
        
        # Validate the generated call graph
        validation_result = validate_call_graph_data(result)
        
        # Should pass validation
        assert validation_result['valid'], f"Generated call graph failed schema validation: {validation_result}"

    def test_schema_compliance(self, temp_code_files):
        """Test that generated call graphs comply with JSON schema."""
        validator = CallGraphValidator()
        
        # Test with minimal valid call graph
        minimal_graph = {
            'metadata': {
                'generation_time': '2024-01-01T00:00:00Z',
                'total_functions': 1,
                'total_calls': 0,
                'filtered_functions': 1,
                'filtered_calls': 0,
                'total_edges': 0
            },
            'nodes': [
                {
                    'id': 'test::main::1',
                    'type': 'function',
                    'name': 'main',
                    'language': 'python'
                }
            ],
            'edges': [],
            'metrics': {
                'total_nodes': 1,
                'total_edges': 0,
                'average_out_degree': 0.0,
                'average_in_degree': 0.0,
                'max_out_degree': 0,
                'max_in_degree': 0,
                'isolated_nodes': 1
            },
            'statistics': {
                'functions_by_language': {'python': 1},
                'calls_by_type': {},
                'complexity_distribution': {
                    'min': 1,
                    'max': 1,
                    'mean': 1.0,
                    'median': 1.0,
                    'high_complexity_count': 0,
                    'distribution': {
                        'low_complexity': 1,
                        'medium_complexity': 0,
                        'high_complexity': 0
                    }
                },
                'file_dependencies': {
                    'total_cross_file_calls': 0,
                    'files_with_dependencies': 0,
                    'dependency_matrix': {}
                }
            },
            'errors': []
        }
        
        result = validator.validate_call_graph(minimal_graph)
        assert result['valid'], f"Schema validation failed: {result}"


@pytest.mark.asyncio
async def test_create_call_graph_generator():
    """Test the factory function for creating CallGraphGenerator instances."""
    generator = await create_call_graph_generator()
    
    assert isinstance(generator, CallGraphGenerator)
    assert generator.executor is not None
    assert generator.function_detector is not None
    assert generator.call_detector is not None


if __name__ == "__main__":
    # Run basic tests if executed directly
    import asyncio
    
    async def run_basic_test():
        """Run a basic test to verify functionality."""
        generator = await create_call_graph_generator()
        
        # Create a simple test file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write('''
def main():
    result = helper()
    return result

def helper():
    return "test"
''')
            temp_file = f.name
        
        try:
            result = await generator.generate_call_graph(
                paths=[temp_file],
                languages=['python']
            )
            
            print("Call graph generated successfully!")
            print(f"Found {len(result['nodes'])} functions and {len(result['edges'])} call relationships")
            
            # Validate schema
            validation_result = validate_call_graph_data(result)
            print(f"Schema validation: {'PASSED' if validation_result['valid'] else 'FAILED'}")
            
        finally:
            os.unlink(temp_file)
    
    asyncio.run(run_basic_test())
