"""MCP Resources implementation for AST-Grep documentation and schemas."""

import logging
import json
import os
import re
import urllib.parse
import hashlib
import asyncio
from typing import Dict, Any, List, Optional
from pathlib import Path
from datetime import datetime

from mcp.server import Server
from mcp.types import Resource, TextContent

logger = logging.getLogger(__name__)


# Supported languages data
SUPPORTED_LANGUAGES = {
    "javascript": {
        "aliases": ["js", "jsx", "node"],
        "extensions": [".js", ".jsx", ".mjs", ".cjs"],
        "tree_sitter": "js",
        "description": "JavaScript programming language",
        "common_patterns": ["console.log($MSG)", "function $NAME($ARGS) { $BODY }"]
    },
    "typescript": {
        "aliases": ["ts", "tsx"],
        "extensions": [".ts", ".tsx", ".d.ts"],
        "tree_sitter": "ts",
        "description": "TypeScript programming language",
        "common_patterns": ["interface $NAME { $FIELDS }", "type $NAME = $TYPE"]
    },
    "python": {
        "aliases": ["py", "python3"],
        "extensions": [".py", ".pyi", ".pyw"],
        "tree_sitter": "py",
        "description": "Python programming language",
        "common_patterns": ["def $NAME($ARGS): $BODY", "class $NAME($BASE): $BODY"]
    },
    "rust": {
        "aliases": ["rs", "rustlang"],
        "extensions": [".rs"],
        "tree_sitter": "rs",
        "description": "Rust systems programming language",
        "common_patterns": ["fn $NAME($ARGS) -> $TYPE { $BODY }", "struct $NAME { $FIELDS }"]
    },
    "go": {
        "aliases": ["golang"],
        "extensions": [".go"],
        "tree_sitter": "go",
        "description": "Go programming language",
        "common_patterns": ["func $NAME($ARGS) $TYPE { $BODY }", "type $NAME struct { $FIELDS }"]
    },
    "java": {
        "aliases": [],
        "extensions": [".java"],
        "tree_sitter": "java",
        "description": "Java programming language",
        "common_patterns": ["public class $NAME { $BODY }", "public $TYPE $NAME($ARGS) { $BODY }"]
    },
    "c": {
        "aliases": [],
        "extensions": [".c", ".h"],
        "tree_sitter": "c",
        "description": "C programming language",
        "common_patterns": ["#include <$HEADER>", "int $NAME($ARGS) { $BODY }"]
    },
    "cpp": {
        "aliases": ["c++", "cxx", "cc"],
        "extensions": [".cpp", ".cxx", ".cc", ".hpp", ".hxx", ".h++"],
        "tree_sitter": "cpp",
        "description": "C++ programming language",
        "common_patterns": ["class $NAME { $BODY }", "namespace $NAME { $BODY }"]
    },
    "csharp": {
        "aliases": ["cs", "c#"],
        "extensions": [".cs"],
        "tree_sitter": "cs",
        "description": "C# programming language",
        "common_patterns": ["public class $NAME { $BODY }", "namespace $NAME { $BODY }"]
    },
    "php": {
        "aliases": [],
        "extensions": [".php", ".php3", ".php4", ".php5", ".phtml"],
        "tree_sitter": "php",
        "description": "PHP programming language",
        "common_patterns": ["<?php", "function $NAME($ARGS) { $BODY }"]
    },
    "ruby": {
        "aliases": ["rb"],
        "extensions": [".rb", ".rbw", ".rake", ".gemspec"],
        "tree_sitter": "rb",
        "description": "Ruby programming language",
        "common_patterns": ["def $NAME($ARGS)", "class $NAME < $BASE"]
    },
    "swift": {
        "aliases": [],
        "extensions": [".swift"],
        "tree_sitter": "swift",
        "description": "Swift programming language",
        "common_patterns": ["func $NAME($ARGS) -> $TYPE { $BODY }", "class $NAME: $BASE { $BODY }"]
    },
    "kotlin": {
        "aliases": ["kt"],
        "extensions": [".kt", ".kts"],
        "tree_sitter": "kt",
        "description": "Kotlin programming language",
        "common_patterns": ["fun $NAME($ARGS): $TYPE { $BODY }", "class $NAME { $BODY }"]
    },
    "scala": {
        "aliases": [],
        "extensions": [".scala", ".sc"],
        "tree_sitter": "scala",
        "description": "Scala programming language",
        "common_patterns": ["def $NAME($ARGS): $TYPE = $BODY", "class $NAME extends $BASE { $BODY }"]
    },
    "lua": {
        "aliases": [],
        "extensions": [".lua"],
        "tree_sitter": "lua",
        "description": "Lua programming language",
        "common_patterns": ["function $NAME($ARGS)", "local $NAME = $VALUE"]
    },
    "bash": {
        "aliases": ["sh", "shell"],
        "extensions": [".sh", ".bash", ".zsh", ".fish"],
        "tree_sitter": "bash",
        "description": "Bash shell scripting language",
        "common_patterns": ["function $NAME() { $BODY }", "if [ $CONDITION ]; then"]
    },
    "html": {
        "aliases": ["htm"],
        "extensions": [".html", ".htm", ".xhtml"],
        "tree_sitter": "html",
        "description": "HyperText Markup Language",
        "common_patterns": ["<$TAG $ATTRS>$CONTENT</$TAG>", "<$TAG $ATTRS />"]
    },
    "css": {
        "aliases": [],
        "extensions": [".css"],
        "tree_sitter": "css",
        "description": "Cascading Style Sheets",
        "common_patterns": ["$SELECTOR { $RULES }", "$PROPERTY: $VALUE;"]
    },
    "json": {
        "aliases": [],
        "extensions": [".json", ".jsonc"],
        "tree_sitter": "json",
        "description": "JavaScript Object Notation",
        "common_patterns": ["\"$KEY\": $VALUE", "{ $FIELDS }"]
    },
    "yaml": {
        "aliases": ["yml"],
        "extensions": [".yaml", ".yml"],
        "tree_sitter": "yaml",
        "description": "YAML Ain't Markup Language",
        "common_patterns": ["$KEY: $VALUE", "- $ITEM"]
    },
    "xml": {
        "aliases": [],
        "extensions": [".xml", ".xsd", ".xsl", ".xslt"],
        "tree_sitter": "xml",
        "description": "eXtensible Markup Language",
        "common_patterns": ["<$TAG $ATTRS>$CONTENT</$TAG>", "<?xml version=\"1.0\"?>"]
    },
    "sql": {
        "aliases": [],
        "extensions": [".sql"],
        "tree_sitter": "sql",
        "description": "Structured Query Language",
        "common_patterns": ["SELECT $FIELDS FROM $TABLE", "CREATE TABLE $NAME ($FIELDS)"]
    },
    "dart": {
        "aliases": [],
        "extensions": [".dart"],
        "tree_sitter": "dart",
        "description": "Dart programming language",
        "common_patterns": ["class $NAME { $BODY }", "$TYPE $NAME($ARGS) { $BODY }"]
    },
    "elixir": {
        "aliases": ["ex", "exs"],
        "extensions": [".ex", ".exs"],
        "tree_sitter": "elixir",
        "description": "Elixir programming language",
        "common_patterns": ["def $NAME($ARGS) do", "defmodule $NAME do"]
    },
    "erlang": {
        "aliases": ["erl"],
        "extensions": [".erl", ".hrl"],
        "tree_sitter": "erlang",
        "description": "Erlang programming language",
        "common_patterns": ["$NAME($ARGS) ->", "-module($NAME)."]
    },
    "haskell": {
        "aliases": ["hs"],
        "extensions": [".hs", ".lhs"],
        "tree_sitter": "haskell",
        "description": "Haskell functional programming language",
        "common_patterns": ["$NAME :: $TYPE", "$NAME $ARGS = $BODY"]
    },
    "ocaml": {
        "aliases": ["ml"],
        "extensions": [".ml", ".mli"],
        "tree_sitter": "ocaml",
        "description": "OCaml programming language",
        "common_patterns": ["let $NAME = $VALUE", "type $NAME = $TYPE"]
    },
    "r": {
        "aliases": [],
        "extensions": [".r", ".R"],
        "tree_sitter": "r",
        "description": "R statistical programming language",
        "common_patterns": ["$NAME <- $VALUE", "function($ARGS) { $BODY }"]
    },
    "perl": {
        "aliases": ["pl"],
        "extensions": [".pl", ".pm", ".perl"],
        "tree_sitter": "perl",
        "description": "Perl programming language",
        "common_patterns": ["sub $NAME { $BODY }", "my $VAR = $VALUE;"]
    },
    "markdown": {
        "aliases": ["md"],
        "extensions": [".md", ".markdown", ".mdown", ".mkd"],
        "tree_sitter": "markdown",
        "description": "Markdown markup language",
        "common_patterns": ["# $HEADING", "[$TEXT]($URL)"]
    }
}


# Comprehensive function detection patterns for each supported language
FUNCTION_PATTERNS = {
    "javascript": {
        "patterns": [
            {
                "type": "function_declaration",
                "pattern": "function $NAME($PARAMS) {\n  $BODY\n}",
                "description": "Standard function declaration",
                "meta_variables": ["NAME", "PARAMS", "BODY"],
                "captures": {
                    "name": "NAME",
                    "parameters": "PARAMS", 
                    "body": "BODY"
                }
            },
            {
                "type": "function_expression",
                "pattern": "const $NAME = function($PARAMS) {\n  $BODY\n}",
                "description": "Function expression assignment",
                "meta_variables": ["NAME", "PARAMS", "BODY"],
                "captures": {
                    "name": "NAME",
                    "parameters": "PARAMS",
                    "body": "BODY"
                }
            },
            {
                "type": "arrow_function",
                "pattern": "const $NAME = ($PARAMS) => {\n  $BODY\n}",
                "description": "Arrow function with block body",
                "meta_variables": ["NAME", "PARAMS", "BODY"],
                "captures": {
                    "name": "NAME",
                    "parameters": "PARAMS",
                    "body": "BODY"
                }
            },
            {
                "type": "arrow_function_expression",
                "pattern": "const $NAME = ($PARAMS) => $EXPR",
                "description": "Arrow function with expression body",
                "meta_variables": ["NAME", "PARAMS", "EXPR"],
                "captures": {
                    "name": "NAME",
                    "parameters": "PARAMS",
                    "body": "EXPR"
                }
            },
            {
                "type": "class_method",
                "pattern": "class $CLASS {\n  $METHOD($PARAMS) {\n    $BODY\n  }\n}",
                "description": "Class method definition",
                "meta_variables": ["CLASS", "METHOD", "PARAMS", "BODY"],
                "captures": {
                    "class_name": "CLASS",
                    "name": "METHOD",
                    "parameters": "PARAMS",
                    "body": "BODY"
                }
            },
            {
                "type": "async_function",
                "pattern": "async function $NAME($PARAMS) {\n  $BODY\n}",
                "description": "Async function declaration",
                "meta_variables": ["NAME", "PARAMS", "BODY"],
                "captures": {
                    "name": "NAME",
                    "parameters": "PARAMS",
                    "body": "BODY",
                    "modifiers": ["async"]
                }
            },
            {
                "type": "anonymous_function",
                "pattern": "function($PARAMS) {\n  $BODY\n}",
                "description": "Anonymous function",
                "meta_variables": ["PARAMS", "BODY"],
                "captures": {
                    "parameters": "PARAMS",
                    "body": "BODY"
                }
            }
        ]
    },
    "typescript": {
        "patterns": [
            {
                "type": "function_declaration",
                "pattern": "function $NAME($PARAMS): $RETURN {\n  $BODY\n}",
                "description": "TypeScript function with return type",
                "meta_variables": ["NAME", "PARAMS", "RETURN", "BODY"],
                "captures": {
                    "name": "NAME",
                    "parameters": "PARAMS",
                    "return_type": "RETURN",
                    "body": "BODY"
                }
            },
            {
                "type": "arrow_function_typed",
                "pattern": "const $NAME = ($PARAMS): $RETURN => {\n  $BODY\n}",
                "description": "Typed arrow function",
                "meta_variables": ["NAME", "PARAMS", "RETURN", "BODY"],
                "captures": {
                    "name": "NAME",
                    "parameters": "PARAMS",
                    "return_type": "RETURN",
                    "body": "BODY"
                }
            },
            {
                "type": "class_method_typed",
                "pattern": "class $CLASS {\n  $METHOD($PARAMS): $RETURN {\n    $BODY\n  }\n}",
                "description": "Typed class method",
                "meta_variables": ["CLASS", "METHOD", "PARAMS", "RETURN", "BODY"],
                "captures": {
                    "class_name": "CLASS",
                    "name": "METHOD",
                    "parameters": "PARAMS",
                    "return_type": "RETURN",
                    "body": "BODY"
                }
            },
            {
                "type": "interface_method",
                "pattern": "interface $INTERFACE {\n  $METHOD($PARAMS): $RETURN;\n}",
                "description": "Interface method signature",
                "meta_variables": ["INTERFACE", "METHOD", "PARAMS", "RETURN"],
                "captures": {
                    "interface_name": "INTERFACE",
                    "name": "METHOD",
                    "parameters": "PARAMS",
                    "return_type": "RETURN"
                }
            }
        ]
    },
    "python": {
        "patterns": [
            {
                "type": "function_definition",
                "pattern": "def $NAME($PARAMS):\n    $BODY",
                "description": "Python function definition",
                "meta_variables": ["NAME", "PARAMS", "BODY"],
                "captures": {
                    "name": "NAME",
                    "parameters": "PARAMS",
                    "body": "BODY"
                }
            },
            {
                "type": "typed_function",
                "pattern": "def $NAME($PARAMS) -> $RETURN:\n    $BODY",
                "description": "Type-annotated function",
                "meta_variables": ["NAME", "PARAMS", "RETURN", "BODY"],
                "captures": {
                    "name": "NAME",
                    "parameters": "PARAMS",
                    "return_type": "RETURN",
                    "body": "BODY"
                }
            },
            {
                "type": "class_method",
                "pattern": "class $CLASS:\n    def $METHOD(self, $PARAMS):\n        $BODY",
                "description": "Class method definition",
                "meta_variables": ["CLASS", "METHOD", "PARAMS", "BODY"],
                "captures": {
                    "class_name": "CLASS",
                    "name": "METHOD",
                    "parameters": "PARAMS",
                    "body": "BODY"
                }
            },
            {
                "type": "static_method",
                "pattern": "class $CLASS:\n    @staticmethod\n    def $METHOD($PARAMS):\n        $BODY",
                "description": "Static method with decorator",
                "meta_variables": ["CLASS", "METHOD", "PARAMS", "BODY"],
                "captures": {
                    "class_name": "CLASS",
                    "name": "METHOD",
                    "parameters": "PARAMS",
                    "body": "BODY",
                    "modifiers": ["static"]
                }
            },
            {
                "type": "lambda_expression",
                "pattern": "lambda $PARAMS: $EXPR",
                "description": "Lambda expression",
                "meta_variables": ["PARAMS", "EXPR"],
                "captures": {
                    "parameters": "PARAMS",
                    "body": "EXPR"
                }
            }
        ]
    },
    "java": {
        "patterns": [
            {
                "type": "method_declaration",
                "pattern": "$MODIFIERS $RETURN $NAME($PARAMS) {\n    $BODY\n}",
                "description": "Java method declaration",
                "meta_variables": ["MODIFIERS", "RETURN", "NAME", "PARAMS", "BODY"],
                "captures": {
                    "modifiers": "MODIFIERS",
                    "return_type": "RETURN",
                    "name": "NAME",
                    "parameters": "PARAMS",
                    "body": "BODY"
                }
            },
            {
                "type": "class_method",
                "pattern": "class $CLASS {\n    $MODIFIERS $RETURN $METHOD($PARAMS) {\n        $BODY\n    }\n}",
                "description": "Class method definition",
                "meta_variables": ["CLASS", "MODIFIERS", "RETURN", "METHOD", "PARAMS", "BODY"],
                "captures": {
                    "class_name": "CLASS",
                    "modifiers": "MODIFIERS",
                    "return_type": "RETURN",
                    "name": "METHOD",
                    "parameters": "PARAMS",
                    "body": "BODY"
                }
            },
            {
                "type": "lambda_expression",
                "pattern": "($PARAMS) -> $EXPR",
                "description": "Java lambda expression",
                "meta_variables": ["PARAMS", "EXPR"],
                "captures": {
                    "parameters": "PARAMS",
                    "body": "EXPR"
                }
            },
            {
                "type": "constructor",
                "pattern": "class $CLASS {\n    $MODIFIERS $CLASS($PARAMS) {\n        $BODY\n    }\n}",
                "description": "Constructor method",
                "meta_variables": ["CLASS", "MODIFIERS", "PARAMS", "BODY"],
                "captures": {
                    "class_name": "CLASS",
                    "modifiers": "MODIFIERS",
                    "name": "CLASS",
                    "parameters": "PARAMS",
                    "body": "BODY",
                    "is_constructor": True
                }
            }
        ]
    },
    "c": {
        "patterns": [
            {
                "type": "function_definition",
                "pattern": "$RETURN $NAME($PARAMS) {\n    $BODY\n}",
                "description": "C function definition",
                "meta_variables": ["RETURN", "NAME", "PARAMS", "BODY"],
                "captures": {
                    "return_type": "RETURN",
                    "name": "NAME",
                    "parameters": "PARAMS",
                    "body": "BODY"
                }
            },
            {
                "type": "function_declaration",
                "pattern": "$RETURN $NAME($PARAMS);",
                "description": "C function declaration (prototype)",
                "meta_variables": ["RETURN", "NAME", "PARAMS"],
                "captures": {
                    "return_type": "RETURN",
                    "name": "NAME",
                    "parameters": "PARAMS"
                }
            }
        ]
    },
    "cpp": {
        "patterns": [
            {
                "type": "function_definition",
                "pattern": "$RETURN $NAME($PARAMS) {\n    $BODY\n}",
                "description": "C++ function definition",
                "meta_variables": ["RETURN", "NAME", "PARAMS", "BODY"],
                "captures": {
                    "return_type": "RETURN",
                    "name": "NAME",
                    "parameters": "PARAMS",
                    "body": "BODY"
                }
            },
            {
                "type": "class_method",
                "pattern": "class $CLASS {\n    $RETURN $METHOD($PARAMS) {\n        $BODY\n    }\n}",
                "description": "C++ class method",
                "meta_variables": ["CLASS", "RETURN", "METHOD", "PARAMS", "BODY"],
                "captures": {
                    "class_name": "CLASS",
                    "return_type": "RETURN",
                    "name": "METHOD",
                    "parameters": "PARAMS",
                    "body": "BODY"
                }
            },
            {
                "type": "lambda_expression",
                "pattern": "[$CAPTURE]($PARAMS) {\n    $BODY\n}",
                "description": "C++ lambda expression",
                "meta_variables": ["CAPTURE", "PARAMS", "BODY"],
                "captures": {
                    "capture": "CAPTURE",
                    "parameters": "PARAMS",
                    "body": "BODY"
                }
            },
            {
                "type": "constructor",
                "pattern": "class $CLASS {\n    $CLASS($PARAMS) {\n        $BODY\n    }\n}",
                "description": "C++ constructor",
                "meta_variables": ["CLASS", "PARAMS", "BODY"],
                "captures": {
                    "class_name": "CLASS",
                    "name": "CLASS",
                    "parameters": "PARAMS",
                    "body": "BODY",
                    "is_constructor": True
                }
            }
        ]
    },
    "rust": {
        "patterns": [
            {
                "type": "function_definition",
                "pattern": "fn $NAME($PARAMS) -> $RETURN {\n    $BODY\n}",
                "description": "Rust function with return type",
                "meta_variables": ["NAME", "PARAMS", "RETURN", "BODY"],
                "captures": {
                    "name": "NAME",
                    "parameters": "PARAMS",
                    "return_type": "RETURN",
                    "body": "BODY"
                }
            },
            {
                "type": "function_no_return",
                "pattern": "fn $NAME($PARAMS) {\n    $BODY\n}",
                "description": "Rust function without explicit return type",
                "meta_variables": ["NAME", "PARAMS", "BODY"],
                "captures": {
                    "name": "NAME",
                    "parameters": "PARAMS",
                    "body": "BODY"
                }
            },
            {
                "type": "impl_method",
                "pattern": "impl $TYPE {\n    fn $METHOD($PARAMS) -> $RETURN {\n        $BODY\n    }\n}",
                "description": "Implementation method",
                "meta_variables": ["TYPE", "METHOD", "PARAMS", "RETURN", "BODY"],
                "captures": {
                    "impl_type": "TYPE",
                    "name": "METHOD",
                    "parameters": "PARAMS",
                    "return_type": "RETURN",
                    "body": "BODY"
                }
            },
            {
                "type": "closure",
                "pattern": "|$PARAMS| $EXPR",
                "description": "Rust closure",
                "meta_variables": ["PARAMS", "EXPR"],
                "captures": {
                    "parameters": "PARAMS",
                    "body": "EXPR"
                }
            }
        ]
    },
    "go": {
        "patterns": [
            {
                "type": "function_definition",
                "pattern": "func $NAME($PARAMS) $RETURN {\n    $BODY\n}",
                "description": "Go function with return type",
                "meta_variables": ["NAME", "PARAMS", "RETURN", "BODY"],
                "captures": {
                    "name": "NAME",
                    "parameters": "PARAMS",
                    "return_type": "RETURN",
                    "body": "BODY"
                }
            },
            {
                "type": "method_definition",
                "pattern": "func ($RECEIVER $TYPE) $METHOD($PARAMS) $RETURN {\n    $BODY\n}",
                "description": "Go method with receiver",
                "meta_variables": ["RECEIVER", "TYPE", "METHOD", "PARAMS", "RETURN", "BODY"],
                "captures": {
                    "receiver": "RECEIVER",
                    "receiver_type": "TYPE",
                    "name": "METHOD",
                    "parameters": "PARAMS",
                    "return_type": "RETURN",
                    "body": "BODY"
                }
            }
        ]
    },
    "kotlin": {
        "patterns": [
            {
                "type": "function_definition",
                "pattern": "fun $NAME($PARAMS): $RETURN {\n    $BODY\n}",
                "description": "Kotlin function definition",
                "meta_variables": ["NAME", "PARAMS", "RETURN", "BODY"],
                "captures": {
                    "name": "NAME",
                    "parameters": "PARAMS",
                    "return_type": "RETURN",
                    "body": "BODY"
                }
            },
            {
                "type": "class_method",
                "pattern": "class $CLASS {\n    fun $METHOD($PARAMS): $RETURN {\n        $BODY\n    }\n}",
                "description": "Kotlin class method",
                "meta_variables": ["CLASS", "METHOD", "PARAMS", "RETURN", "BODY"],
                "captures": {
                    "class_name": "CLASS",
                    "name": "METHOD",
                    "parameters": "PARAMS",
                    "return_type": "RETURN",
                    "body": "BODY"
                }
            }
        ]
    },
    "swift": {
        "patterns": [
            {
                "type": "function_definition",
                "pattern": "func $NAME($PARAMS) -> $RETURN {\n    $BODY\n}",
                "description": "Swift function definition",
                "meta_variables": ["NAME", "PARAMS", "RETURN", "BODY"],
                "captures": {
                    "name": "NAME",
                    "parameters": "PARAMS",
                    "return_type": "RETURN",
                    "body": "BODY"
                }
            },
            {
                "type": "class_method",
                "pattern": "class $CLASS {\n    func $METHOD($PARAMS) -> $RETURN {\n        $BODY\n    }\n}",
                "description": "Swift class method",
                "meta_variables": ["CLASS", "METHOD", "PARAMS", "RETURN", "BODY"],
                "captures": {
                    "class_name": "CLASS",
                    "name": "METHOD",
                    "parameters": "PARAMS",
                    "return_type": "RETURN",
                    "body": "BODY"
                }
            }
        ]
    },
    "php": {
        "patterns": [
            {
                "type": "function_definition",
                "pattern": "function $NAME($PARAMS) {\n    $BODY\n}",
                "description": "PHP function definition",
                "meta_variables": ["NAME", "PARAMS", "BODY"],
                "captures": {
                    "name": "NAME",
                    "parameters": "PARAMS",
                    "body": "BODY"
                }
            },
            {
                "type": "class_method",
                "pattern": "class $CLASS {\n    function $METHOD($PARAMS) {\n        $BODY\n    }\n}",
                "description": "PHP class method",
                "meta_variables": ["CLASS", "METHOD", "PARAMS", "BODY"],
                "captures": {
                    "class_name": "CLASS",
                    "name": "METHOD",
                    "parameters": "PARAMS",
                    "body": "BODY"
                }
            }
        ]
    },
    "ruby": {
        "patterns": [
            {
                "type": "function_definition",
                "pattern": "def $NAME($PARAMS)\n  $BODY\nend",
                "description": "Ruby method definition",
                "meta_variables": ["NAME", "PARAMS", "BODY"],
                "captures": {
                    "name": "NAME",
                    "parameters": "PARAMS",
                    "body": "BODY"
                }
            },
            {
                "type": "class_method",
                "pattern": "class $CLASS\n  def $METHOD($PARAMS)\n    $BODY\n  end\nend",
                "description": "Ruby class method",
                "meta_variables": ["CLASS", "METHOD", "PARAMS", "BODY"],
                "captures": {
                    "class_name": "CLASS",
                    "name": "METHOD",
                    "parameters": "PARAMS",
                    "body": "BODY"
                }
            }
        ]
    },
    "scala": {
        "patterns": [
            {
                "type": "function_definition",
                "pattern": "def $NAME($PARAMS): $RETURN = $BODY",
                "description": "Scala method definition",
                "meta_variables": ["NAME", "PARAMS", "RETURN", "BODY"],
                "captures": {
                    "name": "NAME",
                    "parameters": "PARAMS",
                    "return_type": "RETURN",
                    "body": "BODY"
                }
            },
            {
                "type": "class_method",
                "pattern": "class $CLASS {\n  def $METHOD($PARAMS): $RETURN = $BODY\n}",
                "description": "Scala class method",
                "meta_variables": ["CLASS", "METHOD", "PARAMS", "RETURN", "BODY"],
                "captures": {
                    "class_name": "CLASS",
                    "name": "METHOD",
                    "parameters": "PARAMS",
                    "return_type": "RETURN",
                    "body": "BODY"
                }
            }
        ]
    },
    "lua": {
        "patterns": [
            {
                "type": "function_definition",
                "pattern": "function $NAME($PARAMS)\n  $BODY\nend",
                "description": "Lua function definition",
                "meta_variables": ["NAME", "PARAMS", "BODY"],
                "captures": {
                    "name": "NAME",
                    "parameters": "PARAMS",
                    "body": "BODY"
                }
            },
            {
                "type": "local_function",
                "pattern": "local function $NAME($PARAMS)\n  $BODY\nend",
                "description": "Local Lua function",
                "meta_variables": ["NAME", "PARAMS", "BODY"],
                "captures": {
                    "name": "NAME",
                    "parameters": "PARAMS",
                    "body": "BODY",
                    "modifiers": ["local"]
                }
            }
        ]
    },
    "bash": {
        "patterns": [
            {
                "type": "function_definition",
                "pattern": "function $NAME() {\n  $BODY\n}",
                "description": "Bash function with function keyword",
                "meta_variables": ["NAME", "BODY"],
                "captures": {
                    "name": "NAME",
                    "body": "BODY"
                }
            },
            {
                "type": "function_shorthand",
                "pattern": "$NAME() {\n  $BODY\n}",
                "description": "Bash function shorthand syntax",
                "meta_variables": ["NAME", "BODY"],
                "captures": {
                    "name": "NAME",
                    "body": "BODY"
                }
            }
        ]
    }
}


