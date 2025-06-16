#!/bin/bash
# Virtual Environment Setup Script for PDF-to-Markdown Converter

echo "Setting up virtual environment for PDF-to-Markdown converter..."

# Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python -m venv .venv
fi

# Activate virtual environment
echo "Activating virtual environment..."
source .venv/bin/activate

# Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip

# Install core requirements
echo "Installing core dependencies..."
pip install PyMuPDF tqdm requests

# Optional dependencies (install as needed)
echo ""
echo "Core dependencies installed successfully!"
echo ""
echo "To install optional dependencies for full functionality:"
echo "  pip install pytesseract Pillow opencv-python pandas numpy bibtexparser"
echo ""
echo "To activate the environment in the future, run:"
echo "  source .venv/bin/activate"
echo ""
echo "To test the converter:"
echo "  python pdf-to-md.py --help"
