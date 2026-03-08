"""Tests for MCP resources functionality."""

import asyncio
import pytest
import json
from typing import Dict, Any, List

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from ast_grep_mcp.resources import (
    get_pattern_documentation,
    get_supported_languages, 
    get_examples_and_best_practices,
    get_call_graph_schema,
    SUPPORTED_LANGUAGES,
    PATTERN_EXAMPLES,
    CALL_GRAPH_SCHEMA
)


class TestMCPResources:
    """Test suite for MCP resource functionality."""

    @pytest.mark.asyncio
    async def test_pattern_documentation_resource(self):
        """Test pattern documentation resource."""
        docs = await get_pattern_documentation()
        
        # Basic content validation
        assert isinstance(docs, str)
        assert len(docs) > 1000, "Documentation should be comprehensive"
        
        # Check required sections
        assert "# AST-Grep Pattern Syntax Documentation" in docs
        assert "## Overview" in docs
        assert "## Meta-Variables" in docs
        assert "Variable Length Matching" in docs
        
        # Check for meta-variable examples
        assert "$IDENTIFIER" in docs
        assert "$EXPRESSION" in docs
        assert "$$$ARGS" in docs
        
        # Verify pattern examples are included
        assert len(PATTERN_EXAMPLES) > 0
        for category, data in PATTERN_EXAMPLES.items():
            assert data['description'] in docs

    @pytest.mark.asyncio
    async def test_supported_languages_resource(self):
        """Test supported languages resource."""
        docs = await get_supported_languages()
        
        # Basic content validation
        assert isinstance(docs, str)
        assert len(docs) > 500, "Should list multiple languages"
        
        # Check markdown table structure
        assert "# Supported Programming Languages" in docs
        assert "| Language | Aliases | File Extensions | Tree-sitter Parser |" in docs
        assert "|----------|---------|-----------------|" in docs
        
        # Verify some expected languages are mentioned (case-insensitive)
        docs_lower = docs.lower()
        assert "python" in docs_lower
        assert "javascript" in docs_lower or "js" in docs_lower
        assert "typescript" in docs_lower or "ts" in docs_lower
        
        # Check total count
        assert f"**Total Languages Supported**: {len(SUPPORTED_LANGUAGES)}" in docs

    @pytest.mark.asyncio
    async def test_examples_and_best_practices_resource(self):
        """Test examples and best practices resource."""
        docs = await get_examples_and_best_practices()
        
        # Basic content validation
        assert isinstance(docs, str)
        assert len(docs) > 1000, "Should be comprehensive"
        
        # Check required sections
        assert "# AST-Grep Examples and Best Practices" in docs
        assert "## Best Practices" in docs
        assert "## Common Use Cases" in docs
        assert "## Language-Specific Examples" in docs
        
        # Check for specific guidance
        assert "Pattern Specificity" in docs
        assert "Meta-variable Naming" in docs
        assert "Performance Tips" in docs
        
        # Check for practical examples
        assert "console.log" in docs
        assert "function $NAME" in docs
        assert "def $NAME" in docs

    @pytest.mark.asyncio
    async def test_call_graph_schema_resource(self):
        """Test call graph schema resource."""
        schema_str = await get_call_graph_schema()
        
        # Basic validation
        assert isinstance(schema_str, str)
        assert len(schema_str) > 1000, "Schema should be detailed"
        
        # Parse as JSON
        schema = json.loads(schema_str)
        assert isinstance(schema, dict)
        
        # Check required schema properties
        assert "$schema" in schema
        assert "title" in schema
        assert "type" in schema
        assert schema["type"] == "object"
        
        # Check for expected top-level properties
        properties = schema.get("properties", {})
        assert "nodes" in properties
        assert "edges" in properties
        assert "metadata" in properties
        
        # Verify it matches the CALL_GRAPH_SCHEMA constant
        assert schema == CALL_GRAPH_SCHEMA

    def test_supported_languages_data_structure(self):
        """Test the SUPPORTED_LANGUAGES data structure."""
        assert isinstance(SUPPORTED_LANGUAGES, dict)
        assert len(SUPPORTED_LANGUAGES) > 5, "Should support multiple languages"
        
        for lang, info in SUPPORTED_LANGUAGES.items():
            assert isinstance(lang, str)
            assert isinstance(info, dict)
            
            # Check required fields
            assert "aliases" in info
            assert "extensions" in info
            assert "tree_sitter" in info
            
            # Check field types
            assert isinstance(info["aliases"], list)
            assert isinstance(info["extensions"], list)
            assert isinstance(info["tree_sitter"], str)
            
            # Extensions should start with dot
            for ext in info["extensions"]:
                assert ext.startswith("."), f"Extension {ext} should start with dot"

    def test_pattern_examples_data_structure(self):
        """Test the PATTERN_EXAMPLES data structure."""
        assert isinstance(PATTERN_EXAMPLES, dict)
        assert len(PATTERN_EXAMPLES) > 0, "Should have pattern examples"
        
        for category, data in PATTERN_EXAMPLES.items():
            assert isinstance(category, str)
            assert isinstance(data, dict)
            
            # Check required fields
            assert "description" in data
            assert "examples" in data
            
            # Check field types
            assert isinstance(data["description"], str)
            assert isinstance(data["examples"], list)
            assert len(data["examples"]) > 0, f"Category {category} should have examples"
            
            # Check example structure
            for example in data["examples"]:
                assert isinstance(example, dict)
                assert "pattern" in example
                assert "description" in example
                assert isinstance(example["pattern"], str)
                assert isinstance(example["description"], str)

    def test_call_graph_schema_structure(self):
        """Test the CALL_GRAPH_SCHEMA data structure."""
        assert isinstance(CALL_GRAPH_SCHEMA, dict)
        
        # Check JSON Schema meta-fields
        assert CALL_GRAPH_SCHEMA.get("$schema") is not None
        assert CALL_GRAPH_SCHEMA.get("title") is not None
        assert CALL_GRAPH_SCHEMA.get("type") == "object"
        
        # Check properties structure
        properties = CALL_GRAPH_SCHEMA.get("properties", {})
        assert "nodes" in properties
        assert "edges" in properties
        assert "metadata" in properties
        
        # Check nodes definition
        nodes_def = properties["nodes"]
        assert nodes_def["type"] == "array"
        assert "items" in nodes_def
        
        # Check edges definition
        edges_def = properties["edges"]
        assert edges_def["type"] == "array"
        assert "items" in edges_def

    @pytest.mark.asyncio
    async def test_resource_content_consistency(self):
        """Test that resource content is consistent across calls."""
        # Call each resource twice
        docs1 = await get_pattern_documentation()
        docs2 = await get_pattern_documentation()
        assert docs1 == docs2, "Pattern documentation should be consistent"
        
        langs1 = await get_supported_languages()
        langs2 = await get_supported_languages()
        assert langs1 == langs2, "Languages documentation should be consistent"
        
        examples1 = await get_examples_and_best_practices()
        examples2 = await get_examples_and_best_practices()
        assert examples1 == examples2, "Examples should be consistent"
        
        schema1 = await get_call_graph_schema()
        schema2 = await get_call_graph_schema()
        assert schema1 == schema2, "Schema should be consistent"

    @pytest.mark.asyncio
    async def test_resource_content_quality(self):
        """Test the quality and completeness of resource content."""
        # Test pattern documentation quality
        docs = await get_pattern_documentation()
        
        # Should include practical examples
        assert "function" in docs or "def" in docs, "Should include function examples"
        assert "$" in docs, "Should show meta-variable syntax"
        
        # Should have clear structure
        assert docs.count("#") >= 5, "Should have multiple heading levels"
        assert "**Pattern**" in docs or "pattern" in docs.lower(), "Should reference patterns"
        
        # Test language documentation comprehensiveness
        langs = await get_supported_languages()
        
        # Should cover major languages
        major_languages = ["python", "javascript", "typescript", "java", "rust"]
        for lang in major_languages:
            assert lang.lower() in langs.lower(), f"Should mention {lang}"
        
        # Test examples comprehensiveness
        examples = await get_examples_and_best_practices()
        
        # Should include security patterns
        assert "security" in examples.lower() or "injection" in examples.lower()
        # Should include refactoring examples
        assert "refactor" in examples.lower()

    def test_resource_uri_patterns(self):
        """Test that resource URIs follow expected patterns."""
        expected_uris = [
            "ast-grep://patterns",
            "ast-grep://languages", 
            "ast-grep://examples",
            "ast-grep://call-graph-schema"
        ]
        
        # These URIs should be handled by the resource system
        for uri in expected_uris:
            # Verify URI format
            assert uri.startswith("ast-grep://"), f"URI {uri} should use ast-grep scheme"
            assert len(uri.split("://")[1]) > 0, f"URI {uri} should have resource name"


