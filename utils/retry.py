"""
Reusable retry decorator for Gemini API calls.

Usage:
    from utils.retry import gemini_retry

    @gemini_retry(max_attempts=3, base_delay=2.0)
    def call_gemini(prompt: str) -> str:
        ...
"""
import time
import functools
from typing import Tuple, Type

from core.logging import get_logger

log = get_logger("retry")

# Import Google API exceptions if available; fall back to a broad catch.
try:
    from google.api_core.exceptions import GoogleAPIError, ResourceExhausted
    _GEMINI_EXCEPTIONS: Tuple[Type[Exception], ...] = (GoogleAPIError, ResourceExhausted)
except ImportError:
    _GEMINI_EXCEPTIONS = (Exception,)


def gemini_retry(max_attempts: int = 3, base_delay: float = 2.0):
    """
    Decorator that retries a function on Gemini quota / API errors.

    Retries up to `max_attempts` times with exponential backoff:
      attempt 1 failure → wait base_delay seconds
      attempt 2 failure → wait 2 * base_delay seconds
      ...
    On the final attempt the exception is re-raised.

    Args:
        max_attempts: Total number of attempts (including the first call).
        base_delay:   Base wait time in seconds before the first retry.
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except _GEMINI_EXCEPTIONS as exc:
                    if attempt == max_attempts:
                        log.error(
                            f"{func.__name__}: all {max_attempts} attempts exhausted — {exc}"
                        )
                        raise
                    delay = base_delay * (2 ** (attempt - 1))
                    log.warning(
                        f"{func.__name__}: attempt {attempt}/{max_attempts} failed "
                        f"({type(exc).__name__}). Retrying in {delay:.1f}s..."
                    )
                    time.sleep(delay)
        return wrapper
    return decorator
