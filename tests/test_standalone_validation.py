#!/usr/bin/env python3
"""Standalone test for Pydantic validation enhancements - extracted validation logic only."""

from typing import Optional, List
from pathlib import Path
import sys

# Mock dependencies
class MockField:
    def __init__(self, *args, **kwargs):
        self.description = kwargs.get('description', '')
        self.min_length = kwargs.get('min_length')
        self.max_length = kwargs.get('max_length')

def Field(*args, **kwargs):
    return MockField(*args, **kwargs)

class MockBaseModel:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)
        # Run validation
        self._validate()
    
    def _validate(self):
        # Find all validation methods and run them
        for attr_name in dir(self):
            if attr_name.startswith('validate_'):
                field_name = attr_name.replace('validate_', '')
                if hasattr(self, field_name):
                    validator = getattr(self, attr_name)
                    if callable(validator):
                        value = getattr(self, field_name)
                        validated_value = validator(value)
                        setattr(self, field_name, validated_value)

def field_validator(field_name):
    def decorator(func):
        return func
    return decorator

# Mock language manager
class MockLanguageManager:
    def validate_language_identifier(self, lang):
        valid_langs = ['javascript', 'python', 'js', 'py', 'typescript', 'ts']
        return lang in valid_langs
    
    def suggest_similar_languages(self, lang):
        return ['javascript', 'python']

def get_language_manager():
    return MockLanguageManager()

def sanitize_path(path_str):
    return Path(path_str).resolve()

