import sys
import logging
import colorlog
import time
from pathlib import Path
from datetime import datetime
from typing import Optional, Union, Dict, Any, Callable
from logging.handlers import RotatingFileHandler
from functools import wraps, lru_cache
from contextlib import contextmanager
from proglog import ProgressBarLogger

@contextmanager
def silence_logging():
    logging.disable()
    try:
        yield
    finally:
        logging.disable(logging.NOTSET)

# Log format
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s (%(filename)s:%(lineno)d)"
# Log colors mapping
LOG_COLOR_MAP = {
    "DEBUG": "cyan",
    "INFO": "green",
    "WARNING": "yellow",
    "ERROR": "red",
    "CRITICAL": "bold_red",
}
# Log levels mapping
LOG_LEVEL_MAP = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
    "critical": logging.CRITICAL
}


@lru_cache(maxsize=128)
def get_logger(
    name: Optional[str] = None,
) -> logging.Logger:
    """Get a configured color logger

    Args:
        name: Logger name

    Returns:
        Logger instance
    """
    # Get calling module name
    if name is None:
        frame = sys._getframe(1)
        name = frame.f_globals.get("__name__", "__main__")

    # Logger config
    level = "debug"
    do_console = True
    do_file = False
    log_dir = "logs"
    date_format = "%Y-%m-%d %H:%M:%S"

    # Create logger
    logger = logging.getLogger(name)

    # Set logging level
    level = LOG_LEVEL_MAP.get(level.lower(), logging.INFO)
    logger.setLevel(level)
    logger.propagate = False  # Prevent propagation to root logger
    logger.handlers.clear()  # Clear existing handlers

    # Add console handler
    if do_console:
        console_handler = colorlog.StreamHandler()
        console_handler.setLevel(level)
        colored_formatter = colorlog.ColoredFormatter(
            f"%(log_color)s{LOG_FORMAT}",
            datefmt=date_format,
            log_colors=LOG_COLOR_MAP
        )
        console_handler.setFormatter(colored_formatter)
        logger.addHandler(console_handler)

    # Add file handler
    if do_file:
        # Create log directory
        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)

        # Create log filename
        module_name = name.split(".")[-1]
        timestamp = datetime.now().strftime("%Y-%m-%d")
        filename_template = "{timestamp}.log"
        log_file = log_path / filename_template.format(
            module=module_name,
            timestamp=timestamp
        )

        # Setup file handler
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8"
        )
        file_handler.setLevel(level)
        file_formatter = logging.Formatter(LOG_FORMAT, datefmt=date_format)
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

    return logger


def log_exception(func=None, logger=None, level=logging.ERROR):
    def decorator(fn):
        nonlocal logger
        if logger is None:
            logger = get_logger(name=fn.__module__)

        @wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except Exception as e:
                logger.log(level, f"Exception in {fn.__name__}: {str(e)}", exc_info=True)
                raise  # Re-raise exception
        return wrapper

    # Support direct @log_exception usage
    if func is not None:
        return decorator(func)
    return decorator


def log_time(func=None, logger=None, level=logging.DEBUG):
    def decorator(fn):
        nonlocal logger
        if logger is None:
            logger = get_logger(name=fn.__module__)

        @wraps(fn)
        def wrapper(*args, **kwargs):
            start_time = time.perf_counter()
            result = fn(*args, **kwargs)
            elapsed_time = time.perf_counter() - start_time
            logger.log(level, f"Function {fn.__name__} ellapsed: {elapsed_time:.3f}s")
            return result
        return wrapper

    if func is not None:
        return decorator(func)
    return decorator

from proglog import TqdmProgressBarLogger

class MCPMoviePyLogger(TqdmProgressBarLogger):
    def __init__(self, report: Callable[[float, Optional[float], Optional[str]], None]):
        super().__init__(logged_bars="all", leave_bars=False, print_messages=True)
        self._report = report
        self._last_ts = 0.0
        self._last_p = -1.0
        self._seen = set()

    def bars_callback(self, bar, attr, value, old_value=None):
        super().bars_callback(bar, attr, value, old_value)
        if bar not in ("frame_index", "t", "chunk"):
            return
        if attr != "index":
            return
        st = self.bars.get(bar) or {}
        idx, tot = st.get("index"), st.get("total")
        if idx is None or not tot:
            return
        p = float(idx) / float(tot)
        p = max(0.0, min(1.0, p))

        now = time.monotonic()
        if p < 1.0 and (now - self._last_ts) < 0.2 and (p - self._last_p) < 0.002:
            return
        self._last_ts, self._last_p = now, p

        self._report(float(idx), float(tot), f"rendering {p*100:.1f}%")

if __name__ == "__main__":

    # Create logger with configuration
    logger = get_logger()
    logger.debug("Debug message")
    logger.info("Info message")

    # Test logging decorators
    @log_exception
    @log_time
    def sample_function(x, y):
        import time
        time.sleep(0.1)
        return x + y

    # Test function logging
    result = sample_function(10, 20)
    logger.info(f"Function result: {result}")

    # Test exception logging
    @log_exception
    def dumb_func():
        return 1 / 0

    try:
        dumb_func()
    except ZeroDivisionError:
        logger.info("Exception was logged")
