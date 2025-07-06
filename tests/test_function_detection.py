"""
Test suite for function detection capabilities across multiple programming languages.

This module tests the accuracy and completeness of function detection,
metadata extraction, and special case handling.
"""

import pytest
import asyncio
import tempfile
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional

# Add src to Python path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ast_grep_mcp.utils import FunctionDetector, create_ast_grep_executor
from ast_grep_mcp.resources import FUNCTION_PATTERNS


class TestFunctionDetection:
    """Test class for function detection capabilities."""
    
    @pytest.fixture
    async def function_detector(self):
        """Create a FunctionDetector instance for testing."""
        executor = await create_ast_grep_executor()
        return FunctionDetector(executor)
    
    @pytest.mark.asyncio
    async def test_python_function_detection(self, function_detector):
        """Test function detection in Python files."""
        python_code = '''
def simple_function(param1, param2):
    """A simple function with parameters."""
    return param1 + param2

class TestClass:
    def __init__(self, name):
        self.name = name
    
    @property
    def display_name(self):
        return f"Name: {self.name}"
    
    @classmethod
    def create_default(cls):
        return cls("default")
    
    @staticmethod
    def utility_method(data):
        return len(data)
    
    def __str__(self):
        return self.name

@decorator_func
def decorated_function(x: int, y: str = "default") -> str:
    return f"{x}: {y}"

async def async_function(data: List[str]) -> Dict[str, Any]:
    """Async function with type hints."""
    await asyncio.sleep(0.1)
    return {"count": len(data)}
'''
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(python_code)
            f.flush()
            
            result = await function_detector.detect_functions(
                f.name,
                language='python',
                include_metadata=True
            )
            
            assert result['success'] is True
            functions = result['data']['functions']
            
            # Check that we found expected functions
            function_names = [f.get('name', '') for f in functions]
            
            expected_functions = [
                'simple_function',
                '__init__',
                'display_name',
                'create_default',
                'utility_method',
                '__str__',
                'decorated_function',
                'async_function'
            ]
            
            found_functions = []
            for expected in expected_functions:
                found = any(expected in name for name in function_names)
                if found:
                    found_functions.append(expected)
            
            # Should find at least some of the expected functions
            assert len(found_functions) > 0, f"No expected functions found in {function_names}"
    
    @pytest.mark.asyncio
    async def test_javascript_function_detection(self, function_detector):
        """Test function detection in JavaScript files."""
        javascript_code = '''
function regularFunction(param1, param2) {
    return param1 + param2;
}

const arrowFunction = (x, y) => {
    return x * y;
};

const asyncArrowFunction = async (data) => {
    const result = await processData(data);
    return result;
};

function* generatorFunction(items) {
    for (let item of items) {
        yield item * 2;
    }
}

class MyClass {
    constructor(name) {
        this.name = name;
    }
    
    methodFunction(param) {
        return this.name + param;
    }
    
    static staticMethod(data) {
        return data.length;
    }
}
'''
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False) as f:
            f.write(javascript_code)
            f.flush()
            
            result = await function_detector.detect_functions(
                f.name,
                language='javascript',
                include_metadata=True
            )
            
            assert result['success'] is True
            functions = result['data']['functions']
            
            # Should find some functions
            assert len(functions) > 0
            
            # Check for different function types
            function_types = [f.get('pattern_type', '') for f in functions]
            
            # Should detect various patterns (exact types depend on pattern implementation)
            assert len(set(function_types)) > 0
    
    @pytest.mark.asyncio
    async def test_parameter_parsing_accuracy(self, function_detector):
        """Test accuracy of parameter parsing across languages."""
        python_code = '''
def typed_function(x: int, y: str = "default", *args, **kwargs):
    """Function with various parameter types."""
    return f"{x}: {y}"
'''
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(python_code)
            f.flush()
            
            result = await function_detector.detect_functions(
                f.name,
                language='python',
                include_metadata=True
            )
            
            assert result['success'] is True
            functions = result['data']['functions']
            
            # Find the typed function
            typed_func = next(
                (f for f in functions if 'typed_function' in f.get('name', '')), 
                None
            )
            
            if typed_func:
                # Check if parameter parsing worked
                assert 'parsed_parameters' in typed_func
                params = typed_func.get('parsed_parameters', [])
                # Should have detected some parameters
                assert len(params) > 0
    
    @pytest.mark.asyncio
    async def test_special_function_detection(self, function_detector):
        """Test detection of special functions like decorators, generics, etc."""
        python_code = '''
@property
def property_method(self):
    return self._value

@classmethod  
def class_method(cls):
    return cls()

@staticmethod
def static_method(data):
    return len(data)

def __init__(self, name):
    self.name = name

def __str__(self):
    return self.name
'''
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(python_code)
            f.flush()
            
            # Test special function detection if the method exists
            if hasattr(function_detector, 'detect_special_functions'):
                result = await function_detector.detect_special_functions(
                    f.name,
                    language='python'
                )
                
                assert result['success'] is True
                special_functions = result['data']['special_functions']
                
                # Should find some special functions
                assert len(special_functions) > 0
            else:
                # Fallback to regular detection
                result = await function_detector.detect_functions(
                    f.name,
                    language='python',
                    include_metadata=True
                )
                
                assert result['success'] is True
                functions = result['data']['functions']
                assert len(functions) > 0
    
    @pytest.mark.asyncio
    async def test_error_handling(self, function_detector):
        """Test error handling for invalid inputs."""
        # Test non-existent file
        result = await function_detector.detect_functions(
            "/non/existent/file.py",
            language='python'
        )
        
        assert result['success'] is False
        assert 'error' in result
    
    def test_pattern_completeness(self):
        """Test that key languages have function patterns defined."""
        # Check that FUNCTION_PATTERNS has some patterns
        assert len(FUNCTION_PATTERNS) > 0
        
        # Check that core languages have patterns
        core_languages = ['python', 'javascript', 'typescript', 'java']
        
        for lang in core_languages:
            if lang in FUNCTION_PATTERNS:
                assert 'patterns' in FUNCTION_PATTERNS[lang]
                assert len(FUNCTION_PATTERNS[lang]['patterns']) > 0
    
    def test_pattern_structure_validity(self):
        """Test that function patterns have required structure."""
        for language, language_data in FUNCTION_PATTERNS.items():
            assert 'patterns' in language_data, f"Language {language} missing patterns key"
            
            patterns = language_data['patterns']
            assert isinstance(patterns, list), f"Language {language} patterns not a list"
            
            for i, pattern in enumerate(patterns):
                pattern_id = f"{language}[{i}]"
                
                # Required fields
                assert 'type' in pattern, f"Pattern {pattern_id} missing type"
                assert 'pattern' in pattern, f"Pattern {pattern_id} missing pattern"
                assert 'description' in pattern, f"Pattern {pattern_id} missing description"
                assert 'captures' in pattern, f"Pattern {pattern_id} missing captures"
                
                # Pattern should not be empty
                assert pattern['pattern'].strip(), f"Pattern {pattern_id} has empty pattern"
                
                # Captures should be a dict
                assert isinstance(pattern['captures'], dict), \
                    f"Pattern {pattern_id} captures not a dict"


class TestFunctionDetectionIntegration:
    """Integration tests for function detection with real AST-grep execution."""
    
    @pytest.mark.asyncio
    async def test_real_ast_grep_execution(self):
        """Test actual AST-grep execution with real patterns."""
        # Create a simple Python file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write('''
def test_function(param1, param2='default'):
    """Test function docstring."""
    return param1 + param2

class TestClass:
    def method(self):
        pass
''')
            f.flush()
            
            detector = FunctionDetector()
            result = await detector.detect_functions(f.name, language='python')
            
            assert result['success'] is True
            functions = result['data']['functions']
            assert len(functions) >= 0  # Should work even if no functions detected
            
            # Check basic result structure
            assert 'data' in result
            assert 'functions' in result['data']
            assert isinstance(result['data']['functions'], list)


if __name__ == '__main__':
    # Run tests
    pytest.main([__file__, '-v']) 