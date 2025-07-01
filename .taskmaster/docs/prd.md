# **AST-Grep MCP Server - Product Requirements Document**

## **Executive Summary**

This document outlines the requirements for developing a Model Context Protocol (MCP) server that wraps around the ast-grep tool, enabling AI agents to perform structural code analysis and querying on codebases through a standardized interface.

## **Product Overview**

**Product Name**: AST-Grep MCP Server

**Purpose**: Provide AI agents with standardized access to ast-grep's abstract syntax tree (AST) analysis capabilities, allowing for structural code search, analysis, and call graph generation across multiple programming languages.

**Target Audience**: AI development teams, code analysis tools, and automated development workflows requiring deep code understanding.

## **Background and Context**

### **What is ast-grep?**

ast-grep is a **CLI tool for code structural search, lint, and rewriting written in Rust**[1]. It provides:

- **AST-based pattern matching** using tree-sitter parsers
- **Multi-language support** including JavaScript, TypeScript, Python, Rust, Go, Java, and many others[2]
- **Intuitive pattern syntax** that looks like ordinary code with meta-variables (e.g., `$MATCH`)
- **JSON output format** for programmatic consumption[3]
- **High performance** capable of processing thousands of files in sub-seconds[1]

### **What is MCP?**

The Model Context Protocol (MCP) is an **open standard that enables seamless integration between LLM applications and external data sources and tools**[4]. MCP servers expose three main capabilities:

- **Tools**: Functions for AI models to execute
- **Resources**: Read-only, addressable content entities
- **Prompts**: Templated messages and workflows

## **Technical Requirements**

### **Core Functionality**

#### **1. AST-Grep Integration**

**Primary Tools to Expose:**

- `ast_grep_search`: Execute pattern-based searches using ast-grep's pattern syntax[5]
- `ast_grep_scan`: Scan entire codebases with predefined rules[6]
- `ast_grep_run`: Run one-time queries with pattern and rewrite capabilities[6]

**Input Parameters:**
- `pattern`: AST pattern using ast-grep syntax (e.g., `console.log($GREETING)`)
- `language`: Target programming language (js, ts, py, rust, go, java, etc.)[2]
- `path`: File or directory path to analyze
- `recursive`: Boolean flag for recursive directory scanning
- `output_format`: JSON or text output format
- `rules_config`: Optional YAML configuration for custom rules[7]

**Output Format:**
- **JSON structured data** containing match objects with:
  - `text`: Matched code snippet
  - `range`: Line and column positions
  - `file`: File path
  - `metaVariables`: Captured meta-variable values
  - `language`: Detected programming language[3]

#### **2. Call Graph Generation**

**Approach:**
Since ast-grep doesn't natively generate call graphs, the MCP server will:

1. **Use ast-grep to identify function definitions** across supported languages
2. **Search for function calls** using pattern matching
3. **Build call graph relationships** by correlating definitions with calls
4. **Output structured call graph data** in JSON format

**Implementation Strategy:**
- **Function Definition Patterns**: Language-specific patterns to find function declarations
  - JavaScript/TypeScript: `function $NAME($ARGS) { $BODY }`
  - Python: `def $NAME($ARGS): $BODY`
  - Java: `$MODIFIERS $TYPE $NAME($ARGS) { $BODY }`
- **Function Call Patterns**: Identify function invocations using `$FUNC($ARGS)` patterns
- **Cross-reference Analysis**: Match calls to definitions by name and scope

#### **3. Documentation and Query Assistance**

**Resources to Expose:**
- `ast_grep_patterns`: Documentation of pattern syntax and examples[5]
- `ast_grep_languages`: List of supported languages and their identifiers[2]
- `ast_grep_examples`: Common use cases and pattern examples
- `call_graph_schema`: Schema definition for call graph output format

### **Supported Languages**

Based on ast-grep's built-in support[2], the MCP server will handle:

| **Language Domain** | **Supported Languages** |
|---------------------|------------------------|
| **System Programming** | C, C++, Rust |
| **Server-Side Programming** | Go, Java, Python, C# |
| **Web Development** | JavaScript, TypeScript (JSX/TSX), HTML, CSS |
| **Mobile Development** | Kotlin, Swift |
| **Configuration** | JSON, YAML |
| **Scripting & Others** | Lua, PHP, Ruby, Bash, Scala |

### **MCP Server Architecture**

#### **Tools Implementation**