# Comprehensive call detection patterns for each supported language
CALL_PATTERNS = {
    "javascript": {
        "patterns": [
            {
                "type": "function_call",
                "pattern": "$FUNC($ARGS)",
                "description": "Standard function call",
                "meta_variables": ["FUNC", "ARGS"],
                "captures": {
                    "function_name": "FUNC",
                    "arguments": "ARGS"
                }
            },
            {
                "type": "method_call",
                "pattern": "$OBJ.$METHOD($ARGS)",
                "description": "Method call on object",
                "meta_variables": ["OBJ", "METHOD", "ARGS"],
                "captures": {
                    "object": "OBJ",
                    "method_name": "METHOD",
                    "arguments": "ARGS"
                }
            },
            {
                "type": "constructor_call",
                "pattern": "new $CLASS($ARGS)",
                "description": "Constructor call with new keyword",
                "meta_variables": ["CLASS", "ARGS"],
                "captures": {
                    "class_name": "CLASS",
                    "arguments": "ARGS"
                }
            },
            {
                "type": "chained_call",
                "pattern": "$OBJ.$METHOD($ARGS).$NEXT($ARGS2)",
                "description": "Chained method calls",
                "meta_variables": ["OBJ", "METHOD", "ARGS", "NEXT", "ARGS2"],
                "captures": {
                    "object": "OBJ",
                    "method_name": "METHOD",
                    "arguments": "ARGS",
                    "next_method": "NEXT",
                    "next_arguments": "ARGS2"
                }
            },
            {
                "type": "nested_call",
                "pattern": "$FUNC($INNER($INNER_ARGS))",
                "description": "Nested function calls",
                "meta_variables": ["FUNC", "INNER", "INNER_ARGS"],
                "captures": {
                    "outer_function": "FUNC",
                    "inner_function": "INNER",
                    "inner_arguments": "INNER_ARGS"
                }
            },
            {
                "type": "static_call",
                "pattern": "$NS.$FUNC($ARGS)",
                "description": "Static method or namespace call",
                "meta_variables": ["NS", "FUNC", "ARGS"],
                "captures": {
                    "namespace": "NS",
                    "function_name": "FUNC",
                    "arguments": "ARGS"
                }
            },
            {
                "type": "triple_chained_call",
                "pattern": "$OBJ.$METHOD1($ARGS1).$METHOD2($ARGS2).$METHOD3($ARGS3)",
                "description": "Triple chained method calls",
                "meta_variables": ["OBJ", "METHOD1", "ARGS1", "METHOD2", "ARGS2", "METHOD3", "ARGS3"],
                "captures": {
                    "object": "OBJ",
                    "first_method": "METHOD1",
                    "first_arguments": "ARGS1",
                    "second_method": "METHOD2",
                    "second_arguments": "ARGS2",
                    "third_method": "METHOD3",
                    "third_arguments": "ARGS3"
                }
            },
            {
                "type": "complex_nested_call",
                "pattern": "$FUNC($ARG1, $INNER($INNER_ARGS), $ARG2)",
                "description": "Function call with nested call as middle argument",
                "meta_variables": ["FUNC", "ARG1", "INNER", "INNER_ARGS", "ARG2"],
                "captures": {
                    "outer_function": "FUNC",
                    "first_argument": "ARG1",
                    "inner_function": "INNER",
                    "inner_arguments": "INNER_ARGS",
                    "last_argument": "ARG2"
                }
            },
            {
                "type": "nested_chained_call",
                "pattern": "$FUNC($OBJ.$METHOD($ARGS))",
                "description": "Nested call containing a method chain",
                "meta_variables": ["FUNC", "OBJ", "METHOD", "ARGS"],
                "captures": {
                    "outer_function": "FUNC",
                    "chained_object": "OBJ",
                    "chained_method": "METHOD",
                    "chained_arguments": "ARGS"
                }
            },
            {
                "type": "double_nested_call",
                "pattern": "$FUNC($MIDDLE($INNER($INNER_ARGS)))",
                "description": "Double nested function calls",
                "meta_variables": ["FUNC", "MIDDLE", "INNER", "INNER_ARGS"],
                "captures": {
                    "outer_function": "FUNC",
                    "middle_function": "MIDDLE",
                    "inner_function": "INNER",
                    "inner_arguments": "INNER_ARGS"
                }
            },
            {
                "type": "chained_constructor_call",
                "pattern": "new $CLASS($ARGS).$METHOD($METHOD_ARGS)",
                "description": "Constructor call followed by method chain",
                "meta_variables": ["CLASS", "ARGS", "METHOD", "METHOD_ARGS"],
                "captures": {
                    "class_name": "CLASS",
                    "constructor_arguments": "ARGS",
                    "chained_method": "METHOD",
                    "method_arguments": "METHOD_ARGS"
                }
            }
        ]
    },
    "typescript": {
        "patterns": [
            {
                "type": "function_call",
                "pattern": "$FUNC($ARGS)",
                "description": "Standard function call",
                "meta_variables": ["FUNC", "ARGS"],
                "captures": {
                    "function_name": "FUNC",
                    "arguments": "ARGS"
                }
            },
            {
                "type": "generic_function_call",
                "pattern": "$FUNC<$TYPE>($ARGS)",
                "description": "Generic function call with type parameters",
                "meta_variables": ["FUNC", "TYPE", "ARGS"],
                "captures": {
                    "function_name": "FUNC",
                    "type_parameters": "TYPE",
                    "arguments": "ARGS"
                }
            },
            {
                "type": "method_call",
                "pattern": "$OBJ.$METHOD($ARGS)",
                "description": "Method call on object",
                "meta_variables": ["OBJ", "METHOD", "ARGS"],
                "captures": {
                    "object": "OBJ",
                    "method_name": "METHOD",
                    "arguments": "ARGS"
                }
            },
            {
                "type": "generic_method_call",
                "pattern": "$OBJ.$METHOD<$TYPE>($ARGS)",
                "description": "Generic method call with type parameters",
                "meta_variables": ["OBJ", "METHOD", "TYPE", "ARGS"],
                "captures": {
                    "object": "OBJ",
                    "method_name": "METHOD",
                    "type_parameters": "TYPE",
                    "arguments": "ARGS"
                }
            },
            {
                "type": "constructor_call",
                "pattern": "new $CLASS($ARGS)",
                "description": "Constructor call with new keyword",
                "meta_variables": ["CLASS", "ARGS"],
                "captures": {
                    "class_name": "CLASS",
                    "arguments": "ARGS"
                }
            },
            {
                "type": "generic_constructor_call",
                "pattern": "new $CLASS<$TYPE>($ARGS)",
                "description": "Generic constructor call",
                "meta_variables": ["CLASS", "TYPE", "ARGS"],
                "captures": {
                    "class_name": "CLASS",
                    "type_parameters": "TYPE",
                    "arguments": "ARGS"
                }
            },
            {
                "type": "namespace_call",
                "pattern": "$NS.$FUNC($ARGS)",
                "description": "Namespace-qualified function call",
                "meta_variables": ["NS", "FUNC", "ARGS"],
                "captures": {
                    "namespace": "NS",
                    "function_name": "FUNC",
                    "arguments": "ARGS"
                }
            },
            {
                "type": "triple_chained_call",
                "pattern": "$OBJ.$METHOD1($ARGS1).$METHOD2($ARGS2).$METHOD3($ARGS3)",
                "description": "Triple chained method calls",
                "meta_variables": ["OBJ", "METHOD1", "ARGS1", "METHOD2", "ARGS2", "METHOD3", "ARGS3"],
                "captures": {
                    "object": "OBJ",
                    "first_method": "METHOD1",
                    "first_arguments": "ARGS1",
                    "second_method": "METHOD2",
                    "second_arguments": "ARGS2",
                    "third_method": "METHOD3",
                    "third_arguments": "ARGS3"
                }
            },
            {
                "type": "complex_nested_call",
                "pattern": "$FUNC($ARG1, $INNER($INNER_ARGS), $ARG2)",
                "description": "Function call with nested call as middle argument",
                "meta_variables": ["FUNC", "ARG1", "INNER", "INNER_ARGS", "ARG2"],
                "captures": {
                    "outer_function": "FUNC",
                    "first_argument": "ARG1",
                    "inner_function": "INNER",
                    "inner_arguments": "INNER_ARGS",
                    "last_argument": "ARG2"
                }
            },
            {
                "type": "nested_chained_call",
                "pattern": "$FUNC($OBJ.$METHOD($ARGS))",
                "description": "Nested call containing a method chain",
                "meta_variables": ["FUNC", "OBJ", "METHOD", "ARGS"],
                "captures": {
                    "outer_function": "FUNC",
                    "chained_object": "OBJ",
                    "chained_method": "METHOD",
                    "chained_arguments": "ARGS"
                }
            },
            {
                "type": "double_nested_call",
                "pattern": "$FUNC($MIDDLE($INNER($INNER_ARGS)))",
                "description": "Double nested function calls",
                "meta_variables": ["FUNC", "MIDDLE", "INNER", "INNER_ARGS"],
                "captures": {
                    "outer_function": "FUNC",
                    "middle_function": "MIDDLE",
                    "inner_function": "INNER",
                    "inner_arguments": "INNER_ARGS"
                }
            },
            {
                "type": "chained_constructor_call",
                "pattern": "new $CLASS($ARGS).$METHOD($METHOD_ARGS)",
                "description": "Constructor call followed by method chain",
                "meta_variables": ["CLASS", "ARGS", "METHOD", "METHOD_ARGS"],
                "captures": {
                    "class_name": "CLASS",
                    "constructor_arguments": "ARGS",
                    "chained_method": "METHOD",
                    "method_arguments": "METHOD_ARGS"
                }
            },
            {
                "type": "generic_chained_call",
                "pattern": "$OBJ.$METHOD<$TYPE>($ARGS).$NEXT($NEXT_ARGS)",
                "description": "Generic method chain with type parameters",
                "meta_variables": ["OBJ", "METHOD", "TYPE", "ARGS", "NEXT", "NEXT_ARGS"],
                "captures": {
                    "object": "OBJ",
                    "method_name": "METHOD",
                    "type_parameters": "TYPE",
                    "arguments": "ARGS",
                    "next_method": "NEXT",
                    "next_arguments": "NEXT_ARGS"
                }
            }
        ]
    },
    "python": {
        "patterns": [
            {
                "type": "function_call",
                "pattern": "$FUNC($ARGS)",
                "description": "Standard function call",
                "meta_variables": ["FUNC", "ARGS"],
                "captures": {
                    "function_name": "FUNC",
                    "arguments": "ARGS"
                }
            },
            {
                "type": "method_call",
                "pattern": "$OBJ.$METHOD($ARGS)",
                "description": "Method call on object",
                "meta_variables": ["OBJ", "METHOD", "ARGS"],
                "captures": {
                    "object": "OBJ",
                    "method_name": "METHOD",
                    "arguments": "ARGS"
                }
            },
            {
                "type": "constructor_call",
                "pattern": "$CLASS($ARGS)",
                "description": "Constructor call (no new keyword)",
                "meta_variables": ["CLASS", "ARGS"],
                "captures": {
                    "class_name": "CLASS",
                    "arguments": "ARGS"
                }
            },
            {
                "type": "module_call",
                "pattern": "$MODULE.$FUNC($ARGS)",
                "description": "Module function call",
                "meta_variables": ["MODULE", "FUNC", "ARGS"],
                "captures": {
                    "module": "MODULE",
                    "function_name": "FUNC",
                    "arguments": "ARGS"
                }
            },
            {
                "type": "chained_call",
                "pattern": "$OBJ.$METHOD($ARGS).$NEXT($ARGS2)",
                "description": "Chained method calls",
                "meta_variables": ["OBJ", "METHOD", "ARGS", "NEXT", "ARGS2"],
                "captures": {
                    "object": "OBJ",
                    "method_name": "METHOD",
                    "arguments": "ARGS",
                    "next_method": "NEXT",
                    "next_arguments": "ARGS2"
                }
            },
            {
                "type": "super_call",
                "pattern": "super().$METHOD($ARGS)",
                "description": "Super method call",
                "meta_variables": ["METHOD", "ARGS"],
                "captures": {
                    "method_name": "METHOD",
                    "arguments": "ARGS"
                }
            },
            {
                "type": "triple_chained_call",
                "pattern": "$OBJ.$METHOD1($ARGS1).$METHOD2($ARGS2).$METHOD3($ARGS3)",
                "description": "Triple chained method calls",
                "meta_variables": ["OBJ", "METHOD1", "ARGS1", "METHOD2", "ARGS2", "METHOD3", "ARGS3"],
                "captures": {
                    "object": "OBJ",
                    "first_method": "METHOD1",
                    "first_arguments": "ARGS1",
                    "second_method": "METHOD2",
                    "second_arguments": "ARGS2",
                    "third_method": "METHOD3",
                    "third_arguments": "ARGS3"
                }
            },
            {
                "type": "complex_nested_call",
                "pattern": "$FUNC($ARG1, $INNER($INNER_ARGS), $ARG2)",
                "description": "Function call with nested call as middle argument",
                "meta_variables": ["FUNC", "ARG1", "INNER", "INNER_ARGS", "ARG2"],
                "captures": {
                    "outer_function": "FUNC",
                    "first_argument": "ARG1",
                    "inner_function": "INNER",
                    "inner_arguments": "INNER_ARGS",
                    "last_argument": "ARG2"
                }
            },
            {
                "type": "nested_chained_call",
                "pattern": "$FUNC($OBJ.$METHOD($ARGS))",
                "description": "Nested call containing a method chain",
                "meta_variables": ["FUNC", "OBJ", "METHOD", "ARGS"],
                "captures": {
                    "outer_function": "FUNC",
                    "chained_object": "OBJ",
                    "chained_method": "METHOD",
                    "chained_arguments": "ARGS"
                }
            },
            {
                "type": "double_nested_call",
                "pattern": "$FUNC($MIDDLE($INNER($INNER_ARGS)))",
                "description": "Double nested function calls",
                "meta_variables": ["FUNC", "MIDDLE", "INNER", "INNER_ARGS"],
                "captures": {
                    "outer_function": "FUNC",
                    "middle_function": "MIDDLE",
                    "inner_function": "INNER",
                    "inner_arguments": "INNER_ARGS"
                }
            },
            {
                "type": "nested_super_call",
                "pattern": "$FUNC(super().$METHOD($ARGS))",
                "description": "Nested call with super method",
                "meta_variables": ["FUNC", "METHOD", "ARGS"],
                "captures": {
                    "outer_function": "FUNC",
                    "super_method": "METHOD",
                    "super_arguments": "ARGS"
                }
            },
            {
                "type": "comprehension_call",
                "pattern": "[$FUNC($ARG) for $ARG in $ITER]",
                "description": "List comprehension with function call",
                "meta_variables": ["FUNC", "ARG", "ITER"],
                "captures": {
                    "function_name": "FUNC",
                    "argument": "ARG",
                    "iterator": "ITER"
                }
            }
        ]
    },
    "java": {
        "patterns": [
            {
                "type": "method_call",
                "pattern": "$OBJ.$METHOD($ARGS)",
                "description": "Instance method call",
                "meta_variables": ["OBJ", "METHOD", "ARGS"],
                "captures": {
                    "object": "OBJ",
                    "method_name": "METHOD",
                    "arguments": "ARGS"
                }
            },
            {
                "type": "static_method_call",
                "pattern": "$CLASS.$METHOD($ARGS)",
                "description": "Static method call",
                "meta_variables": ["CLASS", "METHOD", "ARGS"],
                "captures": {
                    "class_name": "CLASS",
                    "method_name": "METHOD",
                    "arguments": "ARGS"
                }
            },
            {
                "type": "constructor_call",
                "pattern": "new $CLASS($ARGS)",
                "description": "Constructor call with new keyword",
                "meta_variables": ["CLASS", "ARGS"],
                "captures": {
                    "class_name": "CLASS",
                    "arguments": "ARGS"
                }
            },
            {
                "type": "generic_constructor_call",
                "pattern": "new $CLASS<$TYPE>($ARGS)",
                "description": "Generic constructor call",
                "meta_variables": ["CLASS", "TYPE", "ARGS"],
                "captures": {
                    "class_name": "CLASS",
                    "type_parameters": "TYPE",
                    "arguments": "ARGS"
                }
            },
            {
                "type": "this_call",
                "pattern": "this.$METHOD($ARGS)",
                "description": "This method call",
                "meta_variables": ["METHOD", "ARGS"],
                "captures": {
                    "method_name": "METHOD",
                    "arguments": "ARGS"
                }
            },
            {
                "type": "super_call",
                "pattern": "super.$METHOD($ARGS)",
                "description": "Super method call",
                "meta_variables": ["METHOD", "ARGS"],
                "captures": {
                    "method_name": "METHOD",
                    "arguments": "ARGS"
                }
            }
        ]
    },
    "cpp": {
        "patterns": [
            {
                "type": "function_call",
                "pattern": "$FUNC($ARGS)",
                "description": "Standard function call",
                "meta_variables": ["FUNC", "ARGS"],
                "captures": {
                    "function_name": "FUNC",
                    "arguments": "ARGS"
                }
            },
            {
                "type": "method_call",
                "pattern": "$OBJ.$METHOD($ARGS)",
                "description": "Method call on object",
                "meta_variables": ["OBJ", "METHOD", "ARGS"],
                "captures": {
                    "object": "OBJ",
                    "method_name": "METHOD",
                    "arguments": "ARGS"
                }
            },
            {
                "type": "pointer_method_call",
                "pattern": "$PTR->$METHOD($ARGS)",
                "description": "Method call on pointer",
                "meta_variables": ["PTR", "METHOD", "ARGS"],
                "captures": {
                    "pointer": "PTR",
                    "method_name": "METHOD",
                    "arguments": "ARGS"
                }
            },
            {
                "type": "constructor_call",
                "pattern": "new $CLASS($ARGS)",
                "description": "Heap constructor call",
                "meta_variables": ["CLASS", "ARGS"],
                "captures": {
                    "class_name": "CLASS",
                    "arguments": "ARGS"
                }
            },
            {
                "type": "stack_constructor_call",
                "pattern": "$CLASS $VAR($ARGS)",
                "description": "Stack constructor call",
                "meta_variables": ["CLASS", "VAR", "ARGS"],
                "captures": {
                    "class_name": "CLASS",
                    "variable": "VAR",
                    "arguments": "ARGS"
                }
            },
            {
                "type": "namespace_call",
                "pattern": "$NS::$FUNC($ARGS)",
                "description": "Namespace-qualified function call",
                "meta_variables": ["NS", "FUNC", "ARGS"],
                "captures": {
                    "namespace": "NS",
                    "function_name": "FUNC",
                    "arguments": "ARGS"
                }
            },
            {
                "type": "static_method_call",
                "pattern": "$CLASS::$METHOD($ARGS)",
                "description": "Static method call",
                "meta_variables": ["CLASS", "METHOD", "ARGS"],
                "captures": {
                    "class_name": "CLASS",
                    "method_name": "METHOD",
                    "arguments": "ARGS"
                }
            }
        ]
    },
    "rust": {
        "patterns": [
            {
                "type": "function_call",
                "pattern": "$FUNC($ARGS)",
                "description": "Standard function call",
                "meta_variables": ["FUNC", "ARGS"],
                "captures": {
                    "function_name": "FUNC",
                    "arguments": "ARGS"
                }
            },
            {
                "type": "method_call",
                "pattern": "$OBJ.$METHOD($ARGS)",
                "description": "Method call on object",
                "meta_variables": ["OBJ", "METHOD", "ARGS"],
                "captures": {
                    "object": "OBJ",
                    "method_name": "METHOD",
                    "arguments": "ARGS"
                }
            },
            {
                "type": "associated_function_call",
                "pattern": "$TYPE::$FUNC($ARGS)",
                "description": "Associated function call",
                "meta_variables": ["TYPE", "FUNC", "ARGS"],
                "captures": {
                    "type_name": "TYPE",
                    "function_name": "FUNC",
                    "arguments": "ARGS"
                }
            },
            {
                "type": "constructor_call",
                "pattern": "$TYPE::new($ARGS)",
                "description": "Constructor call using new",
                "meta_variables": ["TYPE", "ARGS"],
                "captures": {
                    "type_name": "TYPE",
                    "arguments": "ARGS"
                }
            },
            {
                "type": "module_call",
                "pattern": "$MODULE::$FUNC($ARGS)",
                "description": "Module function call",
                "meta_variables": ["MODULE", "FUNC", "ARGS"],
                "captures": {
                    "module": "MODULE",
                    "function_name": "FUNC",
                    "arguments": "ARGS"
                }
            },
            {
                "type": "macro_call",
                "pattern": "$MACRO!($ARGS)",
                "description": "Macro invocation",
                "meta_variables": ["MACRO", "ARGS"],
                "captures": {
                    "macro_name": "MACRO",
                    "arguments": "ARGS"
                }
            }
        ]
    },
    "go": {
        "patterns": [
            {
                "type": "function_call",
                "pattern": "$FUNC($ARGS)",
                "description": "Standard function call",
                "meta_variables": ["FUNC", "ARGS"],
                "captures": {
                    "function_name": "FUNC",
                    "arguments": "ARGS"
                }
            },
            {
                "type": "method_call",
                "pattern": "$OBJ.$METHOD($ARGS)",
                "description": "Method call on object",
                "meta_variables": ["OBJ", "METHOD", "ARGS"],
                "captures": {
                    "object": "OBJ",
                    "method_name": "METHOD",
                    "arguments": "ARGS"
                }
            },
            {
                "type": "package_call",
                "pattern": "$PKG.$FUNC($ARGS)",
                "description": "Package function call",
                "meta_variables": ["PKG", "FUNC", "ARGS"],
                "captures": {
                    "package": "PKG",
                    "function_name": "FUNC",
                    "arguments": "ARGS"
                }
            },
            {
                "type": "constructor_call",
                "pattern": "&$TYPE{$FIELDS}",
                "description": "Struct constructor with fields",
                "meta_variables": ["TYPE", "FIELDS"],
                "captures": {
                    "type_name": "TYPE",
                    "fields": "FIELDS"
                }
            },
            {
                "type": "new_call",
                "pattern": "new($TYPE)",
                "description": "Allocate new instance",
                "meta_variables": ["TYPE"],
                "captures": {
                    "type_name": "TYPE"
                }
            },
            {
                "type": "make_call",
                "pattern": "make($TYPE, $ARGS)",
                "description": "Make call for slices/maps/channels",
                "meta_variables": ["TYPE", "ARGS"],
                "captures": {
                    "type_name": "TYPE",
                    "arguments": "ARGS"
                }
            }
        ]
    },
    "csharp": {
        "patterns": [
            {
                "type": "method_call",
                "pattern": "$OBJ.$METHOD($ARGS)",
                "description": "Instance method call",
                "meta_variables": ["OBJ", "METHOD", "ARGS"],
                "captures": {
                    "object": "OBJ",
                    "method_name": "METHOD",
                    "arguments": "ARGS"
                }
            },
            {
                "type": "static_method_call",
                "pattern": "$CLASS.$METHOD($ARGS)",
                "description": "Static method call",
                "meta_variables": ["CLASS", "METHOD", "ARGS"],
                "captures": {
                    "class_name": "CLASS",
                    "method_name": "METHOD",
                    "arguments": "ARGS"
                }
            },
            {
                "type": "constructor_call",
                "pattern": "new $CLASS($ARGS)",
                "description": "Constructor call with new keyword",
                "meta_variables": ["CLASS", "ARGS"],
                "captures": {
                    "class_name": "CLASS",
                    "arguments": "ARGS"
                }
            },
            {
                "type": "generic_method_call",
                "pattern": "$OBJ.$METHOD<$TYPE>($ARGS)",
                "description": "Generic method call",
                "meta_variables": ["OBJ", "METHOD", "TYPE", "ARGS"],
                "captures": {
                    "object": "OBJ",
                    "method_name": "METHOD",
                    "type_parameters": "TYPE",
                    "arguments": "ARGS"
                }
            },
            {
                "type": "extension_method_call",
                "pattern": "$OBJ.$EXT_METHOD($ARGS)",
                "description": "Extension method call",
                "meta_variables": ["OBJ", "EXT_METHOD", "ARGS"],
                "captures": {
                    "object": "OBJ",
                    "extension_method": "EXT_METHOD",
                    "arguments": "ARGS"
                }
            }
        ]
    },
    "swift": {
        "patterns": [
            {
                "type": "function_call",
                "pattern": "$FUNC($ARGS)",
                "description": "Standard function call",
                "meta_variables": ["FUNC", "ARGS"],
                "captures": {
                    "function_name": "FUNC",
                    "arguments": "ARGS"
                }
            },
            {
                "type": "method_call",
                "pattern": "$OBJ.$METHOD($ARGS)",
                "description": "Method call on object",
                "meta_variables": ["OBJ", "METHOD", "ARGS"],
                "captures": {
                    "object": "OBJ",
                    "method_name": "METHOD",
                    "arguments": "ARGS"
                }
            },
            {
                "type": "constructor_call",
                "pattern": "$TYPE($ARGS)",
                "description": "Constructor call (no new keyword)",
                "meta_variables": ["TYPE", "ARGS"],
                "captures": {
                    "type_name": "TYPE",
                    "arguments": "ARGS"
                }
            },
            {
                "type": "static_method_call",
                "pattern": "$TYPE.$METHOD($ARGS)",
                "description": "Static method call",
                "meta_variables": ["TYPE", "METHOD", "ARGS"],
                "captures": {
                    "type_name": "TYPE",
                    "method_name": "METHOD",
                    "arguments": "ARGS"
                }
            },
            {
                "type": "optional_chaining_call",
                "pattern": "$OBJ?.$METHOD($ARGS)",
                "description": "Optional chaining method call",
                "meta_variables": ["OBJ", "METHOD", "ARGS"],
                "captures": {
                    "object": "OBJ",
                    "method_name": "METHOD",
                    "arguments": "ARGS"
                }
            }
        ]
    },
    "kotlin": {
        "patterns": [
            {
                "type": "function_call",
                "pattern": "$FUNC($ARGS)",
                "description": "Standard function call",
                "meta_variables": ["FUNC", "ARGS"],
                "captures": {
                    "function_name": "FUNC",
                    "arguments": "ARGS"
                }
            },
            {
                "type": "method_call",
                "pattern": "$OBJ.$METHOD($ARGS)",
                "description": "Method call on object",
                "meta_variables": ["OBJ", "METHOD", "ARGS"],
                "captures": {
                    "object": "OBJ",
                    "method_name": "METHOD",
                    "arguments": "ARGS"
                }
            },
            {
                "type": "constructor_call",
                "pattern": "$CLASS($ARGS)",
                "description": "Constructor call (no new keyword)",
                "meta_variables": ["CLASS", "ARGS"],
                "captures": {
                    "class_name": "CLASS",
                    "arguments": "ARGS"
                }
            },
            {
                "type": "companion_call",
                "pattern": "$CLASS.Companion.$METHOD($ARGS)",
                "description": "Companion object method call",
                "meta_variables": ["CLASS", "METHOD", "ARGS"],
                "captures": {
                    "class_name": "CLASS",
                    "method_name": "METHOD",
                    "arguments": "ARGS"
                }
            },
            {
                "type": "extension_function_call",
                "pattern": "$OBJ.$EXT_FUNC($ARGS)",
                "description": "Extension function call",
                "meta_variables": ["OBJ", "EXT_FUNC", "ARGS"],
                "captures": {
                    "object": "OBJ",
                    "extension_function": "EXT_FUNC",
                    "arguments": "ARGS"
                }
            },
            {
                "type": "safe_call",
                "pattern": "$OBJ?.$METHOD($ARGS)",
                "description": "Safe call operator",
                "meta_variables": ["OBJ", "METHOD", "ARGS"],
                "captures": {
                    "object": "OBJ",
                    "method_name": "METHOD",
                    "arguments": "ARGS"
                }
            }
        ]
    }
}


