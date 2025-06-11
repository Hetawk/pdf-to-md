# PDF to Markdown Converter

A sophisticated PDF to Markdown converter specifically designed for academic papers with advanced table extraction capabilities. This tool excels at parsing complex academic tables, handling multi-column layouts, and preserving academic formatting including citations, references, and technical terminology.

## Features

- **Advanced Table Extraction**: Robust table detection and parsing with support for complex academic table structures
- **Academic Citation Handling**: Proper extraction and formatting of citations, references, and bibliographic data
- **Multi-column Layout Support**: Handles both single and multi-column academic paper layouts
- **Algorithmic Pattern Detection**: Uses intelligent pattern recognition instead of hardcoded terms for maximum flexibility
- **High-Quality Markdown Output**: Generates clean, properly formatted Markdown with preserved academic structure
- **Modular Architecture**: Extensible design with separate extractors for different content types

## Installation

1. Clone the repository:

```bash
git clone https://github.com/Hetawk/pdf-to-md.git
cd pdf-to-md
```

2. Install required dependencies:

```bash
pip install -r requirements.txt
```

## Setup

Create the following directories in your project root for input files:

```bash
mkdir pdf docx
```

- `pdf/`: Place your PDF files here for conversion
- `docx/`: Place your DOCX files here for conversion (if needed)

## Usage

### Basic Usage

Convert a PDF file to Markdown:

```bash
python pdf-to-md.py path/to/your/file.pdf
```

### Advanced Usage

The converter supports various configuration options through the main script. You can customize:

- Table extraction sensitivity
- Citation formatting
- Output formatting preferences
- Content processing options

### Example

```bash
# Convert an academic paper
python pdf-to-md.py pdf/academic_paper.pdf

# The output will be generated in the out/ directory
```

## Architecture

The project follows a modular architecture with the following components:

### Core Components

- **Converter Core** (`src/converter/core/`): Main conversion engine
- **Extractors** (`src/converter/extractors/`): Specialized content extractors
  - `table/`: Advanced table extraction with academic focus
  - `text/`: Text content extraction
  - `image/`: Image and figure handling
  - `footnote/`: Footnote and reference extraction
  - `link/`: Link and URL processing
  - `ocr/`: Optical Character Recognition support
- **Processors** (`src/converter/processors/`): Content post-processing
- **Enricher** (`src/enricher/`): Content enhancement and bibliography generation

### Key Features of Table Extraction

The table extractor includes several advanced algorithms:

1. **Academic Citation + Numerical Structure Detection**: Highest priority detection for academic tables with method citations followed by numerical data
2. **Multi-space Column Detection**: Identifies columns based on consistent spacing patterns
3. **Positional Analysis**: Analyzes character positions to determine column boundaries
4. **Pattern-based Detection**: Uses algorithmic patterns to identify table structures
5. **Content Consolidation**: Merges related table sections that should be unified

## Configuration

The system can be configured through `src/config.py`. Key configuration options include:

- Minimum table confidence threshold
- Column detection sensitivity
- Academic content patterns
- Output formatting preferences

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## Requirements

See `requirements.txt` for a complete list of dependencies. Key requirements include:

- PyMuPDF (fitz): PDF processing
- Regular expressions support
- Python 3.7+

## Output Structure

The converter generates:

- Clean Markdown files with preserved academic structure
- Properly formatted tables with academic citations
- Extracted images and figures (when applicable)
- Bibliography and reference sections
- Footnotes and annotations

## Academic Table Handling

This converter is specifically optimized for academic papers and excels at:

- **Complex Table Structures**: Multi-column tables with varying layouts
- **Citation Integration**: Tables with embedded citations and references
- **Technical Terminology**: Proper handling of abbreviations, acronyms, and technical terms
- **Performance Metrics**: Academic performance tables with statistical data
- **Method Comparisons**: Comparative analysis tables common in research papers

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- Built with PyMuPDF for robust PDF processing
- Designed specifically for academic and research document conversion
- Optimized for complex table structures found in scientific papers

## Support

For issues, questions, or contributions, please open an issue on the GitHub repository.
