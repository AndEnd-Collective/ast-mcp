"""Utility functions for AST-Grep MCP Server."""

import os
import sys
import logging
import subprocess  # nosec B404
import asyncio
from typing import Optional, Dict, Any, List, Set, Tuple, Union
from pathlib import Path
import shutil
import re
from datetime import datetime, timezone
import json
import hashlib
import tempfile
import time
import platform
import signal
from dataclasses import dataclass
import resource

# Optional imports for enhanced monitoring
try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    psutil = None
    HAS_PSUTIL = False

# Environment variable names
ENV_AST_GREP_PATH = "AST_GREP_BINARY_PATH"
ENV_MAX_FILES = "AST_GREP_MAX_FILES"
ENV_TIMEOUT = "AST_GREP_TIMEOUT"

# Default configuration values
DEFAULT_TIMEOUT = 300  # 5 minutes
DEFAULT_MAX_FILES = 10000

# Third-party imports
try:
    from .resources import FUNCTION_PATTERNS, CALL_PATTERNS
    from .schemas import validate_call_graph_data, CallGraphValidator
    from .security import (
        get_security_manager,
        secure_validate_path,
        secure_validate_pattern,
        secure_sanitize_command,
        SecurityError,
        CommandInjectionError,
        PathTraversalError,
        ResourceLimitError,
        RateLimitError,
    )
except ImportError:
    # For testing or when module is not installed
    FUNCTION_PATTERNS = {}
    CALL_PATTERNS = {}
    def validate_call_graph_data(data): return {'valid': True, 'errors': []}
    class CallGraphValidator:
        def validate_call_graph(self, data): return {'valid': True, 'errors': []}
    # Mock security functions for testing
    def get_security_manager(): return None
    def secure_validate_path(path, base=None): return Path(path)
    def secure_validate_pattern(pattern): return pattern
    def secure_sanitize_command(cmd, args): return cmd, args
    class SecurityError(Exception): pass
    class CommandInjectionError(SecurityError): pass
    class PathTraversalError(SecurityError): pass
    class ResourceLimitError(SecurityError): pass
    class RateLimitError(SecurityError): pass


class ASTGrepError(Exception):
    """Base exception for AST-Grep related errors."""
    pass


class ASTGrepNotFoundError(ASTGrepError):
    """Raised when ast-grep binary is not found."""
    pass


class ASTGrepValidationError(ASTGrepError):
    """Exception raised for AST-Grep validation errors."""
    pass


def setup_logging(level: str = "INFO") -> None:
    """Set up enhanced logging configuration for the server.
    
    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR)
    """
    # Try to use enhanced logging if available
    try:
        from .logging_config import setup_enhanced_logging, LoggingConfig
        
        # Create config with provided level
        config = LoggingConfig.from_environment()
        config.level = level.upper()
        
        # Setup enhanced logging
        setup_enhanced_logging(config)
        
    except ImportError:
        # Fallback to basic logging
        logging.basicConfig(
            level=getattr(logging, level.upper()),
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            handlers=[
                logging.StreamHandler(sys.stdout),
                logging.FileHandler("ast_grep_mcp.log", mode="a")
            ]
        )
        
        # Set specific log levels for external libraries
        logging.getLogger("mcp").setLevel(logging.WARNING)
        logging.getLogger("asyncio").setLevel(logging.WARNING)


async def find_ast_grep_binary() -> Optional[Path]:
    """Find the ast-grep binary in various locations.
    
    Returns:
        Path to ast-grep binary if found, None otherwise
    """
    # Check environment variable first
    if env_path := os.getenv(ENV_AST_GREP_PATH):
        env_path_obj = Path(env_path)
        if env_path_obj.exists() and env_path_obj.is_file():
            return env_path_obj
    
    # Try to use embedded binary from ast-grep-cli package
    try:
        import importlib.util
        import sys
        
        # Find ast-grep-cli package
        spec = importlib.util.find_spec("ast_grep_cli")
        if spec and spec.origin:
            # Get the package directory
            package_dir = Path(spec.origin).parent
            
            # Look for binary in package
            binary_names = ["ast-grep", "sg", "ast_grep"]
            for binary_name in binary_names:
                binary_path = package_dir / binary_name
                if binary_path.exists() and binary_path.is_file():
                    return binary_path
                
                # Also check bin subdirectory
                bin_path = package_dir / "bin" / binary_name
                if bin_path.exists() and bin_path.is_file():
                    return bin_path
    except ImportError:
        pass
    
    # Common binary names to search for
    binary_names = ["ast-grep", "sg", "ast_grep"]
    
    # Search in PATH
    for binary_name in binary_names:
        if binary_path := shutil.which(binary_name):
            return Path(binary_path)
    
    # Search in common installation paths
    common_paths = [
        Path.home() / ".cargo" / "bin",
        Path("/usr/local/bin"),
        Path("/usr/bin"),
        Path("/opt/homebrew/bin"),  # macOS Homebrew
        Path.home() / ".local" / "bin",  # Python user installs
        Path.home() / "node_modules" / ".bin",  # npm local installs
    ]
    
    for base_path in common_paths:
        for binary_name in binary_names:
            full_path = base_path / binary_name
            if full_path.exists() and full_path.is_file():
                return full_path
    
    return None