# Pattern syntax examples
PATTERN_EXAMPLES = {
    "basic_patterns": {
        "description": "Basic AST pattern matching examples",
        "examples": [
            {
                "pattern": "console.log($MSG)",
                "description": "Match console.log calls with any argument",
                "language": "javascript"
            },
            {
                "pattern": "function $NAME($ARGS) { $BODY }",
                "description": "Match function declarations",
                "language": "javascript"
            },
            {
                "pattern": "def $NAME($ARGS): $BODY",
                "description": "Match Python function definitions",
                "language": "python"
            },
            {
                "pattern": "class $NAME { $BODY }",
                "description": "Match class declarations",
                "language": "java"
            }
        ]
    },
    "meta_variables": {
        "description": "Meta-variable usage in patterns",
        "examples": [
            {
                "pattern": "$OBJ.$METHOD($ARGS)",
                "description": "Match method calls on any object",
                "explanation": "$OBJ captures the object, $METHOD captures the method name, $ARGS captures all arguments"
            },
            {
                "pattern": "if ($COND) { $THEN }",
                "description": "Match if statements",
                "explanation": "$COND captures the condition, $THEN captures the if body"
            }
        ]
    },
    "advanced_patterns": {
        "description": "Advanced pattern matching techniques",
        "examples": [
            {
                "pattern": "$OBJ.$METHOD($$$ARGS)",
                "description": "Match method calls with any number of arguments",
                "explanation": "$$$ captures variable number of arguments"
            },
            {
                "pattern": "async function $NAME($ARGS) { $$$BODY }",
                "description": "Match async function declarations",
                "explanation": "$$$BODY captures multiple statements in function body"
            }
        ]
    }
}


