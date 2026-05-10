import sys
import os
from loguru import logger

def setup_logger():
    """Configure the global logger with JSON serialization."""
    logger.remove()
    
    # Log to stdout
    logger.add(
        sys.stdout,
        serialize=True,
        level="INFO",
        backtrace=True,
        diagnose=True,
    )
    
    # Log to a file with rotation
    os.makedirs("logs", exist_ok=True)
    logger.add(
        "logs/app.log",
        rotation="10 MB",  # Rotate when the file exceeds 10 MB
        serialize=True,
        level="INFO",
        backtrace=True,
        diagnose=True,
    )
    
    return logger

# Export the configured logger
logger = setup_logger()
