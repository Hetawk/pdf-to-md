"""Configuration management for PDF-to-Markdown converter."""

import json
import logging
import os
from pathlib import Path
from typing import Dict, Any, Optional


class Config:
    """Configuration manager for the PDF converter."""

    DEFAULT_CONFIG = {
        # Basic extraction settings
        'extract_images': True,
        'extract_tables': True,
        'handle_multi_column': True,
        'extract_footnotes': True,
        'extract_metadata': True,
        'create_reports': True,

        # Enhanced extraction settings
        'extract_links': True,
        'extract_citations': True,
        'extract_cross_references': True,
        'show_bibliography': True,

        # OCR settings
        'enable_ocr': True,
        'ocr_language': 'eng',
        'ocr_confidence_threshold': 60,
        'detect_scanned_pages': True,

        # Advanced table extraction
        'table_extraction_strategies': ['bbox_analysis', 'text_alignment', 'hybrid'],
        'table_confidence_threshold': 0.7,
        'extract_table_from_images': True,

        # Advanced image extraction
        'intelligent_image_naming': True,
        'extract_figure_captions': True,
        'categorize_images': True,
        'image_context_radius': 50,

        # Link and reference extraction
        'extract_external_links': True,
        'extract_internal_refs': True,
        'extract_doi_links': True,
        'extract_email_links': True,

        # Bibliographic enrichment
        'enrich_metadata': True,
        'generate_bibtex': True,
        'create_individual_bibtex': True,
        'create_combined_bibtex': True,

        # Output and formatting
        'preserve_page_numbers': False,
        'preserve_headers_footers': False,
        'markdown_table_format': 'github',
        'image_reference_style': 'inline',

        # Performance and quality
        'cleanup_temp_files': False,
        'log_level': 'INFO',
        'max_file_size_mb': 100,
        'image_quality': 150,
        'show_progress': False,
        'parallel_processing': False,

        # Quality thresholds
        'min_text_extraction_ratio': 0.1,
        'min_table_confidence': 0.6,
        'min_image_size': 50,
    }

    def __init__(self, config_data: Optional[Dict[str, Any]] = None):
        """Initialize configuration with defaults and user overrides."""
        self.config = self.DEFAULT_CONFIG.copy()
        if config_data:
            self.config.update(config_data)

    @classmethod
    def from_file(cls, config_path: str) -> 'Config':
        """Load configuration from JSON file."""
        config_path = Path(config_path)
        if config_path.exists():
            with open(config_path, 'r') as f:
                config_data = json.load(f)
            return cls(config_data)
        else:
            logging.warning(
                f"Config file {config_path} not found, using defaults")
            return cls()

    def get(self, key: str, default=None):
        """Get configuration value."""
        return self.config.get(key, default)

    def set(self, key: str, value: Any):
        """Set configuration value."""
        self.config[key] = value

    def update(self, updates: Dict[str, Any]):
        """Update multiple configuration values."""
        self.config.update(updates)

    def to_dict(self) -> Dict[str, Any]:
        """Return configuration as dictionary."""
        return self.config.copy()

    def save(self, config_path: str):
        """Save configuration to file."""
        with open(config_path, 'w') as f:
            json.dump(self.config, f, indent=2)


def check_dependencies():
    """Check if required dependencies are installed."""
    missing_deps = []

    try:
        import fitz  # PyMuPDF
    except ImportError:
        missing_deps.append("PyMuPDF")

    try:
        import requests
    except ImportError:
        missing_deps.append("requests")

    try:
        from tqdm import tqdm
    except ImportError:
        missing_deps.append("tqdm")

    try:
        import bibtexparser
    except ImportError:
        missing_deps.append("bibtexparser")

    if missing_deps:
        print("Error: Missing required dependencies!")
        print("Please install the following packages:")
        print(f"pip install {' '.join(missing_deps)}")
        print("\nOr install all at once:")
        print("pip install PyMuPDF requests tqdm bibtexparser")
        import sys
        sys.exit(1)


def check_dependencies():
    """Check for optional dependencies and warn if missing."""
    warnings = []

    # Check for OCR dependencies
    try:
        import pytesseract
        import PIL
    except ImportError:
        warnings.append(
            "OCR functionality requires 'pytesseract' and 'Pillow'. "
            "Install with: pip install pytesseract Pillow"
        )
        warnings.append(
            "Also install Tesseract OCR engine: "
            "macOS: brew install tesseract, "
            "Ubuntu: apt-get install tesseract-ocr"
        )

    # Check for enhanced image processing
    try:
        import cv2
    except ImportError:
        warnings.append(
            "Enhanced image analysis requires 'opencv-python'. "
            "Install with: pip install opencv-python"
        )

    # Check for table detection libraries
    try:
        import pandas as pd
    except ImportError:
        warnings.append(
            "Advanced table processing requires 'pandas'. "
            "Install with: pip install pandas"
        )

    # Check for scientific computing
    try:
        import numpy as np
    except ImportError:
        warnings.append(
            "Advanced algorithms require 'numpy'. "
            "Install with: pip install numpy"
        )

    if warnings:
        print("Optional Dependencies Warning:")
        print("=" * 50)
        for warning in warnings:
            print(f"⚠️  {warning}")
        print("\nThe converter will work with basic functionality, "
              "but some advanced features may be disabled.")
        print("=" * 50)
    else:
        print("✅ All optional dependencies are available!")


def get_available_ocr_languages():
    """Get list of available OCR languages."""
    try:
        import pytesseract
        langs = pytesseract.get_languages()
        return langs
    except ImportError:
        return ['eng']  # Default fallback


def validate_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and adjust configuration based on available dependencies."""
    try:
        import pytesseract
    except ImportError:
        if config.get('enable_ocr', False):
            logging.warning("OCR disabled - pytesseract not available")
            config['enable_ocr'] = False
            config['detect_scanned_pages'] = False

    try:
        import cv2
    except ImportError:
        if config.get('intelligent_image_naming', False):
            logging.warning(
                "Advanced image analysis disabled - opencv not available")
            config['intelligent_image_naming'] = False

    # Validate OCR language
    if config.get('enable_ocr', False):
        available_langs = get_available_ocr_languages()
        if config.get('ocr_language', 'eng') not in available_langs:
            logging.warning(
                f"OCR language '{config.get('ocr_language')}' not available, using 'eng'")
            config['ocr_language'] = 'eng'

    # Validate thresholds
    config['table_confidence_threshold'] = max(0.0, min(1.0,
                                                        config.get('table_confidence_threshold', 0.7)))
    config['ocr_confidence_threshold'] = max(0, min(100,
                                                    config.get('ocr_confidence_threshold', 60)))

    return config
