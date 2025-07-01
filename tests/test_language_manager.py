"""
Tests for LanguageManager class - comprehensive validation of language detection,
mapping, and pattern support functionality.
"""

import pytest
import tempfile
import os
from pathlib import Path
from src.ast_grep_mcp.utils import LanguageManager


class TestLanguageDetection:
    """Test language detection by extension, filename, and content."""
    
    def setup_method(self):
        """Reset LanguageManager for each test."""
        LanguageManager._instance = None
        self.lang_manager = LanguageManager()
    
    def test_detect_by_extension_common_languages(self):
        """Test detection by common file extensions."""
        test_cases = [
            ("file.js", "javascript"),
            ("file.ts", "typescript"),
            ("file.py", "python"),
            ("file.rs", "rust"),
            ("file.go", "go"),
            ("file.java", "java"),
            ("file.c", "c"),
            ("file.cpp", "cpp"),
            ("file.cs", "csharp"),
            ("file.php", "php"),
            ("file.rb", "ruby"),
            ("file.swift", "swift"),
            ("file.kt", "kotlin"),
            ("file.scala", "scala"),
            ("file.lua", "lua"),
            ("file.sh", "bash"),
            ("file.html", "html"),
            ("file.css", "css"),
            ("file.json", "json"),
            ("file.yaml", "yaml"),
        ]
        
        for filename, expected_lang in test_cases:
            detected = self.lang_manager.detect_language(filename)
            assert detected == expected_lang, f"Expected {expected_lang} for {filename}, got {detected}"
    
    def test_detect_by_filename_special_cases(self):
        """Test detection by special filenames."""
        test_cases = [
            ("Makefile", "make"),
            ("makefile", "make"),
            ("Dockerfile", "dockerfile"),
            ("dockerfile", "dockerfile"),
            ("Gemfile", "ruby"),
            ("Rakefile", "ruby"),
            ("CMakeLists.txt", "cmake"),
            ("package.json", "json"),
            ("tsconfig.json", "json"),
            (".bashrc", "bash"),
            (".zshrc", "bash"),
        ]
        
        for filename, expected_lang in test_cases:
            detected = self.lang_manager.detect_language(filename)
            assert detected == expected_lang, f"Expected {expected_lang} for {filename}, got {detected}"
    
    def test_detect_by_content_shebang(self):
        """Test detection by shebang in content."""
        test_cases = [
            ("#!/bin/bash\necho 'hello'", "bash"),
            ("#!/usr/bin/env python3\nprint('hello')", "python"),
            ("#!/usr/bin/env node\nconsole.log('hello')", "javascript"),
            ("#!/usr/bin/ruby\nputs 'hello'", "ruby"),
            ("#!/usr/bin/env php\n<?php echo 'hello';", "php"),
        ]
        
        for content, expected_lang in test_cases:
            detected = self.lang_manager.detect_language("unknown_file", content)
            assert detected == expected_lang, f"Expected {expected_lang} for shebang, got {detected}"
    
    def test_detect_c_cpp_headers(self):
        """Test C/C++ header file detection."""
        c_content = """
        #include <stdio.h>
        
        int main() {
            printf("Hello, World!");
            return 0;
        }
        """
        
        cpp_content = """
        #include <iostream>
        #include <vector>
        
        int main() {
            std::vector<int> v;
            std::cout << "Hello, World!" << std::endl;
            return 0;
        }
        """
        
        assert self.lang_manager.detect_language("test.h", c_content) == "c"
        assert self.lang_manager.detect_language("test.h", cpp_content) == "cpp"
        assert self.lang_manager.detect_language("test.hpp") == "cpp"
        assert self.lang_manager.detect_language("test.hxx") == "cpp"


class TestLanguageValidation:
    """Test language validation and normalization."""
    
    def setup_method(self):
        """Reset LanguageManager for each test."""
        LanguageManager._instance = None
        self.lang_manager = LanguageManager()
    
    def test_validate_language_identifier_valid_names(self):
        """Test validation with valid language names."""
        valid_languages = [
            "javascript", "typescript", "python", "rust", "go", "java",
            "c", "cpp", "csharp", "php", "ruby", "swift", "kotlin",
            "scala", "lua", "bash", "html", "css", "json", "yaml"
        ]
        
        for lang in valid_languages:
            assert self.lang_manager.validate_language_identifier(lang) == True
    
    def test_validate_language_identifier_aliases(self):
        """Test validation with language aliases."""
        alias_cases = [
            ("js", True),
            ("ts", True),
            ("py", True),
            ("rs", True),
            ("rb", True),
            ("cs", True),
            ("kt", True),
            ("sh", True),
        ]
        
        for alias, expected in alias_cases:
            result = self.lang_manager.validate_language_identifier(alias)
            assert result == expected, f"Expected {expected} for alias {alias}, got {result}"
    
    def test_validate_language_identifier_extensions(self):
        """Test validation with file extensions."""
        extension_cases = [
            (".js", True),
            (".ts", True),
            (".py", True),
            (".rs", True),
            (".go", True),
            (".java", True),
            (".invalid", False),
        ]
        
        for ext, expected in extension_cases:
            result = self.lang_manager.validate_language_identifier(ext)
            assert result == expected, f"Expected {expected} for extension {ext}, got {result}"
    
    def test_normalize_language_identifier(self):
        """Test language identifier normalization."""
        normalization_cases = [
            ("js", "javascript"),
            ("ts", "typescript"),
            ("py", "python"), 
            ("rs", "rust"),
            ("rb", "ruby"),
            ("cs", "csharp"),
            ("kt", "kotlin"),
            ("sh", "bash"),
            ("javascript", "javascript"),  # Already normalized
            ("invalid", "invalid"),  # Unknown language
        ]
        
        for input_lang, expected in normalization_cases:
            result = self.lang_manager.normalize_language_identifier(input_lang)
            assert result == expected, f"Expected {expected} for {input_lang}, got {result}"