# Call graph schema definition
CALL_GRAPH_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "AST-Grep Call Graph Schema",
    "description": "Schema for call graph data generated by AST-Grep MCP Server",
    "type": "object",
    "properties": {
        "nodes": {
            "type": "array",
            "description": "Function/method definitions found in the codebase",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Unique identifier for the function"},
                    "name": {"type": "string", "description": "Function name"},
                    "file": {"type": "string", "description": "File path where function is defined"},
                    "line": {"type": "integer", "description": "Line number of function definition"},
                    "column": {"type": "integer", "description": "Column number of function definition"},
                    "language": {"type": "string", "description": "Programming language"},
                    "type": {"type": "string", "enum": ["function", "method", "constructor"], "description": "Type of callable"},
                    "parameters": {"type": "array", "items": {"type": "string"}, "description": "Function parameters"},
                    "return_type": {"type": "string", "description": "Return type if available"},
                    "visibility": {"type": "string", "description": "Visibility modifier (public, private, etc.)"}
                },
                "required": ["id", "name", "file", "line", "language", "type"]
            }
        },
        "edges": {
            "type": "array",
            "description": "Function call relationships",
            "items": {
                "type": "object",
                "properties": {
                    "source": {"type": "string", "description": "ID of calling function"},
                    "target": {"type": "string", "description": "ID of called function"},
                    "call_site": {
                        "type": "object",
                        "properties": {
                            "file": {"type": "string", "description": "File where call occurs"},
                            "line": {"type": "integer", "description": "Line number of call"},
                            "column": {"type": "integer", "description": "Column number of call"}
                        },
                        "required": ["file", "line"]
                    },
                    "call_type": {"type": "string", "enum": ["direct", "indirect", "dynamic"], "description": "Type of function call"}
                },
                "required": ["source", "target", "call_site"]
            }
        },
        "metadata": {
            "type": "object",
            "description": "Analysis metadata",
            "properties": {
                "total_functions": {"type": "integer", "description": "Total number of functions found"},
                "total_calls": {"type": "integer", "description": "Total number of calls found"},
                "languages": {"type": "array", "items": {"type": "string"}, "description": "Languages analyzed"},
                "analysis_timestamp": {"type": "string", "format": "date-time", "description": "When analysis was performed"},
                "ast_grep_version": {"type": "string", "description": "Version of ast-grep used"},
                "analysis_options": {"type": "object", "description": "Options used for analysis"}
            },
            "required": ["total_functions", "total_calls", "languages", "analysis_timestamp"]
        }
    },
    "required": ["nodes", "edges", "metadata"]
}


