#!/usr/bin/env python3
"""
Validation script for call detection functionality.

This script validates the CallDetector system across multiple programming languages,
testing accuracy, completeness, and performance of call detection patterns.
"""

import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Dict, List, Any, Tuple
import tempfile
import argparse

# Add the src directory to the path so we can import our modules
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ast_grep_mcp.utils import CallDetector, create_call_detector


class CallDetectionValidator:
    """Validates call detection functionality across languages and scenarios."""
    
    def __init__(self):
        """Initialize the validator."""
        self.test_cases = self._create_test_cases()
        self.results = {
            "validation_summary": {},
            "language_results": {},
            "pattern_accuracy": {},
            "performance_metrics": {},
            "error_cases": []
        }
    
    def _create_test_cases(self) -> Dict[str, Dict[str, Any]]:
        """Create comprehensive test cases for validation."""
        return {
            "javascript": {
                "file_extension": ".js",
                "test_code": '''
// Basic function calls
console.log("Hello World");
parseInt("123");
Math.random();

// Method calls
obj.method(arg1, arg2);
user.getName().toUpperCase();
array.push(item);

// Constructor calls
const date = new Date();
const regex = new RegExp("pattern");
const obj = new MyClass(param1, param2);

// Chained calls
api.get('/users')
    .then(response => response.json())
    .then(data => processData(data))
    .catch(error => handleError(error));

// Nested calls
const result = Math.floor(Math.random() * 10);
const processed = JSON.parse(JSON.stringify(data));
const complex = func(inner(deep(value)));

// Async/await calls
async function fetchData() {
    const response = await fetch('/api');
    const data = await response.json();
    return data;
}

// Arrow functions and callbacks
items.map(item => transform(item));
events.forEach((event, index) => handle(event, index));
setTimeout(() => callback(), 1000);

// Static and namespace calls
Array.from(iterable);
Object.keys(obj);
MyNamespace.StaticMethod();

// Template literals and modern syntax
const url = fetch(`/api/users/${userId}`);
const optional = obj?.method?.();
const nullish = getValue() ?? getDefault();

// Constructor chaining
const builder = new Builder()
    .setName("test")
    .setAge(25)
    .build();
''',
                "expected_patterns": [
                    "function_call", "method_call", "constructor_call", 
                    "chained_call", "static_call", "nested_call",
                    "triple_chained_call", "constructor_chain"
                ],
                "expected_calls": [
                    "console.log", "parseInt", "Math.random", "obj.method",
                    "user.getName", "toUpperCase", "array.push", "new Date",
                    "new RegExp", "new MyClass", "api.get", "response.json",
                    "processData", "handleError", "Math.floor", "JSON.parse",
                    "JSON.stringify", "func", "inner", "deep", "fetch",
                    "response.json", "transform", "handle", "setTimeout",
                    "Array.from", "Object.keys", "MyNamespace.StaticMethod",
                    "fetch", "getValue", "getDefault", "new Builder",
                    "setName", "setAge", "build"
                ]
            },
            
            "typescript": {
                "file_extension": ".ts",
                "test_code": '''
interface User {
    id: number;
    name: string;
}

class UserService<T extends User> {
    private users: T[] = [];
    
    addUser<U extends T>(user: U): void {
        this.users.push(user);
        this.notifyListeners('user_added', user);
    }
    
    getUser(id: number): T | undefined {
        return this.users.find(u => u.id === id);
    }
    
    async processUsers(): Promise<T[]> {
        return Promise.all(
            this.users.map(async (user: T) => {
                const processed = await this.transformUser(user);
                return this.validateUser?.(processed) ?? processed;
            })
        );
    }
}

// Generic calls
const service = new UserService<User>();
service.addUser<User>({id: 1, name: "John"});
const user = service.getUser(1);

// Type assertions and casting
const element = document.getElementById('app') as HTMLElement;
const value = getValue() as string;

// Optional chaining with generics
const result = api.getData<ResponseType>()?.data?.items;

// Utility type calls
type PartialUser = Partial<User>;
type UserKeys = keyof User;
''',
                "expected_patterns": [
                    "generic_call", "method_call", "constructor_call",
                    "optional_chaining_call", "static_call"
                ],
                "expected_calls": [
                    "push", "notifyListeners", "find", "Promise.all",
                    "map", "transformUser", "validateUser", "new UserService",
                    "addUser", "getUser", "document.getElementById",
                    "getValue", "api.getData"
                ]
            },
            
            "python": {
                "file_extension": ".py",
                "test_code": '''
import json
import requests
from typing import List, Dict

# Basic function calls
print("Hello World")
len([1, 2, 3])
str(123)

# Method calls
obj.method(arg1, arg2)
user.get_name().upper()
items.append(item)

# Constructor calls
date = datetime.now()
pattern = re.compile(r"\\d+")
instance = MyClass(param1, param2)

# Nested calls
result = int(str(len(list(range(10)))))
data = json.loads(json.dumps({"key": "value"}))
complex_result = func(inner(deep(value)))

# List comprehensions and generators
processed = [transform(x) for x in data if validate(x)]
mapped = list(map(lambda x: process(x), items))
filtered = filter(predicate, collection)

# Async calls
async def fetch_data():
    response = await client.get('/api')
    data = await response.json()
    return [await process_item(item) for item in data]

# Class methods and static methods
@classmethod
def create_instance(cls):
    return cls(default_value())

@staticmethod
def utility_function():
    return MyClass.helper_method()

# Property and descriptor calls
@property
def value(self):
    return self._get_value()

# Decorator calls
@decoratorfunction
@decorator_with_args(param1, param2)
def decorated_function():
    pass

# Context managers
with open('file.txt') as f:
    content = f.read()

# Super calls
class Child(Parent):
    def method(self):
        super().method()
        return self.process_result()
''',
                "expected_patterns": [
                    "function_call", "method_call", "nested_call",
                    "comprehension_call", "async_call", "super_call",
                    "decorator_call"
                ],
                "expected_calls": [
                    "print", "len", "str", "obj.method", "get_name", "upper",
                    "append", "datetime.now", "re.compile", "MyClass",
                    "int", "json.loads", "json.dumps", "func", "inner", "deep",
                    "transform", "validate", "map", "process", "filter",
                    "client.get", "response.json", "process_item", "create_instance",
                    "default_value", "helper_method", "_get_value", "decoratorfunction",
                    "decorator_with_args", "open", "read", "super", "process_result"
                ]
            },
            
            "java": {
                "file_extension": ".java",
                "test_code": '''
import java.util.*;

public class CallValidation {
    private String name;
    
    public CallValidation(String name) {
        this.name = name;
    }
    
    public static void main(String[] args) {
        // Constructor calls
        CallValidation obj = new CallValidation("test");
        List<String> list = new ArrayList<>();
        Map<String, Integer> map = new HashMap<>();
        
        // Method calls
        String result = obj.getName().toUpperCase();
        System.out.println(result);
        list.add("item");
        map.put("key", 1);
        
        // Static method calls
        Math.random();
        Arrays.asList(1, 2, 3);
        Collections.sort(list);
        String.valueOf(123);
        
        // Chained method calls
        String processed = "hello world"
            .toUpperCase()
            .trim()
            .substring(0, 5)
            .replace("HELLO", "Hi");
        
        // Nested calls
        int length = Integer.parseInt(String.valueOf(args.length));
        double value = Math.sqrt(Math.pow(2, 3));
        
        // Generic method calls
        List<String> stringList = Arrays.<String>asList("a", "b");
        Optional<String> optional = Optional.<String>of("value");
        
        // Stream API calls
        list.stream()
            .filter(s -> s.length() > 2)
            .map(String::toUpperCase)
            .collect(Collectors.toList());
    }
    
    public String getName() {
        return this.name;
    }
}
''',
                "expected_patterns": [
                    "constructor_call", "method_call", "static_call",
                    "chained_call", "generic_call", "stream_call"
                ],
                "expected_calls": [
                    "new CallValidation", "new ArrayList", "new HashMap",
                    "getName", "toUpperCase", "System.out.println", "add",
                    "put", "Math.random", "Arrays.asList", "Collections.sort",
                    "String.valueOf", "trim", "substring", "replace",
                    "Integer.parseInt", "Math.sqrt", "Math.pow", "Optional.of",
                    "stream", "filter", "map", "collect"
                ]
            },
            
            "cpp": {
                "file_extension": ".cpp",
                "test_code": '''
#include <iostream>
#include <vector>
#include <string>
#include <memory>

class Calculator {
public:
    Calculator(int precision = 2) : precision_(precision) {}
    
    double add(double a, double b) {
        return a + b;
    }
    
    void printResult(double value) {
        std::cout << "Result: " << value << std::endl;
    }

private:
    int precision_;
};

int main() {
    // Constructor calls
    Calculator calc(3);
    std::vector<int> vec = {1, 2, 3};
    std::string str("hello");
    auto ptr = std::make_unique<Calculator>(2);
    
    // Method calls
    double result = calc.add(5.0, 3.0);
    calc.printResult(result);
    vec.push_back(4);
    str.append(" world");
    
    // Static calls and namespaced calls
    std::cout << vec.size() << std::endl;
    std::transform(vec.begin(), vec.end(), vec.begin(), 
                   [](int x) { return x * 2; });
    
    // C-style function calls
    printf("Hello, world!\\n");
    malloc(sizeof(int) * 10);
    strlen(str.c_str());
    
    // Operator calls (function-like)
    Calculator calc2 = Calculator(1);
    std::shared_ptr<int> shared = std::make_shared<int>(42);
    
    // Template function calls
    std::max<int>(1, 2);
    std::min<double>(3.14, 2.71);
    
    return 0;
}
''',
                "expected_patterns": [
                    "constructor_call", "method_call", "namespace_call",
                    "function_call", "template_call"
                ],
                "expected_calls": [
                    "Calculator", "std::vector", "std::string", "std::make_unique",
                    "add", "printResult", "push_back", "append", "std::cout",
                    "size", "std::transform", "printf", "malloc", "strlen",
                    "std::make_shared", "std::max", "std::min"
                ]
            }
        }
    
    async def validate_language(self, language: str, test_case: Dict[str, Any]) -> Dict[str, Any]:
        """Validate call detection for a specific language."""
        print(f"\n🔍 Validating {language.upper()} call detection...")
        
        start_time = time.time()
        detector = await create_call_detector()
        
        # Create temporary test file
        with tempfile.NamedTemporaryFile(
            mode='w', 
            suffix=test_case["file_extension"], 
            delete=False
        ) as f:
            f.write(test_case["test_code"])
            temp_file = f.name
        
        try:
            # Test call detection
            result = await detector.detect_calls(
                file_path=temp_file,
                language=language,
                include_metadata=True
            )
            
            detection_time = time.time() - start_time
            
            # Analyze results
            validation_result = self._analyze_detection_result(
                result, test_case, language, detection_time
            )
            
            return validation_result
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "language": language,
                "detection_time": time.time() - start_time
            }
        finally:
            # Clean up temporary file
            try:
                Path(temp_file).unlink()
            except:
                pass
    
    def _analyze_detection_result(
        self, 
        result: Dict[str, Any], 
        test_case: Dict[str, Any], 
        language: str,
        detection_time: float
    ) -> Dict[str, Any]:
        """Analyze the detection result against expected patterns and calls."""
        analysis = {
            "language": language,
            "success": result.get("success", False),
            "detection_time": detection_time,
            "calls_detected": 0,
            "patterns_found": [],
            "accuracy_metrics": {},
            "metadata_analysis": {},
            "issues": []
        }
        
        if not result.get("success", False):
            analysis["issues"].append("Detection failed")
            return analysis
        
        calls = result.get("calls", [])
        analysis["calls_detected"] = len(calls)
        
        # Analyze detected patterns
        detected_patterns = set()
        detected_calls = []
        
        for call in calls:
            call_type = call.get("type", "unknown")
            detected_patterns.add(call_type)
            
            # Extract function/method name
            call_name = (
                call.get("function_name", "") or 
                call.get("method_name", "") or
                call.get("text", "").split("(")[0].strip()
            )
            if call_name:
                detected_calls.append(call_name)
        
        analysis["patterns_found"] = list(detected_patterns)
        
        # Calculate accuracy metrics
        expected_patterns = set(test_case.get("expected_patterns", []))
        expected_calls = set(test_case.get("expected_calls", []))
        detected_call_names = set(detected_calls)
        
        # Pattern accuracy
        pattern_accuracy = self._calculate_accuracy(detected_patterns, expected_patterns)
        analysis["accuracy_metrics"]["pattern_accuracy"] = pattern_accuracy
        
        # Call accuracy (more lenient - partial matching)
        call_accuracy = self._calculate_call_accuracy(detected_call_names, expected_calls)
        analysis["accuracy_metrics"]["call_accuracy"] = call_accuracy
        
        # Analyze metadata quality
        if calls:
            analysis["metadata_analysis"] = self._analyze_metadata_quality(calls)
        
        # Identify issues
        missing_patterns = expected_patterns - detected_patterns
        if missing_patterns:
            analysis["issues"].append(f"Missing patterns: {missing_patterns}")
        
        if analysis["calls_detected"] == 0:
            analysis["issues"].append("No calls detected")
        
        return analysis
    
    def _calculate_accuracy(self, detected: set, expected: set) -> Dict[str, float]:
        """Calculate precision, recall, and F1 score."""
        if not expected:
            return {"precision": 1.0, "recall": 1.0, "f1": 1.0}
        
        true_positives = len(detected & expected)
        false_positives = len(detected - expected)
        false_negatives = len(expected - detected)
        
        precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) > 0 else 0
        recall = true_positives / (true_positives + false_negatives) if (true_positives + false_negatives) > 0 else 0
        f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
        
        return {
            "precision": round(precision, 3),
            "recall": round(recall, 3),
            "f1": round(f1, 3),
            "true_positives": true_positives,
            "false_positives": false_positives,
            "false_negatives": false_negatives
        }
    
    def _calculate_call_accuracy(self, detected: set, expected: set) -> Dict[str, float]:
        """Calculate call detection accuracy with partial matching."""
        if not expected:
            return {"precision": 1.0, "recall": 1.0, "f1": 1.0}
        
        # Use partial matching for call names
        matched_expected = set()
        matched_detected = set()
        
        for expected_call in expected:
            for detected_call in detected:
                if (expected_call in detected_call or 
                    detected_call in expected_call or
                    expected_call.split('.')[-1] == detected_call.split('.')[-1]):
                    matched_expected.add(expected_call)
                    matched_detected.add(detected_call)
                    break
        
        true_positives = len(matched_expected)
        false_positives = len(detected - matched_detected)
        false_negatives = len(expected - matched_expected)
        
        precision = true_positives / len(detected) if detected else 0
        recall = true_positives / len(expected) if expected else 0
        f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
        
        return {
            "precision": round(precision, 3),
            "recall": round(recall, 3),
            "f1": round(f1, 3),
            "matched_calls": true_positives,
            "total_detected": len(detected),
            "total_expected": len(expected)
        }
    
    def _analyze_metadata_quality(self, calls: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze the quality of extracted metadata."""
        metadata_fields = [
            "call_site_info", "argument_analysis", "scope_analysis",
            "security_analysis", "performance_indicators"
        ]
        
        field_coverage = {}
        for field in metadata_fields:
            count = sum(1 for call in calls if field in call)
            field_coverage[field] = {
                "present": count,
                "percentage": round(count / len(calls) * 100, 1) if calls else 0
            }
        
        # Analyze argument analysis quality
        arg_analysis_quality = self._analyze_argument_quality(calls)
        
        return {
            "field_coverage": field_coverage,
            "argument_analysis_quality": arg_analysis_quality,
            "total_calls_with_metadata": len([c for c in calls if any(field in c for field in metadata_fields)])
        }
    
    def _analyze_argument_quality(self, calls: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze the quality of argument analysis."""
        with_args = [c for c in calls if c.get("argument_analysis", {}).get("count", 0) > 0]
        
        if not with_args:
            return {"calls_with_arguments": 0, "average_types_detected": 0}
        
        total_types = sum(len(c.get("argument_analysis", {}).get("types", [])) for c in with_args)
        average_types = total_types / len(with_args) if with_args else 0
        
        return {
            "calls_with_arguments": len(with_args),
            "average_types_detected": round(average_types, 2),
            "calls_with_patterns": len([c for c in with_args if c.get("argument_analysis", {}).get("patterns")])
        }
    
    async def run_validation(self) -> Dict[str, Any]:
        """Run complete validation across all languages."""
        print("🚀 Starting Call Detection Validation...")
        print("=" * 60)
        
        total_start = time.time()
        
        for language, test_case in self.test_cases.items():
            try:
                result = await self.validate_language(language, test_case)
                self.results["language_results"][language] = result
                
                # Print summary
                if result.get("success", False):
                    print(f"✅ {language}: {result['calls_detected']} calls, "
                          f"{result['accuracy_metrics']['pattern_accuracy']['f1']:.3f} F1, "
                          f"{result['detection_time']:.3f}s")
                else:
                    print(f"❌ {language}: FAILED - {result.get('error', 'Unknown error')}")
                    
            except Exception as e:
                error_result = {
                    "success": False,
                    "error": str(e),
                    "language": language
                }
                self.results["language_results"][language] = error_result
                self.results["error_cases"].append(error_result)
                print(f"💥 {language}: EXCEPTION - {str(e)}")
        
        total_time = time.time() - total_start
        
        # Generate summary
        self.results["validation_summary"] = self._generate_summary(total_time)
        
        print("\n" + "=" * 60)
        print("📊 VALIDATION SUMMARY")
        print("=" * 60)
        
        summary = self.results["validation_summary"]
        print(f"Languages tested: {summary['languages_tested']}")
        print(f"Successful: {summary['successful_languages']}")
        print(f"Failed: {summary['failed_languages']}")
        print(f"Total time: {summary['total_time']:.3f}s")
        print(f"Average F1 score: {summary['average_f1']:.3f}")
        print(f"Total calls detected: {summary['total_calls_detected']}")
        
        if summary['failed_languages'] > 0:
            print(f"\n⚠️  Failed languages: {summary['failed_language_names']}")
        
        return self.results
    
    def _generate_summary(self, total_time: float) -> Dict[str, Any]:
        """Generate validation summary statistics."""
        successful = [r for r in self.results["language_results"].values() if r.get("success", False)]
        failed = [r for r in self.results["language_results"].values() if not r.get("success", False)]
        
        # Calculate averages for successful languages
        if successful:
            avg_f1 = sum(r["accuracy_metrics"]["pattern_accuracy"]["f1"] for r in successful) / len(successful)
            total_calls = sum(r["calls_detected"] for r in successful)
            avg_detection_time = sum(r["detection_time"] for r in successful) / len(successful)
        else:
            avg_f1 = 0
            total_calls = 0
            avg_detection_time = 0
        
        return {
            "languages_tested": len(self.test_cases),
            "successful_languages": len(successful),
            "failed_languages": len(failed),
            "failed_language_names": [r["language"] for r in failed],
            "total_time": round(total_time, 3),
            "average_detection_time": round(avg_detection_time, 3),
            "average_f1": round(avg_f1, 3),
            "total_calls_detected": total_calls
        }
    
    def save_results(self, output_file: str = "call_detection_validation_results.json"):
        """Save validation results to a JSON file."""
        output_path = Path(output_file)
        
        # Add timestamp to results
        import datetime
        self.results["validation_metadata"] = {
            "timestamp": datetime.datetime.now().isoformat(),
            "validator_version": "1.0.0",
            "languages_tested": list(self.test_cases.keys())
        }
        
        with open(output_path, 'w') as f:
            json.dump(self.results, f, indent=2)
        
        print(f"\n💾 Results saved to: {output_path.absolute()}")


async def main():
    """Main function to run call detection validation."""
    parser = argparse.ArgumentParser(description="Validate call detection functionality")
    parser.add_argument(
        "--output", "-o",
        default="call_detection_validation_results.json",
        help="Output file for validation results"
    )
    parser.add_argument(
        "--language", "-l",
        help="Test only a specific language (javascript, typescript, python, java, cpp)"
    )
    
    args = parser.parse_args()
    
    validator = CallDetectionValidator()
    
    # Filter test cases if specific language requested
    if args.language:
        if args.language not in validator.test_cases:
            print(f"❌ Unknown language: {args.language}")
            print(f"Available languages: {', '.join(validator.test_cases.keys())}")
            return
        
        # Test only the specified language
        original_test_cases = validator.test_cases
        validator.test_cases = {args.language: original_test_cases[args.language]}
    
    try:
        results = await validator.run_validation()
        validator.save_results(args.output)
        
        # Exit with appropriate code
        failed_count = results["validation_summary"]["failed_languages"]
        sys.exit(failed_count)
        
    except KeyboardInterrupt:
        print("\n🛑 Validation interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Validation failed with exception: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main()) 