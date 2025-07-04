import asyncio
import json
from pathlib import Path
from ast_grep_mcp.tools import register_tools
from mcp.server import Server

async def test_tool():
    server = Server("test-server")
    
    # Register tools with ast-grep path
    ast_grep_path = Path("/opt/homebrew/bin/ast-grep")
    await register_tools(server, ast_grep_path)
    
    # Test listing tools
    try:
        tools = list(server.list_tools())
        print("Registered tools:")
        for tool in tools:
            print(f"  - {tool.name}")
        
        # Check if ast_grep_search exists
        search_tools = [t for t in tools if t.name == "ast_grep_search"]
        if search_tools:
            print(f"\nFound ast_grep_search tool\!")
            print(f"Schema: {search_tools[0].input_schema}")
        else:
            print("\nast_grep_search tool not found\!")
            
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_tool())