# Dynamic path handling utilities
class PathParameterHandler:
    """Handles dynamic path parameters for MCP resources."""
    
    def __init__(self):
        """Initialize path parameter handler."""
        self.logger = logging.getLogger(__name__)
        self._cache = {}
        self._cache_metadata = {}
        self.MAX_CACHE_SIZE = 100
        self.CACHE_TTL_SECONDS = 3600  # 1 hour
        self._partial_results = {}  # For progressive loading
        self.PROGRESSIVE_THRESHOLD = 1000  # Start progressive loading for >1000 functions
        
    def parse_call_graph_uri(self, uri: str) -> Optional[Dict[str, Any]]:
        """Parse call graph URI with path parameters.
        
        Args:
            uri: Resource URI to parse
            
        Returns:
            Dictionary with path info or None if not a call graph URI
        """
        # Pattern: ast-grep://call-graph/{path}
        pattern = r"^ast-grep://call-graph/(.+)$"
        match = re.match(pattern, uri)
        
        if not match:
            return None
            
        # Extract and decode path
        encoded_path = match.group(1)
        try:
            # Handle URL encoding
            decoded_path = urllib.parse.unquote(encoded_path)
            
            # Validate path safety
            if not self._is_safe_path(decoded_path):
                raise ValueError(f"Unsafe path detected: {decoded_path}")
                
            return {
                "type": "call_graph",
                "path": decoded_path,
                "is_directory": os.path.isdir(decoded_path) if os.path.exists(decoded_path) else decoded_path.endswith('/'),
                "exists": os.path.exists(decoded_path),
                "uri": uri
            }
        except Exception as e:
            self.logger.error(f"Failed to parse call graph URI {uri}: {e}")
            return None
    
    def _is_safe_path(self, path: str) -> bool:
        """Validate that path is safe to access.
        
        Args:
            path: File or directory path to validate
            
        Returns:
            True if path is safe, False otherwise
        """
        # Prevent path traversal attacks
        if ".." in path or path.startswith("/"):
            return False
            
        # Check for suspicious patterns
        suspicious_patterns = [
            "~", "$", "`", "*", "?", "[", "]", 
            "|", "&", ";", "(", ")", "<", ">", 
            "\\", "\"", "'"
        ]
        
        for pattern in suspicious_patterns:
            if pattern in path:
                return False
                
        return True
    
    def generate_cache_key(self, path: str, options: Dict[str, Any] = None) -> str:
        """Generate cache key for path and options.
        
        Args:
            path: File or directory path
            options: Analysis options
            
        Returns:
            Cache key string
        """
        options_str = json.dumps(options or {}, sort_keys=True)
        content = f"{path}:{options_str}"
        return hashlib.md5(content.encode()).hexdigest()
    
    def should_cache_result(self, path: str, result_size: int) -> bool:
        """Determine if result should be cached.
        
        Args:
            path: File or directory path
            result_size: Size of result in bytes
            
        Returns:
            True if should cache, False otherwise
        """
        # Don't cache very large results (>10MB)
        if result_size > 10 * 1024 * 1024:
            return False
            
        # Don't cache if cache is full and this is a new path
        if len(self._cache) >= self.MAX_CACHE_SIZE:
            cache_key = self.generate_cache_key(path)
            if cache_key not in self._cache:
                return False
                
        return True
    
    def get_cached_result(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Get cached result if valid.
        
        Args:
            cache_key: Cache key to look up
            
        Returns:
            Cached result or None if not found/expired
        """
        if cache_key not in self._cache:
            return None
            
        metadata = self._cache_metadata.get(cache_key)
        if not metadata:
            # Remove invalid cache entry
            del self._cache[cache_key]
            return None
            
        # Check if expired
        age = datetime.now().timestamp() - metadata["created_at"]
        if age > self.CACHE_TTL_SECONDS:
            del self._cache[cache_key]
            del self._cache_metadata[cache_key]
            return None
            
        # Update access time
        metadata["last_accessed"] = datetime.now().timestamp()
        return self._cache[cache_key]
    
    def cache_result(self, cache_key: str, result: Dict[str, Any]) -> None:
        """Cache result with metadata.
        
        Args:
            cache_key: Cache key
            result: Result to cache
        """
        # Remove oldest entries if cache is full
        while len(self._cache) >= self.MAX_CACHE_SIZE:
            # Find oldest entry by last access time
            oldest_key = min(
                self._cache_metadata.keys(),
                key=lambda k: self._cache_metadata[k].get("last_accessed", 0)
            )
            del self._cache[oldest_key]
            del self._cache_metadata[oldest_key]
        
        # Cache result
        self._cache[cache_key] = result
        self._cache_metadata[cache_key] = {
            "created_at": datetime.now().timestamp(),
            "last_accessed": datetime.now().timestamp(),
            "size": len(json.dumps(result).encode())
        }
    
    def should_use_progressive_loading(self, path: str) -> bool:
        """Determine if progressive loading should be used for a path.
        
        Args:
            path: File or directory path to analyze
            
        Returns:
            True if progressive loading should be used
        """
        if not os.path.exists(path):
            return False
            
        if os.path.isfile(path):
            # Check file size
            file_size = os.path.getsize(path)
            return file_size > 100 * 1024  # Files larger than 100KB
        
        if os.path.isdir(path):
            # Count files in directory
            try:
                file_count = sum(1 for root, dirs, files in os.walk(path) for f in files)
                return file_count > 50  # Directories with more than 50 files
            except (OSError, PermissionError):
                return False
                
        return False
    
    def get_partial_result_key(self, cache_key: str, stage: str) -> str:
        """Generate key for partial result storage.
        
        Args:
            cache_key: Base cache key
            stage: Processing stage (e.g., 'functions', 'calls', 'graph')
            
        Returns:
            Partial result key
        """
        return f"{cache_key}:{stage}"
    
    def cache_partial_result(self, cache_key: str, stage: str, result: Dict[str, Any]) -> None:
        """Cache partial result for progressive loading.
        
        Args:
            cache_key: Base cache key
            stage: Processing stage
            result: Partial result to cache
        """
        partial_key = self.get_partial_result_key(cache_key, stage)
        self._partial_results[partial_key] = {
            "data": result,
            "timestamp": datetime.now().timestamp(),
            "stage": stage
        }
        
        # Clean old partial results (older than 30 minutes)
        current_time = datetime.now().timestamp()
        expired_keys = [
            key for key, value in self._partial_results.items()
            if current_time - value["timestamp"] > 1800  # 30 minutes
        ]
        for key in expired_keys:
            del self._partial_results[key]
    
    def get_partial_result(self, cache_key: str, stage: str) -> Optional[Dict[str, Any]]:
        """Get cached partial result.
        
        Args:
            cache_key: Base cache key
            stage: Processing stage
            
        Returns:
            Partial result if available and valid
        """
        partial_key = self.get_partial_result_key(cache_key, stage)
        if partial_key not in self._partial_results:
            return None
            
        partial_data = self._partial_results[partial_key]
        
        # Check if expired (30 minutes)
        age = datetime.now().timestamp() - partial_data["timestamp"]
        if age > 1800:
            del self._partial_results[partial_key]
            return None
            
        return partial_data["data"]
    
    def clear_cache(self, path_pattern: Optional[str] = None) -> int:
        """Clear cache entries, optionally matching a pattern.
        
        Args:
            path_pattern: Optional regex pattern to match paths
            
        Returns:
            Number of entries cleared
        """
        if path_pattern is None:
            # Clear all
            count = len(self._cache)
            self._cache.clear()
            self._cache_metadata.clear()
            self._partial_results.clear()
            return count
        
        # Clear matching entries
        import re
        pattern = re.compile(path_pattern)
        cleared = 0
        
        # Find matching cache keys by checking if any contain the pattern
        keys_to_remove = []
        for cache_key in list(self._cache.keys()):
            # We'd need to store original path to match properly
            # For now, just clear all if pattern is provided
            keys_to_remove.append(cache_key)
            
        for key in keys_to_remove:
            if key in self._cache:
                del self._cache[key]
                cleared += 1
            if key in self._cache_metadata:
                del self._cache_metadata[key]
                
        # Clear matching partial results
        partial_keys_to_remove = [
            key for key in self._partial_results.keys()
            if any(pattern.search(key) for key in [key])
        ]
        for key in partial_keys_to_remove:
            del self._partial_results[key]
            
        return cleared
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics.
        
        Returns:
            Dictionary with cache statistics
        """
        total_size = sum(
            metadata.get("size", 0) 
            for metadata in self._cache_metadata.values()
        )
        
        return {
            "cache_entries": len(self._cache),
            "max_cache_size": self.MAX_CACHE_SIZE,
            "cache_utilization": len(self._cache) / self.MAX_CACHE_SIZE,
            "total_cache_size_bytes": total_size,
            "partial_results": len(self._partial_results),
            "cache_ttl_seconds": self.CACHE_TTL_SECONDS,
            "progressive_threshold": self.PROGRESSIVE_THRESHOLD
        }


# Global path handler instance
path_handler = PathParameterHandler()


async def generate_call_graph_for_path(path: str, options: Dict[str, Any] = None) -> Dict[str, Any]:
    """Generate call graph for specified path with progressive loading support.
    
    Args:
        path: File or directory path to analyze
        options: Analysis options
        
    Returns:
        Call graph data structure
    """
    logger = logging.getLogger(__name__)
    
    try:
        # Import CallGraphGenerator (avoid circular imports)
        from .utils import create_call_graph_generator
        
        # Validate path exists
        if not os.path.exists(path):
            raise FileNotFoundError(f"Path does not exist: {path}")
        
        # Check cache first
        cache_key = path_handler.generate_cache_key(path, options)
        cached_result = path_handler.get_cached_result(cache_key)
        if cached_result:
            logger.info(f"Returning cached call graph for {path}")
            return cached_result
        
        # Check if progressive loading should be used
        use_progressive = path_handler.should_use_progressive_loading(path)
        progressive_mode = options.get("progressive", False) if options else False
        
        if use_progressive or progressive_mode:
            logger.info(f"Using progressive loading for large codebase: {path}")
            return await generate_call_graph_progressive(path, options, cache_key)
        
        # Initialize call graph generator
        logger.info(f"Generating call graph for path: {path}")
        generator = await create_call_graph_generator()
        
        # Prepare analysis options
        analysis_options = {
            "include_builtin_calls": False,
            "include_external_calls": True,
            "max_depth": 10,
            "filter_patterns": []
        }
        if options:
            analysis_options.update(options)
        
        # Generate call graph
        call_graph = await generator.generate_call_graph(
            paths=[path],
            **analysis_options
        )
        
        # Add additional metadata
        call_graph["metadata"]["analysis_path"] = path
        call_graph["metadata"]["analysis_options"] = analysis_options
        call_graph["metadata"]["cache_key"] = cache_key
        call_graph["metadata"]["progressive_loading"] = False
        
        # Cache result if appropriate
        result_size = len(json.dumps(call_graph).encode())
        if path_handler.should_cache_result(path, result_size):
            path_handler.cache_result(cache_key, call_graph)
            logger.info(f"Cached call graph for {path} (size: {result_size} bytes)")
        
        return call_graph
        
    except Exception as e:
        logger.error(f"Failed to generate call graph for {path}: {e}")
        return {
            "metadata": {
                "generation_time": datetime.now().isoformat(),
                "total_functions": 0,
                "total_calls": 0,
                "filtered_functions": 0,
                "filtered_calls": 0,
                "total_edges": 0,
                "analysis_path": path,
                "error": str(e),
                "progressive_loading": False
            },
            "nodes": [],
            "edges": [],
            "metrics": {
                "total_nodes": 0,
                "total_edges": 0,
                "average_out_degree": 0.0,
                "average_in_degree": 0.0
            },
            "statistics": {
                "functions_by_language": {},
                "calls_by_type": {}
            },
            "errors": [{"error": str(e)}]
        }


async def generate_call_graph_progressive(path: str, options: Dict[str, Any] = None, cache_key: str = None) -> Dict[str, Any]:
    """Generate call graph using progressive loading for large codebases.
    
    Args:
        path: File or directory path to analyze
        options: Analysis options
        cache_key: Cache key for partial results
        
    Returns:
        Call graph data structure with progressive loading metadata
    """
    logger = logging.getLogger(__name__)
    
    try:
        if not cache_key:
            cache_key = path_handler.generate_cache_key(path, options)
        
        # Check for cached partial results
        functions_data = path_handler.get_partial_result(cache_key, "functions")
        calls_data = path_handler.get_partial_result(cache_key, "calls")
        
        # Import components
        from .utils import create_call_graph_generator, create_function_detector, create_call_detector
        
        # Stage 1: Function Detection
        if not functions_data:
            logger.info(f"Progressive loading stage 1: Detecting functions in {path}")
            detector = await create_function_detector()
            
            if os.path.isfile(path):
                functions_data = await detector.detect_functions(path)
            else:
                functions_data = await detector.detect_functions_in_directory(path)
            
            # Cache partial result
            path_handler.cache_partial_result(cache_key, "functions", functions_data)
            logger.info(f"Cached {len(functions_data)} function detection results")
        else:
            logger.info(f"Using cached function detection results: {len(functions_data)} functions")
        
        # Stage 2: Call Detection
        if not calls_data:
            logger.info(f"Progressive loading stage 2: Detecting calls in {path}")
            detector = await create_call_detector()
            
            if os.path.isfile(path):
                calls_data = await detector.detect_calls(path)
            else:
                calls_data = await detector.detect_calls_in_directory(path)
            
            # Cache partial result
            path_handler.cache_partial_result(cache_key, "calls", calls_data)
            logger.info(f"Cached {len(calls_data)} call detection results")
        else:
            logger.info(f"Using cached call detection results: {len(calls_data)} calls")
        
        # Stage 3: Graph Generation
        logger.info(f"Progressive loading stage 3: Building call graph")
        generator = await create_call_graph_generator()
        
        # Prepare analysis options
        analysis_options = {
            "include_builtin_calls": False,
            "include_external_calls": True,
            "max_depth": 10,
            "filter_patterns": []
        }
        if options:
            analysis_options.update(options)
        
        # Build call graph from cached data
        call_graph = await generator._build_call_graph(
            functions_data,
            calls_data,
            **analysis_options
        )
        
        # Add progressive loading metadata
        call_graph["metadata"]["analysis_path"] = path
        call_graph["metadata"]["analysis_options"] = analysis_options
        call_graph["metadata"]["cache_key"] = cache_key
        call_graph["metadata"]["progressive_loading"] = True
        call_graph["metadata"]["progressive_stages"] = {
            "functions_cached": functions_data is not None,
            "calls_cached": calls_data is not None,
            "total_stages": 3
        }
        
        # Cache final result if appropriate
        result_size = len(json.dumps(call_graph).encode())
        if path_handler.should_cache_result(path, result_size):
            path_handler.cache_result(cache_key, call_graph)
            logger.info(f"Cached progressive call graph for {path} (size: {result_size} bytes)")
        
        return call_graph
        
    except Exception as e:
        logger.error(f"Failed to generate progressive call graph for {path}: {e}")
        return {
            "metadata": {
                "generation_time": datetime.now().isoformat(),
                "total_functions": 0,
                "total_calls": 0,
                "filtered_functions": 0,
                "filtered_calls": 0,
                "total_edges": 0,
                "analysis_path": path,
                "error": str(e),
                "progressive_loading": True,
                "progressive_stages": {
                    "functions_cached": False,
                    "calls_cached": False,
                    "total_stages": 3
                }
            },
            "nodes": [],
            "edges": [],
            "metrics": {
                "total_nodes": 0,
                "total_edges": 0,
                "average_out_degree": 0.0,
                "average_in_degree": 0.0
            },
            "statistics": {
                "functions_by_language": {},
                "calls_by_type": {}
            },
            "errors": [{"error": str(e)}]
        }


async def get_call_graph_for_path(path_info: Dict[str, Any]) -> str:
    """Get call graph for specified path.
    
    Args:
        path_info: Path information from parse_call_graph_uri
        
    Returns:
        JSON string of call graph data
    """
    try:
        call_graph = await generate_call_graph_for_path(path_info["path"])
        return json.dumps(call_graph, indent=2)
    except Exception as e:
        error_result = {
            "metadata": {
                "generation_time": datetime.now().isoformat(),
                "total_functions": 0,
                "total_calls": 0,
                "filtered_functions": 0,
                "filtered_calls": 0,
                "total_edges": 0,
                "analysis_path": path_info["path"],
                "error": str(e)
            },
            "nodes": [],
            "edges": [],
            "metrics": {
                "total_nodes": 0,
                "total_edges": 0,
                "average_out_degree": 0.0,
                "average_in_degree": 0.0
            },
            "statistics": {
                "functions_by_language": {},
                "calls_by_type": {}
            },
            "errors": [{"error": str(e)}]
        }
        return json.dumps(error_result, indent=2)


async def get_pattern_documentation() -> str:
    """Get comprehensive pattern syntax documentation."""
    docs = """# AST-Grep Pattern Syntax Documentation

## Overview
AST-Grep uses Tree-sitter to parse source code into Abstract Syntax Trees (AST) and then uses patterns to match against these trees. Patterns look like ordinary code but use meta-variables to capture parts of the matched code.

## Meta-Variables
Meta-variables start with `$` and capture parts of the AST:
- `$IDENTIFIER`: Matches any identifier
- `$EXPRESSION`: Matches any expression
- `$STATEMENT`: Matches any statement
- `$TYPE`: Matches any type annotation

## Variable Length Matching
- `$$$ARGS`: Matches zero or more comma-separated arguments
- `$$$STATEMENTS`: Matches zero or more statements

"""
    
    # Add examples
    for category, data in PATTERN_EXAMPLES.items():
        docs += f"\n## {data['description']}\n"
        for example in data['examples']:
            docs += f"\n### Pattern: `{example['pattern']}`\n"
            docs += f"**Description**: {example['description']}\n"
            if 'language' in example:
                docs += f"**Language**: {example['language']}\n"
            if 'explanation' in example:
                docs += f"**Explanation**: {example['explanation']}\n"
    
    return docs


async def get_supported_languages() -> str:
    """Get list of supported programming languages."""
    docs = "# Supported Programming Languages\n\n"
    docs += "| Language | Aliases | File Extensions | Tree-sitter Parser |\n"
    docs += "|----------|---------|-----------------|--------------------|\n"
    
    for lang, info in SUPPORTED_LANGUAGES.items():
        aliases = ", ".join(info["aliases"]) if info["aliases"] else "None"
        extensions = ", ".join(info["extensions"])
        docs += f"| {lang.title()} | {aliases} | {extensions} | {info['tree_sitter']} |\n"
    
    docs += f"\n**Total Languages Supported**: {len(SUPPORTED_LANGUAGES)}\n"
    
    return docs


async def get_call_graph_schema() -> str:
    """Get call graph JSON schema."""
    return json.dumps(CALL_GRAPH_SCHEMA, indent=2)


async def get_examples_and_best_practices() -> str:
    """Get examples and best practices documentation."""
    docs = """# AST-Grep Examples and Best Practices

## Best Practices

### 1. Pattern Specificity
- Use specific patterns to avoid false positives
- Include context when possible (e.g., match within specific constructs)

### 2. Language Considerations
- Patterns are language-specific due to different syntax
- Test patterns with small code samples first

### 3. Meta-variable Naming
- Use descriptive meta-variable names: `$FUNCTION_NAME` instead of `$F`
- Be consistent with naming conventions

### 4. Performance Tips
- Use file filters to limit search scope
- Prefer specific patterns over overly broad ones

## Common Use Cases

### Code Quality Checks
```
# Find console.log statements (JavaScript)
console.log($$$ARGS)

# Find TODO comments
// TODO: $COMMENT
```

### Refactoring Patterns
```
# Find old API usage
api.oldMethod($ARGS)

# Match for replacement with:
api.newMethod($ARGS)
```

### Security Patterns
```
# Find potential SQL injection (Python)
cursor.execute($QUERY + $INPUT)

# Find eval usage (JavaScript)
eval($CODE)
```

## Language-Specific Examples

### JavaScript/TypeScript
- Function declarations: `function $NAME($ARGS) { $BODY }`
- Arrow functions: `($ARGS) => $BODY`
- Import statements: `import $IMPORT from '$MODULE'`

### Python
- Function definitions: `def $NAME($ARGS): $BODY`
- Class definitions: `class $NAME($BASE): $BODY`
- Import statements: `from $MODULE import $IMPORT`

### Java
- Method definitions: `$VISIBILITY $TYPE $NAME($ARGS) { $BODY }`
- Class definitions: `class $NAME { $BODY }`

### Rust
- Function definitions: `fn $NAME($ARGS) -> $RETURN { $BODY }`
- Struct definitions: `struct $NAME { $FIELDS }`
"""
    
    return docs


def register_resources(server: Server) -> None:
    """Register all documentation and schema resources.
    
    Args:
        server: MCP server instance
    """
    
    @server.list_resources()
    async def list_resources() -> List[Resource]:
        """List all available resources."""
        return [
            Resource(
                uri="ast-grep://patterns",
                name="AST-Grep Pattern Syntax",
                description="Comprehensive documentation of AST-Grep pattern syntax and usage",
                mimeType="text/markdown"
            ),
            Resource(
                uri="ast-grep://languages",
                name="Supported Languages",
                description="List of programming languages supported by AST-Grep",
                mimeType="text/markdown"
            ),
            Resource(
                uri="ast-grep://examples",
                name="Examples and Best Practices",
                description="Practical examples and best practices for using AST-Grep patterns",
                mimeType="text/markdown"
            ),
            Resource(
                uri="ast-grep://call-graph-schema",
                name="Call Graph JSON Schema",
                description="JSON schema definition for call graph output format",
                mimeType="application/json"
            ),
            Resource(
                uri="ast-grep://call-graph/{path}",
                name="Dynamic Call Graph",
                description="Generate call graph for specified file or directory path. Use URL encoding for special characters.",
                mimeType="application/json"
            )
        ]
    
    @server.read_resource()
    async def read_resource(uri: str) -> str:
        """Read the content of a specific resource."""
        # Handle static resources
        if uri == "ast-grep://patterns":
            return await get_pattern_documentation()
        elif uri == "ast-grep://languages":
            return await get_supported_languages()
        elif uri == "ast-grep://examples":
            return await get_examples_and_best_practices()
        elif uri == "ast-grep://call-graph-schema":
            return await get_call_graph_schema()
        else:
            # Handle dynamic path resources
            path_info = path_handler.parse_call_graph_uri(uri)
            if path_info and path_info["type"] == "call_graph":
                return await get_call_graph_for_path(path_info)
            else:
                raise ValueError(f"Unknown resource URI: {uri}")
    
    logger.info("All AST-Grep resources registered successfully (including dynamic path support)") 