# Now define the models with the validation logic
class CallGraphInput(MockBaseModel):
    """Input model for call_graph_generate tool."""
    
    def __init__(self, **kwargs):
        self.path = kwargs.get('path')
        self.languages = kwargs.get('languages')
        self.include_external = kwargs.get('include_external', False)
        super().__init__(**kwargs)
    
    @classmethod
    def validate_path(cls, v: str) -> str:
        """Validate and sanitize the directory path for analysis."""
        if not v or not v.strip():
            raise ValueError("Path cannot be empty")
        
        try:
            sanitized_path = sanitize_path(v.strip())
            return str(sanitized_path)
        except Exception as e:
            raise ValueError(f"Invalid path '{v}': {str(e)}")
    
    @classmethod
    def validate_languages(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        """Validate language identifiers using LanguageManager."""
        if v is None:
            return v
        
        if not isinstance(v, list):
            raise ValueError("Languages must be a list of language identifiers")
        
        if not v:  # Empty list
            return None
        
        # Validate list size constraints
        if len(v) > 20:
            raise ValueError(f"Too many languages specified ({len(v)}). Maximum allowed: 20")
        
        validated_languages = []
        lang_manager = get_language_manager()
        
        for i, lang in enumerate(v):
            if not isinstance(lang, str):
                raise ValueError(f"Language identifier at index {i} must be a string, got: {type(lang)}")
            
            # Validate individual string length
            if len(lang) > 50:
                raise ValueError(f"Language identifier at index {i} too long ({len(lang)} chars). Maximum: 50")
            
            lang_clean = lang.strip()
            if not lang_clean:
                continue
            
            # Check for dangerous characters in language identifiers
            dangerous_chars = [';', '&', '|', '`', '$', '(', ')', '<', '>', '"', "'"]
            for char in dangerous_chars:
                if char in lang_clean:
                    raise ValueError(f"Language identifier '{lang_clean}' contains dangerous character '{char}'")
            
            try:
                # Validate each language using LanguageManager
                validated = lang_manager.validate_language_identifier(lang_clean)
                if not validated:
                    # Get suggestions for similar languages
                    suggestions = lang_manager.suggest_similar_languages(lang_clean)
                    if suggestions:
                        raise ValueError(
                            f"Unsupported language '{lang_clean}'. Similar languages: {', '.join(suggestions[:3])}"
                        )
                    else:
                        raise ValueError(f"Unsupported language '{lang_clean}'. Check supported languages list.")
                
                validated_languages.append(lang_clean)
                
            except Exception as e:
                if isinstance(e, ValueError):
                    raise
                raise ValueError(f"Language validation failed for '{lang_clean}': {str(e)}")
        
        # Check for duplicate languages
        if len(validated_languages) != len(set(validated_languages)):
            duplicates = [lang for lang in set(validated_languages) if validated_languages.count(lang) > 1]
            raise ValueError(f"Duplicate languages found: {', '.join(duplicates)}")
        
        return validated_languages if validated_languages else None

class SearchToolInput(MockBaseModel):
    """Input model for ast_grep_search tool."""
    
    def __init__(self, **kwargs):
        self.pattern = kwargs.get('pattern')
        self.language = kwargs.get('language')
        self.path = kwargs.get('path')
        self.recursive = kwargs.get('recursive', True)
        self.output_format = kwargs.get('output_format', 'json')
        self.include_globs = kwargs.get('include_globs')
        self.exclude_globs = kwargs.get('exclude_globs')
        super().__init__(**kwargs)
    
    @classmethod
    def validate_include_globs(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        """Validate include glob patterns for security and correctness."""
        if v is None:
            return v
        
        if not isinstance(v, list):
            raise ValueError("Include globs must be a list of glob patterns")
        
        if not v:  # Empty list
            return None
        
        # Validate list size constraints
        if len(v) > 100:
            raise ValueError(f"Too many include globs specified ({len(v)}). Maximum allowed: 100")
        
        validated_globs = []
        for i, glob_pattern in enumerate(v):
            if not isinstance(glob_pattern, str):
                raise ValueError(f"Include glob at index {i} must be a string, got: {type(glob_pattern)}")
            
            pattern = glob_pattern.strip()
            if not pattern:
                continue
            
            # Validate individual glob length
            if len(pattern) > 200:
                raise ValueError(f"Include glob at index {i} too long ({len(pattern)} chars). Maximum: 200")
            
            # Enhanced security check for dangerous characters
            dangerous_patterns = [
                ';', '&&', '||', '`', '$(', '${', '<(', '>(', 
                '&', '|', '<', '>', '"', "'", '\n', '\r', '\t'
            ]
            
            for dangerous in dangerous_patterns:
                if dangerous in pattern:
                    raise ValueError(
                        f"Include glob '{pattern}' contains potentially dangerous character or sequence '{dangerous}'"
                    )
            
            # Validate glob pattern syntax (basic check)
            if pattern.count('[') != pattern.count(']'):
                raise ValueError(f"Include glob '{pattern}' has unmatched brackets")
            
            if pattern.count('{') != pattern.count('}'):
                raise ValueError(f"Include glob '{pattern}' has unmatched braces")
            
            # Prevent overly broad patterns that could cause performance issues
            if pattern in ['*', '**', '***', '/**', '/*']:
                raise ValueError(f"Include glob '{pattern}' is too broad and may cause performance issues")
            
            validated_globs.append(pattern)
        
        return validated_globs if validated_globs else None

def test_call_graph_validation():
    """Test CallGraphInput validation."""
    print("Testing CallGraphInput validation...")
    
    # Test valid input
    try:
        valid_input = CallGraphInput(
            path="./src",
            languages=["javascript", "python"],
            include_external=False
        )
        print("✅ Valid CallGraphInput passes")
    except Exception as e:
        print(f"❌ Valid input failed: {e}")
        return False
    
    # Test too many languages
    try:
        too_many_langs = ["js"] * 25
        CallGraphInput(
            path="./src",
            languages=too_many_langs,
            include_external=False
        )
        print("❌ Should have failed - too many languages")
        return False
    except ValueError as e:
        print(f"✅ Correctly rejected too many languages")
    
    # Test dangerous characters in language
    try:
        CallGraphInput(
            path="./src",
            languages=["javascript; rm -rf /"],
            include_external=False
        )
        print("❌ Should have failed - dangerous characters")
        return False
    except ValueError as e:
        print(f"✅ Correctly rejected dangerous characters")
    
    return True

def test_search_input_validation():
    """Test SearchToolInput validation."""
    print("\nTesting SearchToolInput validation...")
    
    # Test dangerous characters in globs
    try:
        SearchToolInput(
            pattern="test",
            language="javascript",
            path="./src",
            include_globs=["*.js && rm -rf /"]
        )
        print("❌ Should have failed - dangerous glob")
        return False
    except ValueError as e:
        print(f"✅ Correctly rejected dangerous glob")
    
    # Test overly broad patterns
    try:
        SearchToolInput(
            pattern="test",
            language="javascript",
            path="./src",
            include_globs=["*"]
        )
        print("❌ Should have failed - overly broad pattern")
        return False
    except ValueError as e:
        print(f"✅ Correctly rejected broad pattern")
    
    return True

def main():
    """Run validation tests."""
    print("🧪 Testing Pydantic Validation Enhancements")
    print("=" * 50)
    
    success = True
    success &= test_call_graph_validation()
    success &= test_search_input_validation()
    
    print("\n" + "=" * 50)
    if success:
        print("🎉 All validation tests PASSED!")
        return 0
    else:
        print("❌ Some validation tests FAILED!")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 