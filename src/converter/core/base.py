"""Base converter class and common functionality."""

import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any

from ...config import Config


class BaseConverter:
    """Base class for all converters with common functionality."""

    def __init__(self, config: Optional[Config] = None):
        self.config = config or Config()
        self.logger = logging.getLogger(self.__class__.__name__)
        self.setup_logging()

    def setup_logging(self):
        """Setup logging for conversion process."""
        # Create logs directory
        logs_dir = Path("out/logs")
        logs_dir.mkdir(parents=True, exist_ok=True)

        log_file = logs_dir / \
            f"pdf_conversion_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

        logging.basicConfig(
            level=getattr(logging, self.config.get('log_level', 'INFO')),
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler()
            ]
        )

    def validate_input(self, pdf_path: str) -> bool:
        """Validate input PDF file."""
        path = Path(pdf_path)

        if not path.exists():
            self.logger.error(f"PDF file not found: {pdf_path}")
            return False

        if not path.suffix.lower() == '.pdf':
            self.logger.error(f"File is not a PDF: {pdf_path}")
            return False

        # Check file size
        file_size = path.stat().st_size / (1024 * 1024)  # MB
        max_size = self.config.get('max_file_size_mb', 100)

        if file_size > max_size:
            self.logger.warning(
                f"Large file detected ({file_size:.1f}MB). Conversion may take time.")

        return True

    def create_output_directories(self, output_dir: Path) -> Dict[str, Path]:
        """Create necessary output directories."""
        directories = {
            'base': output_dir,
            'images': output_dir / "images",
            'tables': output_dir / "tables",
            'reports': output_dir / "reports",
            'logs': output_dir / "logs"
        }

        for name, path in directories.items():
            path.mkdir(parents=True, exist_ok=True)

        return directories

    def get_file_info(self, pdf_path: str) -> Dict[str, Any]:
        """Get basic file information."""
        path = Path(pdf_path)

        return {
            'filename': path.name,
            'size_mb': path.stat().st_size / (1024 * 1024),
            'modified_date': datetime.fromtimestamp(path.stat().st_mtime).isoformat(),
            'stem': path.stem
        }
