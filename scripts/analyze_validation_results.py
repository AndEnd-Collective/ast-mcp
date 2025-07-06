#!/usr/bin/env python3
"""Analyze MCP validation results and display summary."""

import json
import sys
from pathlib import Path

def main():
    if len(sys.argv) != 2:
        print("Usage: python analyze_validation_results.py <results_file>")
        sys.exit(1)
    
    results_file = Path(sys.argv[1])
    if not results_file.exists():
        print(f"❌ Results file not found: {results_file}")
        sys.exit(1)
    
    try:
        with open(results_file, 'r') as f:
            data = json.load(f)
    except Exception as e:
        print(f"❌ Error reading results file: {e}")
        sys.exit(1)
    
    print('🎯 MCP Validation Results Summary:')
    total_modules = len([k for k in data.keys() if k.startswith('test_')])
    passing_modules = len([k for k, v in data.items() if k.startswith('test_') and v.get('return_code', 1) == 0])
    
    print(f'✅ Modules Passed: {passing_modules}/{total_modules}')
    
    # Check specific compliance targets
    critical_failure = False
    for module, results in data.items():
        if module.startswith('test_mcp_'):
            success_rate = results.get('success_rate', 0)
            total_tests = results.get('total_tests', 0)
            passed_tests = results.get('passed_tests', 0)
            
            status = '✅' if success_rate >= 90 else '⚠️' if success_rate >= 75 else '❌'
            module_name = results.get('name', module)
            print(f'{status} {module_name}: {success_rate:.1f}% ({passed_tests}/{total_tests})')
            
            # Fail if any critical module is below 85%
            if 'protocol' in module.lower() or 'integration' in module.lower():
                if success_rate < 85:
                    print(f'❌ CRITICAL FAILURE: {module} below 85% threshold!')
                    critical_failure = True
    
    if critical_failure:
        sys.exit(1)
    
    print('🎉 All validation checks passed!')

if __name__ == '__main__':
    main()