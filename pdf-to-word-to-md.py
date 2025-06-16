"""
PDF to Markdown Converter - Main Entry Point

A comprehensive tool for converting PDF documents to Markdown format
with bibliographic enrichment and metadata extraction.
"""

from src.converter import PDFToMarkdownConverter
from src.config import Config, check_dependencies
import argparse
import json
import sys
import logging
from pathlib import Path
from datetime import datetime

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))


def setup_logging(verbose=False):
    """Setup comprehensive logging for the conversion process."""
    # Create logs directory
    log_dir = Path("out/logs")
    log_dir.mkdir(parents=True, exist_ok=True)

    # Create timestamped log file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"pdf_conversion_{timestamp}.log"

    # Configure logging
    log_level = logging.DEBUG if verbose else logging.INFO

    # Create formatters
    detailed_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    simple_formatter = logging.Formatter(
        '[%(levelname)s] %(message)s'
    )

    # Setup root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Clear any existing handlers
    root_logger.handlers.clear()

    # File handler (detailed logging)
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(detailed_formatter)
    root_logger.addHandler(file_handler)

    # Console handler (simple logging)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(simple_formatter)
    root_logger.addHandler(console_handler)

    # Log setup completion
    logging.info(
        f"Logging initialized - Level: {logging.getLevelName(log_level)}")
    logging.info(f"Log file: {log_file}")

    return log_file


def main():
    """Main entry point for the PDF to Markdown converter."""
    # Parse arguments first to get verbose setting
    parser = argparse.ArgumentParser(
        description='Convert PDF files to Markdown using hybrid PDF→Word→Markdown pipeline',
        epilog='''
Default behavior (no arguments):
  Processes all PDF files in documents/ directory using hybrid conversion

Examples:
  %(prog)s                                    # Process all PDFs in documents/
  %(prog)s file.pdf                          # Convert single file
  %(prog)s documents/                        # Convert directory
  %(prog)s file.pdf --strategy direct       # Use direct PDF→MD conversion
  %(prog)s --no-enrichment                  # Skip bibliographic enrichment
        ''', formatter_class=argparse.RawDescriptionHelpFormatter)

    parser.add_argument('input', nargs='?',
                        help='PDF file or directory path (default: documents/ directory)')
    parser.add_argument(
        '-o', '--output', help='Output file path (for single file conversion)')
    parser.add_argument('--no-images', action='store_true',
                        help='Skip image extraction')
    parser.add_argument('--no-tables', action='store_true',
                        help='Skip table detection')
    parser.add_argument('--no-metadata', action='store_true',
                        help='Skip metadata extraction')
    parser.add_argument('--no-enrichment', action='store_true',
                        help='Skip bibliographic enrichment')
    parser.add_argument('--no-bibtex', action='store_true',
                        help='Skip BibTeX generation')
    parser.add_argument('--no-individual-bibtex', action='store_true',
                        help='Skip individual BibTeX files')
    parser.add_argument('--strategy', choices=['direct', 'hybrid', 'auto'],
                        default='hybrid',
                        help='Conversion strategy: direct (PDF→MD), hybrid (PDF→Word→MD), or auto (choose best) (default: hybrid)')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Verbose logging')
    parser.add_argument('--config', help='Path to configuration file (JSON)')

    args = parser.parse_args()

    # Setup logging based on verbose setting
    log_file = setup_logging(args.verbose)

    # Check dependencies
    check_dependencies()

    # Load configuration
    config = Config()
    if args.config:
        config.load_from_file(args.config)

    # Apply CLI overrides
    config = _apply_cli_overrides(config, args)

    # If no input provided, use documents/ directory
    if not args.input:
        print("PDF to Markdown Converter")
        print("=" * 50)

        # Check if documents directory exists
        docs_dir = Path("documents")
        if docs_dir.exists() and docs_dir.is_dir():
            pdf_files = list(docs_dir.glob("*.pdf"))
            if pdf_files:
                print(
                    f"Found {len(pdf_files)} PDF files in 'documents/' directory:")
                for pdf_file in pdf_files[:5]:  # Show first 5
                    print(f"  - {pdf_file.name}")
                if len(pdf_files) > 5:
                    print(f"  ... and {len(pdf_files) - 5} more")

                print("\nStarting conversion...")

                # Load configuration
                config = Config()
                if args.config and Path(args.config).exists():
                    config = Config.from_file(args.config)

                # Override config with command line arguments
                config = _apply_cli_overrides(config, args)

                converter = PDFToMarkdownConverter(config)
                converter.convert_directory("documents")
                return
            else:
                print("No PDF files found in 'documents/' directory.")
                print(
                    "Please add PDF files to the 'documents/' directory and run again.")
                return
        else:
            print("No 'documents/' directory found.")
            print("Creating 'documents/' directory...")
            docs_dir.mkdir(exist_ok=True)
            print("Please add PDF files to the 'documents/' directory and run again.")
            print("\nAlternatively, you can run:")
            print("  python pdf-to-word-to-md.py <pdf-file>     # Convert single file")
            print(
                "  python pdf-to-word-to-md.py <directory>    # Convert all PDFs in directory")
            return

    # Load configuration
    config = Config()
    if args.config and Path(args.config).exists():
        config = Config.from_file(args.config)

    # Override config with command line arguments
    config = _apply_cli_overrides(config, args)

    converter = PDFToMarkdownConverter(config)
    input_path = Path(args.input)

    if input_path.is_file() and input_path.suffix.lower() == '.pdf':
        # Convert single file
        if args.output:
            output_path = Path(args.output)
        else:
            out_dir = Path("out")
            md_json_dir = out_dir / "md-json"
            md_json_dir.mkdir(parents=True, exist_ok=True)
            output_path = md_json_dir / input_path.with_suffix('.md').name
        converter.convert_pdf_to_markdown(input_path, output_path)
    elif input_path.is_dir():
        # Convert all PDFs in directory
        converter.convert_directory(input_path)
    else:
        print("Invalid input. Please provide a PDF file or directory containing PDF files.")


def _apply_cli_overrides(config: Config, args) -> Config:
    """Apply command line argument overrides to configuration."""
    overrides = {}

    if args.no_images:
        overrides['extract_images'] = False
    if args.no_tables:
        overrides['extract_tables'] = False
    if args.no_metadata:
        overrides['extract_metadata'] = False
    if args.no_enrichment:
        overrides['enrich_metadata'] = False
    if args.no_bibtex:
        overrides['generate_bibtex'] = False
    if args.no_individual_bibtex:
        overrides['create_individual_bibtex'] = False
    if args.strategy:
        overrides['conversion_strategy'] = args.strategy
    if args.verbose:
        overrides['log_level'] = 'DEBUG'

    config.update(overrides)
    return config


if __name__ == "__main__":
    main()
