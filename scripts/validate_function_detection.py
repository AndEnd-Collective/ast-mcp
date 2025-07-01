#!/usr/bin/env python3
"""
Function Detection Validation Script

This script validates the accuracy and completeness of function detection
across different programming languages by running comprehensive tests.
"""

import asyncio
import sys
import tempfile
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ast_grep_mcp.utils import FunctionDetector, create_ast_grep_executor
from src.ast_grep_mcp.resources import FUNCTION_PATTERNS, SUPPORTED_LANGUAGES


# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class FunctionDetectionValidator:
    """Validates function detection accuracy across multiple languages."""
    
    def __init__(self):
        self.detector = None
        self.results = {}
        
    async def initialize(self):
        """Initialize the function detector."""
        try:
            executor = await create_ast_grep_executor()
            self.detector = FunctionDetector(executor)
            logger.info("Function detector initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize function detector: {e}")
            raise
        
    async def validate_basic_detection(self) -> Dict[str, Any]:
        """Validate basic function detection capabilities."""
        logger.info("Testing basic function detection...")
        
        # Simple Python test
        python_code = '''
def simple_function(param1, param2='default'):
    """A simple function with parameters."""
    return param1 + param2

class TestClass:
    def method(self):
        pass
'''
        
        result = {
            'success': False,
            'functions_found': 0,
            'error': None
        }
        
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                f.write(python_code)
                f.flush()
                
                detection_result = await self.detector.detect_functions(
                    f.name,
                    language='python',
                    include_metadata=True
                )
                
                if detection_result['success']:
                    functions = detection_result['data']['functions']
                    result['functions_found'] = len(functions)
                    result['success'] = True
                    logger.info(f"Basic detection successful: found {len(functions)} functions")
                else:
                    result['error'] = detection_result.get('error', {}).get('message', 'Unknown error')
                    logger.error(f"Basic detection failed: {result['error']}")
                
        except Exception as e:
            result['error'] = str(e)
            logger.error(f"Basic detection exception: {e}")
        
        return result
    
    def validate_pattern_structure(self) -> Dict[str, Any]:
        """Validate the structure of function patterns."""
        logger.info("Validating pattern structure...")
        
        result = {
            'total_languages': len(FUNCTION_PATTERNS),
            'valid_patterns': 0,
            'invalid_patterns': 0,
            'errors': []
        }
        
        for language, language_data in FUNCTION_PATTERNS.items():
            try:
                # Check required structure
                if 'patterns' not in language_data:
                    result['errors'].append(f"{language}: missing 'patterns' key")
                    result['invalid_patterns'] += 1
                    continue
                
                patterns = language_data['patterns']
                if not isinstance(patterns, list):
                    result['errors'].append(f"{language}: 'patterns' is not a list")
                    result['invalid_patterns'] += 1
                    continue
                
                # Validate each pattern
                pattern_valid = True
                for i, pattern in enumerate(patterns):
                    required_fields = ['type', 'pattern', 'description', 'captures']
                    for field in required_fields:
                        if field not in pattern:
                            result['errors'].append(f"{language}[{i}]: missing '{field}' field")
                            pattern_valid = False
                    
                    if not pattern.get('pattern', '').strip():
                        result['errors'].append(f"{language}[{i}]: empty pattern")
                        pattern_valid = False
                    
                    if not isinstance(pattern.get('captures', {}), dict):
                        result['errors'].append(f"{language}[{i}]: 'captures' is not a dict")
                        pattern_valid = False
                
                if pattern_valid:
                    result['valid_patterns'] += 1
                else:
                    result['invalid_patterns'] += 1
                    
            except Exception as e:
                result['errors'].append(f"{language}: validation exception - {e}")
                result['invalid_patterns'] += 1
        
        logger.info(f"Pattern validation: {result['valid_patterns']} valid, {result['invalid_patterns']} invalid")
        return result
    
    async def validate_language_coverage(self) -> Dict[str, Any]:
        """Validate function detection across multiple languages."""
        logger.info("Testing language coverage...")
        
        test_cases = {
            'python': {
                'code': 'def test_func():\n    pass\n',
                'extension': '.py'
            },
            'javascript': {
                'code': 'function testFunc() {\n    return true;\n}\n',
                'extension': '.js'
            },
            'typescript': {
                'code': 'function testFunc(): boolean {\n    return true;\n}\n',
                'extension': '.ts'
            }
        }
        
        result = {
            'languages_tested': 0,
            'successful_detections': 0,
            'failed_detections': 0,
            'language_results': {},
            'errors': []
        }
        
        for language, test_data in test_cases.items():
            if language not in FUNCTION_PATTERNS:
                logger.warning(f"Skipping {language}: no patterns defined")
                continue
            
            result['languages_tested'] += 1
            
            try:
                with tempfile.NamedTemporaryFile(
                    mode='w', 
                    suffix=test_data['extension'],
                    delete=False
                ) as f:
                    f.write(test_data['code'])
                    f.flush()
                    
                    detection_result = await self.detector.detect_functions(
                        f.name,
                        language=language,
                        include_metadata=True
                    )
                    
                    lang_result = {
                        'success': detection_result['success'],
                        'functions_found': 0,
                        'error': None
                    }
                    
                    if detection_result['success']:
                        functions = detection_result['data']['functions']
                        lang_result['functions_found'] = len(functions)
                        result['successful_detections'] += 1
                        logger.info(f"{language}: found {len(functions)} functions")
                    else:
                        lang_result['error'] = detection_result.get('error', {}).get('message', 'Unknown error')
                        result['failed_detections'] += 1
                        logger.warning(f"{language}: detection failed - {lang_result['error']}")
                    
                    result['language_results'][language] = lang_result
                    
            except Exception as e:
                error_msg = f"{language}: exception - {str(e)}"
                result['errors'].append(error_msg)
                result['failed_detections'] += 1
                logger.error(error_msg)
        
        return result
    
    def generate_report(self, basic_result: Dict[str, Any], 
                       pattern_result: Dict[str, Any], 
                       coverage_result: Dict[str, Any]) -> str:
        """Generate a comprehensive validation report."""
        report_lines = [
            "=" * 60,
            "FUNCTION DETECTION VALIDATION REPORT",
            "=" * 60,
            "",
            "BASIC DETECTION TEST:",
            f"  Success: {basic_result['success']}",
            f"  Functions Found: {basic_result['functions_found']}",
        ]
        
        if basic_result.get('error'):
            report_lines.append(f"  Error: {basic_result['error']}")
        
        report_lines.extend([
            "",
            "PATTERN STRUCTURE VALIDATION:",
            f"  Total Languages: {pattern_result['total_languages']}",
            f"  Valid Patterns: {pattern_result['valid_patterns']}",
            f"  Invalid Patterns: {pattern_result['invalid_patterns']}",
        ])
        
        if pattern_result['errors']:
            report_lines.append("  Pattern Errors:")
            for error in pattern_result['errors'][:5]:  # Show first 5 errors
                report_lines.append(f"    - {error}")
            if len(pattern_result['errors']) > 5:
                report_lines.append(f"    ... and {len(pattern_result['errors']) - 5} more")
        
        report_lines.extend([
            "",
            "LANGUAGE COVERAGE TEST:",
            f"  Languages Tested: {coverage_result['languages_tested']}",
            f"  Successful: {coverage_result['successful_detections']}",
            f"  Failed: {coverage_result['failed_detections']}",
        ])
        
        if coverage_result['languages_tested'] > 0:
            success_rate = (coverage_result['successful_detections'] / 
                          coverage_result['languages_tested']) * 100
            report_lines.append(f"  Success Rate: {success_rate:.1f}%")
        
        for language, result in coverage_result['language_results'].items():
            status = "✓" if result['success'] else "✗"
            report_lines.append(f"    {status} {language}: {result['functions_found']} functions")
            if result.get('error'):
                report_lines.append(f"      Error: {result['error']}")
        
        if coverage_result['errors']:
            report_lines.append("  Coverage Errors:")
            for error in coverage_result['errors']:
                report_lines.append(f"    - {error}")
        
        # Overall assessment
        overall_success = (
            basic_result['success'] and 
            pattern_result['invalid_patterns'] == 0 and
            coverage_result['failed_detections'] == 0
        )
        
        report_lines.extend([
            "",
            "OVERALL ASSESSMENT:",
            f"  Status: {'PASS' if overall_success else 'FAIL'}",
            "",
            "=" * 60
        ])
        
        return "\n".join(report_lines)


async def main():
    """Main validation function."""
    validator = FunctionDetectionValidator()
    
    try:
        await validator.initialize()
        
        # Run all validations
        basic_result = await validator.validate_basic_detection()
        pattern_result = validator.validate_pattern_structure()
        coverage_result = await validator.validate_language_coverage()
        
        # Generate and display report
        report = validator.generate_report(basic_result, pattern_result, coverage_result)
        print(report)
        
        # Save report to file
        report_file = Path(__file__).parent.parent / "function_detection_validation_report.txt"
        with open(report_file, 'w') as f:
            f.write(report)
        
        logger.info(f"Report saved to: {report_file}")
        
        # Determine exit code
        overall_success = (
            basic_result['success'] and 
            pattern_result['invalid_patterns'] == 0 and
            coverage_result['failed_detections'] == 0
        )
        
        if overall_success:
            logger.info("All validations passed!")
            sys.exit(0)
        else:
            logger.warning("Some validations failed.")
            sys.exit(1)
            
    except Exception as e:
        logger.error(f"Validation failed with error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main()) 