```python
# Example tool structure
@mcp.tool()
def ast_grep_search(
    pattern: str,
    language: str,
    path: str,
    recursive: bool = True,
    output_format: str = "json"
) -> dict:
    """
    Execute AST-based pattern search using ast-grep
    
    Args:
        pattern: AST pattern (e.g., 'console.log($GREETING)')
        language: Programming language identifier
        path: File or directory path to search
        recursive: Search recursively in directories
        output_format: Output format (json/text)
    
    Returns:
        Structured search results with matches and metadata
    """
```

**Command Execution:**
- Execute ast-grep via subprocess with appropriate arguments
- Parse JSON output using `--json` flag[3]
- Handle errors and provide meaningful error messages
- Support interactive mode capabilities where applicable[6]

#### **Resources Implementation**

```python
@mcp.resource("ast_grep://patterns")
def get_pattern_documentation() -> str:
    """
    Provide comprehensive documentation of ast-grep pattern syntax
    """

@mcp.resource("ast_grep://languages")
def get_supported_languages() -> dict:
    """
    Return list of supported languages and their identifiers
    """

@mcp.resource("ast_grep://call_graph/{path}")
def get_call_graph(path: str) -> dict:
    """
    Generate and return call graph for specified codebase
    """
```

### **Call Graph Schema**

**Output Format:**
```json
{
  "nodes": [
    {
      "id": "function_unique_id",
      "name": "function_name", 
      "file": "path/to/file.py",
      "line": 42,
      "language": "python",
      "type": "function|method|constructor"
    }
  ],
  "edges": [
    {
      "source": "caller_function_id",
      "target": "callee_function_id",
      "call_site": {
        "file": "path/to/file.py",
        "line": 45,
        "column": 12
      }
    }
  ],
  "metadata": {
    "total_functions": 150,
    "total_calls": 320,
    "languages": ["python", "javascript"],
    "analysis_timestamp": "2025-06-30T17:49:00Z"
  }
}
```

## **Technical Specifications**

### **Dependencies**

**Core Requirements:**
- **Python 3.8+**
- **MCP Python SDK** (`@modelcontextprotocol/sdk`)[8]
- **ast-grep binary** (installable via npm, pip, or cargo)[1]

**Installation Methods:**
```bash
# Multiple installation options
npm install --global @ast-grep/cli
pip install ast-grep-cli  
cargo install ast-grep --locked
```

### **Configuration**

**Environment Variables:**
- `AST_GREP_BINARY_PATH`: Custom path to ast-grep executable
- `AST_GREP_MAX_FILES`: Maximum number of files to process (default: 10000)
- `AST_GREP_TIMEOUT`: Command execution timeout in seconds (default: 300)

**Project Configuration Support:**
- **sgconfig.yml discovery**: Automatically locate and use project configuration files[7]
- **Custom rule directories**: Support for custom rule sets and configurations
- **Language-specific settings**: Per-language configuration options

### **Error Handling**

**Robust Error Management:**
- **Binary availability checks**: Verify ast-grep installation on startup
- **Language validation**: Ensure requested language is supported
- **Path validation**: Verify file/directory existence and permissions
- **Timeout handling**: Prevent long-running operations from blocking
- **Graceful degradation**: Provide partial results when possible

### **Performance Considerations**

**Optimization Strategies:**
- **Concurrent processing**: Handle multiple requests efficiently
- **Result caching**: Cache frequently accessed analysis results
- **Resource limits**: Implement safeguards against resource exhaustion
- **Progressive results**: Stream results for large codebases when possible

## **Security Requirements**

**Security Measures:**
- **Path traversal protection**: Prevent access to unauthorized directories
- **Command injection prevention**: Sanitize all user inputs
- **Resource limits**: Prevent DoS through excessive resource consumption
- **Sandboxing**: Isolate ast-grep execution from sensitive system areas

## **Success Criteria**

**Functional Requirements:**
1. **Successfully execute ast-grep commands** through MCP tools interface
2. **Generate accurate call graphs** for supported programming languages  
3. **Provide comprehensive documentation** through MCP resources
4. **Handle multiple concurrent requests** efficiently
5. **Support all major programming languages** supported by ast-grep

**Performance Requirements:**
- **Response time**: < 5 seconds for typical single-file analysis
- **Throughput**: Handle 10+ concurrent requests
- **Scalability**: Process projects up to 100,000 files
- **Memory usage**: < 512MB baseline memory footprint

## **Future Enhancements**

