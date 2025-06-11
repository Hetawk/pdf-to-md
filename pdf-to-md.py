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
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))


def main():
    """Main entry point for the PDF to Markdown converter."""
    # Check dependencies first
    check_dependencies()

    parser = argparse.ArgumentParser(
        description='Convert PDF files to Markdown with bibliographic enrichment')
    parser.add_argument('input', nargs='?', help='PDF file or directory path')
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
    parser.add_argument('--no-individual-bibtex',
                        action='store_true', help='Skip individual BibTeX files')
    parser.add_argument('--verbose', '-v',
                        action='store_true', help='Verbose logging')
    parser.add_argument('--config', help='Path to configuration file (JSON)')

    args = parser.parse_args()

    # If no input provided, use pdf/ directory
    if not args.input:
        print("PDF to Markdown Converter")
        print("=" * 50)

        # Check if pdf directory exists
        pdf_dir = Path("pdf")
        if pdf_dir.exists() and pdf_dir.is_dir():
            pdf_files = list(pdf_dir.glob("*.pdf"))
            if pdf_files:
                print(f"Found {len(pdf_files)} PDF files in 'pdf/' directory:")
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
                converter.convert_directory("pdf")
                return
            else:
                print("No PDF files found in 'pdf/' directory.")
                print("Please add PDF files to the 'pdf/' directory and run again.")
                return
        else:
            print("No 'pdf/' directory found.")
            print("Creating 'pdf/' directory...")
            pdf_dir.mkdir(exist_ok=True)
            print("Please add PDF files to the 'pdf/' directory and run again.")
            print("\nAlternatively, you can run:")
            print("  python pdf-to-md.py <pdf-file>     # Convert single file")
            print("  python pdf-to-md.py <directory>    # Convert all PDFs in directory")
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
    if args.verbose:
        overrides['log_level'] = 'DEBUG'

    config.update(overrides)
    return config


if __name__ == "__main__":
    main()
