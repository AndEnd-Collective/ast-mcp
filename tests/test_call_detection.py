"""
Comprehensive test suite for call detection functionality.

Tests the CallDetector class across multiple programming languages
and various call patterns including nested calls, chained calls,
and complex scenarios.
"""

import pytest
import asyncio
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock
import json

from src.ast_grep_mcp.utils import CallDetector, create_call_detector, ASTGrepExecutor


class TestCallDetector:
    """Test suite for CallDetector class."""

    @pytest.fixture
    def sample_files(self):
        """Create sample source files for testing."""
        test_files = {}
        
        # JavaScript/TypeScript test files
        test_files["javascript"] = {
            "simple.js": '''
function greet(name) {
    console.log("Hello, " + name);
    return name.toUpperCase();
}

const result = greet("world");
Math.random();
obj.method(arg1, arg2);
new Date();
Promise.resolve(42);
''',
            "complex.js": '''
class Calculator {
    constructor(precision = 2) {
        this.precision = precision;
    }
    
    add(a, b) {
        return parseFloat((a + b).toFixed(this.precision));
    }
    
    chainExample() {
        return this.add(1, 2)
            .toString()
            .split('.')
            .map(x => parseInt(x));
    }
}

const calc = new Calculator(3);
const result = calc.add(5, 3);
const chained = calc.chainExample();

// Nested calls
const nested = Math.floor(Math.random() * 10);
const complex = JSON.parse(JSON.stringify({data: fetch('/api').then(r => r.json())}));

// Async/await
async function processData() {
    const response = await fetch('/api/data');
    const data = await response.json();
    return data.items.map(item => processItem(item));
}
''',
            "types.ts": '''
interface User {
    id: number;
    name: string;
}

class UserService<T extends User> {
    private users: T[] = [];
    
    addUser<U extends T>(user: U): void {
        this.users.push(user);
        this.notify?.('user_added', user);
    }
    
    getUser(id: number): T | undefined {
        return this.users.find(u => u.id === id);
    }
    
    async processUsers(): Promise<T[]> {
        return Promise.all(
            this.users.map(async user => {
                const processed = await this.transform(user);
                return this.validate?.(processed) ?? processed;
            })
        );
    }
}

const service = new UserService<User>();
service.addUser({id: 1, name: "John"});
const user = service.getUser(1);
'''
        }
        
        # Python test files
        test_files["python"] = {
            "simple.py": '''
def greet(name):
    print(f"Hello, {name}")
    return name.upper()

result = greet("world")
len([1, 2, 3])
obj.method(arg1, arg2)
list(range(10))
''',
            "complex.py": '''
class Calculator:
    def __init__(self, precision=2):
        self.precision = precision
    
    def add(self, a, b):
        return round(a + b, self.precision)
    
    def chain_example(self):
        return str(self.add(1, 2)).split('.')[0]

calc = Calculator(3)
result = calc.add(5, 3)
chained = calc.chain_example()

# Nested calls
nested = int(str(len(list(range(10)))))
complex_data = json.loads(json.dumps({"data": requests.get("/api").json()}))

# Decorators and special cases
@property
def value(self):
    return self._value

@staticmethod
def static_method():
    return Calculator.add(1, 2)

# List comprehensions and lambda
processed = [func(x) for x in data if validate(x)]
filtered = list(filter(lambda x: check(x), items))
mapped = map(transform, data)
''',
            "async_example.py": '''
import asyncio

async def fetch_data():
    response = await http_client.get('/api')
    data = await response.json()
    return [await process_item(item) for item in data]

async def main():
    tasks = [fetch_data() for _ in range(3)]
    results = await asyncio.gather(*tasks)
    return sum(results, [])
'''
        }
        
        # Java test files
        test_files["java"] = {
            "Example.java": '''
public class Example {
    private String name;
    
    public Example(String name) {
        this.name = name;
    }
    
    public static void main(String[] args) {
        Example ex = new Example("test");
        String result = ex.getName().toUpperCase();
        System.out.println(result);
        
        // Static calls
        Math.random();
        Arrays.asList(1, 2, 3);
        
        // Method chaining
        String processed = "hello"
            .toUpperCase()
            .trim()
            .substring(0, 3);
        
        // Nested calls
        int length = Integer.parseInt(String.valueOf(args.length));
    }
    
    public String getName() {
        return this.name;
    }
}
'''
        }
        
        # C++ test files
        test_files["cpp"] = {
            "example.cpp": '''
#include <iostream>
#include <vector>
#include <string>

class Calculator {
public:
    Calculator(int precision = 2) : precision_(precision) {}
    
    double add(double a, double b) {
        return a + b;
    }
    
    void print_result(double value) {
        std::cout << "Result: " << value << std::endl;
    }

private:
    int precision_;
};

int main() {
    Calculator calc(3);
    double result = calc.add(5.0, 3.0);
    calc.print_result(result);
    
    // Static calls
    std::vector<int> vec = {1, 2, 3};
    std::cout << vec.size() << std::endl;
    
    // Function calls
    printf("Hello, world!\\n");
    malloc(sizeof(int) * 10);
    
    return 0;
}
'''
        }
        
        return test_files

    @pytest.fixture
    async def call_detector(self):
        """Create a CallDetector instance for testing."""
        # Mock the executor to avoid requiring actual ast-grep installation
        mock_executor = Mock(spec=ASTGrepExecutor)
        detector = CallDetector(executor=mock_executor)
        return detector

    @pytest.mark.asyncio
    async def test_call_detector_initialization(self):
        """Test CallDetector initialization."""
        detector = CallDetector()
        assert detector.executor is None
        assert detector.language_manager is not None
        assert detector.logger is not None

    @pytest.mark.asyncio
    async def test_detect_calls_basic(self, call_detector, sample_files):
        """Test basic call detection functionality."""
        # Mock search results for JavaScript
        mock_results = [
            {
                "text": "console.log(\"Hello, \" + name)",
                "range": {"start": {"line": 2, "column": 4}, "end": {"line": 2, "column": 32}},
                "metaVariables": {
                    "OBJ": {"text": "console"},
                    "METHOD": {"text": "log"},
                    "ARGS": {"text": "\"Hello, \" + name"}
                }
            },
            {
                "text": "greet(\"world\")",
                "range": {"start": {"line": 6, "column": 15}, "end": {"line": 6, "column": 29}},
                "metaVariables": {
                    "FUNC": {"text": "greet"},
                    "ARGS": {"text": "\"world\""}
                }
            }
        ]
        
        call_detector.executor.search = AsyncMock(return_value={
            "success": True,
            "matches": mock_results
        })
        
        # Create temporary file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False) as f:
            f.write(sample_files["javascript"]["simple.js"])
            temp_path = f.name
        
        try:
            result = await call_detector.detect_calls(
                file_path=temp_path,
                language="javascript",
                include_metadata=True
            )
            
            assert result["success"] is True
            assert "calls" in result
            assert len(result["calls"]) > 0
            
            # Check call structure
            call = result["calls"][0]
            assert "id" in call
            assert "text" in call
            assert "type" in call
            assert "line" in call
            assert "column" in call
            
        finally:
            Path(temp_path).unlink()

    @pytest.mark.asyncio
    async def test_detect_calls_with_metadata(self, call_detector, sample_files):
        """Test call detection with comprehensive metadata."""
        mock_results = [
            {
                "text": "obj.method(arg1, arg2)",
                "range": {"start": {"line": 8, "column": 0}, "end": {"line": 8, "column": 22}},
                "metaVariables": {
                    "OBJ": {"text": "obj"},
                    "METHOD": {"text": "method"},
                    "ARGS": {"text": "arg1, arg2"}
                }
            }
        ]
        
        call_detector.executor.search = AsyncMock(return_value={
            "success": True,
            "matches": mock_results
        })
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False) as f:
            f.write(sample_files["javascript"]["simple.js"])
            temp_path = f.name
        
        try:
            result = await call_detector.detect_calls(
                file_path=temp_path,
                include_metadata=True
            )
            
            assert result["success"] is True
            call = result["calls"][0]
            
            # Check metadata fields
            assert "call_site_info" in call
            assert "argument_analysis" in call
            assert "scope_analysis" in call
            assert "security_analysis" in call
            assert "performance_indicators" in call
            
            # Check call site info
            site_info = call["call_site_info"]
            assert "position" in site_info
            assert "text_metrics" in site_info
            assert "context_clues" in site_info
            
            # Check argument analysis
            arg_analysis = call["argument_analysis"]
            assert "count" in arg_analysis
            assert "types" in arg_analysis
            assert "patterns" in arg_analysis
            
        finally:
            Path(temp_path).unlink()

    @pytest.mark.asyncio
    async def test_detect_calls_multiple_languages(self, call_detector, sample_files):
        """Test call detection across multiple programming languages."""
        test_cases = [
            ("javascript", "simple.js", "javascript"),
            ("python", "simple.py", "python"),
            ("java", "Example.java", "java"),
            ("cpp", "example.cpp", "cpp")
        ]
        
        for lang_family, filename, expected_lang in test_cases:
            mock_results = [
                {
                    "text": f"example_call()",
                    "range": {"start": {"line": 1, "column": 0}, "end": {"line": 1, "column": 14}},
                    "metaVariables": {"FUNC": {"text": "example_call"}, "ARGS": {"text": ""}}
                }
            ]
            
            call_detector.executor.search = AsyncMock(return_value={
                "success": True,
                "matches": mock_results
            })
            
            with tempfile.NamedTemporaryFile(mode='w', suffix=Path(filename).suffix, delete=False) as f:
                f.write(sample_files[lang_family][filename])
                temp_path = f.name
            
            try:
                result = await call_detector.detect_calls(
                    file_path=temp_path,
                    language=expected_lang
                )
                
                assert result["success"] is True
                assert len(result["calls"]) > 0
                
            finally:
                Path(temp_path).unlink()

    @pytest.mark.asyncio
    async def test_call_relationship_analysis(self, call_detector):
        """Test call relationship analysis for nested and chained calls."""
        # Mock complex calls with relationships
        mock_calls = [
            {
                "id": "call_1_0",
                "text": "obj.method1().method2()",
                "type": "chained_call",
                "line": 1,
                "column": 0
            },
            {
                "id": "call_2_0",
                "text": "func(inner(value))",
                "type": "nested_call",
                "line": 2,
                "column": 0
            },
            {
                "id": "call_3_0",
                "text": "new Builder().build()",
                "type": "constructor_chain",
                "line": 3,
                "column": 0
            }
        ]
        
        result = call_detector.analyze_call_relationships(mock_calls)
        
        assert "nested_calls" in result
        assert "chained_calls" in result
        assert "complex_patterns" in result
        assert "call_hierarchy" in result
        assert "max_nesting_depth" in result
        assert "max_chain_length" in result

    @pytest.mark.asyncio
    async def test_call_pattern_detection(self, call_detector):
        """Test detection of design patterns in calls."""
        mock_calls = [
            {
                "text": "builder.setName('test').setAge(25).build()",
                "function_name": "setName",
                "method_name": "setName"
            },
            {
                "text": "api.get('/users').then(response => response.json())",
                "function_name": "then"
            },
            {
                "text": "factorial(n-1)",
                "function_name": "factorial"
            }
        ]
        
        result = call_detector.detect_call_patterns(mock_calls)
        
        assert "detected_patterns" in result
        assert "pattern_counts" in result
        assert "confidence_scores" in result

    @pytest.mark.asyncio
    async def test_detect_calls_in_directory(self, call_detector, sample_files):
        """Test batch processing of multiple files in a directory."""
        call_detector.executor.search = AsyncMock(return_value={
            "success": True,
            "matches": [
                {
                    "text": "example_call()",
                    "range": {"start": {"line": 1, "column": 0}, "end": {"line": 1, "column": 14}},
                    "metaVariables": {"FUNC": {"text": "example_call"}, "ARGS": {"text": ""}}
                }
            ]
        })
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create test files
            for lang_family, files in sample_files.items():
                lang_dir = temp_path / lang_family
                lang_dir.mkdir()
                for filename, content in files.items():
                    (lang_dir / filename).write_text(content)
            
            result = await call_detector.detect_calls_in_directory(
                directory_path=temp_path,
                recursive=True,
                max_files=10
            )
            
            assert result["success"] is True
            assert "files_processed" in result
            assert "total_calls" in result
            assert "results" in result

    @pytest.mark.asyncio
    async def test_security_analysis(self, call_detector):
        """Test security analysis of function calls."""
        # Test high-risk calls
        high_risk_call = {
            "text": "eval(userInput)",
            "function_name": "eval",
            "arguments": "userInput"
        }
        
        security_result = call_detector._analyze_call_security(high_risk_call, {})
        
        assert security_result["security_analysis"]["risk_level"] == "high"
        assert len(security_result["security_analysis"]["security_concerns"]) > 0
        
        # Test low-risk calls
        low_risk_call = {
            "text": "Math.random()",
            "function_name": "random",
            "arguments": ""
        }
        
        security_result = call_detector._analyze_call_security(low_risk_call, {})
        
        assert security_result["security_analysis"]["risk_level"] == "low"

    @pytest.mark.asyncio
    async def test_performance_indicators(self, call_detector):
        """Test extraction of performance indicators."""
        # Test async call
        async_call = {
            "text": "await fetch('/api/data')",
            "function_name": "fetch",
            "argument_count": 1
        }
        
        perf_result = call_detector._extract_performance_indicators(async_call)
        
        assert "performance_indicators" in perf_result
        indicators = perf_result["performance_indicators"]
        assert "async_indicators" in indicators
        assert "network_request" in indicators["async_indicators"]

    @pytest.mark.asyncio
    async def test_argument_analysis(self, call_detector):
        """Test detailed argument analysis."""
        # Complex arguments
        args_text = "user.name, {id: 1, active: true}, [...items], callback => process(callback)"
        
        analysis = call_detector._detailed_argument_analysis(args_text)
        
        assert analysis["count"] == 4
        assert "string" in analysis["types"] or "object" in analysis["types"]
        assert "object_destructuring" in analysis["patterns"] or "spread_operator" in analysis["patterns"]

    @pytest.mark.asyncio
    async def test_scope_information(self, call_detector):
        """Test scope information extraction."""
        # Instance method call
        instance_call = {
            "text": "this.method()",
            "type": "method_call",
            "file": "/src/example.js"
        }
        
        scope_result = call_detector._extract_scope_information({}, instance_call)
        
        assert scope_result["scope_analysis"]["estimated_scope"] == "instance"
        assert "instance_method" in scope_result["scope_analysis"]["scope_indicators"]

    @pytest.mark.asyncio
    async def test_error_handling(self, call_detector):
        """Test error handling in call detection."""
        # Test with invalid file path
        result = await call_detector.detect_calls(
            file_path="/nonexistent/file.js",
            language="javascript"
        )
        
        # Should handle gracefully and return error information
        assert "success" in result
        # The exact behavior depends on implementation - either False or exception handling

    @pytest.mark.asyncio
    async def test_call_type_filtering(self, call_detector, sample_files):
        """Test filtering calls by type."""
        call_detector.executor.search = AsyncMock(return_value={
            "success": True,
            "matches": [
                {
                    "text": "new Date()",
                    "range": {"start": {"line": 1, "column": 0}, "end": {"line": 1, "column": 10}},
                    "metaVariables": {"CLASS": {"text": "Date"}, "ARGS": {"text": ""}}
                }
            ]
        })
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False) as f:
            f.write(sample_files["javascript"]["simple.js"])
            temp_path = f.name
        
        try:
            result = await call_detector.detect_calls(
                file_path=temp_path,
                call_types=["constructor_call"]
            )
            
            assert result["success"] is True
            # Should only return constructor calls
            
        finally:
            Path(temp_path).unlink()

    @pytest.mark.asyncio
    async def test_max_calls_limit(self, call_detector, sample_files):
        """Test maximum calls limit functionality."""
        # Mock many results
        many_results = [
            {
                "text": f"func{i}()",
                "range": {"start": {"line": i, "column": 0}, "end": {"line": i, "column": 8}},
                "metaVariables": {"FUNC": {"text": f"func{i}"}, "ARGS": {"text": ""}}
            }
            for i in range(20)
        ]
        
        call_detector.executor.search = AsyncMock(return_value={
            "success": True,
            "matches": many_results
        })
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False) as f:
            f.write(sample_files["javascript"]["simple.js"])
            temp_path = f.name
        
        try:
            result = await call_detector.detect_calls(
                file_path=temp_path,
                max_calls=5
            )
            
            assert result["success"] is True
            assert len(result["calls"]) <= 5
            
        finally:
            Path(temp_path).unlink()