**Phase 2 Considerations:**
- **Real-time code analysis**: Watch mode for live code changes
- **Custom rule creation**: AI-assisted rule generation
- **Integration with IDEs**: Language server protocol support
- **Advanced visualizations**: Interactive call graph rendering
- **Semantic analysis**: Beyond structural to semantic code understanding

## **Conclusion**

This MCP server will democratize access to powerful AST-based code analysis through a standardized interface, enabling AI agents to perform sophisticated code understanding tasks across multiple programming languages. The combination of ast-grep's performance and MCP's standardization creates a powerful foundation for AI-assisted development workflows.

[1] https://github.com/ast-grep/ast-grep
[2] https://github.com/Goldziher/tree-sitter-language-pack/
[3] https://github.com/modelcontextprotocol/python-sdk
[4] https://modelcontextprotocol.io/specification/2025-03-26
[5] https://ast-grep.github.io/guide/pattern-syntax.html
[6] https://ast-grep.github.io/guide/tooling-overview.html
[7] https://docs.rs/ast-grep-language/latest/ast_grep_language/
[8] https://github.com/ayush-3006/Mcpthings
[9] https://composio.dev/blog/mcp-server-step-by-step-guide-to-building-from-scrtch
[10] https://ast-grep.github.io/guide/api-usage/js-api.html
[11] https://www.anthropic.com/news/model-context-protocol
[12] https://github.com/kaianuar/mcp-server-guide
[13] https://mutable.ai/ast-grep/ast-grep
[14] https://github.com/modelcontextprotocol
[15] https://www.builder.io/blog/mcp-server
[16] https://github.com/koknat/callGraph
[17] https://ast-grep.github.io/advanced/pattern-parse.html
[18] https://resources.wolframcloud.com/PacletRepository/resources/AntonAntonov/CallGraph/
[19] https://ast-grep.github.io/reference/cli.html
[20] https://ast-grep.github.io/guide/rule-config/atomic-rule.html
[21] https://www.reddit.com/r/AI_Agents/comments/1k784co/has_any_one_here_developing_mcp_servers_from/
[22] https://milvus.io/ai-quick-reference/what-are-resources-in-model-context-protocol-mcp-and-how-do-i-expose-them
[23] https://ast-grep.github.io/guide/tools/json.html
[24] https://modelcontextprotocol.io/docs/concepts/tools
[25] https://www.speakeasy.com/mcp/resources
[26] https://mskelton.dev/bytes/structural-code-search-with-ast-grep
[27] https://ast-grep.github.io/guide/project/project-config.html
[28] https://www.byteplus.com/en/topic/542256
[29] https://docs.rs/crate/ast-grep-language/0.16.1
[30] https://www.byteplus.com/en/topic/542256?title=mcp-json-schema-validation-a-complete-guide
[31] https://ast-grep.github.io/reference/cli/run.html
[32] https://docs.rs/crate/ast-grep-language/latest
[33] https://hexdocs.pm/mcp_ex/MCPEx.Protocol.Schemas.html
[34] https://ast-grep.github.io/reference/languages.html
[35] https://github.com/Goldziher/tree-sitter-language-pack
[36] https://ast-grep.github.io/guide/introduction.html
[37] https://www.tkcnn.com/github/ast-grep/ast-grep.html
[38] https://github.com/coderabbitai/ast-grep-essentials
[39] https://pypi.org/project/tree-sitter-language-pack/
[40] https://en.wikipedia.org/wiki/Call_graph
[41] https://www.jetbrains.com/help/idea/dependencies-analysis.html
[42] https://github.com/zw-normal/pycallgraph
[43] https://www.cyfrin.io/blog/solidity-a-guide-to-internal-call-graphs-for-static-analysis
[44] https://github.com/multilang-depends/depends
[45] https://arxiv.org/pdf/2103.00587.pdf
[46] https://cerfacs.fr/coop/pycallgraph
[47] https://github.com/hannkinnei/depends_new
[48] https://ast-grep.github.io/guide/api-usage/py-api.html
[49] https://docs.anthropic.com/en/docs/mcp
[50] https://www.cs.umd.edu/~bhatele/pubs/pdf/2022/isc2022.pdf
[51] https://scrapfly.io/blog/how-to-build-an-mcp-server-in-python-a-complete-guide/
[52] https://ast-grep.github.io/reference/cli/scan.html
[53] https://ast-grep.github.io/reference/api.html
[54] https://github.com/vitsalis/PyCG
[55] https://stackoverflow.com/questions/5373714/how-to-generate-a-call-graph-for-c-code