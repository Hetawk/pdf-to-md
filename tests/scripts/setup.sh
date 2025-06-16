#!/bin/bash

# Setup script for PDF to Markdown Converter
# This script sets up the virtual environment and installs dependencies

echo "PDF to Markdown Converter Setup"
echo "==============================="

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is required but not found. Please install Python 3.7+ first."
    exit 1
fi

echo "✅ Python 3 found: $(python3 --version)"

# Create virtual environment
echo "📦 Creating virtual environment..."
python3 -m venv .venv

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source .venv/bin/activate

# Upgrade pip
echo "⬆️  Upgrading pip..."
pip install --upgrade pip

# Install dependencies from requirements.txt
echo "📚 Installing core dependencies from requirements.txt..."
if [ -f "../../../requirements.txt" ]; then
    pip install -r ../../../requirements.txt
else
    echo "⚠️ requirements.txt not found. Skipping core dependency installation."
fi

# Install development dependencies from requirements-dev.txt
echo "🛠️ Installing development dependencies from requirements-dev.txt..."
if [ -f "../../../requirements-dev.txt" ]; then
    pip install -r ../../../requirements-dev.txt
else
    echo "⚠️ requirements-dev.txt not found. Skipping development dependency installation."
fi

echo ""
echo "✅ Setup completed successfully!"
echo ""
echo "To use the converter:"
echo "1. Activate the virtual environment: source .venv/bin/activate"
echo "2. Place PDF files in the 'pdf/' directory"
echo "3. Run: python pdf-to-md.py"
echo ""
echo "Note: For full OCR functionality, install Tesseract OCR engine separately:"
echo "- macOS: brew install tesseract"
echo "- Ubuntu: sudo apt-get install tesseract-ocr"
echo "- Windows: Download from GitHub releases"
echo ""
echo "The converter will work without Tesseract, just with reduced OCR capabilities."
