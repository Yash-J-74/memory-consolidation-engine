import sys
import os
import traceback
from loguru import logger

def _format_record(record):
    timestamp = record["time"].strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    base = (
        f"{timestamp} | "
        f"{record['level'].name:<8} | "
        f"{record['name']}:{record['function']}:{record['line']} - "
        f"{record['message']}"
    )
    if record["extra"]:
        extra_items = ", ".join(f"{key}={value}" for key, value in record["extra"].items())
        base = f"{base} | {extra_items}"

    if record["exception"]:
        exc = record["exception"]
        traceback_text = "".join(
            traceback.format_exception(exc.type, exc.value, exc.traceback)
        ).rstrip()
        return f"{base}\n{traceback_text}\n"

    return f"{base}\n"

def setup_logger():
    """Configure the global logger with a readable text format."""
    logger.remove()
    
    # Log to stdout
    logger.add(
        sys.stdout,
        format=_format_record,
        colorize=True,
        level="INFO",
        backtrace=True,
        diagnose=True,
    )
    
    # Log to a file with rotation
    os.makedirs("logs", exist_ok=True)
    logger.add(
        "logs/app.log",
        rotation="10 MB",  # Rotate when the file exceeds 10 MB
        format=_format_record,
        colorize=False,
        level="INFO",
        backtrace=True,
        diagnose=True,
    )
    
    return logger

# Export the configured logger
logger = setup_logger()