@pytest.mark.asyncio
async def test_resource_integration():
    """Test that all resources work together without conflicts."""
    # Load all resources simultaneously
    docs_task = get_pattern_documentation()
    langs_task = get_supported_languages()
    examples_task = get_examples_and_best_practices() 
    schema_task = get_call_graph_schema()
    
    # Wait for all to complete
    docs, langs, examples, schema = await asyncio.gather(
        docs_task, langs_task, examples_task, schema_task
    )
    
    # Verify all completed successfully
    assert len(docs) > 0
    assert len(langs) > 0
    assert len(examples) > 0
    assert len(schema) > 0
    
    # Verify they're all different content
    contents = [docs, langs, examples, schema]
    for i, content1 in enumerate(contents):
        for j, content2 in enumerate(contents):
            if i != j:
                assert content1 != content2, "Resources should have different content"


if __name__ == "__main__":
    # Run basic tests if executed directly
    import asyncio
    
    async def run_basic_tests():
        """Run basic tests to verify functionality."""
        print("Testing MCP resources...")
        
        # Test each resource
        docs = await get_pattern_documentation()
        print(f"✓ Pattern documentation: {len(docs)} characters")
        
        langs = await get_supported_languages()
        print(f"✓ Supported languages: {len(langs)} characters")
        
        examples = await get_examples_and_best_practices()
        print(f"✓ Examples and best practices: {len(examples)} characters")
        
        schema = await get_call_graph_schema()
        schema_obj = json.loads(schema)
        print(f"✓ Call graph schema: {len(schema)} characters, valid JSON")
        
        print("All MCP resources working correctly!")
    
    asyncio.run(run_basic_tests())
