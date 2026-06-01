import sys
from loguru import logger
from utils.config import config

logger.remove()
logger.add(
    sys.stdout,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan> - {message}",
    level=config.LOG_LEVEL if hasattr(config, 'LOG_LEVEL') else "INFO",
    colorize=True,
)
logger.add(
    "logs/spilled_{time:YYYY-MM-DD}.log",
    rotation="1 day",
    retention="7 days",
    level="DEBUG",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {name} - {message}",
)