class TestLanguageMapping:
    """Test AST-grep language mapping functionality."""
    
    def setup_method(self):
        """Reset LanguageManager for each test."""
        LanguageManager._instance = None
        self.lang_manager = LanguageManager()
    
    def test_map_to_ast_grep_language(self):
        """Test mapping to AST-grep language codes."""
        mapping_cases = [
            ("javascript", "js"),
            ("typescript", "ts"),
            ("python", "py"),
            ("rust", "rs"),
            ("go", "go"), 
            ("java", "java"),
            ("c", "c"),
            ("cpp", "cpp"),
            ("csharp", "cs"),
            ("php", "php"),
            ("ruby", "rb"),
            ("swift", "swift"),
            ("kotlin", "kt"),
            ("scala", "scala"),
            ("lua", "lua"),
            ("bash", "bash"),
            ("html", "html"),
            ("css", "css"),
            ("json", "json"),
            ("yaml", "yaml"),
        ]
        
        for lang_name, expected_ast_grep in mapping_cases:
            result = self.lang_manager.map_to_ast_grep_language(lang_name)
            assert result == expected_ast_grep, f"Expected {expected_ast_grep} for {lang_name}, got {result}"
    
    def test_map_to_ast_grep_language_with_aliases(self):
        """Test mapping with language aliases."""
        alias_mapping_cases = [
            ("js", "js"),
            ("ts", "ts"), 
            ("py", "py"),
            ("rs", "rs"),
            ("rb", "rb"),
            ("cs", "cs"),
            ("kt", "kt"),
            ("sh", "bash"),
        ]
        
        for alias, expected_ast_grep in alias_mapping_cases:
            result = self.lang_manager.map_to_ast_grep_language(alias)
            assert result == expected_ast_grep, f"Expected {expected_ast_grep} for alias {alias}, got {result}"


class TestLanguagePatterns:
    """Test language pattern examples functionality."""
    
    def setup_method(self):
        """Reset LanguageManager for each test."""
        LanguageManager._instance = None
        self.lang_manager = LanguageManager()
    
    def test_get_language_patterns_javascript(self):
        """Test JavaScript pattern examples."""
        patterns = self.lang_manager.get_language_patterns("javascript")
        assert len(patterns) > 0
        
        # Check that patterns have required structure
        for pattern in patterns:
            assert "pattern" in pattern
            assert "description" in pattern
            assert "category" in pattern
    
    def test_get_language_patterns_python(self):
        """Test Python pattern examples."""
        patterns = self.lang_manager.get_language_patterns("python") 
        assert len(patterns) > 0
        
        # Verify specific Python patterns exist
        pattern_descriptions = [p["description"] for p in patterns]
        assert any("function definition" in desc.lower() for desc in pattern_descriptions)
        assert any("class definition" in desc.lower() for desc in pattern_descriptions)
    
    def test_get_language_patterns_invalid_language(self):
        """Test pattern retrieval for invalid language."""
        patterns = self.lang_manager.get_language_patterns("invalid_language")
        assert patterns == []


class TestLanguageClassification:
    """Test language family classification."""
    
    def setup_method(self):
        """Reset LanguageManager for each test."""
        LanguageManager._instance = None
        self.lang_manager = LanguageManager()
    
    def test_get_language_family(self):
        """Test language family classification."""
        family_cases = [
            ("javascript", "scripting"),
            ("typescript", "scripting"),
            ("python", "scripting"),
            ("rust", "systems"),
            ("go", "systems"),
            ("java", "c-like"),
            ("c", "c-like"),
            ("cpp", "c-like"),
            ("csharp", "c-like"),
            ("swift", "mobile"),
            ("kotlin", "mobile"),
            ("html", "markup"),
            ("css", "markup"),
            ("json", "data"),
            ("yaml", "data"),
        ]
        
        for lang, expected_family in family_cases:
            result = self.lang_manager.get_language_family(lang)
            assert result == expected_family, f"Expected {expected_family} for {lang}, got {result}"


class TestSimilarLanguageSuggestions:
    """Test similar language suggestion functionality."""
    
    def setup_method(self):
        """Reset LanguageManager for each test."""
        LanguageManager._instance = None
        self.lang_manager = LanguageManager()
    
    def test_suggest_similar_languages(self):
        """Test similar language suggestions."""
        suggestion_cases = [
            ("javascrip", ["javascript"]),  # Close match
            ("pytho", ["python"]),  # Close match
            ("typ", ["typescript"]),  # Partial match
            ("jav", ["java", "javascript"]),  # Multiple matches
        ]
        
        for input_lang, expected_suggestions in suggestion_cases:
            suggestions = self.lang_manager.suggest_similar_languages(input_lang)
            for expected in expected_suggestions:
                assert expected in suggestions, f"Expected {expected} in suggestions for {input_lang}"


class TestCaching:
    """Test caching behavior."""
    
    def setup_method(self):
        """Reset LanguageManager for each test."""
        LanguageManager._instance = None
        self.lang_manager = LanguageManager()
    
    def test_detection_caching(self):
        """Test that language detection results are cached."""
        filename = "test.js"
        
        # First detection
        result1 = self.lang_manager.detect_language(filename)
        
        # Second detection should use cache
        result2 = self.lang_manager.detect_language(filename)
        
        assert result1 == result2 == "javascript"
        
        # Verify cache contains the result
        cache_key = self.lang_manager._get_cache_key(filename, None)
        assert cache_key in self.lang_manager._cache


class TestIntegrity:
    """Test language mapping integrity validation."""
    
    def setup_method(self):
        """Reset LanguageManager for each test."""
        LanguageManager._instance = None
        self.lang_manager = LanguageManager()
    
    def test_validate_language_mapping_integrity(self):
        """Test language mapping integrity validation."""
        issues = self.lang_manager.validate_language_mapping_integrity()
        
        # Should not have critical integrity issues
        assert len(issues) == 0, f"Found integrity issues: {issues}"
    
    def test_create_language_mapping_report(self):
        """Test language mapping report generation."""
        report = self.lang_manager.create_language_mapping_report()
        
        # Verify report structure
        assert "total_languages" in report
        assert "extension_mappings" in report
        assert "tree_sitter_mappings" in report
        assert "aliases" in report
        assert "language_families" in report
        
        # Verify counts are reasonable
        assert report["total_languages"] >= 20
        assert len(report["extension_mappings"]) >= 30


class TestErrorHandling:
    """Test error handling and edge cases."""
    
    def setup_method(self):
        """Reset LanguageManager for each test."""
        LanguageManager._instance = None
        self.lang_manager = LanguageManager()
    
    def test_detect_language_none_filename(self):
        """Test detection with None filename."""
        result = self.lang_manager.detect_language(None)
        assert result == "text"
    
    def test_detect_language_empty_filename(self):
        """Test detection with empty filename."""
        result = self.lang_manager.detect_language("")
        assert result == "text"
    
    def test_detect_language_unknown_extension(self):
        """Test detection with unknown extension."""
        result = self.lang_manager.detect_language("file.unknown")
        assert result == "text"
    
    def test_validate_language_identifier_none(self):
        """Test validation with None identifier."""
        result = self.lang_manager.validate_language_identifier(None)
        assert result == False
    
    def test_validate_language_identifier_empty(self):
        """Test validation with empty identifier."""
        result = self.lang_manager.validate_language_identifier("")
        assert result == False


class TestRealWorldScenarios:
    """Test real-world usage scenarios."""
    
    def setup_method(self):
        """Reset LanguageManager for each test."""
        LanguageManager._instance = None
        self.lang_manager = LanguageManager()
    
    def test_project_file_detection(self):
        """Test detection for common project files."""
        project_files = [
            ("src/components/Button.tsx", "typescript"),
            ("lib/utils.js", "javascript"),
            ("main.py", "python"),
            ("main.rs", "rust"),
            ("main.go", "go"),
            ("App.java", "java"),
            ("main.c", "c"),
            ("main.cpp", "cpp"),
            ("Program.cs", "csharp"),
            ("index.php", "php"),
            ("app.rb", "ruby"),
            ("ViewController.swift", "swift"),
            ("MainActivity.kt", "kotlin"),
            ("Main.scala", "scala"),
            ("script.lua", "lua"),
            ("deploy.sh", "bash"),
            ("index.html", "html"),
            ("styles.css", "css"),
            ("config.json", "json"),
            ("docker-compose.yml", "yaml"),
        ]
        
        for filepath, expected_lang in project_files:
            detected = self.lang_manager.detect_language(filepath)
            assert detected == expected_lang, f"Expected {expected_lang} for {filepath}, got {detected}"
    
    def test_content_based_detection_realistic(self):
        """Test content-based detection with realistic code samples."""
        code_samples = [
            ("""
            function calculateSum(a, b) {
                return a + b;
            }
            """, "javascript"),
            ("""
            def calculate_sum(a: int, b: int) -> int:
                return a + b
            """, "python"),
            ("""
            fn calculate_sum(a: i32, b: i32) -> i32 {
                a + b
            }
            """, "rust"),
        ]
        
        for content, expected_lang in code_samples:
            detected = self.lang_manager.detect_language("unknown", content)
            assert detected == expected_lang, f"Expected {expected_lang} for content, got {detected}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 