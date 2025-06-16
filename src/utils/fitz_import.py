"""Utility for safe PyMuPDF import."""

try:
    import fitz  # PyMuPDF
except ImportError as e:
    # Try alternative import method if there's a conflict
    try:
        import PyMuPDF as fitz
    except ImportError:
        raise ImportError(
            f"PyMuPDF is required but not found. Please install with: pip install PyMuPDF. Original error: {e}")

# Export fitz for use by other modules
__all__ = ['fitz']