async def validate_ast_grep_version(binary_path: Path) -> Dict[str, Any]:
    """Validate ast-grep binary and get version information.
    
    Args:
        binary_path: Path to ast-grep binary
        
    Returns:
        Dictionary containing version and capability information
        
    Raises:
        ASTGrepValidationError: If validation fails
    """
    try:
        # Run ast-grep --version
        process = await asyncio.create_subprocess_exec(
            str(binary_path), "--version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await asyncio.wait_for(
            process.communicate(), timeout=10
        )
        
        if process.returncode != 0:
            raise ASTGrepValidationError(
                f"ast-grep --version failed: {stderr.decode()}"
            )
        
        version_output = stdout.decode().strip()
        
        # Parse version information
        version_info = {
            "version": version_output,
            "binary_path": str(binary_path),
            "supports_json": True,  # Assume modern version
            "supports_interactive": True
        }
        
        # Test JSON output capability
        test_process = await asyncio.create_subprocess_exec(
            str(binary_path), "--help",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        test_stdout, _ = await asyncio.wait_for(
            test_process.communicate(), timeout=10
        )
        
        help_output = test_stdout.decode()
        version_info["supports_json"] = "--json" in help_output
        
        return version_info
        
    except asyncio.TimeoutError:
        raise ASTGrepValidationError("ast-grep validation timed out")
    except Exception as e:
        raise ASTGrepValidationError(f"ast-grep validation failed: {e}")


async def validate_ast_grep_installation() -> Path:
    """Validate that ast-grep is properly installed and accessible.
    
    Returns:
        Path to validated ast-grep binary
        
    Raises:
        ASTGrepNotFoundError: If ast-grep is not found
        ASTGrepValidationError: If validation fails
    """
    logger = logging.getLogger(__name__)
    
    # Find the binary
    binary_path = await find_ast_grep_binary()
    if not binary_path:
        raise ASTGrepNotFoundError(
            "ast-grep binary not found. Please install ast-grep using:\n"
            "  npm install -g @ast-grep/cli\n"
            "  or cargo install ast-grep --locked\n"
            "  or pip install ast-grep-cli"
        )
    
    logger.info(f"Found ast-grep binary at: {binary_path}")
    
    # Validate the binary
    version_info = await validate_ast_grep_version(binary_path)
    logger.info(f"ast-grep validation successful: {version_info['version']}")
    
    return binary_path


def get_timeout() -> int:
    """Get configured timeout value from environment or default."""
    try:
        return int(os.getenv(ENV_TIMEOUT, DEFAULT_TIMEOUT))
    except ValueError:
        return DEFAULT_TIMEOUT


def get_max_files() -> int:
    """Get configured max files limit from environment or default."""
    try:
        return int(os.getenv(ENV_MAX_FILES, DEFAULT_MAX_FILES))
    except ValueError:
        return DEFAULT_MAX_FILES


def sanitize_path(path: str, base_path: Optional[str] = None) -> Path:
    """Sanitize and validate file paths to prevent traversal attacks.
    
    Args:
        path: Input path to sanitize
        base_path: Optional base path to restrict access to
        
    Returns:
        Sanitized Path object
        
    Raises:
        ValueError: If path is invalid or contains traversal attempts
    """
    try:
        # Convert to Path and resolve
        path_obj = Path(path).resolve()
        
        # Check for path traversal attempts
        if ".." in str(path_obj):
            raise ValueError("Path traversal detected")
        
        # If base_path is provided, ensure the path is within it
        if base_path:
            base_path_obj = Path(base_path).resolve()
            try:
                path_obj.relative_to(base_path_obj)
            except ValueError:
                raise ValueError(f"Path {path} is outside allowed base path {base_path}")
        
        return path_obj
        
    except Exception as e:
        raise ValueError(f"Invalid path: {e}")


class LanguageManager:
    """Comprehensive language support system with detection, validation, and mapping."""
    
    def __init__(self):
        """Initialize the language manager with caching and logging."""
        self._language_cache = {}
        self.logger = logging.getLogger(__name__)
        
        # Add backward compatibility alias
        self._cache = self._language_cache
        
    def detect_language_from_extension(self, file_path: Union[str, Path]) -> Optional[str]:
        """Detect programming language from file extension with enhanced accuracy.

        Args:
            file_path: Path to the file (string or Path object)

        Returns:
            Detected language identifier or None if not detected
        """
        from .resources import SUPPORTED_LANGUAGES

        if not file_path:
            return None
            
        # Convert to Path object if string
        if isinstance(file_path, str):
            file_path = Path(file_path)
            
        extension = file_path.suffix.lower()
        
        # Handle special cases first
        if extension == ".h":
            # Check for C++ headers by looking at content or directory context
            return self._detect_c_or_cpp_header(file_path)
        
        # Standard extension matching
        for language, info in SUPPORTED_LANGUAGES.items():
            if extension in info.get("extensions", []):
                return language
        
        return None
    
    def _get_cache_key(self, file_path: str, content: Optional[str] = None) -> str:
        """Generate cache key for language detection results.
        
        Args:
            file_path: File path
            content: Optional content for cache key
            
        Returns:
            Cache key string
        """
        if content is not None:
            content_hash = hash(content[:1000])  # Use first 1000 chars for hash
            return f"{file_path}:{content_hash}"
        return file_path
    
    def _detect_language_from_content_string(self, content: str) -> Optional[str]:
        """Detect language from content string.
        
        Args:
            content: File content
            
        Returns:
            Detected language identifier or None if not detected
        """
        if not content or not content.strip():
            return None
            
        lines = content.strip().split('\n')[:10]  # Check first 10 lines
        
        # Check for shebang
        if lines and lines[0].startswith('#!'):
            shebang = lines[0].lower()
            shebang_patterns = {
                'python': ['python', 'python3'],
                'bash': ['bash', 'sh'],
                'javascript': ['node'],
                'ruby': ['ruby'],
                'php': ['php'],
                'perl': ['perl'],
            }
            
            for lang, patterns in shebang_patterns.items():
                if any(pattern in shebang for pattern in patterns):
                    return lang
        
        # Check for language-specific patterns
        content_lower = content.lower()
        
        # TypeScript/JavaScript patterns
        if any(pattern in content_lower for pattern in ['interface ', 'namespace ', ': string', ': number']):
            return 'typescript'
        elif any(pattern in content_lower for pattern in ['console.log', 'function ', 'const ', 'let ', 'var ']):
            return 'javascript'
        
        # Python patterns
        if any(pattern in content_lower for pattern in ['def ', 'import ', 'from ', 'class ', 'if __name__']):
            return 'python'
        
        # Rust patterns  
        if any(pattern in content_lower for pattern in ['fn ', 'let ', 'struct ', 'impl ', 'use ']):
            return 'rust'
        
        # C/C++ patterns
        if any(pattern in content_lower for pattern in ['#include', 'int main', 'printf', 'cout']):
            if any(cpp_pattern in content_lower for cpp_pattern in ['std::', 'cout', 'cin', 'vector']):
                return 'cpp'
            return 'c'
            
        return None

    def detect_language_from_filename(self, file_path: Union[str, Path]) -> Optional[str]:
        """Detect language from specific filename patterns.
        
        Args:
            file_path: Path to the file (string or Path object)
            
        Returns:
            Detected language identifier or None if not detected
        """
        # Handle None/empty inputs
        if not file_path:
            return None
            
        # Convert string to Path
        if isinstance(file_path, str):
            if not file_path.strip():
                return None
            file_path = Path(file_path)
            
        filename = file_path.name.lower()
        
        # Special filename patterns
        filename_patterns = {
            "makefile": "make",
            "dockerfile": "dockerfile", 
            "gemfile": "ruby",
            "rakefile": "ruby",
            "gulpfile.js": "javascript",
            "gruntfile.js": "javascript",
            "webpack.config.js": "javascript",
            "package.json": "json",
            "composer.json": "json",
            "tsconfig.json": "json",
            "cmakelist.txt": "cmake",
            "cmakelists.txt": "cmake",
            ".bashrc": "bash",
            ".zshrc": "bash",
            ".eslintrc": "json",
            ".babelrc": "json",
            "requirements.txt": "text",
            "readme.md": "markdown",
            ".gitignore": "gitignore",
            ".env": "env"
        }
        
        for pattern, language in filename_patterns.items():
            if filename == pattern or filename.endswith(pattern):
                return language
        
        return None
    
    def detect_language_from_content(self, file_path: Path, max_lines: int = 10) -> Optional[str]:
        """Detect language from file content analysis.
        
        Args:
            file_path: Path to the file
            max_lines: Maximum lines to analyze
            
        Returns:
            Detected language identifier or None if not detected
        """
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = [f.readline().strip() for _ in range(max_lines)]
            
            content = '\n'.join(lines)
            
            # Shebang detection
            if lines and lines[0].startswith('#!'):
                shebang = lines[0]
                if 'python' in shebang:
                    return 'python'
                elif 'node' in shebang or 'nodejs' in shebang:
                    return 'javascript'
                elif 'ruby' in shebang:
                    return 'ruby'
                elif 'bash' in shebang or 'sh' in shebang:
                    return 'bash'
                elif 'php' in shebang:
                    return 'php'
            
            # Content-based detection patterns
            content_patterns = [
                (r'^\s*import\s+.*\s+from\s+["\']', 'javascript'),
                (r'^\s*const\s+.*\s*=\s*require\(', 'javascript'),
                (r'^\s*export\s+(default\s+)?', 'javascript'),
                (r'^\s*interface\s+\w+', 'typescript'),
                (r'^\s*type\s+\w+\s*=', 'typescript'),
                (r'^\s*def\s+\w+\s*\(', 'python'),
                (r'^\s*class\s+\w+\s*\(.*\):', 'python'),
                (r'^\s*from\s+\w+\s+import', 'python'),
                (r'^\s*fn\s+\w+\s*\(', 'rust'),
                (r'^\s*use\s+std::', 'rust'),
                (r'^\s*package\s+main', 'go'),
                (r'^\s*func\s+\w+\s*\(', 'go'),
                (r'^\s*public\s+class\s+\w+', 'java'),
                (r'^\s*#include\s*<.*>', 'c'),
                (r'^\s*using\s+namespace\s+', 'cpp'),
                (r'^\s*class\s+\w+\s*{', 'cpp'),
                (r'^\s*namespace\s+\w+', 'csharp'),
                (r'^\s*using\s+System;', 'csharp'),
                (r'^\s*<?php', 'php'),
                (r'^\s*class\s+\w+\s*<', 'ruby'),
                (r'^\s*module\s+\w+', 'ruby'),
                (r'^\s*import\s+Foundation', 'swift'),
                (r'^\s*class\s+\w+\s*:', 'swift'),
                (r'^\s*fun\s+\w+\s*\(', 'kotlin'),
                (r'^\s*class\s+\w+\s*extends', 'scala'),
                (r'^\s*object\s+\w+', 'scala'),
            ]
            
            for pattern, language in content_patterns:
                if re.search(pattern, content, re.MULTILINE):
                    return language
            
        except Exception as e:
            self.logger.debug(f"Content analysis failed for {file_path}: {e}")
        
        return None
    
    def detect_language(self, file_path: Union[str, Path], content: Optional[str] = None) -> str:
        """Comprehensive language detection using multiple strategies.
        
        Args:
            file_path: Path to the file (string or Path object)  
            content: Optional file content for content-based detection
            
        Returns:
            Detected language identifier or "text" if not detected
        """
        # Handle None/empty inputs
        if not file_path:
            return "text"
            
        # Convert string to Path
        if isinstance(file_path, str):
            if not file_path.strip():
                return "text"
            file_path = Path(file_path)
        
        # Cache key
        cache_key = self._get_cache_key(str(file_path), content)
        if cache_key in self._language_cache:
            return self._language_cache[cache_key]
        
        # Special handling for .h files with content
        if file_path.suffix.lower() == ".h" and content is not None:
            detected = self._detect_c_or_cpp_header(file_path, content)
            self._language_cache[cache_key] = detected
            return detected
        
        # Strategy 1: Extension-based detection
        if detected := self.detect_language_from_extension(file_path):
            self._language_cache[cache_key] = detected
            return detected
        
        # Strategy 2: Filename-based detection
        if detected := self.detect_language_from_filename(file_path):
            self._language_cache[cache_key] = detected
            return detected
        
        # Strategy 3: Content-based detection
        if content is not None:
            # Use provided content for detection
            if detected := self._detect_language_from_content_string(content):
                self._language_cache[cache_key] = detected
                return detected
        elif file_path.exists() and file_path.is_file():
            if detected := self.detect_language_from_content(file_path):
                self._language_cache[cache_key] = detected
                return detected
        
        # Return "text" for unknown files instead of None
        result = "text"
        self._language_cache[cache_key] = result
        return result
    
    def validate_language_identifier(self, language: str, return_normalized: bool = False) -> Union[str, bool]:
        """Validate language identifier and optionally return normalized form.
        
        Args:
            language: Language identifier to validate
            return_normalized: If True, return normalized language name instead of boolean
            
        Returns:
            Boolean indicating validity, or normalized language identifier if return_normalized=True
            
        Raises:
            ValueError: If language is not supported and return_normalized=True
        """
        from .resources import SUPPORTED_LANGUAGES
        
        if not language:
            if return_normalized:
                raise ValueError("Language identifier cannot be empty")
            return False
        
        language = language.lower().strip()
        
        # Direct match
        if language in SUPPORTED_LANGUAGES:
            return language if return_normalized else True
        
        # Alias matching
        for lang, info in SUPPORTED_LANGUAGES.items():
            if language in info.get("aliases", []):
                return lang if return_normalized else True
        
        # Extension matching (without leading dot)
        if language.startswith('.'):
            for lang, info in SUPPORTED_LANGUAGES.items():
                if language in info.get("extensions", []):
                    return lang if return_normalized else True
        
        # Tree-sitter name matching
        for lang, info in SUPPORTED_LANGUAGES.items():
            if language == info.get("tree_sitter", ""):
                return lang if return_normalized else True
        
        if not return_normalized:
            return False
            
        # Create helpful error message
        supported = set(SUPPORTED_LANGUAGES.keys())
        for info in SUPPORTED_LANGUAGES.values():
            supported.update(info.get("aliases", []))
        
        raise ValueError(
            f"Unsupported language: '{language}'. "
            f"Supported languages: {', '.join(sorted(supported))}"
        )
    
    def get_language_info(self, language: str) -> Dict[str, Any]:
        """Get comprehensive information about a language.
        
        Args:
            language: Language identifier
            
        Returns:
            Dictionary containing language information
            
        Raises:
            ValueError: If language is not supported
        """
        from .resources import SUPPORTED_LANGUAGES
        
        normalized = self.validate_language_identifier(language, return_normalized=True)
        info = SUPPORTED_LANGUAGES[normalized].copy()
        info["canonical_name"] = normalized
        return info
    
    def get_supported_languages(self) -> Set[str]:
        """Get set of all supported language identifiers."""
        from .resources import SUPPORTED_LANGUAGES
        return set(SUPPORTED_LANGUAGES.keys())
    
    def get_supported_extensions(self) -> Set[str]:
        """Get set of all supported file extensions."""
        from .resources import SUPPORTED_LANGUAGES
        extensions = set()
        for info in SUPPORTED_LANGUAGES.values():
            extensions.update(info.get("extensions", []))
        return extensions
    
    def map_to_ast_grep_language(self, language: str) -> str:
        """Map language identifier to ast-grep compatible language code.
        
        Args:
            language: Language identifier
            
        Returns:
            ast-grep compatible language code
        """
        from .resources import SUPPORTED_LANGUAGES
        
        # First normalize the language identifier
        normalized = self.validate_language_identifier(language, return_normalized=True)
        
        # Get the tree-sitter mapping from the language info
        language_info = SUPPORTED_LANGUAGES[normalized]
        tree_sitter_code = language_info.get("tree_sitter", normalized)
        
        return tree_sitter_code
    
    def get_language_patterns(self, language: str) -> List[Dict[str, Any]]:
        """Get common pattern examples for a specific language.
        
        Args:
            language: Language identifier
            
        Returns:
            List of pattern examples for the language
        """
        # Handle invalid languages gracefully
        try:
            normalized = self.validate_language_identifier(language, return_normalized=True)
        except ValueError:
            return []
        
        # Comprehensive language-specific pattern examples
        patterns = {
            "javascript": [
                {"pattern": "console.log($MSG)", "description": "Console log statements", "category": "debugging"},
                {"pattern": "function $NAME($ARGS) { $BODY }", "description": "Function declarations", "category": "functions"},
                {"pattern": "$OBJ.$METHOD($ARGS)", "description": "Method calls", "category": "methods"},
                {"pattern": "const $VAR = require($MODULE)", "description": "CommonJS imports", "category": "imports"},
                {"pattern": "import $VAR from $MODULE", "description": "ES6 imports", "category": "imports"},
                {"pattern": "export default $EXPR", "description": "Default exports", "category": "exports"},
                {"pattern": "async function $NAME($ARGS) { $BODY }", "description": "Async function declarations", "category": "async"},
                {"pattern": "await $EXPR", "description": "Await expressions", "category": "async"},
                {"pattern": "try { $BODY } catch ($ERR) { $HANDLER }", "description": "Error handling", "category": "error-handling"},
                {"pattern": "class $NAME { $BODY }", "description": "Class declarations", "category": "classes"},
                {"pattern": "new $CLASS($ARGS)", "description": "Object instantiation", "category": "objects"},
                {"pattern": "if ($COND) { $THEN }", "description": "Conditional statements", "category": "control-flow"},
                {"pattern": "for (let $VAR of $ITER) { $BODY }", "description": "For-of loops", "category": "loops"},
                {"pattern": "$VAR => $EXPR", "description": "Arrow functions", "category": "functions"},
                {"pattern": "JSON.parse($STR)", "description": "JSON parsing", "category": "data"}
            ],
            "typescript": [
                {"pattern": "interface $NAME { $FIELDS }", "description": "Interface declarations", "category": "types"},
                {"pattern": "type $NAME = $TYPE", "description": "Type aliases", "category": "types"},
                {"pattern": "class $NAME implements $INTERFACE { $BODY }", "description": "Class implementations", "category": "classes"},
                {"pattern": "$VAR: $TYPE", "description": "Type annotations", "category": "types"},
                {"pattern": "function $NAME<$GENERICS>($ARGS): $RETURN { $BODY }", "description": "Generic functions", "category": "generics"},
                {"pattern": "enum $NAME { $VALUES }", "description": "Enum declarations", "category": "enums"},
                {"pattern": "namespace $NAME { $BODY }", "description": "Namespace declarations", "category": "namespaces"},
                {"pattern": "import type { $TYPES } from $MODULE", "description": "Type imports", "category": "imports"},
                {"pattern": "as $TYPE", "description": "Type assertions", "category": "types"},
                {"pattern": "readonly $PROP: $TYPE", "description": "Readonly properties", "category": "types"}
            ],
            "python": [
                {"pattern": "def $NAME($ARGS): $BODY", "description": "Function definitions", "category": "functions"},
                {"pattern": "class $NAME($BASE): $BODY", "description": "Class definitions", "category": "classes"},
                {"pattern": "import $MODULE", "description": "Import statements", "category": "imports"},
                {"pattern": "from $MODULE import $NAMES", "description": "From imports", "category": "imports"},
                {"pattern": "if __name__ == '__main__': $BODY", "description": "Main guard", "category": "main"},
                {"pattern": "try: $BODY except $EXCEPTION: $HANDLER", "description": "Exception handling", "category": "error-handling"},
                {"pattern": "with $CONTEXT as $VAR: $BODY", "description": "Context managers", "category": "context"},
                {"pattern": "for $VAR in $ITER: $BODY", "description": "For loops", "category": "loops"},
                {"pattern": "[$EXPR for $VAR in $ITER]", "description": "List comprehensions", "category": "comprehensions"},
                {"pattern": "@$DECORATOR", "description": "Decorators", "category": "decorators"},
                {"pattern": "lambda $ARGS: $EXPR", "description": "Lambda functions", "category": "lambdas"},
                {"pattern": "async def $NAME($ARGS): $BODY", "description": "Async function definitions", "category": "async"},
                {"pattern": "yield $EXPR", "description": "Generator yield", "category": "generators"},
                {"pattern": "self.$ATTR", "description": "Instance attributes", "category": "attributes"},
                {"pattern": "print($ARGS)", "description": "Print statements", "category": "output"}
            ],
            "rust": [
                {"pattern": "fn $NAME($ARGS) -> $TYPE { $BODY }", "description": "Function definitions", "category": "functions"},
                {"pattern": "struct $NAME { $FIELDS }", "description": "Struct definitions", "category": "structs"},
                {"pattern": "impl $NAME { $METHODS }", "description": "Implementation blocks", "category": "impl"},
                {"pattern": "use $MODULE;", "description": "Use statements", "category": "imports"},
                {"pattern": "let $VAR = $EXPR;", "description": "Variable bindings", "category": "variables"},
                {"pattern": "match $EXPR { $ARMS }", "description": "Pattern matching", "category": "matching"},
                {"pattern": "if let $PATTERN = $EXPR { $BODY }", "description": "If let patterns", "category": "matching"},
                {"pattern": "&$EXPR", "description": "References", "category": "borrowing"},
                {"pattern": "*$EXPR", "description": "Dereferences", "category": "borrowing"},
                {"pattern": "Box::new($EXPR)", "description": "Heap allocation", "category": "memory"},
                {"pattern": "Result<$OK, $ERR>", "description": "Result types", "category": "error-handling"},
                {"pattern": "Option<$TYPE>", "description": "Option types", "category": "optional"},
                {"pattern": "enum $NAME { $VARIANTS }", "description": "Enum definitions", "category": "enums"},
                {"pattern": "trait $NAME { $METHODS }", "description": "Trait definitions", "category": "traits"},
                {"pattern": "macro_rules! $NAME { $RULES }", "description": "Macro definitions", "category": "macros"}
            ],
            "go": [
                {"pattern": "func $NAME($ARGS) $TYPE { $BODY }", "description": "Function definitions", "category": "functions"},
                {"pattern": "type $NAME struct { $FIELDS }", "description": "Struct definitions", "category": "structs"},
                {"pattern": "package $NAME", "description": "Package declarations", "category": "packages"},
                {"pattern": "import $PACKAGE", "description": "Import statements", "category": "imports"},
                {"pattern": "var $VAR $TYPE", "description": "Variable declarations", "category": "variables"},
                {"pattern": "if err != nil { $BODY }", "description": "Error checking", "category": "error-handling"},
                {"pattern": "go $FUNC($ARGS)", "description": "Goroutine creation", "category": "concurrency"},
                {"pattern": "chan $TYPE", "description": "Channel types", "category": "channels"},
                {"pattern": "select { $CASES }", "description": "Channel selection", "category": "channels"},
                {"pattern": "defer $FUNC($ARGS)", "description": "Deferred function calls", "category": "defer"},
                {"pattern": "for $COND { $BODY }", "description": "For loops", "category": "loops"},
                {"pattern": "interface{}", "description": "Empty interfaces", "category": "interfaces"},
                {"pattern": "type $NAME interface { $METHODS }", "description": "Interface definitions", "category": "interfaces"},
                {"pattern": "$VAR := $EXPR", "description": "Short variable declarations", "category": "variables"},
                {"pattern": "make($TYPE, $ARGS)", "description": "Make built-in", "category": "built-ins"}
            ],
            "java": [
                {"pattern": "public class $NAME { $BODY }", "description": "Public class declarations", "category": "classes"},
                {"pattern": "public $TYPE $NAME($ARGS) { $BODY }", "description": "Public method definitions", "category": "methods"},
                {"pattern": "import $PACKAGE;", "description": "Import statements", "category": "imports"},
                {"pattern": "@$ANNOTATION", "description": "Annotations", "category": "annotations"},
                {"pattern": "try { $BODY } catch ($EXCEPTION $VAR) { $HANDLER }", "description": "Exception handling", "category": "error-handling"},
                {"pattern": "for ($INIT; $COND; $UPDATE) { $BODY }", "description": "For loops", "category": "loops"},
                {"pattern": "if ($COND) { $BODY }", "description": "Conditional statements", "category": "control-flow"},
                {"pattern": "new $CLASS($ARGS)", "description": "Object instantiation", "category": "objects"},
                {"pattern": "extends $CLASS", "description": "Class inheritance", "category": "inheritance"},
                {"pattern": "implements $INTERFACE", "description": "Interface implementation", "category": "interfaces"},
                {"pattern": "static $TYPE $NAME", "description": "Static members", "category": "static"},
                {"pattern": "final $TYPE $NAME", "description": "Final variables", "category": "final"},
                {"pattern": "System.out.println($MSG)", "description": "Console output", "category": "output"},
                {"pattern": "synchronized ($OBJ) { $BODY }", "description": "Synchronization", "category": "concurrency"},
                {"pattern": "lambda $ARGS -> $EXPR", "description": "Lambda expressions", "category": "lambdas"}
            ],
            "c": [
                {"pattern": "#include <$HEADER>", "description": "System header includes", "category": "includes"},
                {"pattern": "#include \"$HEADER\"", "description": "Local header includes", "category": "includes"},
                {"pattern": "int $NAME($ARGS) { $BODY }", "description": "Function definitions", "category": "functions"},
                {"pattern": "struct $NAME { $FIELDS };", "description": "Struct definitions", "category": "structs"},
                {"pattern": "typedef $TYPE $NAME;", "description": "Type definitions", "category": "typedefs"},
                {"pattern": "if ($COND) { $BODY }", "description": "Conditional statements", "category": "control-flow"},
                {"pattern": "for ($INIT; $COND; $UPDATE) { $BODY }", "description": "For loops", "category": "loops"},
                {"pattern": "while ($COND) { $BODY }", "description": "While loops", "category": "loops"},
                {"pattern": "malloc($SIZE)", "description": "Memory allocation", "category": "memory"},
                {"pattern": "free($PTR)", "description": "Memory deallocation", "category": "memory"},
                {"pattern": "printf($FORMAT, $ARGS)", "description": "Formatted output", "category": "output"},
                {"pattern": "*$PTR", "description": "Pointer dereference", "category": "pointers"},
                {"pattern": "&$VAR", "description": "Address-of operator", "category": "pointers"},
                {"pattern": "#define $NAME $VALUE", "description": "Macro definitions", "category": "macros"},
                {"pattern": "return $EXPR;", "description": "Return statements", "category": "control-flow"}
            ],
            "cpp": [
                {"pattern": "class $NAME { $BODY };", "description": "Class declarations", "category": "classes"},
                {"pattern": "namespace $NAME { $BODY }", "description": "Namespace declarations", "category": "namespaces"},
                {"pattern": "template<$PARAMS> $DECL", "description": "Template declarations", "category": "templates"},
                {"pattern": "std::$IDENTIFIER", "description": "Standard library usage", "category": "std"},
                {"pattern": "using namespace $NAME;", "description": "Using declarations", "category": "using"},
                {"pattern": "$TYPE& $NAME", "description": "Reference parameters", "category": "references"},
                {"pattern": "const $TYPE& $NAME", "description": "Const references", "category": "const"},
                {"pattern": "virtual $TYPE $NAME($ARGS)", "description": "Virtual functions", "category": "virtual"},
                {"pattern": "override", "description": "Function overrides", "category": "override"},
                {"pattern": "new $TYPE($ARGS)", "description": "Dynamic allocation", "category": "memory"},
                {"pattern": "delete $PTR", "description": "Memory deallocation", "category": "memory"},
                {"pattern": "auto $VAR = $EXPR", "description": "Auto type deduction", "category": "auto"},
                {"pattern": "for (auto $VAR : $CONTAINER) { $BODY }", "description": "Range-based for loops", "category": "loops"},
                {"pattern": "std::unique_ptr<$TYPE>", "description": "Smart pointers", "category": "smart-pointers"},
                {"pattern": "lambda $CAPTURE($ARGS) { $BODY }", "description": "Lambda expressions", "category": "lambdas"}
            ],
            "csharp": [
                {"pattern": "public class $NAME { $BODY }", "description": "Public class declarations", "category": "classes"},
                {"pattern": "using $NAMESPACE;", "description": "Using statements", "category": "imports"},
                {"pattern": "namespace $NAME { $BODY }", "description": "Namespace declarations", "category": "namespaces"},
                {"pattern": "public $TYPE $NAME($ARGS) { $BODY }", "description": "Public method definitions", "category": "methods"},
                {"pattern": "var $VAR = $EXPR;", "description": "Implicit variable declarations", "category": "variables"},
                {"pattern": "async Task<$TYPE> $NAME($ARGS) { $BODY }", "description": "Async method definitions", "category": "async"},
                {"pattern": "await $EXPR", "description": "Await expressions", "category": "async"},
                {"pattern": "try { $BODY } catch ($EXCEPTION $VAR) { $HANDLER }", "description": "Exception handling", "category": "error-handling"},
                {"pattern": "interface I$NAME { $METHODS }", "description": "Interface declarations", "category": "interfaces"},
                {"pattern": "[$ATTRIBUTE]", "description": "Attributes", "category": "attributes"},
                {"pattern": "Console.WriteLine($MSG)", "description": "Console output", "category": "output"},
                {"pattern": "LINQ query expressions", "description": "LINQ queries", "category": "linq"},
                {"pattern": "=> $EXPR", "description": "Lambda expressions", "category": "lambdas"},
                {"pattern": "get; set;", "description": "Auto-properties", "category": "properties"},
                {"pattern": "null-conditional operator", "description": "Null propagation", "category": "null-safety"}
            ],
            "php": [
                {"pattern": "<?php $BODY", "description": "PHP opening tags", "category": "tags"},
                {"pattern": "function $NAME($ARGS) { $BODY }", "description": "Function definitions", "category": "functions"},
                {"pattern": "class $NAME { $BODY }", "description": "Class definitions", "category": "classes"},
                {"pattern": "$$VAR", "description": "Variable declarations", "category": "variables"},
                {"pattern": "include $FILE;", "description": "File inclusions", "category": "includes"},
                {"pattern": "require_once $FILE;", "description": "Required inclusions", "category": "includes"},
                {"pattern": "echo $EXPR;", "description": "Output statements", "category": "output"},
                {"pattern": "if ($COND) { $BODY }", "description": "Conditional statements", "category": "control-flow"},
                {"pattern": "foreach ($$ARRAY as $$VAR) { $BODY }", "description": "Foreach loops", "category": "loops"},
                {"pattern": "try { $BODY } catch ($EXCEPTION $$VAR) { $HANDLER }", "description": "Exception handling", "category": "error-handling"},
                {"pattern": "new $CLASS($ARGS)", "description": "Object instantiation", "category": "objects"},
                {"pattern": "extends $CLASS", "description": "Class inheritance", "category": "inheritance"},
                {"pattern": "implements $INTERFACE", "description": "Interface implementation", "category": "interfaces"},
                {"pattern": "$ARRAY[$KEY]", "description": "Array access", "category": "arrays"},
                {"pattern": "->$PROPERTY", "description": "Object property access", "category": "properties"}
            ],
            "ruby": [
                {"pattern": "def $NAME($ARGS) $BODY end", "description": "Method definitions", "category": "methods"},
                {"pattern": "class $NAME $BODY end", "description": "Class definitions", "category": "classes"},
                {"pattern": "require '$MODULE'", "description": "Require statements", "category": "requires"},
                {"pattern": "if $COND $BODY end", "description": "Conditional statements", "category": "control-flow"},
                {"pattern": "$ARRAY.each do |$VAR| $BODY end", "description": "Each iteration", "category": "iteration"},
                {"pattern": "puts $EXPR", "description": "Output statements", "category": "output"},
                {"pattern": "$HASH[:$KEY]", "description": "Hash access", "category": "hashes"},
                {"pattern": "@$VAR", "description": "Instance variables", "category": "variables"},
                {"pattern": "@@$VAR", "description": "Class variables", "category": "variables"},
                {"pattern": "begin $BODY rescue $EXCEPTION $HANDLER end", "description": "Exception handling", "category": "error-handling"},
                {"pattern": "yield $ARGS", "description": "Block yielding", "category": "blocks"},
                {"pattern": "$OBJ.send(:$METHOD, $ARGS)", "description": "Dynamic method calls", "category": "metaprogramming"},
                {"pattern": "attr_accessor :$NAME", "description": "Attribute accessors", "category": "attributes"},
                {"pattern": "lambda { |$ARGS| $BODY }", "description": "Lambda expressions", "category": "lambdas"},
                {"pattern": "case $EXPR when $PATTERN then $BODY end", "description": "Case statements", "category": "control-flow"}
            ],
            "swift": [
                {"pattern": "func $NAME($ARGS) -> $TYPE { $BODY }", "description": "Function definitions", "category": "functions"},
                {"pattern": "class $NAME { $BODY }", "description": "Class definitions", "category": "classes"},
                {"pattern": "struct $NAME { $BODY }", "description": "Struct definitions", "category": "structs"},
                {"pattern": "import $MODULE", "description": "Import statements", "category": "imports"},
                {"pattern": "var $VAR: $TYPE", "description": "Variable declarations", "category": "variables"},
                {"pattern": "let $VAR = $EXPR", "description": "Constant declarations", "category": "constants"},
                {"pattern": "if $COND { $BODY }", "description": "Conditional statements", "category": "control-flow"},
                {"pattern": "for $VAR in $SEQUENCE { $BODY }", "description": "For-in loops", "category": "loops"},
                {"pattern": "switch $EXPR { case $PATTERN: $BODY }", "description": "Switch statements", "category": "control-flow"},
                {"pattern": "guard $COND else { $BODY }", "description": "Guard statements", "category": "guard"},
                {"pattern": "do { $BODY } catch { $HANDLER }", "description": "Error handling", "category": "error-handling"},
                {"pattern": "protocol $NAME { $REQUIREMENTS }", "description": "Protocol definitions", "category": "protocols"},
                {"pattern": "extension $TYPE { $BODY }", "description": "Type extensions", "category": "extensions"},
                {"pattern": "optional var $VAR: $TYPE?", "description": "Optional properties", "category": "optionals"},
                {"pattern": "lazy var $VAR = $EXPR", "description": "Lazy properties", "category": "lazy"}
            ],
            "kotlin": [
                {"pattern": "fun $NAME($ARGS): $TYPE { $BODY }", "description": "Function definitions", "category": "functions"},
                {"pattern": "class $NAME { $BODY }", "description": "Class definitions", "category": "classes"},
                {"pattern": "data class $NAME($PROPERTIES)", "description": "Data class definitions", "category": "data-classes"},
                {"pattern": "import $PACKAGE", "description": "Import statements", "category": "imports"},
                {"pattern": "val $VAR = $EXPR", "description": "Immutable variable declarations", "category": "variables"},
                {"pattern": "var $VAR = $EXPR", "description": "Mutable variable declarations", "category": "variables"},
                {"pattern": "if ($COND) { $BODY }", "description": "Conditional statements", "category": "control-flow"},
                {"pattern": "when ($EXPR) { $ARMS }", "description": "When expressions", "category": "control-flow"},
                {"pattern": "for ($VAR in $RANGE) { $BODY }", "description": "For loops", "category": "loops"},
                {"pattern": "try { $BODY } catch (e: $EXCEPTION) { $HANDLER }", "description": "Exception handling", "category": "error-handling"},
                {"pattern": "suspend fun $NAME($ARGS): $TYPE { $BODY }", "description": "Suspend function definitions", "category": "coroutines"},
                {"pattern": "object $NAME { $BODY }", "description": "Object declarations", "category": "objects"},
                {"pattern": "interface $NAME { $METHODS }", "description": "Interface definitions", "category": "interfaces"},
                {"pattern": "$VAR?.let { $BODY }", "description": "Safe call operations", "category": "null-safety"},
                {"pattern": "lambda { $ARGS -> $BODY }", "description": "Lambda expressions", "category": "lambdas"}
            ],
            "scala": [
                {"pattern": "def $NAME($ARGS): $TYPE = $BODY", "description": "Method definitions", "category": "methods"},
                {"pattern": "class $NAME($ARGS) { $BODY }", "description": "Class definitions", "category": "classes"},
                {"pattern": "object $NAME { $BODY }", "description": "Object definitions", "category": "objects"},
                {"pattern": "import $PACKAGE", "description": "Import statements", "category": "imports"},
                {"pattern": "val $VAR = $EXPR", "description": "Value declarations", "category": "values"},
                {"pattern": "var $VAR = $EXPR", "description": "Variable declarations", "category": "variables"},
                {"pattern": "if ($COND) $THEN else $ELSE", "description": "Conditional expressions", "category": "control-flow"},
                {"pattern": "$COLLECTION.map($FUNC)", "description": "Map operations", "category": "collections"},
                {"pattern": "$COLLECTION.filter($PREDICATE)", "description": "Filter operations", "category": "collections"},
                {"pattern": "case class $NAME($FIELDS)", "description": "Case class definitions", "category": "case-classes"},
                {"pattern": "$EXPR match { case $PATTERN => $BODY }", "description": "Pattern matching", "category": "pattern-matching"},
                {"pattern": "trait $NAME { $BODY }", "description": "Trait definitions", "category": "traits"},
                {"pattern": "extends $TRAIT", "description": "Trait extension", "category": "inheritance"},
                {"pattern": "for ($GENERATOR) yield $EXPR", "description": "For comprehensions", "category": "comprehensions"},
                {"pattern": "implicit $DECL", "description": "Implicit declarations", "category": "implicits"}
            ],
            "lua": [
                {"pattern": "function $NAME($ARGS) $BODY end", "description": "Function definitions", "category": "functions"},
                {"pattern": "local $VAR = $EXPR", "description": "Local variable declarations", "category": "variables"},
                {"pattern": "if $COND then $BODY end", "description": "Conditional statements", "category": "control-flow"},
                {"pattern": "for $VAR = $START, $END do $BODY end", "description": "Numeric for loops", "category": "loops"},
                {"pattern": "for $KEY, $VALUE in pairs($TABLE) do $BODY end", "description": "Table iteration", "category": "loops"},
                {"pattern": "while $COND do $BODY end", "description": "While loops", "category": "loops"},
                {"pattern": "repeat $BODY until $COND", "description": "Repeat loops", "category": "loops"},
                {"pattern": "$TABLE[$KEY]", "description": "Table access", "category": "tables"},
                {"pattern": "require '$MODULE'", "description": "Module loading", "category": "modules"},
                {"pattern": "print($ARGS)", "description": "Output statements", "category": "output"},
                {"pattern": "$OBJ:$METHOD($ARGS)", "description": "Method calls", "category": "methods"},
                {"pattern": "{ $FIELDS }", "description": "Table constructors", "category": "tables"},
                {"pattern": "...", "description": "Varargs", "category": "varargs"},
                {"pattern": "$STRING .. $STRING", "description": "String concatenation", "category": "strings"},
                {"pattern": "pcall($FUNC, $ARGS)", "description": "Protected calls", "category": "error-handling"}
            ],
            "bash": [
                {"pattern": "#!/bin/bash", "description": "Shebang lines", "category": "shebang"},
                {"pattern": "$VAR=$VALUE", "description": "Variable assignments", "category": "variables"},
                {"pattern": "function $NAME() { $BODY }", "description": "Function definitions", "category": "functions"},
                {"pattern": "if [ $COND ]; then $BODY fi", "description": "Conditional statements", "category": "control-flow"},
                {"pattern": "for $VAR in $LIST; do $BODY done", "description": "For loops", "category": "loops"},
                {"pattern": "while [ $COND ]; do $BODY done", "description": "While loops", "category": "loops"},
                {"pattern": "case $VAR in $PATTERNS esac", "description": "Case statements", "category": "control-flow"},
                {"pattern": "echo $MESSAGE", "description": "Output statements", "category": "output"},
                {"pattern": "$COMMAND | $COMMAND", "description": "Command pipes", "category": "pipes"},
                {"pattern": "$COMMAND > $FILE", "description": "Output redirection", "category": "redirection"},
                {"pattern": "$COMMAND < $FILE", "description": "Input redirection", "category": "redirection"},
                {"pattern": "$$", "description": "Process ID variable", "category": "variables"},
                {"pattern": "$#", "description": "Argument count variable", "category": "variables"},
                {"pattern": "$@", "description": "All arguments variable", "category": "variables"},
                {"pattern": "[ -f $FILE ]", "description": "File existence tests", "category": "tests"}
            ],
            "html": [
                {"pattern": "<$TAG $ATTRS>$CONTENT</$TAG>", "description": "HTML elements", "category": "elements"},
                {"pattern": "<!DOCTYPE html>", "description": "Document type declarations", "category": "doctype"},
                {"pattern": "<html $ATTRS>$CONTENT</html>", "description": "HTML root elements", "category": "root"},
                {"pattern": "<head>$CONTENT</head>", "description": "Document head", "category": "head"},
                {"pattern": "<body $ATTRS>$CONTENT</body>", "description": "Document body", "category": "body"},
                {"pattern": "<div $ATTRS>$CONTENT</div>", "description": "Div elements", "category": "layout"},
                {"pattern": "<span $ATTRS>$CONTENT</span>", "description": "Span elements", "category": "inline"},
                {"pattern": "<a href=\"$URL\">$TEXT</a>", "description": "Anchor links", "category": "links"},
                {"pattern": "<img src=\"$SRC\" alt=\"$ALT\">", "description": "Image elements", "category": "media"},
                {"pattern": "<form $ATTRS>$CONTENT</form>", "description": "Form elements", "category": "forms"},
                {"pattern": "<input type=\"$TYPE\" $ATTRS>", "description": "Input elements", "category": "forms"},
                {"pattern": "<script $ATTRS>$CONTENT</script>", "description": "Script elements", "category": "scripts"},
                {"pattern": "<link rel=\"$REL\" href=\"$HREF\">", "description": "Link elements", "category": "links"},
                {"pattern": "<!-- $COMMENT -->", "description": "HTML comments", "category": "comments"},
                {"pattern": "class=\"$CLASSES\"", "description": "CSS class attributes", "category": "attributes"}
            ],
            "css": [
                {"pattern": "$SELECTOR { $DECLARATIONS }", "description": "CSS rules", "category": "rules"},
                {"pattern": "$PROPERTY: $VALUE;", "description": "CSS declarations", "category": "declarations"},
                {"pattern": ".$CLASS", "description": "Class selectors", "category": "selectors"},
                {"pattern": "#$ID", "description": "ID selectors", "category": "selectors"},
                {"pattern": "$ELEMENT", "description": "Element selectors", "category": "selectors"},
                {"pattern": "$SELECTOR:$PSEUDO", "description": "Pseudo-class selectors", "category": "pseudo"},
                {"pattern": "$SELECTOR::$PSEUDO", "description": "Pseudo-element selectors", "category": "pseudo"},
                {"pattern": "@media $QUERY { $RULES }", "description": "Media queries", "category": "media"},
                {"pattern": "@import url($URL);", "description": "Import statements", "category": "imports"},
                {"pattern": "@keyframes $NAME { $FRAMES }", "description": "Keyframe animations", "category": "animations"},
                {"pattern": "/* $COMMENT */", "description": "CSS comments", "category": "comments"},
                {"pattern": "$PARENT > $CHILD", "description": "Child selectors", "category": "selectors"},
                {"pattern": "$SIBLING + $ADJACENT", "description": "Adjacent sibling selectors", "category": "selectors"},
                {"pattern": "$SELECTOR[$ATTRIBUTE]", "description": "Attribute selectors", "category": "selectors"},
                {"pattern": "var(--$NAME)", "description": "CSS custom properties", "category": "variables"}
            ],
            "json": [
                {"pattern": "{ $FIELDS }", "description": "JSON objects", "category": "objects"},
                {"pattern": "[ $ELEMENTS ]", "description": "JSON arrays", "category": "arrays"},
                {"pattern": "\"$KEY\": $VALUE", "description": "Key-value pairs", "category": "pairs"},
                {"pattern": "\"$STRING\"", "description": "String values", "category": "strings"},
                {"pattern": "$NUMBER", "description": "Numeric values", "category": "numbers"},
                {"pattern": "true", "description": "Boolean true", "category": "booleans"},
                {"pattern": "false", "description": "Boolean false", "category": "booleans"},
                {"pattern": "null", "description": "Null values", "category": "null"}
            ],
            "yaml": [
                {"pattern": "$KEY: $VALUE", "description": "Key-value pairs", "category": "pairs"},
                {"pattern": "- $ITEM", "description": "List items", "category": "lists"},
                {"pattern": "$KEY:", "description": "Object keys", "category": "keys"},
                {"pattern": "# $COMMENT", "description": "Comments", "category": "comments"},
                {"pattern": "---", "description": "Document separators", "category": "separators"},
                {"pattern": "$KEY: |", "description": "Literal scalars", "category": "scalars"},
                {"pattern": "$KEY: >", "description": "Folded scalars", "category": "scalars"},
                {"pattern": "&$ANCHOR", "description": "Anchors", "category": "anchors"},
                {"pattern": "*$REFERENCE", "description": "References", "category": "references"},
                {"pattern": "<<: *$MERGE", "description": "Merge keys", "category": "merge"}
            ],
            "xml": [
                {"pattern": "<?xml version=\"$VERSION\"?>", "description": "XML declarations", "category": "declarations"},
                {"pattern": "<$TAG $ATTRS>$CONTENT</$TAG>", "description": "XML elements", "category": "elements"},
                {"pattern": "<$TAG $ATTRS/>", "description": "Self-closing elements", "category": "elements"},
                {"pattern": "$ATTR=\"$VALUE\"", "description": "Attributes", "category": "attributes"},
                {"pattern": "<!-- $COMMENT -->", "description": "XML comments", "category": "comments"},
                {"pattern": "<![CDATA[$DATA]]>", "description": "CDATA sections", "category": "cdata"},
                {"pattern": "<!DOCTYPE $ROOT $DTD>", "description": "Document type definitions", "category": "dtd"},
                {"pattern": "&$ENTITY;", "description": "Entity references", "category": "entities"}
            ],
            "sql": [
                {"pattern": "SELECT $COLUMNS FROM $TABLE", "description": "Select statements", "category": "queries"},
                {"pattern": "INSERT INTO $TABLE ($COLUMNS) VALUES ($VALUES)", "description": "Insert statements", "category": "dml"},
                {"pattern": "UPDATE $TABLE SET $ASSIGNMENTS WHERE $CONDITION", "description": "Update statements", "category": "dml"},
                {"pattern": "DELETE FROM $TABLE WHERE $CONDITION", "description": "Delete statements", "category": "dml"},
                {"pattern": "CREATE TABLE $NAME ($COLUMNS)", "description": "Table creation", "category": "ddl"},
                {"pattern": "ALTER TABLE $NAME $CHANGES", "description": "Table alteration", "category": "ddl"},
                {"pattern": "DROP TABLE $NAME", "description": "Table deletion", "category": "ddl"},
                {"pattern": "WHERE $CONDITION", "description": "Where clauses", "category": "clauses"},
                {"pattern": "JOIN $TABLE ON $CONDITION", "description": "Join clauses", "category": "joins"},
                {"pattern": "GROUP BY $COLUMNS", "description": "Group by clauses", "category": "aggregation"},
                {"pattern": "ORDER BY $COLUMNS", "description": "Order by clauses", "category": "sorting"},
                {"pattern": "HAVING $CONDITION", "description": "Having clauses", "category": "aggregation"},
                {"pattern": "CREATE INDEX $NAME ON $TABLE ($COLUMNS)", "description": "Index creation", "category": "indexes"},
                {"pattern": "-- $COMMENT", "description": "SQL comments", "category": "comments"},
                {"pattern": "UNION $QUERY", "description": "Union operations", "category": "set-operations"}
            ]
        }
        
        # Return patterns for the specified language, or empty list if not found
        return patterns.get(normalized, [])
    
    def _detect_c_or_cpp_header(self, file_path: Path, content: Optional[str] = None) -> str:
        """Detect whether a .h file is C or C++ based on content.
        
        Args:
            file_path: Path to the header file
            content: Optional content string (if file doesn't exist)
            
        Returns:
            'c' or 'cpp' based on content analysis
        """
        try:
            if content is not None:
                # Use provided content
                content_to_analyze = content
            else:
                # Read content from file
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content_to_analyze = f.read(1024)  # Read first 1KB
            
            # C++ indicators
            cpp_indicators = [
                'extern "C"', 'namespace ', 'class ', 'template<',
                '#include <iostream>', '#include <string>', '#include <vector>',
                'std::', 'using namespace', 'public:', 'private:', 'protected:'
            ]
            
            for indicator in cpp_indicators:
                if indicator in content_to_analyze:
                    return 'cpp'
            
            # Default to C for .h files without C++ indicators
            return 'c'
            
        except Exception:
            # Default to C if content analysis fails
            return 'c'
    
    def create_language_mapping_report(self) -> Dict[str, Any]:
        """Create a comprehensive report of language mappings and validation status.
        
        Returns:
            Dictionary containing mapping report
        """
        from .resources import SUPPORTED_LANGUAGES
        
        report = {
            "total_languages": len(SUPPORTED_LANGUAGES),
            "languages": {},
            "extension_mappings": {},  # Changed from "extensions" 
            "aliases": {},
            "tree_sitter_mappings": {},
            "language_families": {},  # Added language families
            "validation_stats": {
                "total_extensions": 0,
                "total_aliases": 0,
                "languages_with_patterns": 0,
                "languages_with_descriptions": 0
            }
        }
        
        all_extensions = set()
        all_aliases = set()
        
        for lang_id, info in SUPPORTED_LANGUAGES.items():
            # Language details
            lang_report = {
                "canonical_name": lang_id,
                "description": info.get("description", ""),
                "tree_sitter": info.get("tree_sitter", lang_id),
                "extensions": info.get("extensions", []),
                "aliases": info.get("aliases", []),
                "common_patterns": info.get("common_patterns", []),
                "validation_status": "valid"
            }
            
            # Validate tree-sitter mapping
            try:
                mapped = self.map_to_ast_grep_language(lang_id)
                lang_report["ast_grep_language"] = mapped
            except Exception as e:
                lang_report["validation_status"] = f"mapping_error: {e}"
            
            report["languages"][lang_id] = lang_report
            
            # Track extensions
            for ext in info.get("extensions", []):
                if ext in all_extensions:
                    report["extension_mappings"].setdefault("conflicts", []).append({
                        "extension": ext,
                        "languages": [existing_lang for existing_lang, existing_info in SUPPORTED_LANGUAGES.items() 
                                    if ext in existing_info.get("extensions", [])]
                    })
                all_extensions.add(ext)
                report["extension_mappings"][ext] = lang_id
            
            # Track aliases
            for alias in info.get("aliases", []):
                if alias in all_aliases:
                    report["aliases"].setdefault("conflicts", []).append({
                        "alias": alias,
                        "languages": [existing_lang for existing_lang, existing_info in SUPPORTED_LANGUAGES.items()
                                    if alias in existing_info.get("aliases", [])]
                    })
                all_aliases.add(alias)
                report["aliases"][alias] = lang_id
            
            # Tree-sitter mappings
            tree_sitter = info.get("tree_sitter", lang_id)
            if tree_sitter in report["tree_sitter_mappings"]:
                report["tree_sitter_mappings"].setdefault("conflicts", []).append({
                    "tree_sitter": tree_sitter,
                    "languages": [existing_lang for existing_lang, existing_info in SUPPORTED_LANGUAGES.items()
                                if existing_info.get("tree_sitter", existing_lang) == tree_sitter]
                })
            report["tree_sitter_mappings"][tree_sitter] = lang_id
            
            # Statistics
            if info.get("common_patterns"):
                report["validation_stats"]["languages_with_patterns"] += 1
            if info.get("description"):
                report["validation_stats"]["languages_with_descriptions"] += 1
        
        report["validation_stats"]["total_extensions"] = len(all_extensions)
        report["validation_stats"]["total_aliases"] = len(all_aliases)
        
        # Add language families
        families = {
            "scripting": [],
            "systems": [],
            "c-like": [],
            "functional": [],
            "markup": [],
            "data": [],
            "mobile": [],
            "statistical": [],
            "other": []
        }
        
        for lang_id in SUPPORTED_LANGUAGES:
            family = self.get_language_family(lang_id)
            if family in families:
                families[family].append(lang_id)
            else:
                families["other"].append(lang_id)
        
        report["language_families"] = families
        
        return report
    
    def validate_language_mapping_integrity(self) -> List[Dict[str, Any]]:
        """Validate the integrity of language mappings and identify issues.
        
        Returns:
            List of validation issues found
        """
        issues = []
        from .resources import SUPPORTED_LANGUAGES
        
        # Check for duplicate extensions
        extension_map = {}
        for lang_id, info in SUPPORTED_LANGUAGES.items():
            for ext in info.get("extensions", []):
                if ext in extension_map:
                    issues.append({
                        "type": "duplicate_extension",
                        "severity": "warning",
                        "extension": ext,
                        "languages": [extension_map[ext], lang_id],
                        "message": f"Extension '{ext}' is mapped to multiple languages"
                    })
                extension_map[ext] = lang_id
        
        # Check for duplicate aliases
        alias_map = {}
        for lang_id, info in SUPPORTED_LANGUAGES.items():
            for alias in info.get("aliases", []):
                if alias in alias_map:
                    issues.append({
                        "type": "duplicate_alias",
                        "severity": "error",
                        "alias": alias,
                        "languages": [alias_map[alias], lang_id],
                        "message": f"Alias '{alias}' is mapped to multiple languages"
                    })
                alias_map[alias] = lang_id
        
        # Check for missing tree-sitter mappings
        for lang_id, info in SUPPORTED_LANGUAGES.items():
            if not info.get("tree_sitter"):
                issues.append({
                    "type": "missing_tree_sitter",
                    "severity": "warning",
                    "language": lang_id,
                    "message": f"Language '{lang_id}' missing tree-sitter mapping"
                })
        
        # Check for invalid tree-sitter mappings
        tree_sitter_map = {}
        for lang_id, info in SUPPORTED_LANGUAGES.items():
            tree_sitter = info.get("tree_sitter", lang_id)
            if tree_sitter in tree_sitter_map:
                issues.append({
                    "type": "duplicate_tree_sitter",
                    "severity": "warning",
                    "tree_sitter": tree_sitter,
                    "languages": [tree_sitter_map[tree_sitter], lang_id],
                    "message": f"Tree-sitter mapping '{tree_sitter}' used by multiple languages"
                })
            tree_sitter_map[tree_sitter] = lang_id
        
        # Check for missing descriptions
        for lang_id, info in SUPPORTED_LANGUAGES.items():
            if not info.get("description"):
                issues.append({
                    "type": "missing_description",
                    "severity": "info",
                    "language": lang_id,
                    "message": f"Language '{lang_id}' missing description"
                })
        
        # Check for missing extensions
        for lang_id, info in SUPPORTED_LANGUAGES.items():
            if not info.get("extensions"):
                issues.append({
                    "type": "missing_extensions",
                    "severity": "warning",
                    "language": lang_id,
                    "message": f"Language '{lang_id}' has no file extensions defined"
                })
        
        return issues
    
    def normalize_language_identifier(self, identifier: str) -> str:
        """Normalize a language identifier to canonical form.
        
        Args:
            identifier: Raw language identifier
            
        Returns:
            Normalized canonical language identifier
        """
        if not identifier:
            raise ValueError("Language identifier cannot be empty")
        
        # Basic normalization
        normalized = identifier.lower().strip()
        
        # Handle common variations
        replacements = {
            "js": "javascript",
            "ts": "typescript", 
            "py": "python",
            "rs": "rust",
            "rb": "ruby",
            "cs": "csharp",
            "kt": "kotlin",
            "c++": "cpp",
            "c#": "csharp",
            "golang": "go",
            "sh": "bash",
            "shell": "bash"
        }
        
        return replacements.get(normalized, normalized)
    
    def get_language_family(self, language: str) -> str:
        """Get the language family for a given language.
        
        Args:
            language: Language identifier
            
        Returns:
            Language family category
        """
        normalized = self.validate_language_identifier(language, return_normalized=True)
        
        families = {
            "scripting": ["javascript", "typescript", "python", "ruby", "php", "perl", "bash", "lua"],
            "systems": ["rust", "go"],
            "c-like": ["c", "cpp", "java", "csharp"],
            "functional": ["haskell", "ocaml", "elixir", "erlang", "scala"],
            "markup": ["html", "xml", "markdown", "css"],
            "data": ["json", "yaml", "sql"],
            "mobile": ["swift", "kotlin", "dart"],
            "statistical": ["r"]
        }
        
        for family, languages in families.items():
            if normalized in languages:
                return family
        
        return "other"
    
    def suggest_similar_languages(self, language: str, max_suggestions: int = 5) -> List[str]:
        """Suggest similar language identifiers for a given (possibly invalid) language.
        
        Args:
            language: Language identifier to find suggestions for
            max_suggestions: Maximum number of suggestions to return
            
        Returns:
            List of similar language names
        """
        from difflib import SequenceMatcher
        from .resources import SUPPORTED_LANGUAGES
        
        language = language.lower().strip()
        suggestions = []
        
        # Check against all supported languages and aliases
        all_identifiers = set(SUPPORTED_LANGUAGES.keys())
        for info in SUPPORTED_LANGUAGES.values():
            all_identifiers.update(info.get("aliases", []))
        
        for identifier in all_identifiers:
            similarity = SequenceMatcher(None, language, identifier).ratio()
            if similarity > 0.4:  # Only suggest reasonably similar names
                suggestions.append((identifier, similarity))
        
        # Sort by similarity and return top suggestions (just the names)
        suggestions.sort(key=lambda x: x[1], reverse=True)
        return [name for name, _ in suggestions[:max_suggestions]]


# Global language manager instance
_language_manager = None

def get_language_manager() -> LanguageManager:
    """Get the global language manager instance."""
    global _language_manager
    if _language_manager is None:
        _language_manager = LanguageManager()
    return _language_manager


# Backward compatibility functions for existing API
def validate_language(language: str) -> str:
    """Validate and normalize language identifier (backward compatibility).
    
    Args:
        language: Language identifier to validate
        
    Returns:
        Normalized language identifier
        
    Raises:
        ValueError: If language is not supported
    """
    return get_language_manager().validate_language_identifier(language)


def detect_language_from_file(file_path: Path) -> Optional[str]:
    """Detect programming language from file extension (backward compatibility).
    
    Args:
        file_path: Path to the file
        
    Returns:
        Detected language identifier or None if not detected
    """
    return get_language_manager().detect_language(file_path)


async def run_ast_grep_command(
    args: List[str],
    binary_path: Path,
    timeout: Optional[int] = None,
    cwd: Optional[Path] = None
) -> Dict[str, Any]:
    """Run an ast-grep command with proper error handling.
    
    Args:
        args: Command arguments (without the binary name)
        binary_path: Path to ast-grep binary
        timeout: Command timeout in seconds
        cwd: Working directory for the command
        
    Returns:
        Dictionary with command results
        
    Raises:
        ASTGrepError: If command execution fails
    """
    if timeout is None:
        timeout = get_timeout()
    
    command = [str(binary_path)] + args
    logger = logging.getLogger(__name__)
    
    logger.debug(f"Running command: {' '.join(command)}")
    
    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd
        )
        
        stdout, stderr = await asyncio.wait_for(
            process.communicate(), timeout=timeout
        )
        
        result = {
            "returncode": process.returncode,
            "stdout": stdout.decode(),
            "stderr": stderr.decode(),
            "command": command
        }
        
        if process.returncode != 0:
            raise ASTGrepError(
                f"Command failed with return code {process.returncode}: {stderr.decode()}"
            )
        
        return result
        
    except asyncio.TimeoutError:
        raise ASTGrepError(f"Command timed out after {timeout} seconds")
    except Exception as e:
        raise ASTGrepError(f"Command execution failed: {e}")


