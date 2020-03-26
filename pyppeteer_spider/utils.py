import pyppeteer.page
from pathlib import Path
import asyncio
import random
import logging
import logging.handlers
import sys

def get_logger(logger_name, log_save_path=None, log_level=logging.INFO):
    """Create a logger with an optional log file."""
    formatter = logging.Formatter('[%(name)s][%(levelname)s]%(asctime)s: %(message)s')
    sh = logging.StreamHandler(sys.stdout)
    sh.setLevel(log_level)
    sh.setFormatter(formatter)
    #logging.basicConfig(stream=sh)
    logger = logging.getLogger(logger_name)
    logger.setLevel(log_level)
    logger.addHandler(sh)
    if log_save_path is not None:
        log_save_path = Path(log_save_path)
        if not log_save_path.is_file():
            try:
                log_save_path.parent.mkdir(exist_ok=True, parents=True)
            except (FileNotFoundError, PermissionError) as e:
                logger.error(f"Error creating log directory '{log_save_path.parent}'. No log will be saved. Error: {e}")
                return logger
        logger.info(f"Using log_save_path '{str(log_save_path)}'")
        fh = logging.handlers.RotatingFileHandler(log_save_path, maxBytes=10_000_000, backupCount=2)
        fh.setLevel(log_level)
        fh.setFormatter(formatter)
        logger.addHandler(fh)
    return logger