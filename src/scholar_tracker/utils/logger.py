import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

# Ensure data dir exists
data_dir = Path("data")
data_dir.mkdir(exist_ok=True)


def setup_logger(log_file="data/scholar_tracker.log", level=logging.INFO):
    logger = logging.getLogger("scholar_tracker")

    # Avoid duplicate handlers
    if logger.handlers:
        return logger

    logger.setLevel(level)

    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # 7-day log rotation at midnight
    file_handler = TimedRotatingFileHandler(
        log_file,
        when="midnight",
        interval=1,
        backupCount=7,
        encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(level)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


logger = setup_logger()
