"""Utility functions for bibliographic enrichment."""

import re
from typing import Dict


def extract_identifiers_from_text(text: str) -> Dict[str, str]:
    """Extract DOI, arXiv ID, PMID from text."""
    identifiers = {}

    # DOI patterns
    doi_patterns = [
        r'(?:doi:?\s*)(10\.\d+/[^\s]+)',
        r'(?:dx\.doi\.org/)(10\.\d+/[^\s]+)',
        r'(?:doi\.org/)(10\.\d+/[^\s]+)'
    ]

    for pattern in doi_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            identifiers['doi'] = matches[0].rstrip('.,;)')
            break

    # arXiv patterns
    arxiv_patterns = [
        r'arXiv:(\d{4}\.\d{4,5})',
        r'arxiv\.org/abs/(\d{4}\.\d{4,5})'
    ]

    for pattern in arxiv_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            identifiers['arxiv'] = matches[0]
            break

    # PMID patterns
    pmid_matches = re.findall(r'PMID:?\s*(\d+)', text, re.IGNORECASE)
    if pmid_matches:
        identifiers['pmid'] = pmid_matches[0]

    return identifiers