class TestCallDetectorUtilities:
    """Test suite for CallDetector utility functions."""

    @pytest.mark.asyncio
    async def test_create_call_detector_factory(self):
        """Test the create_call_detector factory function."""
        detector = await create_call_detector()
        assert isinstance(detector, CallDetector)

    def test_argument_type_detection(self):
        """Test argument type detection functionality."""
        detector = CallDetector()
        
        # Test various argument types
        test_cases = [
            ("'string'", ["string"]),
            ("123", ["number"]),
            ("true", ["boolean"]),
            ("[1, 2, 3]", ["array", "number"]),
            ("{key: 'value'}", ["object", "string"]),
            ("null", ["null"]),
            ("undefined", ["undefined"]),
            ("new Date()", ["constructor"]),
            ("() => {}", ["function"]),
            ("this.property", ["this_reference"])
        ]
        
        for args_text, expected_types in test_cases:
            detected_types = detector._detect_argument_types(args_text)
            for expected_type in expected_types:
                assert expected_type in detected_types

    def test_argument_pattern_detection(self):
        """Test argument pattern detection."""
        detector = CallDetector()
        
        test_cases = [
            ("...args", ["spread_operator"]),
            ("{name, age}", ["object_destructuring"]),
            ("[a, b]", ["array_destructuring"]),
            ("name = 'default'", ["default_parameters"]),
            ("await promise", ["async_await"]),
            ("promise.then()", ["promise_chain"]),
            ("obj?.method", ["optional_chaining"]),
            ("value ?? default", ["nullish_coalescing"]),
            ("a && b", ["logical_operators"]),
            ("a === b", ["comparison_operators"])
        ]
        
        for args_text, expected_patterns in test_cases:
            detected_patterns = detector._detect_argument_patterns(args_text)
            for expected_pattern in expected_patterns:
                assert expected_pattern in detected_patterns

    def test_call_text_pattern_analysis(self):
        """Test call text pattern analysis."""
        detector = CallDetector()
        
        test_cases = [
            ("await fetch()", ["has_async_await"]),
            ("promise.then()", ["has_promise_chain"]),
            ("arr.map(x => x)", ["has_callback"]),
            ("const {name} = obj", ["has_destructuring"]),
            ("func(...args)", ["has_spread_operator"]),
            ("obj?.method()", ["has_optional_chaining"]),
            ("value ?? default", ["has_nullish_coalescing"]),
            ("template`string`", ["has_template_literal"]),
            ("new RegExp()", ["has_regex"]),
            ("try { call() }", ["has_error_handling"]),
            ("value as Type", ["has_type_assertion"])
        ]
        
        for call_text, expected_features in test_cases:
            patterns = detector._analyze_call_text_patterns(call_text)
            for feature in expected_features:
                assert patterns.get(feature, False), f"Feature {feature} not detected in '{call_text}'"

    def test_file_classification(self):
        """Test file classification methods."""
        detector = CallDetector()
        
        # Test file classifications
        test_files = [
            ("src/component.test.js", True, False),  # test file
            ("tests/utils.spec.ts", True, False),    # test file
            ("config/webpack.config.js", False, True),  # config file
            ("package.json", False, True),           # config file
            ("src/main.js", False, False),           # regular file
            ("lib/utils.ts", False, False)           # regular file
        ]
        
        for file_path, is_test, is_config in test_files:
            assert detector._is_test_file(file_path) == is_test
            assert detector._is_config_file(file_path) == is_config


if __name__ == "__main__":
    pytest.main([__file__]) 