def parse_ast_grep_json_output(output: str) -> List[Dict[str, Any]]:
    """Parse JSON output from ast-grep commands.
    
    Args:
        output: Raw JSON output from ast-grep
        
    Returns:
        Parsed list of match objects
        
    Raises:
        ValueError: If JSON parsing fails
    """
    if not output.strip():
        return []
    
    try:
        # ast-grep outputs one JSON object per line
        results = []
        for line in output.strip().split('\n'):
            if line.strip():
                results.append(json.loads(line))
        return results
        
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse ast-grep JSON output: {e}")


@dataclass 
class ResourceConfig:
    """Configuration for resource limits and sandboxing."""
    max_files: int = 1000
    max_memory_mb: int = 512  # Maximum memory in MB
    max_cpu_time: int = 30   # Maximum CPU time in seconds
    max_wall_time: int = 60  # Maximum wall clock time in seconds
    max_open_files: int = 100
    max_processes: int = 5
    enable_sandboxing: bool = True
    temp_dir_size_mb: int = 100
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary."""
        return {
            'max_files': self.max_files,
            'max_memory_mb': self.max_memory_mb,
            'max_cpu_time': self.max_cpu_time,
            'max_wall_time': self.max_wall_time,
            'max_open_files': self.max_open_files,
            'max_processes': self.max_processes,
            'enable_sandboxing': self.enable_sandboxing,
            'temp_dir_size_mb': self.temp_dir_size_mb
        }

class ResourceManager:
    """Enhanced resource management with sandboxing and comprehensive limits."""
    
    def __init__(self, config: Optional[ResourceConfig] = None):
        """Initialize resource manager.
        
        Args:
            config: Resource configuration limits
        """
        self.config = config or ResourceConfig()
        self.file_count = 0
        self.start_time = None
        self.temp_dir = None
        self.process_group = None
        self.logger = logging.getLogger(__name__)
        
        # Platform-specific capabilities
        self.is_unix = platform.system() in ('Linux', 'Darwin', 'FreeBSD')
        self.has_resource_module = hasattr(resource, 'RLIMIT_AS')
        self.has_psutil = self._check_psutil()
        
    def _check_psutil(self) -> bool:
        """Check if psutil is available for process monitoring."""
        if HAS_PSUTIL:
            return True
        else:
            self.logger.warning("psutil not available - limited resource monitoring")
            return False
    
    async def __aenter__(self):
        """Enter resource management context."""
        self.start_time = time.time()
        await self._setup_resource_limits()
        await self._setup_sandboxing()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit resource management context."""
        await self._cleanup_resources()
    
    async def _setup_resource_limits(self) -> None:
        """Set up system resource limits."""
        if not self.is_unix or not self.has_resource_module:
            self.logger.info("Resource limits not available on this platform")
            return
        
        try:
            # Set memory limit (virtual memory)
            memory_bytes = self.config.max_memory_mb * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
            
            # Set CPU time limit
            resource.setrlimit(resource.RLIMIT_CPU, (self.config.max_cpu_time, self.config.max_cpu_time))
            
            # Set file descriptor limit
            resource.setrlimit(resource.RLIMIT_NOFILE, (self.config.max_open_files, self.config.max_open_files))
            
            # Set process limit (if available)
            if hasattr(resource, 'RLIMIT_NPROC'):
                resource.setrlimit(resource.RLIMIT_NPROC, (self.config.max_processes, self.config.max_processes))
            
            self.logger.debug(f"Resource limits set: {self.config.to_dict()}")
            
        except Exception as e:
            self.logger.warning(f"Failed to set resource limits: {e}")
    
    async def _setup_sandboxing(self) -> None:
        """Set up sandboxing environment."""
        if not self.config.enable_sandboxing:
            return
        
        try:
            # Create secure temporary directory
            self.temp_dir = Path(tempfile.mkdtemp(prefix='ast_grep_sandbox_'))
            self.temp_dir.chmod(0o700)  # Restrict to owner only
            
            # Set up process group for better process management
            if self.is_unix:
                self.process_group = os.getpid()
            
            self.logger.debug(f"Sandbox environment set up: {self.temp_dir}")
            
        except Exception as e:
            self.logger.warning(f"Failed to set up sandboxing: {e}")
    
    async def _cleanup_resources(self) -> None:
        """Clean up resources and temporary files."""
        try:
            # Kill any remaining processes in our group
            if self.process_group and self.is_unix:
                try:
                    os.killpg(self.process_group, signal.SIGTERM)
                    await asyncio.sleep(0.1)
                    os.killpg(self.process_group, signal.SIGKILL)
                except ProcessLookupError:
                    pass  # Process group already terminated
            
            # Clean up temporary directory
            if self.temp_dir and self.temp_dir.exists():
                shutil.rmtree(self.temp_dir, ignore_errors=True)
                self.logger.debug(f"Cleaned up sandbox: {self.temp_dir}")
                
        except Exception as e:
            self.logger.warning(f"Error during resource cleanup: {e}")
    
    def check_file_limit(self, file_path: Path) -> bool:
        """Check if we've exceeded the file limit.
        
        Args:
            file_path: Path to check
            
        Returns:
            True if within limit, False otherwise
            
        Raises:
            ResourceLimitError: If file limit exceeded
        """
        self.file_count += 1
        if self.file_count > self.config.max_files:
            raise ResourceLimitError(
                f"File limit exceeded: {self.file_count} > {self.config.max_files}"
            )
        return True
    
    def check_time_limit(self) -> bool:
        """Check if wall clock time limit has been exceeded.
        
        Returns:
            True if within limit, False otherwise
            
        Raises:
            ResourceLimitError: If time limit exceeded
        """
        if not self.start_time:
            return True
            
        elapsed = time.time() - self.start_time
        if elapsed > self.config.max_wall_time:
            raise ResourceLimitError(
                f"Wall time limit exceeded: {elapsed:.2f}s > {self.config.max_wall_time}s"
            )
        return True
    
    async def monitor_process(self, process: asyncio.subprocess.Process) -> None:
        """Monitor a running process for resource violations.
        
        Args:
            process: Process to monitor
            
        Raises:
            ResourceLimitError: If process exceeds limits
        """
        if not self.has_psutil or not process.pid:
            return
        
        try:
            psutil_process = psutil.Process(process.pid)
            
            # Monitor memory usage
            memory_info = psutil_process.memory_info()
            memory_mb = memory_info.rss / (1024 * 1024)
            
            if memory_mb > self.config.max_memory_mb:
                process.kill()
                raise ResourceLimitError(
                    f"Memory limit exceeded: {memory_mb:.2f}MB > {self.config.max_memory_mb}MB"
                )
            
            # Monitor CPU usage would require time-based sampling
            # For now, rely on RLIMIT_CPU for CPU time limiting
            
        except psutil.NoSuchProcess:
            # Process already terminated
            pass
        except Exception as e:
            self.logger.warning(f"Error monitoring process: {e}")
    
    def get_sandboxed_env(self) -> Dict[str, str]:
        """Get environment variables for sandboxed execution.
        
        Returns:
            Sanitized environment dictionary
        """
        # Start with minimal environment
        safe_env = {
            'PATH': os.environ.get('PATH', ''),
            'HOME': str(self.temp_dir) if self.temp_dir else os.environ.get('HOME', ''),
            'TERM': 'xterm',
            'LANG': 'C.UTF-8',
            'LC_ALL': 'C.UTF-8'
        }
        
        # Add temp directory if available
        if self.temp_dir:
            safe_env['TMPDIR'] = str(self.temp_dir)
            safe_env['TEMP'] = str(self.temp_dir)
            safe_env['TMP'] = str(self.temp_dir)
        
        return safe_env
    
    def get_subprocess_kwargs(self) -> Dict[str, Any]:
        """Get subprocess creation arguments for sandboxing.
        
        Returns:
            Dictionary of subprocess.Popen arguments
        """
        kwargs = {
            'env': self.get_sandboxed_env(),
            'cwd': self.temp_dir if self.temp_dir else None,
        }
        
        # Unix-specific sandboxing
        if self.is_unix and self.config.enable_sandboxing:
            # Start new process group for better isolation
            kwargs['start_new_session'] = True
            
            # Preexec function to further restrict the process
            def preexec_fn():
                try:
                    # Set process group
                    os.setpgrp()
                    
                    # Additional resource limits in child process
                    if self.has_resource_module:
                        # Disable core dumps
                        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
                        
                        # Limit file size
                        max_file_size = 100 * 1024 * 1024  # 100MB
                        resource.setrlimit(resource.RLIMIT_FSIZE, (max_file_size, max_file_size))
                        
                except Exception as e:
                    # Don't fail the process creation if preexec fails
                    logger.debug(f"Failed to set resource limits in preexec: {e}")  # nosec B110 - intentional non-blocking
            
            kwargs['preexec_fn'] = preexec_fn
        
        return kwargs
    
    def get_resource_usage(self) -> Dict[str, Any]:
        """Get current resource usage statistics.
        
        Returns:
            Dictionary with resource usage information
        """
        usage = {
            'files_processed': self.file_count,
            'max_files': self.config.max_files,
            'elapsed_time': time.time() - self.start_time if self.start_time else 0,
            'max_wall_time': self.config.max_wall_time
        }
        
        if self.has_resource_module and self.is_unix:
            try:
                rusage = resource.getrusage(resource.RUSAGE_SELF)
                usage.update({
                    'user_time': rusage.ru_utime,
                    'system_time': rusage.ru_stime,
                    'max_memory_kb': rusage.ru_maxrss,
                    'page_faults': rusage.ru_majflt,
                    'voluntary_context_switches': rusage.ru_nvcsw,
                    'involuntary_context_switches': rusage.ru_nivcsw
                })
            except Exception as e:
                logger.debug(f"Failed to get detailed resource usage: {e}")  # nosec B110 - intentional non-blocking
        
        return usage

# Update the original ResourceLimiter for backward compatibility
class ResourceLimiter:
    """Legacy ResourceLimiter for backward compatibility."""
    
    def __init__(self, max_files: Optional[int] = None):
        config = ResourceConfig(max_files=max_files or get_max_files())
        self.manager = ResourceManager(config)
    
    def check_file_limit(self, file_path: Path) -> bool:
        return self.manager.check_file_limit(file_path)
    
    async def __aenter__(self):
        return await self.manager.__aenter__()
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return await self.manager.__aexit__(exc_type, exc_val, exc_tb)


