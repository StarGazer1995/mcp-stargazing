"""
Retry utilities for external API calls.
"""
import asyncio
import time
from typing import Any, Callable, Optional
from functools import wraps

class RetryConfig:
    """Configuration for retry behavior."""
    def __init__(self, max_attempts: int = 3, base_delay: float = 1.0, max_delay: float = 30.0, backoff_factor: float = 2.0):
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor

def retry_on_failure(config: RetryConfig, retryable_errors: tuple = (Exception,)):
    """
    Decorator that retries a function on specified exceptions.
    
    Args:
        config: RetryConfig with retry parameters
        retryable_errors: Tuple of exception types to retry on
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs) -> Any:
            last_exception = None
            for attempt in range(config.max_attempts):
                try:
                    return await func(*args, **kwargs)
                except retryable_errors as e:
                    last_exception = e
                    if attempt < config.max_attempts - 1:
                        delay = min(config.base_delay * (config.backoff_factor ** attempt), config.max_delay)
                        await asyncio.sleep(delay)
                    # Continue to next attempt
            # All attempts failed
            raise last_exception
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs) -> Any:
            last_exception = None
            for attempt in range(config.max_attempts):
                try:
                    return func(*args, **kwargs)
                except retryable_errors as e:
                    last_exception = e
                    if attempt < config.max_attempts - 1:
                        delay = min(config.base_delay * (config.backoff_factor ** attempt), config.max_delay)
                        time.sleep(delay)
                    # Continue to next attempt
            # All attempts failed
            raise last_exception
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator