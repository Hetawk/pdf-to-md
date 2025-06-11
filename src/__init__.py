"""
PDF to Markdown Converter Package

A comprehensive tool for converting PDF documents to Markdown format
with bibliographic enrichment and metadata extraction.
"""

__version__ = "1.0.0"
__author__ = "PDF-to-Markdown Converter Team"

from .converter import PDFToMarkdownConverter
from .enricher import BibliographicEnricher
from .config import Config

__all__ = ["PDFToMarkdownConverter", "BibliographicEnricher", "Config"]
