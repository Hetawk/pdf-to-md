#!/bin/bash
# Main Setup Script for PDF-to-Markdown Converter
# This script sets up the project with virtual environment and dependencies

echo "🚀 PDF-to-Markdown Converter Setup"
echo "=================================="

# Check if Python 3 is available
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is required but not found. Please install Python 3.7+"
    exit 1
fi

echo "✅ Python 3 found: $(python3 --version)"

# Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv .venv
    echo "✅ Virtual environment created"
else
    echo "✅ Virtual environment already exists"
fi

# Activate virtual environment
echo "🔌 Activating virtual environment..."
source .venv/bin/activate

# Upgrade pip
echo "⬆️  Upgrading pip..."
pip install --upgrade pip

# Install core requirements
echo "📚 Installing core requirements..."
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
    echo "✅ Core requirements installed"
else
    echo "❌ requirements.txt not found"
    exit 1
fi

# Install development requirements (optional)
if [ -f "requirements-dev.txt" ]; then
    echo "🔧 Installing development requirements..."
    pip install -r requirements-dev.txt
    echo "✅ Development requirements installed"
fi

# Create directory structure
echo "📁 Creating project directories..."
mkdir -p documents
mkdir -p out/markdown/hybrid
mkdir -p out/markdown/direct
mkdir -p out/word
mkdir -p src
mkdir -p tests
mkdir -p docs

echo ""
echo "✅ Setup completed successfully!"
echo ""
echo "📋 Next steps:"
echo "  1. Add PDF/DOCX files to documents/"
echo "  2. Run: python pdf-to-md.py"
echo "  3. Check output in out/"
echo ""
echo "🔧 To activate virtual environment manually:"
echo "  source .venv/bin/activate"
echo ""
echo "📖 For more information, see README.md"
