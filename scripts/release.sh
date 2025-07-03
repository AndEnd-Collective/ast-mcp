#!/bin/bash
set -e

# AST-Grep MCP Release Script
# Creates distributable packages for PyPI

echo "🚀 Starting AST-Grep MCP Release Process"

# Check prerequisites
echo "📋 Checking prerequisites..."

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is required but not installed"
    exit 1
fi

# Check build tools
if ! python3 -m pip show build &> /dev/null; then
    echo "📦 Installing build tools..."
    python3 -m pip install build twine
fi

# Check AST-Grep
if ! command -v ast-grep &> /dev/null; then
    echo "⚠️  AST-Grep binary not found. Users will need to install it separately."
    echo "   See: https://ast-grep.github.io/guide/quick-start.html#installation"
fi

# Clean previous builds
echo "🧹 Cleaning previous builds..."
rm -rf build/ dist/ *.egg-info/

# Validate package structure
echo "🔍 Validating package structure..."
if [ ! -f "pyproject.toml" ]; then
    echo "❌ pyproject.toml not found"
    exit 1
fi

if [ ! -f "README.md" ]; then
    echo "❌ README.md not found"
    exit 1
fi

if [ ! -d "src/ast_grep_mcp" ]; then
    echo "❌ Source package not found"
    exit 1
fi

# Run tests if they exist
if [ -d "tests" ] && [ -f "pytest.ini" ] || grep -q pytest pyproject.toml; then
    echo "🧪 Running tests..."
    python3 -m pytest tests/ || {
        echo "❌ Tests failed. Fix tests before releasing."
        exit 1
    }
fi

# Build the package
echo "🏗️  Building package..."
python3 -m build

# Verify the build
echo "✅ Verifying build..."
if [ ! -f dist/*.whl ] || [ ! -f dist/*.tar.gz ]; then
    echo "❌ Build failed - distribution files not found"
    exit 1
fi

# Check package metadata
echo "📋 Checking package metadata..."
python3 -m twine check dist/*

# Display build results
echo ""
echo "🎉 Build Complete!"
echo "📦 Distribution files:"
ls -la dist/

echo ""
echo "🚀 Next Steps:"
echo ""
echo "1. Test the built package locally:"
echo "   pip install dist/ast_grep_mcp-*.whl"
echo ""
echo "2. Upload to Test PyPI (optional):"
echo "   python3 -m twine upload --repository testpypi dist/*"
echo ""
echo "3. Upload to PyPI:"
echo "   python3 -m twine upload dist/*"
echo ""
echo "4. Create GitHub release:"
echo "   gh release create v$(grep version pyproject.toml | cut -d'\"' -f2) dist/* --title 'AST-Grep MCP v$(grep version pyproject.toml | cut -d'\"' -f2)'"
echo ""
echo "5. Users can then install with:"
echo "   pip install ast-grep-mcp"
echo ""