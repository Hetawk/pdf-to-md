"""Utility functions for PDF conversion."""

import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any


def create_conversion_report(pdf_path: str, metadata: Dict[str, Any],
                             quality_metrics: Dict[str, Any], output_path: str):
    """Create a detailed conversion report."""
    report = {
        'source_file': str(pdf_path),
        'output_file': str(output_path),
        'conversion_timestamp': datetime.now().isoformat(),
        'metadata': metadata,
        'quality_metrics': quality_metrics,
        'converter_version': '1.0'
    }

    report_path = Path(output_path).with_suffix('.json')
    try:
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        logging.info(f"Conversion report saved: {report_path}")
    except Exception as e:
        logging.error(f"Could not save conversion report: {e}")


def validate_conversion_quality(doc, content: str) -> Dict[str, Any]:
    """Validate the quality of PDF to Markdown conversion."""
    quality_metrics = {
        'word_count': len(content.split()),
        'char_count': len(content),
        'page_count': len(doc),
        'images_extracted': content.count('!['),
        'tables_detected': content.count('|') // 3 if content.count('|') > 0 else 0,
        'headings_detected': content.count('#'),
        'has_mathematical_content': any(symbol in content for symbol in ['∫', '∑', '√', '∞', '±', '≤', '≥', '≠', '∝']),
        'empty_content': len(content.strip()) == 0,
        # Reasonable content extracted
        'extraction_success': len(content.strip()) > 100,
    }

    # Calculate quality score
    score = 0
    if quality_metrics['word_count'] > 100:
        score += 30
    if quality_metrics['images_extracted'] > 0:
        score += 20
    if quality_metrics['tables_detected'] > 0:
        score += 20
    if quality_metrics['headings_detected'] > 0:
        score += 20
    if not quality_metrics['empty_content']:
        score += 10

    quality_metrics['quality_score'] = min(score, 100)

    return quality_metrics
