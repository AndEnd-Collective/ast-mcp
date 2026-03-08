"""Allow running ast_grep_mcp as a module: python -m ast_grep_mcp"""

from ast_grep_mcp.server import main_sync

if __name__ == "__main__":
    main_sync()
