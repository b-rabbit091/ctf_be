"""
Function execution logging decorator for comprehensive tracing.
Logs every function call with parameters, return values, and exceptions.
"""
import logging
import time
import functools
import traceback
from typing import Any, Callable
import inspect

logger = logging.getLogger('monitoring')


def log_function_execution(
    log_args: bool = True,
    log_result: bool = True,
    log_exceptions: bool = True,
    max_arg_length: int = 500,
    exclude_args: list = None
):
    """
    Decorator to log function execution with detailed information.

    Args:
        log_args: Whether to log function arguments
        log_result: Whether to log function return value
        log_exceptions: Whether to log exceptions
        max_arg_length: Maximum length for argument values in logs
        exclude_args: List of argument names to exclude from logging (e.g., passwords)

    Usage:
        @log_function_execution()
        def my_function(arg1, arg2):
            return result
    """
    exclude_args = exclude_args or ['password', 'token', 'secret', 'api_key']

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            func_name = f"{func.__module__}.{func.__qualname__}"
            start_time = time.time()

            # Get function signature
            sig = inspect.signature(func)
            bound_args = sig.bind_partial(*args, **kwargs)
            bound_args.apply_defaults()

            # Prepare log data
            log_data = {
                'event': 'function_call',
                'function': func_name,
                'module': func.__module__,
                'line': func.__code__.co_firstlineno,
            }

            # Log arguments (sanitized)
            if log_args:
                sanitized_args = {}
                for arg_name, arg_value in bound_args.arguments.items():
                    if arg_name.lower() in exclude_args:
                        sanitized_args[arg_name] = '***REDACTED***'
                    else:
                        arg_str = str(arg_value)
                        if len(arg_str) > max_arg_length:
                            arg_str = arg_str[:max_arg_length] + '...'
                        sanitized_args[arg_name] = arg_str
                log_data['arguments'] = sanitized_args

            logger.debug(f'Function called: {func_name}', extra=log_data)

            try:
                # Execute function
                result = func(*args, **kwargs)

                duration = time.time() - start_time

                # Prepare success log
                success_log_data = {
                    'event': 'function_completed',
                    'function': func_name,
                    'duration_seconds': round(duration, 4),
                    'duration_ms': round(duration * 1000, 2),
                    'status': 'success',
                }

                # Log result (sanitized)
                if log_result and result is not None:
                    result_str = str(result)
                    if len(result_str) > max_arg_length:
                        result_str = result_str[:max_arg_length] + '...'
                    success_log_data['result_preview'] = result_str
                    success_log_data['result_type'] = type(result).__name__

                logger.debug(f'Function completed: {func_name}', extra=success_log_data)

                return result

            except Exception as e:
                duration = time.time() - start_time

                # Prepare error log
                error_log_data = {
                    'event': 'function_exception',
                    'function': func_name,
                    'duration_seconds': round(duration, 4),
                    'duration_ms': round(duration * 1000, 2),
                    'status': 'error',
                    'exception_type': type(e).__name__,
                    'exception_message': str(e),
                    'traceback': traceback.format_exc(),
                }

                if log_exceptions:
                    logger.error(
                        f'Function raised exception: {func_name}',
                        extra=error_log_data,
                        exc_info=True
                    )

                # Re-raise the exception
                raise

        return wrapper
    return decorator