class ASTGrepExecutor:
    """Core AST-Grep command execution engine with comprehensive safety and resource management."""
    
    def __init__(
        self,
        binary_path: Optional[Path] = None,
        timeout: Optional[int] = None,
        max_files: Optional[int] = None,
        working_directory: Optional[Path] = None
    ):
        """Initialize the AST-Grep executor.
        
        Args:
            binary_path: Path to ast-grep binary (auto-detected if None)
            timeout: Command timeout in seconds (uses AST_GREP_TIMEOUT env if None)
            max_files: Maximum files to process (uses AST_GREP_MAX_FILES env if None)
            working_directory: Working directory for commands
        """
        self.binary_path = binary_path
        self.timeout = timeout or get_timeout()
        self.max_files = max_files or get_max_files()
        self.working_directory = working_directory
        self.logger = logging.getLogger(__name__)
        
    async def initialize(self) -> None:
        """Initialize the executor by validating ast-grep binary."""
        if not self.binary_path:
            self.binary_path = await validate_ast_grep_installation()
        else:
            # Validate provided binary path
            if not self.binary_path.exists():
                raise ASTGrepNotFoundError(f"Binary not found at: {self.binary_path}")
            
            # Validate version and capabilities
            await validate_ast_grep_version(self.binary_path)
        
        self.logger.info(f"AST-Grep executor initialized with binary: {self.binary_path}")
    
    def _sanitize_command_args(self, args: List[str]) -> List[str]:
        """Sanitize command arguments to prevent injection attacks using security layer.
        
        Args:
            args: Raw command arguments
            
        Returns:
            Sanitized command arguments
            
        Raises:
            CommandInjectionError: If dangerous patterns are detected
            ValueError: For backwards compatibility
        """
        try:
            # Use the comprehensive security layer for command sanitization
            sanitized_command, sanitized_args = secure_sanitize_command('ast-grep', args)
            return sanitized_args
        except CommandInjectionError as e:
            # Convert to ValueError for backwards compatibility
            raise ValueError(f"Command injection detected: {e}")
        except SecurityError as e:
            # Handle other security errors
            raise ValueError(f"Security validation failed: {e}")
        except Exception:
            # Fallback to basic sanitization if security layer is unavailable
            self.logger.warning("Security layer unavailable, using basic sanitization")
            return self._basic_sanitize_command_args(args)
    
    def _basic_sanitize_command_args(self, args: List[str]) -> List[str]:
        """Basic command argument sanitization fallback.
        
        Args:
            args: Raw command arguments
            
        Returns:
            Sanitized command arguments
            
        Raises:
            ValueError: If dangerous patterns are detected
        """
        sanitized_args = []
        dangerous_patterns = [
            ';', '&', '|', '`', '$', '>', '<', '(', ')', '{', '}',
            '&&', '||', '>>', '<<', '$(', '`', '\n', '\r'
        ]
        
        for arg in args:
            # Check for dangerous shell patterns
            if any(pattern in arg for pattern in dangerous_patterns):
                raise ValueError(f"Potentially dangerous command argument detected: {arg}")
            
            # Ensure arguments don't start with dangerous prefixes
            if arg.startswith(('-', '/')):
                # Only allow known safe flags
                safe_flags = {
                    '--json', '--color', '--no-color', '--help', '--version',
                    '-p', '--pattern', '-r', '--rewrite', '-l', '--lang',
                    '-f', '--file', '-d', '--debug', '-q', '--quiet',
                    '--stdin', '--no-ignore', '--hidden'
                }
                
                # Extract flag name (before = if present)
                flag_name = arg.split('=')[0]
                if flag_name not in safe_flags:
                    self.logger.warning(f"Unknown flag detected: {flag_name}")
            
            sanitized_args.append(arg)
        
        return sanitized_args
    
    def _build_command(self, subcommand: str, args: List[str]) -> List[str]:
        """Build a complete ast-grep command with sanitization.
        
        Args:
            subcommand: AST-Grep subcommand (search, scan, run, etc.)
            args: Additional command arguments
            
        Returns:
            Complete sanitized command list
            
        Raises:
            ValueError: If subcommand or args are invalid
        """
        # Validate subcommand
        valid_subcommands = {'search', 'scan', 'run', 'new', 'test', 'lsp', 'completions'}
        if subcommand not in valid_subcommands:
            raise ValueError(f"Invalid subcommand: {subcommand}. Valid: {valid_subcommands}")
        
        # Sanitize arguments
        sanitized_args = self._sanitize_command_args(args)
        
        # Build complete command
        command = [str(self.binary_path), subcommand] + sanitized_args
        
        # Ensure JSON output for parseable commands
        if subcommand in {'search', 'scan'} and '--json' not in sanitized_args:
            command.append('--json')
        
        return command
    
    async def _monitor_process_with_limits(
        self, 
        process: asyncio.subprocess.Process, 
        resource_manager: ResourceManager
    ) -> None:
        """Monitor process for resource limit violations.
        
        Args:
            process: Process to monitor
            resource_manager: Resource manager instance
            
        Raises:
            ResourceLimitError: If limits are exceeded
        """
        try:
            while process.returncode is None:
                # Check time limits
                resource_manager.check_time_limit()
                
                # Monitor process resources
                await resource_manager.monitor_process(process)
                
                # Check periodically
                await asyncio.sleep(0.5)
                
        except ResourceLimitError:
            # Re-raise to be caught by caller
            raise
        except Exception as e:
            # Log monitoring errors but don't fail execution
            self.logger.warning(f"Process monitoring error: {e}")
    
    async def _execute_command(
        self,
        command: List[str],
        input_data: Optional[str] = None
    ) -> Dict[str, Any]:
        """Execute a command with proper resource management and error handling.
        
        Args:
            command: Complete command to execute
            input_data: Optional stdin data
            
        Returns:
            Execution result dictionary
            
        Raises:
            ASTGrepError: If execution fails
        """
        self.logger.debug(f"Executing command: {' '.join(command)}")
        
        try:
            # Execute with enhanced resource management and monitoring
            resource_config = ResourceConfig(
                max_files=self.max_files,
                max_wall_time=self.timeout,
                max_memory_mb=512,  # 512MB limit
                max_cpu_time=min(self.timeout, 30),  # CPU time limit
                enable_sandboxing=True
            )
            
            async with ResourceManager(resource_config) as resource_manager:
                # Update subprocess arguments with sandboxing
                sandbox_kwargs = resource_manager.get_subprocess_kwargs()
                
                # Create new subprocess with enhanced sandboxing
                process = await asyncio.create_subprocess_exec(
                    *command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    stdin=asyncio.subprocess.PIPE if input_data else None,
                    cwd=sandbox_kwargs.get('cwd', self.working_directory),
                    env=sandbox_kwargs.get('env'),
                    **{k: v for k, v in sandbox_kwargs.items() if k not in ['env', 'cwd']}
                )
                
                try:
                    # Start monitoring task
                    monitor_task = asyncio.create_task(
                        self._monitor_process_with_limits(process, resource_manager)
                    )
                    
                    # Execute with timeout
                    try:
                        stdout, stderr = await asyncio.wait_for(
                            process.communicate(input_data.encode() if input_data else None),
                            timeout=self.timeout
                        )
                    finally:
                        # Cancel monitoring
                        monitor_task.cancel()
                        try:
                            await monitor_task
                        except asyncio.CancelledError:
                            pass
                    
                except asyncio.TimeoutError:
                    # Kill the process if it times out
                    try:
                        process.kill()
                        await process.wait()
                    except ProcessLookupError:
                        pass  # Process already terminated
                    
                    raise ASTGrepError(
                        f"Command execution timed out after {self.timeout} seconds"
                    )
                except ResourceLimitError as e:
                    # Kill the process if resource limits exceeded
                    try:
                        process.kill()
                        await process.wait()
                    except ProcessLookupError:
                        pass
                    
                    raise ASTGrepError(f"Resource limit exceeded: {e}")
                
                # Check final resource usage
                resource_usage = resource_manager.get_resource_usage()
                self.logger.debug(f"Resource usage: {resource_usage}")
            
            # Decode output
            stdout_str = stdout.decode('utf-8', errors='replace')
            stderr_str = stderr.decode('utf-8', errors='replace')
            
            # Create structured result
            result = {
                'success': process.returncode == 0,
                'returncode': process.returncode,
                'stdout': stdout_str,
                'stderr': stderr_str,
                'command': command,
                'timeout': self.timeout,
                'execution_time': None  # Could add timing if needed
            }
            
            # Log execution details
            if process.returncode == 0:
                self.logger.debug(f"Command executed successfully: {result['command']}")
            else:
                self.logger.warning(
                    f"Command failed with code {process.returncode}: {stderr_str}"
                )
            
            return result
            
        except Exception as e:
            if isinstance(e, ASTGrepError):
                raise
            
            error_msg = f"Command execution failed: {str(e)}"
            self.logger.error(error_msg)
            raise ASTGrepError(error_msg) from e
    
    async def search(
        self,
        pattern: str,
        language: Optional[str] = None,
        paths: Optional[List[str]] = None,
        additional_args: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Execute ast-grep search command.
        
        Args:
            pattern: Search pattern
            language: Programming language filter
            paths: Paths to search in
            additional_args: Additional command arguments
            
        Returns:
            Search results with parsed JSON output
        """
        if not self.binary_path:
            await self.initialize()
        
        args = ['-p', pattern]
        
        if language:
            validated_lang = get_language_manager().validate_language_identifier(language)
            args.extend(['-l', validated_lang])
        
        if paths:
            for path in paths:
                sanitized_path = sanitize_path(path, str(self.working_directory) if self.working_directory else None)
                args.append(str(sanitized_path))
        
        if additional_args:
            args.extend(additional_args)
        
        command = self._build_command('search', args)
        result = await self._execute_command(command)
        
        # Parse JSON output if successful
        if result['success'] and result['stdout']:
            try:
                result['parsed_output'] = parse_ast_grep_json_output(result['stdout'])
                result['match_count'] = len(result['parsed_output'])
            except ValueError as e:
                self.logger.warning(f"Failed to parse JSON output: {e}")
                result['parse_error'] = str(e)
        
        return result
    
    async def scan(
        self,
        rule_file: str,
        paths: Optional[List[str]] = None,
        additional_args: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Execute ast-grep scan command.
        
        Args:
            rule_file: Path to rule file
            paths: Paths to scan
            additional_args: Additional command arguments
            
        Returns:
            Scan results with parsed JSON output
        """
        if not self.binary_path:
            await self.initialize()
        
        # Validate rule file path
        rule_path = sanitize_path(rule_file, str(self.working_directory) if self.working_directory else None)
        if not rule_path.exists():
            raise ValueError(f"Rule file not found: {rule_file}")
        
        args = ['-r', str(rule_path)]
        
        if paths:
            for path in paths:
                sanitized_path = sanitize_path(path, str(self.working_directory) if self.working_directory else None)
                args.append(str(sanitized_path))
        
        if additional_args:
            args.extend(additional_args)
        
        command = self._build_command('scan', args)
        result = await self._execute_command(command)
        
        # Parse JSON output if successful
        if result['success'] and result['stdout']:
            try:
                result['parsed_output'] = parse_ast_grep_json_output(result['stdout'])
                result['match_count'] = len(result['parsed_output'])
            except ValueError as e:
                self.logger.warning(f"Failed to parse JSON output: {e}")
                result['parse_error'] = str(e)
        
        return result
    
    async def run(
        self,
        pattern: str,
        rewrite: str,
        language: Optional[str] = None,
        paths: Optional[List[str]] = None,
        dry_run: bool = True,
        additional_args: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Execute ast-grep run command for code transformation.
        
        Args:
            pattern: Search pattern
            rewrite: Rewrite template
            language: Programming language filter
            paths: Paths to transform
            dry_run: Whether to perform dry run (recommended for safety)
            additional_args: Additional command arguments
            
        Returns:
            Transformation results
        """
        if not self.binary_path:
            await self.initialize()
        
        args = ['-p', pattern, '-r', rewrite]
        
        if language:
            validated_lang = get_language_manager().validate_language_identifier(language)
            args.extend(['-l', validated_lang])
        
        # Default to dry run for safety unless explicitly disabled
        if dry_run:
            args.append('--dry-run')
        
        if paths:
            for path in paths:
                sanitized_path = sanitize_path(path, str(self.working_directory) if self.working_directory else None)
                args.append(str(sanitized_path))
        
        if additional_args:
            args.extend(additional_args)
        
        command = self._build_command('run', args)
        result = await self._execute_command(command)
        
        # Add safety warning for non-dry-run operations
        if not dry_run and result['success']:
            result['warning'] = 'Files were modified. Please review changes carefully.'
            self.logger.warning("ast-grep run executed without dry-run - files may have been modified")
        
        return result
    
    async def execute_custom(
        self,
        subcommand: str,
        args: List[str],
        input_data: Optional[str] = None
    ) -> Dict[str, Any]:
        """Execute a custom ast-grep command.
        
        Args:
            subcommand: AST-Grep subcommand
            args: Command arguments
            input_data: Optional stdin data
            
        Returns:
            Execution results
        """
        if not self.binary_path:
            await self.initialize()
        
        command = self._build_command(subcommand, args)
        return await self._execute_command(command, input_data)


# Factory function for creating pre-configured executors
async def create_ast_grep_executor(
    auto_initialize: bool = True,
    **kwargs
) -> ASTGrepExecutor:
    """Create and optionally initialize an AST-Grep executor.
    
    Args:
        auto_initialize: Whether to automatically initialize the executor
        **kwargs: Arguments passed to ASTGrepExecutor constructor
        
    Returns:
        Configured AST-Grep executor
    """
    executor = ASTGrepExecutor(**kwargs)
    
    if auto_initialize:
        await executor.initialize()
    
    return executor 


# Error handling and response utilities

def create_error_response(
    error_type: str,
    message: str,
    details: Optional[Dict[str, Any]] = None,
    path: Optional[str] = None,
    suggestions: Optional[List[str]] = None
) -> Dict[str, Any]:
    """Create a standardized error response dictionary.
    
    Args:
        error_type: Type of error (e.g., "ValidationError", "ConfigurationError")
        message: Human-readable error message
        details: Optional additional error details
        path: Optional file or directory path related to the error
        suggestions: Optional list of suggestions to fix the error
        
    Returns:
        Standardized error response dictionary
    """
    error_response = {
        "error": error_type,
        "message": message,
        "status": "error",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    if path:
        error_response["path"] = path
    
    if details:
        error_response["details"] = details
        
    if suggestions:
        error_response["suggestions"] = suggestions
    
    return error_response


def create_success_response(
    data: Any,
    message: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Create a standardized success response dictionary.
    
    Args:
        data: Response data
        message: Optional success message
        metadata: Optional metadata about the operation
        
    Returns:
        Standardized success response dictionary
    """
    response = {
        "status": "success",
        "data": data,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    if message:
        response["message"] = message
        
    if metadata:
        response["metadata"] = metadata
    
    return response


def handle_validation_error(
    error: Exception,
    context: str,
    path: Optional[str] = None
) -> Dict[str, Any]:
    """Handle validation errors with consistent formatting.
    
    Args:
        error: The validation error exception
        context: Context where the error occurred
        path: Optional path related to the error
        
    Returns:
        Formatted error response
    """
    suggestions = []
    
    if isinstance(error, ASTGrepValidationError):
        error_type = "AST-Grep Validation Error"
        # Extract suggestions from error message if available
        if "Similar languages:" in str(error):
            suggestions.append("Check the list of supported languages")
            suggestions.append("Verify the language identifier is correct")
    elif isinstance(error, ValueError):
        error_type = "Validation Error"
        if "pattern" in str(error).lower():
            suggestions.append("Check pattern syntax for AST-grep compatibility")
            suggestions.append("Ensure no shell injection characters are present")
        elif "language" in str(error).lower():
            suggestions.append("Use a supported language identifier")
            suggestions.append("Check language name spelling")
    else:
        error_type = "Validation Error"
    
    return create_error_response(
        error_type=error_type,
        message=f"{context}: {str(error)}",
        path=path,
        suggestions=suggestions if suggestions else None
    )


def handle_configuration_error(
    error: Exception,
    config_path: Optional[str] = None
) -> Dict[str, Any]:
    """Handle configuration-related errors.
    
    Args:
        error: The configuration error exception
        config_path: Optional path to the configuration file
        
    Returns:
        Formatted error response
    """
    suggestions = [
        "Verify the configuration file exists and is readable",
        "Check the YAML syntax is valid",
        "Ensure all required fields are present",
        "Review the sgconfig.yml documentation"
    ]
    
    if "ruleDirs" in str(error):
        suggestions.extend([
            "Ensure 'ruleDirs' field is present in configuration",
            "Verify rule directories exist and contain valid rule files"
        ])
    
    return create_error_response(
        error_type="Configuration Error",
        message=str(error),
        path=config_path,
        suggestions=suggestions
    )


def handle_execution_error(
    error: Exception,
    command: Optional[List[str]] = None,
    path: Optional[str] = None
) -> Dict[str, Any]:
    """Handle execution-related errors.
    
    Args:
        error: The execution error exception
        command: Optional command that failed
        path: Optional path being processed
        
    Returns:
        Formatted error response
    """
    suggestions = []
    
    if isinstance(error, ASTGrepNotFoundError):
        suggestions.extend([
            "Install ast-grep: npm install -g @ast-grep/cli",
            "Ensure ast-grep is in your PATH",
            "Check ast-grep installation with: sg --version"
        ])
    elif "timeout" in str(error).lower():
        suggestions.extend([
            "Reduce the scope of files being processed",
            "Increase timeout value if needed",
            "Check for infinite loops in patterns"
        ])
    elif "permission" in str(error).lower():
        suggestions.extend([
            "Check file and directory permissions",
            "Ensure read access to target files",
            "Run with appropriate user permissions"
        ])
    
    details = {}
    if command:
        details["command"] = " ".join(command)
    
    return create_error_response(
        error_type="Execution Error",
        message=str(error),
        details=details if details else None,
        path=path,
        suggestions=suggestions if suggestions else None
    )


def format_tool_response(
    data: Any,
    output_format: str = "json",
    success: bool = True,
    message: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    error_info: Optional[Dict[str, Any]] = None
) -> List[Any]:  # Import TextContent if needed
    """Format tool response consistently across all AST-Grep tools.
    
    Args:
        data: Response data (results, error info, etc.)
        output_format: Output format ("json" or "text")
        success: Whether the operation was successful
        message: Optional message
        metadata: Optional metadata about the operation
        error_info: Optional error information for failed operations
        
    Returns:
        List containing formatted TextContent response
    """
    from mcp.types import TextContent
    
    if success:
        response = create_success_response(data, message, metadata)
    else:
        response = error_info or create_error_response(
            error_type="Operation Failed",
            message=message or "Operation completed with errors"
        )
    
    if output_format == "json":
        return [TextContent(type="text", text=json.dumps(response, indent=2, default=str))]
    else:
        # Format as human-readable text
        if success:
            if isinstance(data, str):
                return [TextContent(type="text", text=data)]
            elif isinstance(data, dict) and "formatted_text" in data:
                return [TextContent(type="text", text=data["formatted_text"])]
            else:
                # Fallback to JSON for complex data
                return [TextContent(type="text", text=json.dumps(response, indent=2, default=str))]
        else:
            error_message = response.get("message", "An error occurred")
            suggestions = response.get("suggestions", [])
            
            text_parts = [f"Error: {error_message}"]
            if suggestions:
                text_parts.append("\nSuggestions:")
                for suggestion in suggestions:
                    text_parts.append(f"  • {suggestion}")
            
            return [TextContent(type="text", text="\n".join(text_parts))]


# Meta-variable utilities for AST-Grep patterns and rewrites

def extract_meta_variables(pattern: str) -> List[str]:
    """Extract meta-variables from an AST-Grep pattern.
    
    Args:
        pattern: AST-Grep pattern string
        
    Returns:
        List of meta-variable names (including the $ prefix)
    """
    import re
    if not pattern:
        return []
    
    # Match meta-variables: $VARIABLE_NAME format
    meta_var_pattern = r'\$[A-Za-z_][A-Za-z0-9_]*'
    return re.findall(meta_var_pattern, pattern)


def validate_meta_variable_name(meta_var: str) -> bool:
    """Validate if a meta-variable follows naming conventions.
    
    Args:
        meta_var: Meta-variable name (with $ prefix)
        
    Returns:
        True if valid, False otherwise
    """
    import re
    # Recommended format: $UPPERCASE_WITH_UNDERSCORES
    recommended_pattern = r'^\$[A-Z_][A-Z0-9_]*$'
    return bool(re.match(recommended_pattern, meta_var))


def analyze_meta_variable_consistency(pattern: str, rewrite: str) -> Dict[str, Any]:
    """Analyze meta-variable consistency between pattern and rewrite.
    
    Args:
        pattern: Search pattern containing meta-variables
        rewrite: Rewrite pattern using meta-variables
        
    Returns:
        Analysis result with consistency information
    """
    pattern_vars = set(extract_meta_variables(pattern))
    rewrite_vars = set(extract_meta_variables(rewrite))
    
    return {
        "pattern_variables": sorted(list(pattern_vars)),
        "rewrite_variables": sorted(list(rewrite_vars)),
        "consistent": pattern_vars == rewrite_vars,
        "missing_in_rewrite": sorted(list(pattern_vars - rewrite_vars)),
        "extra_in_rewrite": sorted(list(rewrite_vars - pattern_vars)),
        "naming_warnings": [
            var for var in pattern_vars | rewrite_vars 
            if not validate_meta_variable_name(var)
        ]
    }


def create_meta_variable_usage_report(pattern: str, rewrite: Optional[str] = None) -> Dict[str, Any]:
    """Create a comprehensive meta-variable usage report.
    
    Args:
        pattern: Search pattern
        rewrite: Optional rewrite pattern
        
    Returns:
        Detailed meta-variable usage report
    """
    pattern_vars = extract_meta_variables(pattern)
    
    report = {
        "total_variables": len(pattern_vars),
        "unique_variables": len(set(pattern_vars)),
        "variables": pattern_vars,
        "naming_compliance": {
            "compliant": [var for var in pattern_vars if validate_meta_variable_name(var)],
            "non_compliant": [var for var in pattern_vars if not validate_meta_variable_name(var)]
        }
    }
    
    if rewrite is not None:
        consistency = analyze_meta_variable_consistency(pattern, rewrite)
        report["rewrite_consistency"] = consistency
    
    return report


def suggest_meta_variable_fixes(pattern: str, rewrite: Optional[str] = None) -> List[str]:
    """Suggest fixes for meta-variable issues.
    
    Args:
        pattern: Search pattern
        rewrite: Optional rewrite pattern
        
    Returns:
        List of suggested fixes
    """
    suggestions = []
    
    pattern_vars = extract_meta_variables(pattern)
    
    # Check naming conventions
    non_compliant = [var for var in pattern_vars if not validate_meta_variable_name(var)]
    if non_compliant:
        suggestions.append(
            f"Consider using UPPERCASE naming for meta-variables: {', '.join(non_compliant)}"
        )
    
    if rewrite is not None:
        consistency = analyze_meta_variable_consistency(pattern, rewrite)
        
        if consistency["missing_in_rewrite"]:
            suggestions.append(
                f"Meta-variables missing in rewrite pattern: {', '.join(consistency['missing_in_rewrite'])}"
            )
        
        if consistency["extra_in_rewrite"]:
            suggestions.append(
                f"Extra meta-variables in rewrite pattern: {', '.join(consistency['extra_in_rewrite'])}"
            )
        
        if not consistency["consistent"]:
            suggestions.append(
                "Ensure all meta-variables from the search pattern are used in the rewrite pattern"
            )
    
    if not pattern_vars:
        suggestions.append(
            "Pattern contains no meta-variables. Consider using meta-variables like $VAR to capture code parts."
        )
    
    return suggestions


def validate_meta_variable_usage(pattern: str, rewrite: Optional[str] = None) -> Dict[str, Any]:
    """Comprehensive validation of meta-variable usage.
    
    Args:
        pattern: Search pattern
        rewrite: Optional rewrite pattern
        
    Returns:
        Validation result with errors and warnings
    """
    errors = []
    warnings = []
    
    pattern_vars = extract_meta_variables(pattern)
    
    # Basic validation
    if not pattern_vars and rewrite:
        warnings.append("Pattern has no meta-variables but rewrite pattern is provided")
    
    # Naming validation
    for var in pattern_vars:
        if not validate_meta_variable_name(var):
            warnings.append(f"Meta-variable '{var}' doesn't follow UPPERCASE convention")
    
    # Consistency validation
    if rewrite is not None:
        consistency = analyze_meta_variable_consistency(pattern, rewrite)
        
        if not consistency["consistent"]:
            if consistency["missing_in_rewrite"]:
                errors.append(
                    f"Meta-variables from pattern missing in rewrite: {', '.join(consistency['missing_in_rewrite'])}"
                )
            
            if consistency["extra_in_rewrite"]:
                warnings.append(
                    f"Extra meta-variables in rewrite not defined in pattern: {', '.join(consistency['extra_in_rewrite'])}"
                )
    
    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "suggestions": suggest_meta_variable_fixes(pattern, rewrite)
    }


def validate_rewrite_pattern_syntax(pattern: str, rewrite: str, language: str) -> Dict[str, Any]:
    """Validate the syntax and structure of a rewrite pattern.
    
    Args:
        pattern: The search pattern
        rewrite: The rewrite pattern to validate
        language: Programming language for context
        
    Returns:
        Validation result with errors, warnings, and suggestions
    """
    validation_result = {
        "valid": True,
        "errors": [],
        "warnings": [],
        "suggestions": [],
        "meta_variables": {
            "pattern_vars": extract_meta_variables(pattern),
            "rewrite_vars": extract_meta_variables(rewrite),
            "consistency_check": analyze_meta_variable_consistency(pattern, rewrite)
        }
    }
    
    # Basic syntax validation
    if not rewrite or not rewrite.strip():
        validation_result["valid"] = False
        validation_result["errors"].append("Rewrite pattern cannot be empty")
        return validation_result
    
    # Check for balanced brackets/parentheses
    bracket_pairs = [('(', ')'), ('[', ']'), ('{', '}')]
    for open_bracket, close_bracket in bracket_pairs:
        open_count = rewrite.count(open_bracket)
        close_count = rewrite.count(close_bracket)
        if open_count != close_count:
            validation_result["warnings"].append(
                f"Unbalanced {open_bracket}{close_bracket} brackets in rewrite pattern"
            )
    
    # Check for potentially problematic patterns
    if '$' in rewrite and not extract_meta_variables(rewrite):
        validation_result["warnings"].append(
            "Rewrite pattern contains '$' but no valid meta-variables found"
        )
    
    # Meta-variable consistency check
    consistency = validation_result["meta_variables"]["consistency_check"]
    if consistency["undefined_in_rewrite"]:
        validation_result["errors"].extend([
            f"Meta-variable '{var}' used in rewrite but not defined in pattern"
            for var in consistency["undefined_in_rewrite"]
        ])
        validation_result["valid"] = False
    
    if consistency["unused_in_rewrite"]:
        validation_result["warnings"].extend([
            f"Meta-variable '{var}' defined in pattern but not used in rewrite"
            for var in consistency["unused_in_rewrite"]
        ])
    
    # Language-specific validation
    if language.lower() in ['javascript', 'typescript']:
        if 'var ' in rewrite:
            validation_result["suggestions"].append(
                "Consider using 'const' or 'let' instead of 'var' for modern JavaScript"
            )
    elif language.lower() == 'python':
        if rewrite.count('"') % 2 != 0 or rewrite.count("'") % 2 != 0:
            validation_result["warnings"].append(
                "Unbalanced quotes detected in Python rewrite pattern"
            )
    
    return validation_result


def generate_transformation_preview(
    pattern: str,
    rewrite: str,
    sample_matches: List[Dict[str, Any]],
    language: str
) -> Dict[str, Any]:
    """Generate a preview of how the transformation would be applied.
    
    Args:
        pattern: The search pattern
        rewrite: The rewrite pattern
        sample_matches: Sample match results from ast-grep
        language: Programming language
        
    Returns:
        Preview information with before/after examples and metadata
    """
    preview = {
        "transformation_summary": {
            "pattern": pattern,
            "rewrite": rewrite,
            "language": language,
            "total_matches": len(sample_matches),
            "meta_variables": extract_meta_variables(pattern)
        },
        "previews": [],
        "statistics": {
            "files_affected": set(),
            "lines_affected": [],
            "transformation_types": set()
        }
    }
    
    for i, match in enumerate(sample_matches[:10]):  # Limit to first 10 for preview
        match_preview = {
            "match_index": i + 1,
            "file": match.get("file", "unknown"),
            "line_range": {
                "start": match.get("range", {}).get("start", {}).get("line", "?"),
                "end": match.get("range", {}).get("end", {}).get("line", "?")
            },
            "original_text": match.get("text", ""),
            "meta_variable_bindings": match.get("metaVariables", {}),
            "transformed_text": None,
            "diff": None
        }
        
        # Generate transformed text if we have meta-variable bindings
        if match.get("metaVariables") and rewrite:
            transformed = rewrite
            for var_name, var_value in match["metaVariables"].items():
                transformed = transformed.replace(f"${var_name}", var_value.get("text", ""))
            match_preview["transformed_text"] = transformed
            
            # Generate a simple diff representation
            original_lines = match_preview["original_text"].splitlines()
            transformed_lines = transformed.splitlines()
            match_preview["diff"] = {
                "removed": original_lines,
                "added": transformed_lines,
                "context": f"Line {match_preview['line_range']['start']}"
            }
        
        preview["previews"].append(match_preview)
        
        # Update statistics
        if match.get("file"):
            preview["statistics"]["files_affected"].add(match["file"])
        if match.get("range", {}).get("start", {}).get("line"):
            preview["statistics"]["lines_affected"].append(
                match["range"]["start"]["line"]
            )
    
    # Convert sets to lists for JSON serialization
    preview["statistics"]["files_affected"] = list(preview["statistics"]["files_affected"])
    preview["statistics"]["total_files"] = len(preview["statistics"]["files_affected"])
    preview["statistics"]["total_lines"] = len(preview["statistics"]["lines_affected"])
    
    return preview


def create_diff_visualization(original: str, transformed: str, context_lines: int = 3) -> str:
    """Create a unified diff visualization for code changes.
    
    Args:
        original: Original code text
        transformed: Transformed code text
        context_lines: Number of context lines to show
        
    Returns:
        Unified diff string
    """
    import difflib
    
    original_lines = original.splitlines(keepends=True)
    transformed_lines = transformed.splitlines(keepends=True)
    
    diff = list(difflib.unified_diff(
        original_lines,
        transformed_lines,
        fromfile="before",
        tofile="after",
        n=context_lines
    ))
    
    return ''.join(diff)


def validate_transformation_safety(
    pattern: str,
    rewrite: str,
    language: str,
    sample_matches: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Validate the safety of a proposed transformation.
    
    Args:
        pattern: The search pattern
        rewrite: The rewrite pattern
        language: Programming language
        sample_matches: Sample matches to analyze
        
    Returns:
        Safety analysis with risk assessment and recommendations
    """
    safety_result = {
        "risk_level": "low",  # low, medium, high
        "safety_checks": {
            "syntax_validation": True,
            "semantic_consistency": True,
            "meta_variable_usage": True,
            "potential_breaking_changes": False
        },
        "warnings": [],
        "recommendations": [],
        "blocking_issues": []
    }
    
    # Check pattern and rewrite syntax
    syntax_validation = validate_rewrite_pattern_syntax(pattern, rewrite, language)
    if not syntax_validation["valid"]:
        safety_result["safety_checks"]["syntax_validation"] = False
        safety_result["blocking_issues"].extend(syntax_validation["errors"])
        safety_result["risk_level"] = "high"
    
    safety_result["warnings"].extend(syntax_validation["warnings"])
    
    # Check meta-variable consistency
    meta_var_analysis = validate_meta_variable_usage(pattern, rewrite)
    if meta_var_analysis["errors"]:
        safety_result["safety_checks"]["meta_variable_usage"] = False
        safety_result["blocking_issues"].extend(meta_var_analysis["errors"])
        safety_result["risk_level"] = "high"
    
    safety_result["warnings"].extend(meta_var_analysis["warnings"])
    
    # Analyze potential breaking changes
    breaking_change_indicators = [
        "import ", "require(", "from ", "use ",  # Import changes
        "class ", "interface ", "type ",  # Type changes
        "function ", "def ", "fn ",  # Function signature changes
        "export ", "module.exports",  # Export changes
    ]
    
    for match in sample_matches[:5]:  # Check first 5 matches
        original = match.get("text", "").lower()
        if any(indicator in original for indicator in breaking_change_indicators):
            safety_result["safety_checks"]["potential_breaking_changes"] = True
            safety_result["warnings"].append(
                "Transformation may affect imports, exports, or type definitions"
            )
            if safety_result["risk_level"] == "low":
                safety_result["risk_level"] = "medium"
            break
    
    # Generate recommendations based on analysis
    if safety_result["risk_level"] == "high":
        safety_result["recommendations"].append(
            "Review and fix blocking issues before applying transformation"
        )
    elif safety_result["risk_level"] == "medium":
        safety_result["recommendations"].extend([
            "Test the transformation on a small subset of files first",
            "Review changes carefully before committing",
            "Consider running your test suite after transformation"
        ])
    else:
        safety_result["recommendations"].append(
            "Transformation appears safe, but always review changes before committing"
        )
    
    if len(sample_matches) > 50:
        safety_result["recommendations"].append(
            f"Large number of matches ({len(sample_matches)}). Consider applying in batches."
        )
    
    return safety_result


def create_transformation_report(
    pattern: str,
    rewrite: str,
    language: str,
    matches: List[Dict[str, Any]],
    validation_result: Dict[str, Any],
    safety_result: Dict[str, Any]
) -> Dict[str, Any]:
    """Create a comprehensive transformation report.
    
    Args:
        pattern: Search pattern
        rewrite: Rewrite pattern
        language: Programming language
        matches: All match results
        validation_result: Pattern validation results
        safety_result: Safety analysis results
        
    Returns:
        Comprehensive transformation report
    """
    # Generate preview for subset of matches
    preview = generate_transformation_preview(pattern, rewrite, matches[:10], language)
    
    report = {
        "transformation_info": {
            "pattern": pattern,
            "rewrite": rewrite,
            "language": language,
            "timestamp": "2024-01-01T00:00:00Z",  # Would use actual timestamp
            "meta_variables": extract_meta_variables(pattern)
        },
        "match_summary": {
            "total_matches": len(matches),
            "files_affected": len(set(m.get("file", "") for m in matches if m.get("file"))),
            "preview_shown": min(10, len(matches))
        },
        "validation": validation_result,
        "safety_analysis": safety_result,
        "preview": preview,
        "recommendations": {
            "should_proceed": (
                validation_result.get("valid", False) and 
                safety_result.get("risk_level") != "high" and
                not safety_result.get("blocking_issues")
            ),
            "suggested_next_steps": [],
            "warnings": validation_result.get("warnings", []) + safety_result.get("warnings", [])
        }
    }
    
    # Generate contextual recommendations
    if not report["recommendations"]["should_proceed"]:
        report["recommendations"]["suggested_next_steps"].extend([
            "Fix validation errors before proceeding",
            "Review pattern and rewrite syntax",
            "Check meta-variable consistency"
        ])
    elif safety_result.get("risk_level") == "medium":
        report["recommendations"]["suggested_next_steps"].extend([
            "Test on a small subset first",
            "Review changes carefully",
            "Run tests after transformation"
        ])
    else:
        report["recommendations"]["suggested_next_steps"].extend([
            "Apply transformation with dry-run first",
            "Review generated diffs",
            "Apply changes when satisfied"
        ])
    
    return report


class FunctionDetector:
    """Detects function definitions across multiple programming languages using AST-grep patterns."""
    
    def __init__(self, executor: Optional['ASTGrepExecutor'] = None):
        """Initialize the function detector.
        
        Args:
            executor: Optional AST-grep executor instance. If None, creates a new one.
        """
        self.executor = executor
        self.language_manager = LanguageManager()
        self.logger = logging.getLogger(__name__)
        
    async def detect_functions(
        self,
        file_path: Union[str, Path],
        language: Optional[str] = None,
        pattern_types: Optional[List[str]] = None,
        include_metadata: bool = True
    ) -> Dict[str, Any]:
        """Detect function definitions in a source file.
        
        Args:
            file_path: Path to the source file
            language: Programming language (auto-detected if None)
            pattern_types: Specific pattern types to search for (all if None)
            include_metadata: Whether to extract function metadata
            
        Returns:
            Dictionary containing detected functions and metadata
        """
        try:
            # Normalize path
            file_path = Path(file_path)
            if not file_path.exists():
                return create_error_response(
                    "file_not_found",
                    f"File not found: {file_path}",
                    path=str(file_path)
                )
            
            # Detect language if not provided
            if not language:
                language = self.language_manager.detect_language(file_path)
                if not language:
                    return create_error_response(
                        "language_detection_failed",
                        f"Could not detect language for file: {file_path}",
                        path=str(file_path)
                    )
            
            # Validate language
            language = self.language_manager.validate_language_identifier(language, return_normalized=True)
            if not language:
                return create_error_response(
                    "unsupported_language",
                    f"Unsupported language: {language}",
                    path=str(file_path)
                )
            
            # Get function patterns for the language
            patterns = self._get_language_patterns(language, pattern_types)
            if not patterns:
                return create_error_response(
                    "no_patterns_found", 
                    f"No function patterns found for language: {language}",
                    details={"language": language, "available_patterns": list(self._get_available_pattern_types(language))}
                )
            
            # Initialize executor if needed
            if not self.executor:
                self.executor = await create_ast_grep_executor()
            
            # Detect functions using each pattern
            detected_functions = []
            for pattern_info in patterns:
                try:
                    matches = await self._search_with_pattern(
                        file_path, 
                        pattern_info, 
                        language
                    )
                    if matches:
                        for match in matches:
                            function_data = self._extract_function_metadata(
                                match, 
                                pattern_info,
                                include_metadata
                            )
                            if function_data:
                                detected_functions.append(function_data)
                                
                except Exception as pattern_error:
                    self.logger.warning(
                        f"Pattern matching failed for {pattern_info['type']}: {pattern_error}"
                    )
                    continue
            
            # Remove duplicates and sort results
            unique_functions = self._deduplicate_functions(detected_functions)
            sorted_functions = sorted(unique_functions, key=lambda f: (f.get('line', 0), f.get('column', 0)))
            
            return create_success_response(
                data={
                    "functions": sorted_functions,
                    "file_path": str(file_path),
                    "language": language,
                    "total_functions": len(sorted_functions),
                    "pattern_types_used": [p["type"] for p in patterns]
                },
                message=f"Found {len(sorted_functions)} function(s) in {file_path.name}"
            )
            
        except Exception as e:
            return handle_execution_error(
                e,
                path=str(file_path) if 'file_path' in locals() else None
            )
    
    async def detect_functions_in_directory(
        self,
        directory_path: Union[str, Path],
        language: Optional[str] = None,
        recursive: bool = True,
        file_patterns: Optional[List[str]] = None,
        max_files: Optional[int] = None
    ) -> Dict[str, Any]:
        """Detect functions in all source files in a directory.
        
        Args:
            directory_path: Path to the directory
            language: Specific language to search for (all supported if None)
            recursive: Whether to search subdirectories
            file_patterns: File patterns to include (e.g., ['*.py', '*.js'])
            max_files: Maximum number of files to process
            
        Returns:
            Dictionary containing detected functions across all files
        """
        try:
            directory_path = Path(directory_path)
            if not directory_path.is_dir():
                return create_error_response(
                    "invalid_directory",
                    f"Directory not found: {directory_path}",
                    path=str(directory_path)
                )
            
            # Find source files
            source_files = self._find_source_files(
                directory_path,
                language, 
                recursive,
                file_patterns,
                max_files
            )
            
            if not source_files:
                return create_success_response(
                    data={
                        "files": [],
                        "total_files": 0,
                        "total_functions": 0,
                        "directory": str(directory_path)
                    },
                    message="No source files found"
                )
            
            # Process each file
            results = []
            total_functions = 0
            
            for file_path in source_files:
                try:
                    file_result = await self.detect_functions(file_path, language)
                    if file_result and file_result.get("success", False):
                        data = file_result.get("data", {})
                        functions = data.get("functions", [])
                        
                        results.append({
                            "file_path": str(file_path),
                            "relative_path": str(file_path.relative_to(directory_path)),
                            "language": data.get("language"),
                            "function_count": len(functions),
                            "functions": functions
                        })
                        total_functions += len(functions)
                        
                except Exception as file_error:
                    self.logger.warning(f"Failed to process {file_path}: {file_error}")
                    continue
            
            return create_success_response(
                data={
                    "files": results,
                    "total_files": len(results),
                    "total_functions": total_functions,
                    "directory": str(directory_path),
                    "search_recursive": recursive
                },
                message=f"Processed {len(results)} files, found {total_functions} functions"
            )
            
        except Exception as e:
            return handle_execution_error(
                e,
                path=str(directory_path) if 'directory_path' in locals() else None
            )
    
    def _get_language_patterns(self, language: str, pattern_types: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Get function patterns for a specific language.
        
        Args:
            language: Programming language identifier
            pattern_types: Specific pattern types to retrieve
            
        Returns:
            List of pattern dictionaries
        """
        from .resources import FUNCTION_PATTERNS, CALL_PATTERNS
        
        language_patterns = FUNCTION_PATTERNS.get(language, {}).get("patterns", [])
        
        if pattern_types:
            # Filter by specified pattern types
            return [p for p in language_patterns if p.get("type") in pattern_types]
        
        return language_patterns
    
    def _get_available_pattern_types(self, language: str) -> Set[str]:
        """Get available pattern types for a language.
        
        Args:
            language: Programming language identifier
            
        Returns:
            Set of available pattern type names
        """
        patterns = self._get_language_patterns(language)
        return {p.get("type", "unknown") for p in patterns}
    
    async def _search_with_pattern(
        self,
        file_path: Path,
        pattern_info: Dict[str, Any],
        language: str
    ) -> List[Dict[str, Any]]:
        """Search for functions using a specific pattern.
        
        Args:
            file_path: Path to the source file
            pattern_info: Pattern information dictionary
            language: Programming language
            
        Returns:
            List of matches from AST-grep
        """
        pattern = pattern_info.get("pattern", "")
        if not pattern:
            return []
        
        # Map language to AST-grep language code
        ast_grep_language = self.language_manager.map_to_ast_grep_language(language)
        
        # Execute search
        result = await self.executor.search(
            pattern=pattern,
            language=ast_grep_language,
            paths=[str(file_path)],
            additional_args=["--json"]
        )
        
        if not result.get("success", False):
            return []
        
        # Parse JSON output
        stdout = result.get("stdout", "")
        if stdout:
            try:
                return parse_ast_grep_json_output(stdout)
            except Exception as parse_error:
                self.logger.warning(f"Failed to parse AST-grep output: {parse_error}")
                return []
        
        return []
    
    def _extract_function_metadata(
        self,
        match: Dict[str, Any],
        pattern_info: Dict[str, Any],
        include_metadata: bool = True
    ) -> Optional[Dict[str, Any]]:
        """Extract function metadata from an AST-grep match.
        
        Args:
            match: AST-grep match result
            pattern_info: Pattern information
            include_metadata: Whether to include detailed metadata
            
        Returns:
            Function metadata dictionary
        """
        try:
            # Basic information from match
            function_data = {
                "pattern_type": pattern_info.get("type", "unknown"),
                "pattern_description": pattern_info.get("description", ""),
                "file": match.get("file", ""),
                "line": match.get("line", 0),
                "column": match.get("column", 0),
                "text": match.get("text", "").strip()
            }
            
            if not include_metadata:
                return function_data
            
            # Extract meta-variables
            meta_vars = match.get("metaVars", {})
            captures = pattern_info.get("captures", {})
            
            # Map captures to extracted data
            for capture_key, meta_var_name in captures.items():
                if meta_var_name in meta_vars:
                    meta_var_data = meta_vars[meta_var_name]
                    if isinstance(meta_var_data, dict):
                        function_data[capture_key] = meta_var_data.get("text", "").strip()
                    else:
                        function_data[capture_key] = str(meta_var_data).strip()
            
            # Enhanced metadata extraction
            language = self.language_manager.detect_language_from_extension(
                match.get("file", "")
            ) or "unknown"
            
            # Parse function parameters if available
            params_text = function_data.get("parameters", "")
            if params_text:
                try:
                    parsed_params = parse_function_parameters(params_text, language)
                    function_data["parsed_parameters"] = parsed_params
                    function_data["parameter_count"] = len(parsed_params)
                    function_data["has_default_parameters"] = any(
                        p.get("default") for p in parsed_params
                    )
                    function_data["has_typed_parameters"] = any(
                        p.get("type") for p in parsed_params
                    )
                except Exception as param_error:
                    self.logger.warning(f"Failed to parse parameters: {param_error}")
                    function_data["parsed_parameters"] = []
                    function_data["parameter_count"] = 0
            else:
                function_data["parsed_parameters"] = []
                function_data["parameter_count"] = 0
            
            # Extract function documentation
            try:
                doc_text = extract_function_documentation(
                    function_data.get("text", ""),
                    language
                )
                function_data["documentation"] = doc_text
                function_data["has_documentation"] = bool(doc_text)
            except Exception as doc_error:
                self.logger.warning(f"Failed to extract documentation: {doc_error}")
                function_data["documentation"] = None
                function_data["has_documentation"] = False
            
            # Analyze function complexity
            try:
                complexity_analysis = analyze_function_complexity(function_data)
                function_data["complexity"] = complexity_analysis
            except Exception as complexity_error:
                self.logger.warning(f"Failed to analyze complexity: {complexity_error}")
                function_data["complexity"] = {
                    "score": 1,
                    "level": "unknown",
                    "factors": []
                }
            
            # Additional metadata
            function_data.update({
                "meta_variables": list(meta_vars.keys()),
                "has_return_type": bool(function_data.get("return_type")),
                "has_parameters": bool(function_data.get("parameters")),
                "is_class_method": bool(function_data.get("class_name")),
                "is_constructor": pattern_info.get("captures", {}).get("is_constructor", False),
                "modifiers": pattern_info.get("captures", {}).get("modifiers", []),
                "language": language,
                "function_type": self._classify_function_type(function_data, pattern_info),
                "signature": self._generate_function_signature(function_data)
            })
            
            return function_data
            
        except Exception as e:
            self.logger.warning(f"Failed to extract function metadata: {e}")
            return None
    
    def _classify_function_type(self, function_data: Dict[str, Any], pattern_info: Dict[str, Any]) -> str:
        """Classify the type of function based on metadata.
        
        Args:
            function_data: Function metadata
            pattern_info: Pattern information
            
        Returns:
            Function classification string
        """
        pattern_type = pattern_info.get("type", "")
        
        if function_data.get("is_constructor"):
            return "constructor"
        elif function_data.get("is_class_method"):
            return "method"
        elif "lambda" in pattern_type or "closure" in pattern_type:
            return "lambda"
        elif "arrow" in pattern_type:
            return "arrow_function"
        elif "async" in pattern_type or "async" in function_data.get("modifiers", []):
            return "async_function"
        elif function_data.get("modifiers"):
            return "modified_function"
        else:
            return "function"
    
    def _generate_function_signature(self, function_data: Dict[str, Any]) -> str:
        """Generate a human-readable function signature.
        
        Args:
            function_data: Function metadata
            
        Returns:
            Function signature string
        """
        try:
            signature_parts = []
            
            # Add modifiers
            modifiers = function_data.get("modifiers", [])
            if modifiers:
                signature_parts.extend(modifiers)
            
            # Add function name
            name = function_data.get("name", "anonymous")
            
            # Add parameters
            params = function_data.get("parsed_parameters", [])
            param_strings = []
            
            for param in params:
                param_str = param.get("name", "")
                
                # Add type if available
                param_type = param.get("type")
                if param_type:
                    param_str += f": {param_type}"
                
                # Add default value if available
                default = param.get("default")
                if default:
                    param_str += f" = {default}"
                
                param_strings.append(param_str)
            
            params_str = f"({', '.join(param_strings)})"
            
            # Add return type if available
            return_type = function_data.get("return_type")
            return_str = f" -> {return_type}" if return_type else ""
            
            # Combine parts
            if signature_parts:
                return f"{' '.join(signature_parts)} {name}{params_str}{return_str}"
            else:
                return f"{name}{params_str}{return_str}"
                
        except Exception as e:
            self.logger.warning(f"Failed to generate function signature: {e}")
            return function_data.get("name", "unknown")
    
    def _deduplicate_functions(self, functions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove duplicate function detections.
        
        Args:
            functions: List of detected functions
            
        Returns:
            List of unique functions
        """
        unique_functions = []
        seen_locations = set()
        
        for func in functions:
            # Create a location key for deduplication
            location_key = (
                func.get("file", ""),
                func.get("line", 0),
                func.get("column", 0),
                func.get("name", "")
            )
            
            if location_key not in seen_locations:
                seen_locations.add(location_key)
                unique_functions.append(func)
        
        return unique_functions
    
    def _find_source_files(
        self,
        directory: Path,
        language: Optional[str] = None,
        recursive: bool = True,
        file_patterns: Optional[List[str]] = None,
        max_files: Optional[int] = None
    ) -> List[Path]:
        """Find source files in a directory.
        
        Args:
            directory: Directory to search
            language: Specific language to search for
            recursive: Whether to search subdirectories
            file_patterns: File patterns to include
            max_files: Maximum number of files to return
            
        Returns:
            List of source file paths
        """
        from .resources import SUPPORTED_LANGUAGES
        
        source_files = []
        
        # Determine file extensions to search for
        if language:
            # Get extensions for specific language
            lang_info = SUPPORTED_LANGUAGES.get(language, {})
            extensions = set(lang_info.get("extensions", []))
        else:
            # Get extensions for all supported languages
            extensions = set()
            for lang_info in SUPPORTED_LANGUAGES.values():
                extensions.update(lang_info.get("extensions", []))
        
        # Search for files
        pattern = "**/*" if recursive else "*"
        
        for file_path in directory.glob(pattern):
            if not file_path.is_file():
                continue
            
            # Check file extension
            if extensions and file_path.suffix.lower() not in extensions:
                continue
            
            # Check file patterns if specified
            if file_patterns:
                import fnmatch
                if not any(fnmatch.fnmatch(file_path.name, pattern) for pattern in file_patterns):
                    continue
            
            source_files.append(file_path)
            
            # Check max files limit
            if max_files and len(source_files) >= max_files:
                break
        
        return source_files

async def create_function_detector(**kwargs) -> FunctionDetector:
    """Create and initialize a function detector instance.
    
    Args:
        **kwargs: Arguments passed to FunctionDetector constructor
        
    Returns:
        Initialized FunctionDetector instance
    """
    detector = FunctionDetector(**kwargs)
    if not detector.executor:
        detector.executor = await create_ast_grep_executor()
    return detector

def parse_function_parameters(params_text: str, language: str) -> List[Dict[str, Any]]:
    """Parse function parameters from text into structured data.
    
    Args:
        params_text: Raw parameter text from function definition
        language: Programming language for context-specific parsing
        
    Returns:
        List of parameter dictionaries with name, type, default value, etc.
    """
    if not params_text or not params_text.strip():
        return []
    
    parameters = []
    params_text = params_text.strip()
    
    # Remove outer parentheses if present
    if params_text.startswith('(') and params_text.endswith(')'):
        params_text = params_text[1:-1].strip()
    
    if not params_text:
        return []
    
    # Language-specific parameter parsing
    if language in ['python']:
        parameters = _parse_python_parameters(params_text)
    elif language in ['javascript', 'typescript']:
        parameters = _parse_js_ts_parameters(params_text, language)
    elif language in ['java', 'csharp', 'kotlin']:
        parameters = _parse_java_like_parameters(params_text, language)
    elif language in ['cpp', 'c']:
        parameters = _parse_c_cpp_parameters(params_text)
    elif language in ['rust']:
        parameters = _parse_rust_parameters(params_text)
    elif language in ['go']:
        parameters = _parse_go_parameters(params_text)
    else:
        # Generic parsing for other languages
        parameters = _parse_generic_parameters(params_text)
    
    return parameters

def _parse_python_parameters(params_text: str) -> List[Dict[str, Any]]:
    """Parse Python function parameters."""
    parameters = []
    
    # Split by comma, but handle nested structures
    param_parts = _split_parameters(params_text)
    
    for param in param_parts:
        param = param.strip()
        if not param:
            continue
            
        param_info = {
            "name": "",
            "type": None,
            "default": None,
            "is_variadic": False,
            "is_keyword": False
        }
        
        # Handle *args and **kwargs
        if param.startswith('**'):
            param_info["is_keyword"] = True
            param = param[2:]
        elif param.startswith('*'):
            param_info["is_variadic"] = True
            param = param[1:]
        
        # Split by type annotation (:)
        if ':' in param:
            name_part, type_part = param.split(':', 1)
            param_info["name"] = name_part.strip()
            
            # Check for default value in type part
            if '=' in type_part:
                type_part, default_part = type_part.split('=', 1)
                param_info["type"] = type_part.strip()
                param_info["default"] = default_part.strip()
            else:
                param_info["type"] = type_part.strip()
        elif '=' in param:
            # No type annotation, but has default value
            name_part, default_part = param.split('=', 1)
            param_info["name"] = name_part.strip()
            param_info["default"] = default_part.strip()
        else:
            # Just parameter name
            param_info["name"] = param.strip()
        
        if param_info["name"]:
            parameters.append(param_info)
    
    return parameters

def _parse_js_ts_parameters(params_text: str, language: str) -> List[Dict[str, Any]]:
    """Parse JavaScript/TypeScript function parameters."""
    parameters = []
    param_parts = _split_parameters(params_text)
    
    for param in param_parts:
        param = param.strip()
        if not param:
            continue
            
        param_info = {
            "name": "",
            "type": None,
            "default": None,
            "is_optional": False,
            "is_rest": False
        }
        
        # Handle rest parameters
        if param.startswith('...'):
            param_info["is_rest"] = True
            param = param[3:]
        
        # TypeScript type annotations
        if language == 'typescript' and ':' in param:
            name_part, type_part = param.split(':', 1)
            
            # Check for optional parameter
            if name_part.endswith('?'):
                param_info["is_optional"] = True
                name_part = name_part[:-1]
            
            param_info["name"] = name_part.strip()
            
            # Check for default value in type part
            if '=' in type_part:
                type_part, default_part = type_part.split('=', 1)
                param_info["type"] = type_part.strip()
                param_info["default"] = default_part.strip()
            else:
                param_info["type"] = type_part.strip()
        elif '=' in param:
            # Default value without type
            name_part, default_part = param.split('=', 1)
            param_info["name"] = name_part.strip()
            param_info["default"] = default_part.strip()
        else:
            # Just parameter name
            param_info["name"] = param.strip()
        
        if param_info["name"]:
            parameters.append(param_info)
    
    return parameters

def _parse_java_like_parameters(params_text: str, language: str) -> List[Dict[str, Any]]:
    """Parse Java/C#/Kotlin-like function parameters."""
    parameters = []
    param_parts = _split_parameters(params_text)
    
    for param in param_parts:
        param = param.strip()
        if not param:
            continue
            
        param_info = {
            "name": "",
            "type": None,
            "default": None,
            "modifiers": []
        }
        
        # Split into tokens
        tokens = param.split()
        if not tokens:
            continue
        
        # Handle modifiers (final, const, etc.)
        modifier_keywords = ['final', 'const', 'var', 'val']
        while tokens and tokens[0] in modifier_keywords:
            param_info["modifiers"].append(tokens.pop(0))
        
        if len(tokens) >= 2:
            # Type and name
            param_info["type"] = tokens[0]
            name_with_default = ' '.join(tokens[1:])
            
            # Check for default value
            if '=' in name_with_default:
                name_part, default_part = name_with_default.split('=', 1)
                param_info["name"] = name_part.strip()
                param_info["default"] = default_part.strip()
            else:
                param_info["name"] = name_with_default.strip()
        elif len(tokens) == 1:
            param_info["name"] = tokens[0]
        
        if param_info["name"]:
            parameters.append(param_info)
    
    return parameters

def _parse_c_cpp_parameters(params_text: str) -> List[Dict[str, Any]]:
    """Parse C/C++ function parameters."""
    parameters = []
    param_parts = _split_parameters(params_text)
    
    for param in param_parts:
        param = param.strip()
        if not param or param == 'void':
            continue
            
        param_info = {
            "name": "",
            "type": None,
            "default": None,
            "is_pointer": False,
            "is_reference": False
        }
        
        # Check for default value
        if '=' in param:
            param, default_part = param.split('=', 1)
            param_info["default"] = default_part.strip()
            param = param.strip()
        
        # Analyze type and name
        tokens = param.split()
        if tokens:
            # Last token is usually the name
            param_info["name"] = tokens[-1]
            
            # Check for pointer/reference
            if param_info["name"].startswith('*'):
                param_info["is_pointer"] = True
                param_info["name"] = param_info["name"][1:]
            elif param_info["name"].startswith('&'):
                param_info["is_reference"] = True
                param_info["name"] = param_info["name"][1:]
            
            # Everything else is the type
            if len(tokens) > 1:
                type_tokens = tokens[:-1]
                param_info["type"] = ' '.join(type_tokens)
        
        if param_info["name"]:
            parameters.append(param_info)
    
    return parameters

def _parse_rust_parameters(params_text: str) -> List[Dict[str, Any]]:
    """Parse Rust function parameters."""
    parameters = []
    param_parts = _split_parameters(params_text)
    
    for param in param_parts:
        param = param.strip()
        if not param:
            continue
            
        param_info = {
            "name": "",
            "type": None,
            "is_mutable": False,
            "is_self": False
        }
        
        # Handle self parameter
        if param in ['self', '&self', '&mut self', 'mut self']:
            param_info["is_self"] = True
            param_info["name"] = "self"
            if 'mut' in param:
                param_info["is_mutable"] = True
            parameters.append(param_info)
            continue
        
        # Check for mutability
        if param.startswith('mut '):
            param_info["is_mutable"] = True
            param = param[4:]
        
        # Split by type annotation (:)
        if ':' in param:
            name_part, type_part = param.split(':', 1)
            param_info["name"] = name_part.strip()
            param_info["type"] = type_part.strip()
        else:
            param_info["name"] = param.strip()
        
        if param_info["name"]:
            parameters.append(param_info)
    
    return parameters

def _parse_go_parameters(params_text: str) -> List[Dict[str, Any]]:
    """Parse Go function parameters."""
    parameters = []
    param_parts = _split_parameters(params_text)
    
    for param in param_parts:
        param = param.strip()
        if not param:
            continue
            
        param_info = {
            "name": "",
            "type": None,
            "is_variadic": False
        }
        
        # Handle variadic parameters
        if '...' in param:
            param_info["is_variadic"] = True
            param = param.replace('...', '').strip()
        
        # Go parameters can be "name type" or just "type"
        tokens = param.split()
        if len(tokens) >= 2:
            param_info["name"] = tokens[0]
            param_info["type"] = ' '.join(tokens[1:])
        elif len(tokens) == 1:
            # Just type, no explicit name
            param_info["type"] = tokens[0]
            param_info["name"] = f"param{len(parameters)}"  # Generate name
        
        if param_info["name"]:
            parameters.append(param_info)
    
    return parameters

def _parse_generic_parameters(params_text: str) -> List[Dict[str, Any]]:
    """Generic parameter parsing for unsupported languages."""
    parameters = []
    param_parts = _split_parameters(params_text)
    
    for i, param in enumerate(param_parts):
        param = param.strip()
        if not param:
            continue
            
        param_info = {
            "name": param,
            "type": None,
            "default": None
        }
        
        # Try to extract default value
        if '=' in param:
            name_part, default_part = param.split('=', 1)
            param_info["name"] = name_part.strip()
            param_info["default"] = default_part.strip()
        
        parameters.append(param_info)
    
    return parameters

def _split_parameters(params_text: str) -> List[str]:
    """Split parameter text by commas, respecting nested structures."""
    if not params_text:
        return []
    
    parameters = []
    current_param = ""
    nesting_level = 0
    in_string = False
    string_char = None
    
    for char in params_text:
        if not in_string:
            if char in ['"', "'", '`']:
                in_string = True
                string_char = char
            elif char in ['(', '[', '{']:
                nesting_level += 1
            elif char in [')', ']', '}']:
                nesting_level -= 1
            elif char == ',' and nesting_level == 0:
                parameters.append(current_param)
                current_param = ""
                continue
        else:
            if char == string_char:
                in_string = False
                string_char = None
        
        current_param += char
    
    if current_param:
        parameters.append(current_param)
    
    return parameters

def extract_function_documentation(text: str, language: str, line_before: Optional[str] = None) -> Optional[str]:
    """Extract documentation/comments from function definition.
    
    Args:
        text: Function definition text
        language: Programming language
        line_before: Text from line before function definition
        
    Returns:
        Extracted documentation string or None
    """
    if not text:
        return None
    
    doc_text = None
    
    if language == 'python':
        # Look for docstring
        lines = text.split('\n')
        for line in lines[1:]:  # Skip function definition line
            line = line.strip()
            if line.startswith('"""') or line.startswith("'''"):
                # Found docstring start
                if line.count('"""') >= 2 or line.count("'''") >= 2:
                    # Single line docstring
                    doc_text = line.strip('"""').strip("'''").strip()
                else:
                    # Multi-line docstring - would need more complex parsing
                    doc_text = line.strip('"""').strip("'''").strip()
                break
            elif line and not line.startswith('#'):
                break  # Found non-comment code
    
    elif language in ['javascript', 'typescript']:
        # Look for JSDoc
        if line_before and '/**' in line_before:
            doc_text = line_before.strip()
    
    elif language in ['java', 'csharp']:
        # Look for JavaDoc or XML comments
        if line_before:
            if '/**' in line_before:  # JavaDoc
                doc_text = line_before.strip()
            elif '///' in line_before:  # C# XML doc
                doc_text = line_before.strip()
    
    elif language in ['rust']:
        # Look for Rust doc comments
        if line_before and '///' in line_before:
            doc_text = line_before.strip()
    
    elif language in ['go']:
        # Look for Go doc comments
        if line_before and line_before.strip().startswith('//'):
            doc_text = line_before.strip()
    
    return doc_text

def analyze_function_complexity(function_data: Dict[str, Any]) -> Dict[str, Any]:
    """Analyze function complexity based on available metadata.
    
    Args:
        function_data: Function metadata dictionary
        
    Returns:
        Complexity analysis results
    """
    complexity = {
        "score": 1,
        "factors": [],
        "level": "simple"
    }
    
    # Parameter count complexity
    parameters = function_data.get("parsed_parameters", [])
    param_count = len(parameters)
    
    if param_count > 5:
        complexity["score"] += 2
        complexity["factors"].append(f"High parameter count ({param_count})")
    elif param_count > 3:
        complexity["score"] += 1
        complexity["factors"].append(f"Moderate parameter count ({param_count})")
    
    # Function length complexity (estimate from text)
    text = function_data.get("text", "")
    line_count = len(text.split('\n'))
    
    if line_count > 50:
        complexity["score"] += 3
        complexity["factors"].append(f"Long function ({line_count} lines)")
    elif line_count > 20:
        complexity["score"] += 2
        complexity["factors"].append(f"Medium function ({line_count} lines)")
    elif line_count > 10:
        complexity["score"] += 1
        complexity["factors"].append(f"Short function ({line_count} lines)")
    
    # Nested structures
    nesting_indicators = ['{', 'if', 'for', 'while', 'switch', 'try']
    nesting_count = sum(text.lower().count(indicator) for indicator in nesting_indicators)
    
    if nesting_count > 10:
        complexity["score"] += 2
        complexity["factors"].append(f"High nesting complexity")
    elif nesting_count > 5:
        complexity["score"] += 1
        complexity["factors"].append(f"Moderate nesting complexity")
    
    # Determine complexity level
    if complexity["score"] >= 7:
        complexity["level"] = "complex"
    elif complexity["score"] >= 4:
        complexity["level"] = "moderate"
    else:
        complexity["level"] = "simple"
    
    return complexity

class CallDetector:
    """Detects function calls, method invocations, and constructor calls across multiple programming languages using AST-grep patterns."""
    
    def __init__(self, executor: Optional['ASTGrepExecutor'] = None):
        """Initialize the call detector.
        
        Args:
            executor: Optional AST-grep executor instance. If None, creates a new one.
        """
        self.executor = executor
        self.language_manager = LanguageManager()
        self.logger = logging.getLogger(__name__)
        
    async def detect_calls(
        self,
        file_path: Union[str, Path],
        language: Optional[str] = None,
        call_types: Optional[List[str]] = None,
        include_metadata: bool = True,
        max_calls: Optional[int] = None
    ) -> Dict[str, Any]:
        """Detect function calls in a source file.
        
        Args:
            file_path: Path to the source file
            language: Programming language (auto-detected if None)
            call_types: Specific call types to search for (all if None)
            include_metadata: Whether to extract call metadata
            max_calls: Maximum number of calls to detect (unlimited if None)
            
        Returns:
            Dictionary containing detected calls and metadata
        """
        try:
            # Normalize path
            file_path = Path(file_path)
            if not file_path.exists():
                return create_error_response(
                    "file_not_found",
                    f"File not found: {file_path}",
                    path=str(file_path)
                )
            
            # Detect language if not provided
            if not language:
                language = self.language_manager.detect_language(file_path)
                if not language:
                    return create_error_response(
                        "language_detection_failed",
                        f"Could not detect language for file: {file_path}",
                        path=str(file_path)
                    )
            
            # Validate language
            language = self.language_manager.validate_language_identifier(language, return_normalized=True)
            if not language:
                return create_error_response(
                    "unsupported_language",
                    f"Unsupported language: {language}",
                    path=str(file_path)
                )
            
            # Get call patterns for the language
            patterns = self._get_call_patterns(language, call_types)
            if not patterns:
                return create_error_response(
                    "no_patterns_found", 
                    f"No call patterns found for language: {language}",
                    details={"language": language, "available_types": list(self._get_available_call_types(language))}
                )
            
            # Initialize executor if needed
            if not self.executor:
                self.executor = await create_ast_grep_executor()
            
            # Detect calls using each pattern
            detected_calls = []
            for pattern_info in patterns:
                try:
                    matches = await self._search_with_call_pattern(
                        file_path, 
                        pattern_info, 
                        language
                    )
                    if matches:
                        for match in matches:
                            call_data = self._extract_call_metadata(
                                match, 
                                pattern_info,
                                include_metadata
                            )
                            if call_data:
                                detected_calls.append(call_data)
                                
                                # Check max calls limit
                                if max_calls and len(detected_calls) >= max_calls:
                                    break
                                
                except Exception as pattern_error:
                    self.logger.warning(
                        f"Call pattern matching failed for {pattern_info['type']}: {pattern_error}"
                    )
                    continue
                
                # Check max calls limit
                if max_calls and len(detected_calls) >= max_calls:
                    break
            
            # Remove duplicates and sort results
            unique_calls = self._deduplicate_calls(detected_calls)
            sorted_calls = sorted(unique_calls, key=lambda c: (c.get('line', 0), c.get('column', 0)))
            
            return create_success_response(
                data={
                    "calls": sorted_calls,
                    "file_path": str(file_path),
                    "language": language,
                    "total_calls": len(sorted_calls),
                    "call_types_used": [p["type"] for p in patterns],
                    "truncated": max_calls and len(detected_calls) >= max_calls
                },
                message=f"Found {len(sorted_calls)} call(s) in {file_path.name}"
            )
            
        except Exception as e:
            return handle_execution_error(
                e,
                path=str(file_path) if 'file_path' in locals() else None
            )
    
    async def detect_calls_in_directory(
        self,
        directory_path: Union[str, Path],
        language: Optional[str] = None,
        recursive: bool = True,
        file_patterns: Optional[List[str]] = None,
        max_files: Optional[int] = None,
        max_calls_per_file: Optional[int] = None
    ) -> Dict[str, Any]:
        """Detect calls in all source files in a directory.
        
        Args:
            directory_path: Path to the directory
            language: Specific language to search for (all supported if None)
            recursive: Whether to search subdirectories
            file_patterns: File patterns to include (e.g., ['*.py', '*.js'])
            max_files: Maximum number of files to process
            max_calls_per_file: Maximum calls to detect per file
            
        Returns:
            Dictionary containing detected calls across all files
        """
        try:
            directory_path = Path(directory_path)
            if not directory_path.is_dir():
                return create_error_response(
                    "invalid_directory",
                    f"Directory not found: {directory_path}",
                    path=str(directory_path)
                )
            
            # Find source files (reuse FunctionDetector logic)
            function_detector = FunctionDetector()
            source_files = function_detector._find_source_files(
                directory_path,
                language, 
                recursive,
                file_patterns,
                max_files
            )
            
            if not source_files:
                return create_success_response(
                    data={
                        "files": [],
                        "total_files": 0,
                        "total_calls": 0,
                        "directory": str(directory_path)
                    },
                    message="No source files found"
                )
            
            # Process each file
            results = []
            total_calls = 0
            
            for file_path in source_files:
                try:
                    file_result = await self.detect_calls(
                        file_path, 
                        language,
                        max_calls=max_calls_per_file
                    )
                    if file_result and file_result.get("success", False):
                        data = file_result.get("data", {})
                        calls = data.get("calls", [])
                        
                        results.append({
                            "file_path": str(file_path),
                            "relative_path": str(file_path.relative_to(directory_path)),
                            "language": data.get("language"),
                            "call_count": len(calls),
                            "calls": calls,
                            "truncated": data.get("truncated", False)
                        })
                        total_calls += len(calls)
                        
                except Exception as file_error:
                    self.logger.warning(f"Failed to process {file_path}: {file_error}")
                    continue
            
            return create_success_response(
                data={
                    "files": results,
                    "total_files": len(results),
                    "total_calls": total_calls,
                    "directory": str(directory_path),
                    "search_recursive": recursive
                },
                message=f"Processed {len(results)} files, found {total_calls} call(s)"
            )
            
        except Exception as e:
            return handle_execution_error(
                e,
                path=str(directory_path) if 'directory_path' in locals() else None
            )
    
    def _get_call_patterns(self, language: str, call_types: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Get call patterns for a specific language.
        
        Args:
            language: Programming language identifier
            call_types: Specific call types to include (all if None)
            
        Returns:
            List of pattern dictionaries
        """
        language_patterns = CALL_PATTERNS.get(language, {}).get("patterns", [])
        
        if call_types:
            # Filter patterns by specified types
            language_patterns = [
                pattern for pattern in language_patterns 
                if pattern.get("type") in call_types
            ]
        
        return language_patterns
    
    def _get_available_call_types(self, language: str) -> Set[str]:
        """Get available call types for a language.
        
        Args:
            language: Programming language identifier
            
        Returns:
            Set of available call type names
        """
        patterns = CALL_PATTERNS.get(language, {}).get("patterns", [])
        return {pattern.get("type", "unknown") for pattern in patterns}
    
    async def _search_with_call_pattern(
        self,
        file_path: Path,
        pattern_info: Dict[str, Any],
        language: str
    ) -> List[Dict[str, Any]]:
        """Search for calls using a specific pattern.
        
        Args:
            file_path: Path to the source file
            pattern_info: Pattern definition dictionary
            language: Programming language identifier
            
        Returns:
            List of match dictionaries
        """
        pattern = pattern_info.get("pattern", "")
        if not pattern:
            return []
        
        try:
            # Map language for ast-grep compatibility
            ast_grep_language = self.language_manager.map_to_ast_grep_language(language)
            
            result = await self.executor.search(
                pattern=pattern,
                language=ast_grep_language,
                paths=[str(file_path)]
            )
            
            if not result.get("success", False):
                return []
            
            return result.get("data", {}).get("matches", [])
            
        except Exception as e:
            self.logger.warning(f"Pattern search failed: {e}")
            return []
    
    def _extract_call_metadata(
        self,
        match: Dict[str, Any],
        pattern_info: Dict[str, Any],
        include_metadata: bool = True
    ) -> Optional[Dict[str, Any]]:
        """Extract comprehensive call metadata from a pattern match.
        
        Args:
            match: AST-grep match result
            pattern_info: Pattern definition used for matching
            include_metadata: Whether to include detailed metadata
            
        Returns:
            Call data dictionary or None if extraction fails
        """
        try:
            # Basic call information
            call_data = {
                "id": f"call_{match.get('range', {}).get('start', {}).get('line', 0)}_{match.get('range', {}).get('start', {}).get('column', 0)}",
                "text": match.get("text", "").strip(),
                "type": pattern_info.get("type", "unknown"),
                "pattern_description": pattern_info.get("description", ""),
                "file": match.get("file", ""),
                "line": match.get("range", {}).get("start", {}).get("line", 0),
                "column": match.get("range", {}).get("start", {}).get("column", 0),
                "end_line": match.get("range", {}).get("end", {}).get("line", 0),
                "end_column": match.get("range", {}).get("end", {}).get("column", 0)
            }
            
            # Extract meta-variables from the match
            meta_vars = match.get("metaVariables", {})
            captures = pattern_info.get("captures", {})
            
            # Map captures to call data
            for capture_name, meta_var in captures.items():
                if meta_var in meta_vars:
                    var_data = meta_vars[meta_var]
                    call_data[capture_name] = var_data.get("text", "").strip()
            
            if include_metadata:
                # Comprehensive metadata extraction
                call_data.update(self._extract_call_context(match, pattern_info))
                call_data.update(self._analyze_call_complexity(call_data, pattern_info))
                call_data.update(self._extract_call_site_info(match, call_data))
                call_data.update(self._analyze_argument_patterns(call_data, meta_vars))
                call_data.update(self._extract_scope_information(match, call_data))
                call_data.update(self._analyze_call_security(call_data, pattern_info))
                call_data.update(self._extract_performance_indicators(call_data))
            
            return call_data
            
        except Exception as e:
            self.logger.warning(f"Call metadata extraction failed: {e}")
            return None
    
    def _extract_call_context(self, match: Dict[str, Any], pattern_info: Dict[str, Any]) -> Dict[str, Any]:
        """Extract contextual information about the call.
        
        Args:
            match: AST-grep match result
            pattern_info: Pattern definition
            
        Returns:
            Dictionary with context information
        """
        context = {}
        
        # Determine call classification
        call_type = pattern_info.get("type", "unknown")
        context["call_classification"] = self._classify_call_type(call_type)
        
        # Extract argument count if available
        meta_vars = match.get("metaVariables", {})
        if "ARGS" in meta_vars:
            args_text = meta_vars["ARGS"].get("text", "").strip()
            context["argument_count"] = self._count_arguments(args_text)
            context["has_arguments"] = bool(args_text)
        
        # Extract chaining information for chained calls
        if call_type == "chained_call":
            context["is_chained"] = True
            context["chain_length"] = 2  # At least 2 in a chain
        else:
            context["is_chained"] = False
        
        # Extract generic type information if available
        if "TYPE" in meta_vars:
            context["has_generic_types"] = True
            context["generic_types"] = meta_vars["TYPE"].get("text", "").strip()
        else:
            context["has_generic_types"] = False
        
        return context
    
    def _classify_call_type(self, pattern_type: str) -> str:
        """Classify the type of call for analysis.
        
        Args:
            pattern_type: The pattern type from the call detection
            
        Returns:
            Simplified call classification
        """
        if "constructor" in pattern_type:
            return "constructor"
        elif "method" in pattern_type:
            return "method"
        elif "function" in pattern_type:
            return "function"
        elif "static" in pattern_type:
            return "static"
        elif "macro" in pattern_type:
            return "macro"
        else:
            return "other"
    
    def _count_arguments(self, args_text: str) -> int:
        """Count the number of arguments in a call.
        
        Args:
            args_text: Raw argument text
            
        Returns:
            Number of arguments (0 if empty or unparseable)
        """
        if not args_text or not args_text.strip():
            return 0
        
        # Simple argument counting (handles basic cases)
        # Remove whitespace and check for empty
        args_text = args_text.strip()
        if not args_text:
            return 0
        
        # Count commas + 1, but handle nested parentheses/brackets
        paren_depth = 0
        bracket_depth = 0
        brace_depth = 0
        comma_count = 0
        
        for char in args_text:
            if char == '(':
                paren_depth += 1
            elif char == ')':
                paren_depth -= 1
            elif char == '[':
                bracket_depth += 1
            elif char == ']':
                bracket_depth -= 1
            elif char == '{':
                brace_depth += 1
            elif char == '}':
                brace_depth -= 1
            elif char == ',' and paren_depth == 0 and bracket_depth == 0 and brace_depth == 0:
                comma_count += 1
        
        return comma_count + 1 if args_text else 0
    
    def _analyze_call_complexity(self, call_data: Dict[str, Any], pattern_info: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze the complexity characteristics of a call.
        
        Args:
            call_data: Basic call data
            pattern_info: Pattern definition
            
        Returns:
            Dictionary with complexity analysis
        """
        complexity = {
            "complexity_score": 1,  # Base complexity
            "complexity_factors": []
        }
        
        # Factor in argument count
        arg_count = call_data.get("argument_count", 0)
        if arg_count > 5:
            complexity["complexity_score"] += 2
            complexity["complexity_factors"].append("high_argument_count")
        elif arg_count > 2:
            complexity["complexity_score"] += 1
            complexity["complexity_factors"].append("moderate_argument_count")
        
        # Factor in chaining
        if call_data.get("is_chained", False):
            complexity["complexity_score"] += 1
            complexity["complexity_factors"].append("method_chaining")
        
        # Factor in generics
        if call_data.get("has_generic_types", False):
            complexity["complexity_score"] += 1
            complexity["complexity_factors"].append("generic_types")
        
        # Factor in call type
        call_classification = call_data.get("call_classification", "other")
        if call_classification == "constructor":
            complexity["complexity_score"] += 1
            complexity["complexity_factors"].append("constructor_call")
        
        # Clamp complexity score
        complexity["complexity_score"] = min(complexity["complexity_score"], 10)
        
        return complexity
    
    def _deduplicate_calls(self, calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove duplicate calls from the list.
        
        Args:
            calls: List of call dictionaries
            
        Returns:
            List with duplicates removed
        """
        seen = set()
        unique_calls = []
        
        for call in calls:
            # Create a unique key based on location and text
            key = (
                call.get("file", ""),
                call.get("line", 0),
                call.get("column", 0),
                call.get("text", "")
            )
            
            if key not in seen:
                seen.add(key)
                unique_calls.append(call)
        
        return unique_calls

    def analyze_call_relationships(self, calls: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze relationships between detected calls (nesting, chaining).
        
        Args:
            calls: List of detected call dictionaries
            
        Returns:
            Dictionary with relationship analysis
        """
        relationships = {
            "nested_calls": [],
            "chained_calls": [],
            "complex_patterns": [],
            "call_hierarchy": {},
            "max_nesting_depth": 0,
            "max_chain_length": 0
        }
        
        # Group calls by line for analysis
        calls_by_line = {}
        for call in calls:
            line = call.get("line", 0)
            if line not in calls_by_line:
                calls_by_line[line] = []
            calls_by_line[line].append(call)
        
        # Analyze each line for relationships
        for line, line_calls in calls_by_line.items():
            line_analysis = self._analyze_line_calls(line_calls)
            
            # Update relationships
            relationships["nested_calls"].extend(line_analysis.get("nested", []))
            relationships["chained_calls"].extend(line_analysis.get("chained", []))
            relationships["complex_patterns"].extend(line_analysis.get("complex", []))
            
            # Update maximums
            relationships["max_nesting_depth"] = max(
                relationships["max_nesting_depth"],
                line_analysis.get("max_nesting", 0)
            )
            relationships["max_chain_length"] = max(
                relationships["max_chain_length"],
                line_analysis.get("max_chain_length", 0)
            )
        
        # Build call hierarchy
        relationships["call_hierarchy"] = self._build_call_hierarchy(calls)
        
        return relationships
    
    def _analyze_line_calls(self, calls: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze calls on a single line for relationships.
        
        Args:
            calls: List of calls on the same line
            
        Returns:
            Dictionary with line-specific analysis
        """
        analysis = {
            "nested": [],
            "chained": [],
            "complex": [],
            "max_nesting": 0,
            "max_chain_length": 0
        }
        
        for call in calls:
            call_type = call.get("type", "")
            
            # Analyze based on call type
            if "nested" in call_type:
                nested_info = self._analyze_nested_call(call)
                analysis["nested"].append(nested_info)
                analysis["max_nesting"] = max(analysis["max_nesting"], nested_info.get("depth", 0))
                
            elif "chained" in call_type or "triple_chained" in call_type:
                chained_info = self._analyze_chained_call(call)
                analysis["chained"].append(chained_info)
                analysis["max_chain_length"] = max(analysis["max_chain_length"], chained_info.get("length", 0))
                
            elif "complex" in call_type:
                complex_info = self._analyze_complex_call(call)
                analysis["complex"].append(complex_info)
        
        return analysis
    
    def _analyze_nested_call(self, call: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze a nested call structure.
        
        Args:
            call: Call data dictionary
            
        Returns:
            Dictionary with nested call analysis
        """
        analysis = {
            "call_id": call.get("id"),
            "type": call.get("type"),
            "depth": 1,  # Base depth
            "nested_structure": []
        }
        
        call_type = call.get("type", "")
        
        if call_type == "double_nested_call":
            analysis["depth"] = 3
            analysis["nested_structure"] = [
                {"level": 1, "function": call.get("outer_function", "")},
                {"level": 2, "function": call.get("middle_function", "")},
                {"level": 3, "function": call.get("inner_function", "")}
            ]
        elif call_type == "nested_call":
            analysis["depth"] = 2
            analysis["nested_structure"] = [
                {"level": 1, "function": call.get("outer_function", "")},
                {"level": 2, "function": call.get("inner_function", "")}
            ]
        elif call_type == "nested_chained_call":
            analysis["depth"] = 2
            analysis["nested_structure"] = [
                {"level": 1, "function": call.get("outer_function", "")},
                {"level": 2, "chain": f"{call.get('chained_object', '')}.{call.get('chained_method', '')}"}
            ]
        
        return analysis
    
    def _analyze_chained_call(self, call: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze a chained call structure.
        
        Args:
            call: Call data dictionary
            
        Returns:
            Dictionary with chained call analysis
        """
        analysis = {
            "call_id": call.get("id"),
            "type": call.get("type"),
            "length": 2,  # Base chain length
            "chain_structure": []
        }
        
        call_type = call.get("type", "")
        
        if call_type == "triple_chained_call":
            analysis["length"] = 3
            analysis["chain_structure"] = [
                {"step": 1, "method": call.get("first_method", ""), "args": call.get("first_arguments", "")},
                {"step": 2, "method": call.get("second_method", ""), "args": call.get("second_arguments", "")},
                {"step": 3, "method": call.get("third_method", ""), "args": call.get("third_arguments", "")}
            ]
        elif call_type == "chained_call":
            analysis["length"] = 2
            analysis["chain_structure"] = [
                {"step": 1, "method": call.get("method_name", ""), "args": call.get("arguments", "")},
                {"step": 2, "method": call.get("next_method", ""), "args": call.get("next_arguments", "")}
            ]
        elif call_type == "chained_constructor_call":
            analysis["length"] = 2
            analysis["chain_structure"] = [
                {"step": 1, "constructor": call.get("class_name", ""), "args": call.get("constructor_arguments", "")},
                {"step": 2, "method": call.get("chained_method", ""), "args": call.get("method_arguments", "")}
            ]
        elif call_type == "generic_chained_call":
            analysis["length"] = 2
            analysis["chain_structure"] = [
                {"step": 1, "method": call.get("method_name", ""), "types": call.get("type_parameters", ""), "args": call.get("arguments", "")},
                {"step": 2, "method": call.get("next_method", ""), "args": call.get("next_arguments", "")}
            ]
        
        return analysis
    
    def _analyze_complex_call(self, call: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze a complex call pattern.
        
        Args:
            call: Call data dictionary
            
        Returns:
            Dictionary with complex call analysis
        """
        analysis = {
            "call_id": call.get("id"),
            "type": call.get("type"),
            "complexity_factors": []
        }
        
        call_type = call.get("type", "")
        
        if call_type == "complex_nested_call":
            analysis["complexity_factors"] = [
                "multiple_arguments",
                "nested_call_as_argument",
                "positional_argument_mixing"
            ]
            analysis["structure"] = {
                "outer_function": call.get("outer_function", ""),
                "arguments": [
                    {"type": "simple", "value": call.get("first_argument", "")},
                    {"type": "nested_call", "function": call.get("inner_function", ""), "args": call.get("inner_arguments", "")},
                    {"type": "simple", "value": call.get("last_argument", "")}
                ]
            }
        
        return analysis
    
    def _build_call_hierarchy(self, calls: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Build a hierarchical representation of call relationships.
        
        Args:
            calls: List of all detected calls
            
        Returns:
            Dictionary representing call hierarchy
        """
        hierarchy = {
            "root_calls": [],
            "nested_structures": {},
            "chain_structures": {}
        }
        
        # Identify root calls (not nested within others)
        nested_call_ids = set()
        
        for call in calls:
            call_type = call.get("type", "")
            call_id = call.get("id", "")
            
            # Track nested calls
            if "nested" in call_type:
                nested_call_ids.add(call_id)
                hierarchy["nested_structures"][call_id] = self._extract_hierarchy_info(call)
            
            # Track chained calls
            elif "chained" in call_type:
                hierarchy["chain_structures"][call_id] = self._extract_hierarchy_info(call)
        
        # Identify root calls
        for call in calls:
            call_id = call.get("id", "")
            if call_id not in nested_call_ids:
                hierarchy["root_calls"].append({
                    "id": call_id,
                    "type": call.get("type", ""),
                    "function": call.get("function_name", call.get("method_name", "")),
                    "line": call.get("line", 0)
                })
        
        return hierarchy
    
    def _extract_hierarchy_info(self, call: Dict[str, Any]) -> Dict[str, Any]:
        """Extract hierarchical information from a call.
        
        Args:
            call: Call data dictionary
            
        Returns:
            Dictionary with hierarchy information
        """
        info = {
            "type": call.get("type", ""),
            "line": call.get("line", 0),
            "column": call.get("column", 0),
            "components": []
        }
        
        # Extract components based on call type
        call_type = call.get("type", "")
        
        if "nested" in call_type:
            if "outer_function" in call:
                info["components"].append({"type": "outer", "name": call.get("outer_function", "")})
            if "middle_function" in call:
                info["components"].append({"type": "middle", "name": call.get("middle_function", "")})
            if "inner_function" in call:
                info["components"].append({"type": "inner", "name": call.get("inner_function", "")})
        
        elif "chained" in call_type:
            if "method_name" in call:
                info["components"].append({"type": "first", "name": call.get("method_name", "")})
            if "next_method" in call:
                info["components"].append({"type": "next", "name": call.get("next_method", "")})
            if "third_method" in call:
                info["components"].append({"type": "third", "name": call.get("third_method", "")})
        
        return info
    
    def detect_call_patterns(self, calls: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Detect common call patterns in a list of calls.
        
        Args:
            calls: List of detected call dictionaries
            
        Returns:
            Dictionary with pattern analysis
        """
        patterns = {
            "builder_patterns": [],
            "fluent_interfaces": [],
            "callback_patterns": [],
            "recursive_patterns": [],
            "decorator_patterns": []
        }
        
        # Analyze for builder patterns (long chains)
        for call in calls:
            if self._is_builder_pattern(call):
                patterns["builder_patterns"].append(call.get("id"))
        
        # Analyze for fluent interfaces (method chaining with return of self)
        chained_calls = [call for call in calls if "chained" in call.get("type", "")]
        for call in chained_calls:
            if self._is_fluent_interface(call):
                patterns["fluent_interfaces"].append(call.get("id"))
        
        # Analyze for callback patterns (function passed as argument)
        for call in calls:
            if self._is_callback_pattern(call):
                patterns["callback_patterns"].append(call.get("id"))
        
        # Analyze for recursive patterns
        for call in calls:
            if self._is_recursive_pattern(call, calls):
                patterns["recursive_patterns"].append(call.get("id"))
        
        return patterns
    
    def _is_builder_pattern(self, call: Dict[str, Any]) -> bool:
        """Check if a call represents a builder pattern.
        
        Args:
            call: Call data dictionary
            
        Returns:
            True if this appears to be a builder pattern
        """
        call_type = call.get("type", "")
        
        # Triple chained calls are likely builder patterns
        if call_type == "triple_chained_call":
            return True
        
        # Long method chains with builder-like method names
        if "chained" in call_type:
            method_names = []
            if "method_name" in call:
                method_names.append(call.get("method_name", "").lower())
            if "next_method" in call:
                method_names.append(call.get("next_method", "").lower())
            if "third_method" in call:
                method_names.append(call.get("third_method", "").lower())
            
            builder_keywords = ["set", "with", "add", "build", "create", "configure", "option"]
            return any(keyword in method for method in method_names for keyword in builder_keywords)
        
        return False
    
    def _is_fluent_interface(self, call: Dict[str, Any]) -> bool:
        """Check if a call represents a fluent interface pattern.
        
        Args:
            call: Call data dictionary
            
        Returns:
            True if this appears to be a fluent interface
        """
        call_type = call.get("type", "")
        
        # Chained calls that are likely fluent
        if "chained" in call_type:
            # Check for fluent method names
            method_names = []
            if "method_name" in call:
                method_names.append(call.get("method_name", "").lower())
            if "next_method" in call:
                method_names.append(call.get("next_method", "").lower())
            
            fluent_keywords = ["then", "and", "or", "also", "plus", "chain", "pipe"]
            return any(keyword in method for method in method_names for keyword in fluent_keywords)
        
        return False
    
    def _is_callback_pattern(self, call: Dict[str, Any]) -> bool:
        """Check if a call represents a callback pattern.
        
        Args:
            call: Call data dictionary
            
        Returns:
            True if this appears to use callbacks
        """
        args = call.get("arguments", "")
        
        # Look for function-like arguments
        callback_indicators = ["=>", "function", "lambda", "def ", "async ", "await"]
        return any(indicator in args for indicator in callback_indicators)
    
    def _is_recursive_pattern(self, call: Dict[str, Any], all_calls: List[Dict[str, Any]]) -> bool:
        """Check if a call represents a recursive pattern.
        
        Args:
            call: Call data dictionary
            all_calls: All detected calls for context
            
        Returns:
            True if this appears to be recursive
        """
        function_name = call.get("function_name", call.get("method_name", ""))
        if not function_name:
            return False
        
        # Look for calls to the same function name
        same_name_calls = [
            c for c in all_calls 
            if c.get("function_name", c.get("method_name", "")) == function_name
            and c.get("id") != call.get("id")
        ]
        
        return len(same_name_calls) > 0

    def _extract_call_site_info(self, match: Dict[str, Any], call_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract detailed call site information.
        
        Args:
            match: AST-grep match result
            call_data: Basic call data
            
        Returns:
            Dictionary with call site information
        """
        site_info = {
            "position": {
                "start": {
                    "line": call_data.get("line", 0),
                    "column": call_data.get("column", 0)
                },
                "end": {
                    "line": call_data.get("end_line", 0),
                    "column": call_data.get("end_column", 0)
                }
            },
            "text_metrics": {},
            "context_clues": {}
        }
        
        # Analyze text metrics
        call_text = call_data.get("text", "")
        site_info["text_metrics"] = {
            "length": len(call_text),
            "line_span": call_data.get("end_line", 0) - call_data.get("line", 0) + 1,
            "is_multiline": call_data.get("end_line", 0) > call_data.get("line", 0),
            "character_span": call_data.get("end_column", 0) - call_data.get("column", 0)
        }
        
        # Extract context clues from call text
        site_info["context_clues"] = self._analyze_call_text_patterns(call_text)
        
        # Extract file context
        file_path = call_data.get("file", "")
        if file_path:
            site_info["file_context"] = {
                "filename": Path(file_path).name,
                "extension": Path(file_path).suffix,
                "directory": str(Path(file_path).parent),
                "is_test_file": self._is_test_file(file_path),
                "is_config_file": self._is_config_file(file_path)
            }
        
        return {"call_site_info": site_info}
    
    def _analyze_call_text_patterns(self, call_text: str) -> Dict[str, Any]:
        """Analyze patterns in the call text for context clues.
        
        Args:
            call_text: Raw call text
            
        Returns:
            Dictionary with pattern analysis
        """
        patterns = {
            "has_async_await": "await " in call_text or "async " in call_text,
            "has_promise_chain": ".then(" in call_text or ".catch(" in call_text,
            "has_callback": "=>" in call_text or "function(" in call_text,
            "has_destructuring": "{" in call_text and "}" in call_text,
            "has_spread_operator": "..." in call_text,
            "has_optional_chaining": "?." in call_text,
            "has_nullish_coalescing": "??" in call_text,
            "has_template_literal": "`" in call_text,
            "has_regex": "new RegExp(" in call_text or "/.*/" in call_text,
            "has_error_handling": "try" in call_text or "catch" in call_text,
            "has_type_assertion": " as " in call_text or "<" in call_text and ">" in call_text
        }
        return patterns
    
    def _is_test_file(self, file_path: str) -> bool:
        """Check if the file appears to be a test file.
        
        Args:
            file_path: Path to the file
            
        Returns:
            True if this appears to be a test file
        """
        test_indicators = ["test", "spec", "__tests__", "tests"]
        file_path_lower = file_path.lower()
        return any(indicator in file_path_lower for indicator in test_indicators)
    
    def _is_config_file(self, file_path: str) -> bool:
        """Check if the file appears to be a configuration file.
        
        Args:
            file_path: Path to the file
            
        Returns:
            True if this appears to be a config file
        """
        config_indicators = ["config", "settings", "env", ".rc", "package.json", "tsconfig", "webpack"]
        file_path_lower = file_path.lower()
        return any(indicator in file_path_lower for indicator in config_indicators)
    
    def _analyze_argument_patterns(self, call_data: Dict[str, Any], meta_vars: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze argument patterns for sophisticated argument analysis.
        
        Args:
            call_data: Basic call data
            meta_vars: Meta-variables from the match
            
        Returns:
            Dictionary with argument analysis
        """
        analysis = {
            "argument_analysis": {
                "count": 0,
                "types": [],
                "patterns": [],
                "complexity_indicators": []
            }
        }
        
        # Extract argument text
        args_text = ""
        for key, value in call_data.items():
            if "argument" in key.lower() and isinstance(value, str):
                if args_text:
                    args_text += ", " + value
                else:
                    args_text = value
        
        if not args_text:
            # Try extracting from meta-variables
            for meta_var, data in meta_vars.items():
                if "ARGS" in meta_var:
                    args_text = data.get("text", "")
                    break
        
        if args_text:
            analysis["argument_analysis"] = self._detailed_argument_analysis(args_text)
        
        return analysis
    
    def _detailed_argument_analysis(self, args_text: str) -> Dict[str, Any]:
        """Perform detailed analysis of function arguments.
        
        Args:
            args_text: Raw arguments text
            
        Returns:
            Dictionary with detailed argument analysis
        """
        if not args_text or not args_text.strip():
            return {
                "count": 0,
                "types": [],
                "patterns": [],
                "complexity_indicators": []
            }
        
        args_text = args_text.strip()
        
        # Count arguments more accurately
        arg_count = self._count_arguments(args_text)
        
        # Detect argument types and patterns
        arg_types = self._detect_argument_types(args_text)
        arg_patterns = self._detect_argument_patterns(args_text)
        complexity_indicators = self._detect_argument_complexity(args_text)
        
        return {
            "count": arg_count,
            "types": arg_types,
            "patterns": arg_patterns,
            "complexity_indicators": complexity_indicators,
            "raw_text": args_text,
            "is_empty": arg_count == 0,
            "has_spread": "..." in args_text,
            "has_destructuring": "{" in args_text or "[" in args_text,
            "has_callbacks": "=>" in args_text or "function" in args_text
        }
    
    def _detect_argument_types(self, args_text: str) -> List[str]:
        """Detect types of arguments being passed.
        
        Args:
            args_text: Arguments text
            
        Returns:
            List of detected argument types
        """
        types = []
        
        # Simple pattern detection
        if '"' in args_text or "'" in args_text or '`' in args_text:
            types.append("string")
        if any(num in args_text for num in "0123456789"):
            types.append("number")
        if "true" in args_text or "false" in args_text:
            types.append("boolean")
        if "[" in args_text and "]" in args_text:
            types.append("array")
        if "{" in args_text and "}" in args_text:
            types.append("object")
        if "null" in args_text:
            types.append("null")
        if "undefined" in args_text:
            types.append("undefined")
        if "new " in args_text:
            types.append("constructor")
        if "=>" in args_text or "function" in args_text:
            types.append("function")
        if "this." in args_text:
            types.append("this_reference")
        
        return list(set(types))  # Remove duplicates
    
    def _detect_argument_patterns(self, args_text: str) -> List[str]:
        """Detect common argument patterns.
        
        Args:
            args_text: Arguments text
            
        Returns:
            List of detected patterns
        """
        patterns = []
        
        if "..." in args_text:
            patterns.append("spread_operator")
        if "{" in args_text and "}" in args_text and ":" in args_text:
            patterns.append("object_destructuring")
        if "[" in args_text and "]" in args_text:
            patterns.append("array_destructuring")
        if "=" in args_text:
            patterns.append("default_parameters")
        if "await " in args_text:
            patterns.append("async_await")
        if ".then(" in args_text:
            patterns.append("promise_chain")
        if "?." in args_text:
            patterns.append("optional_chaining")
        if "??" in args_text:
            patterns.append("nullish_coalescing")
        if any(op in args_text for op in ["&&", "||", "!"]):
            patterns.append("logical_operators")
        if any(op in args_text for op in ["===", "!==", "==", "!="]):
            patterns.append("comparison_operators")
        
        return patterns
    
    def _detect_argument_complexity(self, args_text: str) -> List[str]:
        """Detect complexity indicators in arguments.
        
        Args:
            args_text: Arguments text
            
        Returns:
            List of complexity indicators
        """
        indicators = []
        
        # Nesting level indicators
        paren_depth = args_text.count("(") - args_text.count(")")
        bracket_depth = args_text.count("[") - args_text.count("]")
        brace_depth = args_text.count("{") - args_text.count("}")
        
        if abs(paren_depth) > 2 or abs(bracket_depth) > 2 or abs(brace_depth) > 2:
            indicators.append("high_nesting")
        
        # Length indicators
        if len(args_text) > 100:
            indicators.append("long_arguments")
        if args_text.count(",") > 5:
            indicators.append("many_arguments")
        
        # Complexity patterns
        if args_text.count(".") > 3:
            indicators.append("deep_property_access")
        if "new " in args_text:
            indicators.append("object_instantiation")
        if any(keyword in args_text for keyword in ["if", "for", "while", "switch"]):
            indicators.append("control_flow")
        
        return indicators
    
    def _extract_scope_information(self, match: Dict[str, Any], call_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract scope and context information about the call.
        
        Args:
            match: AST-grep match result
            call_data: Basic call data
            
        Returns:
            Dictionary with scope information
        """
        scope_info = {
            "scope_analysis": {
                "estimated_scope": "unknown",
                "scope_indicators": [],
                "context_clues": []
            }
        }
        
        call_text = call_data.get("text", "")
        call_type = call_data.get("type", "")
        
        # Analyze scope based on call patterns
        scope_indicators = []
        context_clues = []
        
        # Global scope indicators
        if call_type == "function_call" and "." not in call_text:
            scope_indicators.append("likely_global")
        
        # Module scope indicators
        if "." in call_text and not call_text.startswith("this."):
            scope_indicators.append("module_or_static")
        
        # Instance scope indicators
        if "this." in call_text:
            scope_indicators.append("instance_method")
            context_clues.append("class_context")
        
        # Static scope indicators
        if call_type == "static_call" or call_type == "namespace_call":
            scope_indicators.append("static_context")
        
        # Constructor scope indicators
        if call_type == "constructor_call":
            scope_indicators.append("constructor_context")
            context_clues.append("object_creation")
        
        # Async context indicators
        if "await " in call_text:
            context_clues.append("async_context")
        
        # Error handling context
        file_path = call_data.get("file", "")
        if self._is_test_file(file_path):
            context_clues.append("test_context")
        
        # Estimate primary scope
        estimated_scope = "unknown"
        if "instance_method" in scope_indicators:
            estimated_scope = "instance"
        elif "static_context" in scope_indicators:
            estimated_scope = "static"
        elif "likely_global" in scope_indicators:
            estimated_scope = "global"
        elif "module_or_static" in scope_indicators:
            estimated_scope = "module"
        
        scope_info["scope_analysis"] = {
            "estimated_scope": estimated_scope,
            "scope_indicators": scope_indicators,
            "context_clues": context_clues
        }
        
        return scope_info
    
    def _analyze_call_security(self, call_data: Dict[str, Any], pattern_info: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze security implications of the call.
        
        Args:
            call_data: Call data
            pattern_info: Pattern information
            
        Returns:
            Dictionary with security analysis
        """
        security_analysis = {
            "security_analysis": {
                "risk_level": "low",
                "security_concerns": [],
                "safety_indicators": []
            }
        }
        
        call_text = call_data.get("text", "")
        function_name = call_data.get("function_name", call_data.get("method_name", ""))
        
        # High-risk function patterns
        high_risk_patterns = [
            "eval", "setTimeout", "setInterval", "innerHTML", "outerHTML",
            "document.write", "execScript", "Function", "script"
        ]
        
        # Medium-risk function patterns
        medium_risk_patterns = [
            "fetch", "XMLHttpRequest", "import", "require", "open",
            "location", "href", "src", "action"
        ]
        
        # Low-risk but notable patterns
        notable_patterns = [
            "JSON.parse", "parseInt", "parseFloat", "decodeURI", "unescape"
        ]
        
        security_concerns = []
        risk_level = "low"
        
        # Check for high-risk patterns
        for pattern in high_risk_patterns:
            if pattern.lower() in call_text.lower():
                security_concerns.append(f"high_risk_function: {pattern}")
                risk_level = "high"
        
        # Check for medium-risk patterns
        if risk_level != "high":
            for pattern in medium_risk_patterns:
                if pattern.lower() in call_text.lower():
                    security_concerns.append(f"medium_risk_function: {pattern}")
                    risk_level = "medium"
        
        # Check for notable patterns
        for pattern in notable_patterns:
            if pattern.lower() in call_text.lower():
                security_concerns.append(f"parsing_function: {pattern}")
        
        # Additional security checks
        if "document." in call_text:
            security_concerns.append("dom_manipulation")
        if "window." in call_text:
            security_concerns.append("global_object_access")
        if any(arg in call_text for arg in ["user", "input", "param", "query"]):
            security_concerns.append("potential_user_input")
        
        # Safety indicators
        safety_indicators = []
        if "try" in call_text or "catch" in call_text:
            safety_indicators.append("error_handling")
        if "validate" in function_name.lower() or "sanitize" in function_name.lower():
            safety_indicators.append("validation_function")
        
        security_analysis["security_analysis"] = {
            "risk_level": risk_level,
            "security_concerns": security_concerns,
            "safety_indicators": safety_indicators
        }
        
        return security_analysis
    
    def _extract_performance_indicators(self, call_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract performance-related indicators from the call.
        
        Args:
            call_data: Call data
            
        Returns:
            Dictionary with performance indicators
        """
        performance_info = {
            "performance_indicators": {
                "async_indicators": [],
                "optimization_hints": [],
                "potential_bottlenecks": []
            }
        }
        
        call_text = call_data.get("text", "")
        function_name = call_data.get("function_name", call_data.get("method_name", ""))
        arg_count = call_data.get("argument_count", 0)
        
        async_indicators = []
        optimization_hints = []
        potential_bottlenecks = []
        
        # Async operation indicators
        if "await " in call_text:
            async_indicators.append("async_await")
        if ".then(" in call_text:
            async_indicators.append("promise_chain")
        if "setTimeout" in call_text or "setInterval" in call_text:
            async_indicators.append("timer_function")
        if "fetch" in call_text or "XMLHttpRequest" in call_text:
            async_indicators.append("network_request")
        
        # Performance optimization hints
        if "memo" in function_name.lower() or "cache" in function_name.lower():
            optimization_hints.append("caching_function")
        if "lazy" in function_name.lower() or "defer" in function_name.lower():
            optimization_hints.append("lazy_loading")
        if "batch" in function_name.lower() or "bulk" in function_name.lower():
            optimization_hints.append("batch_operation")
        
        # Potential bottleneck indicators
        if arg_count > 10:
            potential_bottlenecks.append("many_arguments")
        if "loop" in call_text or "forEach" in call_text or "map" in call_text:
            potential_bottlenecks.append("iteration_function")
        if "sort" in function_name.lower():
            potential_bottlenecks.append("sorting_operation")
        if "search" in function_name.lower() or "find" in function_name.lower():
            potential_bottlenecks.append("search_operation")
        if "parse" in function_name.lower() or "stringify" in function_name.lower():
            potential_bottlenecks.append("serialization_operation")
        
        performance_info["performance_indicators"] = {
            "async_indicators": async_indicators,
            "optimization_hints": optimization_hints,
            "potential_bottlenecks": potential_bottlenecks
        }
        
        return performance_info

async def create_call_detector(**kwargs) -> CallDetector:
    """Create and initialize a call detector instance.
    
    Args:
        **kwargs: Optional arguments to pass to CallDetector constructor
        
    Returns:
        Configured CallDetector instance
    """
    detector = CallDetector(**kwargs)
    return detector


class CallGraphGenerator:
    """
    Call graph generation engine that integrates function and call detectors
    to build relationship graphs across multiple files and languages.
    """
    
    def __init__(self, executor: Optional['ASTGrepExecutor'] = None):
        """Initialize the call graph generator.
        
        Args:
            executor: Optional AST-grep executor instance
        """
        self.executor = executor
        self.function_detector: Optional[FunctionDetector] = None
        self.call_detector: Optional[CallDetector] = None
        self.language_manager = get_language_manager()
        self.logger = logging.getLogger(__name__)
        
    async def initialize(self) -> None:
        """Initialize the detectors and executor."""
        if self.executor is None:
            self.executor = await create_ast_grep_executor()
        
        if self.function_detector is None:
            self.function_detector = await create_function_detector(executor=self.executor)
        
        if self.call_detector is None:
            self.call_detector = await create_call_detector(executor=self.executor)
    
    async def generate_call_graph(
        self,
        paths: List[Union[str, Path]],
        languages: Optional[List[str]] = None,
        include_builtin_calls: bool = False,
        include_external_calls: bool = True,
        max_depth: Optional[int] = None,
        filter_patterns: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Generate a comprehensive call graph for the specified paths.
        
        Args:
            paths: List of file paths or directories to analyze
            languages: Optional list of languages to focus on
            include_builtin_calls: Whether to include builtin/standard library calls
            include_external_calls: Whether to include external library calls
            max_depth: Maximum call depth to analyze
            filter_patterns: Optional regex patterns to filter function names
            
        Returns:
            Call graph data structure with nodes, edges, and metadata
        """
        await self.initialize()
        
        # Step 1: Detect all functions across the codebase
        self.logger.info("Detecting functions across codebase...")
        functions_data = await self._detect_all_functions(paths, languages)
        
        # Step 2: Detect all function calls
        self.logger.info("Detecting function calls...")
        calls_data = await self._detect_all_calls(paths, languages)
        
        # Step 3: Build the call graph
        self.logger.info("Building call graph...")
        call_graph = await self._build_call_graph(
            functions_data, 
            calls_data,
            include_builtin_calls=include_builtin_calls,
            include_external_calls=include_external_calls,
            max_depth=max_depth,
            filter_patterns=filter_patterns
        )
        
        # Step 4: Validate against JSON schema
        self.logger.info("Validating call graph schema...")
        validation_result = validate_call_graph_data(call_graph)
        
        if not validation_result.get('valid', False):
            self.logger.warning(f"Call graph schema validation failed: {validation_result.get('message', 'Unknown validation error')}")
            # Add validation errors to the call graph for debugging
            if 'errors' not in call_graph:
                call_graph['errors'] = []
            call_graph['errors'].extend([
                {
                    'error': f"Schema validation error: {error.get('message', 'Unknown error')}",
                    'path': error.get('path', [])
                }
                for error in validation_result.get('errors', [])
            ])
        else:
            self.logger.info("Call graph schema validation successful")
        
        return call_graph
    
    async def _detect_all_functions(
        self, 
        paths: List[Union[str, Path]], 
        languages: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Detect all functions across the specified paths.
        
        Args:
            paths: List of paths to analyze
            languages: Optional list of languages to focus on
            
        Returns:
            Aggregated function detection results
        """
        all_functions = []
        file_count = 0
        errors = []
        
        for path in paths:
            path_obj = Path(path)
            
            try:
                if path_obj.is_file():
                    # Single file analysis
                    lang = languages[0] if languages else None
                    result = await self.function_detector.detect_functions(
                        path_obj, language=lang, include_metadata=True
                    )
                    
                    if result.get('success', False):
                        functions = result.get('data', {}).get('functions', [])
                        # Add source file information
                        for func in functions:
                            func['source_file'] = str(path_obj)
                            func['source_file_relative'] = str(path_obj.name)
                        all_functions.extend(functions)
                        file_count += 1
                    else:
                        errors.append({
                            'file': str(path_obj),
                            'error': result.get('error', 'Unknown error')
                        })
                
                elif path_obj.is_dir():
                    # Directory analysis
                    for lang in (languages or [None]):
                        result = await self.function_detector.detect_functions_in_directory(
                            path_obj, language=lang, recursive=True
                        )
                        
                        if result.get('success', False):
                            data = result.get('data', {})
                            functions = data.get('functions', [])
                            all_functions.extend(functions)
                            file_count += data.get('files_processed', 0)
                            errors.extend(data.get('errors', []))
                        else:
                            errors.append({
                                'path': str(path_obj),
                                'language': lang,
                                'error': result.get('error', 'Unknown error')
                            })
                            
            except Exception as e:
                self.logger.error(f"Error processing path {path}: {e}")
                errors.append({
                    'path': str(path),
                    'error': str(e)
                })
        
        return {
            'functions': all_functions,
            'files_processed': file_count,
            'total_functions': len(all_functions),
            'errors': errors,
            'summary': self._create_function_summary(all_functions)
        }
    
    async def _detect_all_calls(
        self,
        paths: List[Union[str, Path]],
        languages: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Detect all function calls across the specified paths.
        
        Args:
            paths: List of paths to analyze
            languages: Optional list of languages to focus on
            
        Returns:
            Aggregated call detection results
        """
        all_calls = []
        file_count = 0
        errors = []
        
        for path in paths:
            path_obj = Path(path)
            
            try:
                if path_obj.is_file():
                    # Single file analysis
                    lang = languages[0] if languages else None
                    result = await self.call_detector.detect_calls(
                        path_obj, language=lang, include_metadata=True
                    )
                    
                    if result.get('success', False):
                        calls = result.get('data', {}).get('calls', [])
                        # Add source file information
                        for call in calls:
                            call['source_file'] = str(path_obj)
                            call['source_file_relative'] = str(path_obj.name)
                        all_calls.extend(calls)
                        file_count += 1
                    else:
                        errors.append({
                            'file': str(path_obj),
                            'error': result.get('error', 'Unknown error')
                        })
                
                elif path_obj.is_dir():
                    # Directory analysis
                    for lang in (languages or [None]):
                        result = await self.call_detector.detect_calls_in_directory(
                            path_obj, language=lang, recursive=True
                        )
                        
                        if result.get('success', False):
                            data = result.get('data', {})
                            calls = data.get('calls', [])
                            all_calls.extend(calls)
                            file_count += data.get('files_processed', 0)
                            errors.extend(data.get('errors', []))
                        else:
                            errors.append({
                                'path': str(path_obj),
                                'language': lang,
                                'error': result.get('error', 'Unknown error')
                            })
                            
            except Exception as e:
                self.logger.error(f"Error processing path {path}: {e}")
                errors.append({
                    'path': str(path),
                    'error': str(e)
                })
        
        return {
            'calls': all_calls,
            'files_processed': file_count,
            'total_calls': len(all_calls),
            'errors': errors,
            'summary': self._create_call_summary(all_calls)
        }
    
    async def _build_call_graph(
        self,
        functions_data: Dict[str, Any],
        calls_data: Dict[str, Any],
        include_builtin_calls: bool = False,
        include_external_calls: bool = True,
        max_depth: Optional[int] = None,
        filter_patterns: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Build the call graph from function and call data.
        
        Args:
            functions_data: Function detection results
            calls_data: Call detection results
            include_builtin_calls: Whether to include builtin calls
            include_external_calls: Whether to include external calls
            max_depth: Maximum call depth
            filter_patterns: Function name filter patterns
            
        Returns:
            Complete call graph structure
        """
        functions = functions_data.get('functions', [])
        calls = calls_data.get('calls', [])
        
        # Create function index for fast lookup
        function_index = self._create_function_index(functions, filter_patterns)
        
        # Filter calls based on configuration
        filtered_calls = self._filter_calls(
            calls, 
            include_builtin_calls=include_builtin_calls,
            include_external_calls=include_external_calls,
            filter_patterns=filter_patterns
        )
        
        # Build graph nodes (functions)
        nodes = self._build_graph_nodes(function_index)
        
        # Build graph edges (call relationships)
        edges = self._build_graph_edges(filtered_calls, function_index)
        
        # Calculate graph metrics
        metrics = self._calculate_graph_metrics(nodes, edges, max_depth)
        
        # Build call graph structure
        call_graph = {
            'metadata': {
                'generation_time': datetime.now(timezone.utc).isoformat(),
                'total_functions': len(functions),
                'total_calls': len(calls),
                'filtered_functions': len(nodes),
                'filtered_calls': len(filtered_calls),
                'total_edges': len(edges),
                'include_builtin_calls': include_builtin_calls,
                'include_external_calls': include_external_calls,
                'max_depth': max_depth,
                'filter_patterns': filter_patterns
            },
            'nodes': nodes,
            'edges': edges,
            'metrics': metrics,
            'statistics': {
                'functions_by_language': self._group_by_language(functions),
                'calls_by_type': self._group_calls_by_type(filtered_calls),
                'complexity_distribution': self._analyze_complexity_distribution(functions),
                'file_dependencies': self._analyze_file_dependencies(edges)
            },
            'errors': functions_data.get('errors', []) + calls_data.get('errors', [])
        }
        
        return call_graph
    
    def _create_function_index(
        self, 
        functions: List[Dict[str, Any]], 
        filter_patterns: Optional[List[str]] = None
    ) -> Dict[str, Dict[str, Any]]:
        """Create an index for fast function lookup.
        
        Args:
            functions: List of detected functions
            filter_patterns: Optional regex patterns to filter function names
            
        Returns:
            Function index keyed by function identifier
        """
        function_index = {}
        filter_regexes = []
        
        if filter_patterns:
            filter_regexes = [re.compile(pattern) for pattern in filter_patterns]
        
        for func in functions:
            func_name = func.get('name', '')
            
            # Apply filtering if patterns are provided
            if filter_regexes:
                if not any(regex.search(func_name) for regex in filter_regexes):
                    continue
            
            # Create unique identifier
            source_file = func.get('source_file', '')
            func_id = self._create_function_identifier(func, source_file)
            
            # Store in index with additional metadata
            function_index[func_id] = {
                **func,
                'id': func_id,
                'qualified_name': self._create_qualified_name(func),
                'module_path': source_file,
                'namespace': self._extract_namespace(func, source_file)
            }
        
        return function_index
    
    def _filter_calls(
        self,
        calls: List[Dict[str, Any]],
        include_builtin_calls: bool = False,
        include_external_calls: bool = True,
        filter_patterns: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """Filter calls based on configuration.
        
        Args:
            calls: List of detected calls
            include_builtin_calls: Whether to include builtin calls
            include_external_calls: Whether to include external calls
            filter_patterns: Function name filter patterns
            
        Returns:
            Filtered list of calls
        """
        filtered_calls = []
        filter_regexes = []
        
        if filter_patterns:
            filter_regexes = [re.compile(pattern) for pattern in filter_patterns]
        
        for call in calls:
            call_name = call.get('function_name', '')
            
            # Apply name filtering
            if filter_regexes:
                if not any(regex.search(call_name) for regex in filter_regexes):
                    continue
            
            # Check if it's a builtin call
            if not include_builtin_calls and self._is_builtin_call(call):
                continue
            
            # Check if it's an external call
            if not include_external_calls and self._is_external_call(call):
                continue
            
            filtered_calls.append(call)
        
        return filtered_calls
    
    def _build_graph_nodes(self, function_index: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Build graph nodes from function index.
        
        Args:
            function_index: Indexed functions
            
        Returns:
            List of graph nodes
        """
        nodes = []
        
        for func_id, func_data in function_index.items():
            node = {
                'id': func_id,
                'type': 'function',
                'name': func_data.get('name', ''),
                'qualified_name': func_data.get('qualified_name', ''),
                'signature': func_data.get('signature', ''),
                'module': func_data.get('module_path', ''),
                'namespace': func_data.get('namespace', ''),
                'language': func_data.get('language', ''),
                'function_type': func_data.get('function_type', ''),
                'access_modifier': func_data.get('access_modifier', ''),
                'is_async': func_data.get('is_async', False),
                'is_static': func_data.get('is_static', False),
                'is_constructor': func_data.get('is_constructor', False),
                'line_number': func_data.get('start_line', 0),
                'complexity': func_data.get('complexity', {}).get('cyclomatic_complexity', 1),
                'parameters': func_data.get('parameters', []),
                'return_type': func_data.get('return_type', ''),
                'documentation': func_data.get('documentation', ''),
                'metadata': {
                    'file_path': func_data.get('source_file', ''),
                    'start_line': func_data.get('start_line', 0),
                    'end_line': func_data.get('end_line', 0),
                    'pattern_type': func_data.get('pattern_type', ''),
                    'scope': func_data.get('scope', ''),
                    'decorators': func_data.get('decorators', []),
                    'annotations': func_data.get('annotations', [])
                }
            }
            nodes.append(node)
        
        return nodes
    
    def _build_graph_edges(
        self, 
        calls: List[Dict[str, Any]], 
        function_index: Dict[str, Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Build graph edges from call relationships.
        
        Args:
            calls: Filtered calls list
            function_index: Indexed functions
            
        Returns:
            List of graph edges
        """
        edges = []
        edge_id_counter = 0
        
        for call in calls:
            # Find caller function
            caller_id = self._find_caller_function(call, function_index)
            
            # Find callee function(s)
            callee_candidates = self._find_callee_functions(call, function_index)
            
            # Create edges for each caller-callee relationship
            for callee_id in callee_candidates:
                edge = {
                    'id': f"edge_{edge_id_counter}",
                    'source': caller_id,
                    'target': callee_id,
                    'type': 'calls',
                    'call_type': call.get('call_type', 'function_call'),
                    'line_number': call.get('start_line', 0),
                    'column': call.get('start_column', 0),
                    'arguments_count': call.get('arguments_count', 0),
                    'is_conditional': call.get('complexity', {}).get('is_conditional', False),
                    'is_in_loop': call.get('complexity', {}).get('is_in_loop', False),
                    'confidence': self._calculate_call_confidence(call, callee_id, function_index),
                    'metadata': {
                        'source_file': call.get('source_file', ''),
                        'call_text': call.get('text', ''),
                        'arguments': call.get('arguments', []),
                        'context': call.get('context', {}),
                        'security_risk': call.get('security', {}).get('risk_level', 'low'),
                        'performance_impact': call.get('performance', {}).get('bottleneck_risk', 'low')
                    }
                }
                edges.append(edge)
                edge_id_counter += 1
        
        return edges
    
    def _create_function_identifier(self, func: Dict[str, Any], source_file: str) -> str:
        """Create a unique identifier for a function.
        
        Args:
            func: Function data
            source_file: Source file path
            
        Returns:
            Unique function identifier
        """
        name = func.get('name', 'unknown')
        signature = func.get('signature', '')
        line_num = func.get('start_line', 0)
        
        # Use relative path for better portability
        file_path = Path(source_file).name if source_file else 'unknown'
        
        # Create deterministic identifier
        if signature:
            return f"{file_path}::{name}::{signature}::{line_num}"
        else:
            return f"{file_path}::{name}::{line_num}"
    
    def _create_qualified_name(self, func: Dict[str, Any]) -> str:
        """Create a qualified name for a function.
        
        Args:
            func: Function data
            
        Returns:
            Qualified function name
        """
        name = func.get('name', '')
        scope = func.get('scope', '')
        namespace = func.get('namespace', '')
        
        parts = [part for part in [namespace, scope, name] if part]
        return '.'.join(parts) if parts else name
    
    def _extract_namespace(self, func: Dict[str, Any], source_file: str) -> str:
        """Extract namespace information for a function.
        
        Args:
            func: Function data
            source_file: Source file path
            
        Returns:
            Function namespace
        """
        # Use module/class information if available
        if 'class_name' in func:
            return func['class_name']
        elif 'module' in func:
            return func['module']
        else:
            # Use file-based namespace
            return Path(source_file).stem if source_file else ''
    
    def _is_builtin_call(self, call: Dict[str, Any]) -> bool:
        """Check if a call is to a builtin function.
        
        Args:
            call: Call data
            
        Returns:
            True if builtin call
        """
        function_name = call.get('function_name', '').lower()
        language = call.get('language', '').lower()
        
        # Language-specific builtin patterns
        builtin_patterns = {
            'python': ['print', 'len', 'str', 'int', 'float', 'list', 'dict', 'set', 'tuple'],
            'javascript': ['console', 'alert', 'parseInt', 'parseFloat', 'isNaN', 'isFinite'],
            'java': ['System.out', 'Math.', 'String.', 'Integer.', 'Double.'],
            'c++': ['std::', 'printf', 'scanf', 'malloc', 'free'],
            'rust': ['println!', 'print!', 'vec!', 'format!', 'panic!']
        }
        
        if language in builtin_patterns:
            return any(pattern in function_name for pattern in builtin_patterns[language])
        
        return False
    
    def _is_external_call(self, call: Dict[str, Any]) -> bool:
        """Check if a call is to an external library function.
        
        Args:
            call: Call data
            
        Returns:
            True if external call
        """
        function_name = call.get('function_name', '')
        
        # Common external library patterns
        external_patterns = [
            'import', 'require', 'from', 'use',  # Import statements
            'axios', 'fetch', 'request',  # HTTP libraries
            'lodash', '_', 'jQuery', '$',  # Utility libraries
            'React', 'Vue', 'Angular',  # Frontend frameworks
            'express', 'fastapi', 'flask',  # Backend frameworks
        ]
        
        return any(pattern in function_name for pattern in external_patterns)
    
    def _find_caller_function(
        self, 
        call: Dict[str, Any], 
        function_index: Dict[str, Dict[str, Any]]
    ) -> Optional[str]:
        """Find the function that contains this call.
        
        Args:
            call: Call data
            function_index: Indexed functions
            
        Returns:
            Caller function ID or None
        """
        call_file = call.get('source_file', '')
        call_line = call.get('start_line', 0)
        
        # Find functions in the same file that could contain this call
        candidates = []
        for func_id, func_data in function_index.items():
            if func_data.get('source_file', '') == call_file:
                func_start = func_data.get('start_line', 0)
                func_end = func_data.get('end_line', 0)
                
                if func_start <= call_line <= func_end:
                    candidates.append((func_id, func_start, func_end))
        
        # Return the most specific (innermost) function
        if candidates:
            # Sort by scope size (smallest scope = most specific)
            candidates.sort(key=lambda x: x[2] - x[1])
            return candidates[0][0]
        
        return None
    
    def _find_callee_functions(
        self, 
        call: Dict[str, Any], 
        function_index: Dict[str, Dict[str, Any]]
    ) -> List[str]:
        """Find possible target functions for this call.
        
        Args:
            call: Call data
            function_index: Indexed functions
            
        Returns:
            List of possible callee function IDs
        """
        call_name = call.get('function_name', '')
        candidates = []
        
        # Direct name matching
        for func_id, func_data in function_index.items():
            func_name = func_data.get('name', '')
            
            if func_name == call_name:
                candidates.append(func_id)
        
        # If no direct match, try partial matching
        if not candidates:
            for func_id, func_data in function_index.items():
                func_name = func_data.get('name', '')
                qualified_name = func_data.get('qualified_name', '')
                
                if (call_name in func_name or 
                    call_name in qualified_name or
                    func_name in call_name):
                    candidates.append(func_id)
        
        return candidates
    
    def _calculate_call_confidence(
        self, 
        call: Dict[str, Any], 
        callee_id: str, 
        function_index: Dict[str, Dict[str, Any]]
    ) -> float:
        """Calculate confidence score for a call relationship.
        
        Args:
            call: Call data
            callee_id: Target function ID
            function_index: Indexed functions
            
        Returns:
            Confidence score between 0 and 1
        """
        confidence = 0.5  # Base confidence
        
        callee = function_index.get(callee_id, {})
        call_name = call.get('function_name', '')
        func_name = callee.get('name', '')
        
        # Exact name match
        if call_name == func_name:
            confidence += 0.3
        
        # Same file bonus
        if call.get('source_file') == callee.get('source_file'):
            confidence += 0.1
        
        # Argument count match
        call_args = call.get('arguments_count', 0)
        func_params = len(callee.get('parameters', []))
        if call_args == func_params:
            confidence += 0.1
        
        return min(confidence, 1.0)
    
    def _calculate_graph_metrics(
        self, 
        nodes: List[Dict[str, Any]], 
        edges: List[Dict[str, Any]], 
        max_depth: Optional[int] = None
    ) -> Dict[str, Any]:
        """Calculate various graph metrics.
        
        Args:
            nodes: Graph nodes
            edges: Graph edges
            max_depth: Maximum depth for analysis
            
        Returns:
            Graph metrics
        """
        # Build adjacency lists
        outgoing = {}  # node_id -> [target_ids]
        incoming = {}  # node_id -> [source_ids]
        
        for node in nodes:
            node_id = node['id']
            outgoing[node_id] = []
            incoming[node_id] = []
        
        for edge in edges:
            source = edge['source']
            target = edge['target']
            if source in outgoing and target in incoming:
                outgoing[source].append(target)
                incoming[target].append(source)
        
        # Calculate metrics
        metrics = {
            'total_nodes': len(nodes),
            'total_edges': len(edges),
            'average_out_degree': sum(len(targets) for targets in outgoing.values()) / len(nodes) if nodes else 0,
            'average_in_degree': sum(len(sources) for sources in incoming.values()) / len(nodes) if nodes else 0,
            'max_out_degree': max(len(targets) for targets in outgoing.values()) if outgoing else 0,
            'max_in_degree': max(len(sources) for sources in incoming.values()) if incoming else 0,
            'isolated_nodes': len([node_id for node_id in outgoing.keys() 
                                 if not outgoing[node_id] and not incoming[node_id]]),
            'strongly_connected_components': self._count_strongly_connected_components(outgoing, incoming),
            'cyclic_dependencies': self._detect_cycles(outgoing),
            'call_depth_analysis': self._analyze_call_depths(outgoing, max_depth)
        }
        
        return metrics
    
    def _count_strongly_connected_components(
        self, 
        outgoing: Dict[str, List[str]], 
        incoming: Dict[str, List[str]]
    ) -> int:
        """Count strongly connected components in the graph.
        
        Args:
            outgoing: Outgoing adjacency list
            incoming: Incoming adjacency list
            
        Returns:
            Number of strongly connected components
        """
        # Simplified SCC detection (Tarjan's algorithm would be more accurate)
        visited = set()
        components = 0
        
        for node_id in outgoing.keys():
            if node_id not in visited:
                # DFS to find reachable nodes
                stack = [node_id]
                component = set()
                
                while stack:
                    current = stack.pop()
                    if current not in visited:
                        visited.add(current)
                        component.add(current)
                        stack.extend(outgoing.get(current, []))
                
                if len(component) > 1:
                    components += 1
        
        return components
    
    def _detect_cycles(self, outgoing: Dict[str, List[str]]) -> List[List[str]]:
        """Detect cycles in the call graph.
        
        Args:
            outgoing: Outgoing adjacency list
            
        Returns:
            List of detected cycles
        """
        cycles = []
        visited = set()
        rec_stack = set()
        path = []
        
        def dfs(node_id: str) -> bool:
            if node_id in rec_stack:
                # Found a cycle
                cycle_start = path.index(node_id)
                cycle = path[cycle_start:] + [node_id]
                cycles.append(cycle)
                return True
            
            if node_id in visited:
                return False
            
            visited.add(node_id)
            rec_stack.add(node_id)
            path.append(node_id)
            
            for neighbor in outgoing.get(node_id, []):
                if dfs(neighbor):
                    break
            
            rec_stack.remove(node_id)
            path.pop()
            return False
        
        for node_id in outgoing.keys():
            if node_id not in visited:
                dfs(node_id)
        
        return cycles
    
    def _analyze_call_depths(
        self, 
        outgoing: Dict[str, List[str]], 
        max_depth: Optional[int] = None
    ) -> Dict[str, Any]:
        """Analyze call depths in the graph.
        
        Args:
            outgoing: Outgoing adjacency list
            max_depth: Maximum depth to analyze
            
        Returns:
            Call depth analysis
        """
        if max_depth is None:
            max_depth = 10
        
        depth_distribution = {}
        max_observed_depth = 0
        
        # Find root nodes (no incoming edges)
        root_nodes = []
        all_targets = set()
        for targets in outgoing.values():
            all_targets.update(targets)
        
        for node_id in outgoing.keys():
            if node_id not in all_targets:
                root_nodes.append(node_id)
        
        # BFS from each root to calculate depths
        for root in root_nodes:
            visited = set()
            queue = [(root, 0)]
            
            while queue:
                node_id, depth = queue.pop(0)
                
                if node_id in visited or depth > max_depth:
                    continue
                
                visited.add(node_id)
                max_observed_depth = max(max_observed_depth, depth)
                
                if depth not in depth_distribution:
                    depth_distribution[depth] = 0
                depth_distribution[depth] += 1
                
                for target in outgoing.get(node_id, []):
                    queue.append((target, depth + 1))
        
        return {
            'max_depth': max_observed_depth,
            'depth_distribution': depth_distribution,
            'root_nodes': len(root_nodes),
            'average_depth': sum(d * c for d, c in depth_distribution.items()) / sum(depth_distribution.values()) if depth_distribution else 0
        }
    
    def _create_function_summary(self, functions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Create a summary of detected functions.
        
        Args:
            functions: List of functions
            
        Returns:
            Function summary statistics
        """
        if not functions:
            return {}
        
        languages = {}
        function_types = {}
        total_complexity = 0
        
        for func in functions:
            lang = func.get('language', 'unknown')
            func_type = func.get('function_type', 'unknown')
            complexity = func.get('complexity', {}).get('cyclomatic_complexity', 1)
            
            languages[lang] = languages.get(lang, 0) + 1
            function_types[func_type] = function_types.get(func_type, 0) + 1
            total_complexity += complexity
        
        return {
            'total_functions': len(functions),
            'languages': languages,
            'function_types': function_types,
            'average_complexity': total_complexity / len(functions),
            'most_common_language': max(languages.items(), key=lambda x: x[1])[0] if languages else None,
            'most_common_type': max(function_types.items(), key=lambda x: x[1])[0] if function_types else None
        }
    
    def _create_call_summary(self, calls: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Create a summary of detected calls.
        
        Args:
            calls: List of calls
            
        Returns:
            Call summary statistics
        """
        if not calls:
            return {}
        
        call_types = {}
        languages = {}
        total_args = 0
        
        for call in calls:
            call_type = call.get('call_type', 'unknown')
            lang = call.get('language', 'unknown')
            args_count = call.get('arguments_count', 0)
            
            call_types[call_type] = call_types.get(call_type, 0) + 1
            languages[lang] = languages.get(lang, 0) + 1
            total_args += args_count
        
        return {
            'total_calls': len(calls),
            'call_types': call_types,
            'languages': languages,
            'average_arguments': total_args / len(calls),
            'most_common_call_type': max(call_types.items(), key=lambda x: x[1])[0] if call_types else None,
            'most_common_language': max(languages.items(), key=lambda x: x[1])[0] if languages else None
        }
    
    def _group_by_language(self, functions: List[Dict[str, Any]]) -> Dict[str, int]:
        """Group functions by programming language.
        
        Args:
            functions: List of functions
            
        Returns:
            Language distribution
        """
        distribution = {}
        for func in functions:
            lang = func.get('language', 'unknown')
            distribution[lang] = distribution.get(lang, 0) + 1
        return distribution
    
    def _group_calls_by_type(self, calls: List[Dict[str, Any]]) -> Dict[str, int]:
        """Group calls by call type.
        
        Args:
            calls: List of calls
            
        Returns:
            Call type distribution
        """
        distribution = {}
        for call in calls:
            call_type = call.get('call_type', 'unknown')
            distribution[call_type] = distribution.get(call_type, 0) + 1
        return distribution
    
    def _analyze_complexity_distribution(self, functions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze complexity distribution of functions.
        
        Args:
            functions: List of functions
            
        Returns:
            Complexity analysis
        """
        complexities = []
        for func in functions:
            complexity = func.get('complexity', {}).get('cyclomatic_complexity', 1)
            complexities.append(complexity)
        
        if not complexities:
            return {}
        
        complexities.sort()
        n = len(complexities)
        
        return {
            'min': min(complexities),
            'max': max(complexities),
            'mean': sum(complexities) / n,
            'median': complexities[n // 2],
            'high_complexity_count': sum(1 for c in complexities if c > 10),
            'distribution': {
                'low_complexity': sum(1 for c in complexities if c <= 5),
                'medium_complexity': sum(1 for c in complexities if 5 < c <= 10),
                'high_complexity': sum(1 for c in complexities if c > 10)
            }
        }
    
    def _analyze_file_dependencies(self, edges: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze dependencies between files.
        
        Args:
            edges: Graph edges
            
        Returns:
            File dependency analysis
        """
        file_calls = {}  # source_file -> {target_file: count}
        
        for edge in edges:
            source_file = edge.get('metadata', {}).get('source_file', '')
            target_node = edge.get('target', '')
            
            # Extract target file from node ID (simplified)
            target_file = target_node.split('::')[0] if '::' in target_node else ''
            
            if source_file and target_file and source_file != target_file:
                if source_file not in file_calls:
                    file_calls[source_file] = {}
                
                file_calls[source_file][target_file] = file_calls[source_file].get(target_file, 0) + 1
        
        # Calculate metrics
        total_cross_file_calls = sum(
            sum(targets.values()) for targets in file_calls.values()
        )
        
        most_dependent_file = None
        max_dependencies = 0
        
        for source_file, targets in file_calls.items():
            dependency_count = len(targets)
            if dependency_count > max_dependencies:
                max_dependencies = dependency_count
                most_dependent_file = source_file
        
        return {
            'total_cross_file_calls': total_cross_file_calls,
            'files_with_dependencies': len(file_calls),
            'most_dependent_file': most_dependent_file,
            'max_dependencies': max_dependencies,
            'dependency_matrix': file_calls
        }


async def create_call_graph_generator(**kwargs) -> CallGraphGenerator:
    """Create an initialized CallGraphGenerator instance.
    
    Args:
        **kwargs: Arguments to pass to CallGraphGenerator constructor
        
    Returns:
        Initialized CallGraphGenerator instance
    """
    generator = CallGraphGenerator(**kwargs)
    await generator.initialize()
    return generator
