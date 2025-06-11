"""Base class for content extractors."""

import logging


class BaseExtractor:
    """Base class for content extractors."""

    def __init__(self, config):
        self.config = config
        self.logger = logging.getLogger(__name__)
