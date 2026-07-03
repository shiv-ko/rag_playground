"""ロギング設定。rich が入っていれば色付き出力、なければ標準logging。"""
import logging
import sys


def setup_logging(level: str = "INFO") -> logging.Logger:
    logger = logging.getLogger("rag_comp")
    if logger.handlers:
        return logger

    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    try:
        from rich.logging import RichHandler
        handler: logging.Handler = RichHandler(rich_tracebacks=True)
    except ImportError:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))

    logger.addHandler(handler)
    return logger
