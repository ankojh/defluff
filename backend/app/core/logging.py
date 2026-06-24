import logging


def setup_logging() -> None:
    """Configure root logging for the backend process."""
    logging.basicConfig(level=logging.INFO)
