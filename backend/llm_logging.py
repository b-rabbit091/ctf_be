"""
LLM logging utilities for tracking all LLM API calls with detailed metrics.
"""
import logging
import time
import json
import functools
from typing import Any, Dict, Optional
from backend.metrics import record_llm_request, llm_retry_attempts

logger = logging.getLogger('llm')


class LLMLogger:
    """Structured logger for LLM interactions."""

    @staticmethod
    def log_request(provider: str, model: str, app: str, prompt: str,
                   temperature: Optional[float] = None,
                   max_tokens: Optional[int] = None,
                   request_id: Optional[str] = None,
                   user_id: Optional[str] = None,
                   **kwargs):
        """Log LLM request details."""
        log_data = {
            'event': 'llm_request',
            'provider': provider,
            'model': model,
            'app': app,
            'prompt_length': len(prompt) if prompt else 0,
            'temperature': temperature,
            'max_tokens': max_tokens,
            'request_id': request_id,
            'user_id': user_id,
        }
        log_data.update(kwargs)

        logger.info(f'LLM Request to {provider}/{model}', extra=log_data)

    @staticmethod
    def log_response(provider: str, model: str, app: str,
                    response_text: str, status: str,
                    duration: float,
                    prompt_tokens: int = 0,
                    completion_tokens: int = 0,
                    total_tokens: int = 0,
                    request_id: Optional[str] = None,
                    user_id: Optional[str] = None,
                    **kwargs):
        """Log LLM response details with metrics."""
        log_data = {
            'event': 'llm_response',
            'provider': provider,
            'model': model,
            'app': app,
            'status': status,
            'duration_seconds': round(duration, 3),
            'duration_ms': round(duration * 1000, 2),
            'response_length': len(response_text) if response_text else 0,
            'prompt_tokens': prompt_tokens,
            'completion_tokens': completion_tokens,
            'total_tokens': total_tokens,
            'request_id': request_id,
            'user_id': user_id,
        }
        log_data.update(kwargs)

        # Record Prometheus metrics
        record_llm_request(
            provider=provider,
            model=model,
            app=app,
            status=status,
            duration=duration,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens
        )

        if status == 'success':
            logger.info(f'LLM Response from {provider}/{model}', extra=log_data)
        else:
            logger.warning(f'LLM Response Failed from {provider}/{model}', extra=log_data)

    @staticmethod
    def log_error(provider: str, model: str, app: str,
                 error_type: str, error_message: str,
                 duration: float,
                 request_id: Optional[str] = None,
                 user_id: Optional[str] = None,
                 **kwargs):
        """Log LLM errors with metrics."""
        log_data = {
            'event': 'llm_error',
            'provider': provider,
            'model': model,
            'app': app,
            'error_type': error_type,
            'error_message': error_message,
            'duration_seconds': round(duration, 3),
            'request_id': request_id,
            'user_id': user_id,
        }
        log_data.update(kwargs)

        # Record Prometheus metrics
        record_llm_request(
            provider=provider,
            model=model,
            app=app,
            status='error',
            duration=duration,
            error_type=error_type
        )

        logger.error(f'LLM Error from {provider}/{model}: {error_type}', extra=log_data)

    @staticmethod
    def log_retry(provider: str, model: str, app: str,
                 retry_number: int, reason: str,
                 request_id: Optional[str] = None):
        """Log LLM retry attempts."""
        log_data = {
            'event': 'llm_retry',
            'provider': provider,
            'model': model,
            'app': app,
            'retry_number': retry_number,
            'reason': reason,
            'request_id': request_id,
        }

        llm_retry_attempts.labels(
            provider=provider,
            model=model,
            app=app
        ).inc()

        logger.warning(f'LLM Retry {retry_number} for {provider}/{model}', extra=log_data)


def track_llm_call(app: str):
    """
    Decorator to automatically track LLM calls with logging and metrics.

    Usage:
        @track_llm_call(app='chat')
        def call_llm(provider, model, prompt, **kwargs):
            # your LLM call logic
            return response
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Extract common parameters
            provider = kwargs.get('provider', 'unknown')
            model = kwargs.get('model', 'unknown')
            request_id = kwargs.get('request_id')
            user_id = kwargs.get('user_id')

            start_time = time.time()

            try:
                # Log the request
                LLMLogger.log_request(
                    provider=provider,
                    model=model,
                    app=app,
                    prompt=kwargs.get('prompt', ''),
                    temperature=kwargs.get('temperature'),
                    max_tokens=kwargs.get('max_tokens'),
                    request_id=request_id,
                    user_id=user_id
                )

                # Execute the function
                result = func(*args, **kwargs)

                duration = time.time() - start_time

                # Extract response details
                response_text = ''
                prompt_tokens = 0
                completion_tokens = 0
                total_tokens = 0

                if isinstance(result, dict):
                    response_text = result.get('text', result.get('content', ''))
                    usage = result.get('usage', {})
                    prompt_tokens = usage.get('prompt_tokens', 0)
                    completion_tokens = usage.get('completion_tokens', 0)
                    total_tokens = usage.get('total_tokens', 0)
                elif isinstance(result, str):
                    response_text = result

                # Log the response
                LLMLogger.log_response(
                    provider=provider,
                    model=model,
                    app=app,
                    response_text=response_text,
                    status='success',
                    duration=duration,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                    request_id=request_id,
                    user_id=user_id
                )

                return result

            except Exception as e:
                duration = time.time() - start_time

                # Log the error
                LLMLogger.log_error(
                    provider=provider,
                    model=model,
                    app=app,
                    error_type=type(e).__name__,
                    error_message=str(e),
                    duration=duration,
                    request_id=request_id,
                    user_id=user_id
                )

                # Re-raise the exception
                raise

        return wrapper
    return decorator


def export_llm_logs_to_json(output_file: str, start_date: Optional[str] = None,
                           end_date: Optional[str] = None) -> int:
    """
    Export LLM logs to JSON format for analysis.

    Args:
        output_file: Path to output JSON file
        start_date: Optional start date filter (YYYY-MM-DD)
        end_date: Optional end date filter (YYYY-MM-DD)

    Returns:
        Number of records exported
    """
    import re
    from pathlib import Path
    from datetime import datetime

    log_file = Path(__file__).resolve().parent.parent / 'logs' / 'llm_responses.log'

    if not log_file.exists():
        logger.warning(f'Log file not found: {log_file}')
        return 0

    records = []

    with open(log_file, 'r') as f:
        for line in f:
            try:
                record = json.loads(line.strip())

                # Filter by date if provided
                if start_date or end_date:
                    timestamp = record.get('timestamp', '')
                    if start_date and timestamp < start_date:
                        continue
                    if end_date and timestamp > end_date:
                        continue

                records.append(record)
            except json.JSONDecodeError:
                continue

    with open(output_file, 'w') as f:
        json.dump(records, f, indent=2)

    logger.info(f'Exported {len(records)} LLM log records to {output_file}')
    return len(records)


def export_llm_logs_to_csv(output_file: str, start_date: Optional[str] = None,
                          end_date: Optional[str] = None) -> int:
    """
    Export LLM logs to CSV format for analysis.

    Args:
        output_file: Path to output CSV file
        start_date: Optional start date filter (YYYY-MM-DD)
        end_date: Optional end date filter (YYYY-MM-DD)

    Returns:
        Number of records exported
    """
    import csv
    import json
    from pathlib import Path

    log_file = Path(__file__).resolve().parent.parent / 'logs' / 'llm_responses.log'

    if not log_file.exists():
        logger.warning(f'Log file not found: {log_file}')
        return 0

    records = []

    with open(log_file, 'r') as f:
        for line in f:
            try:
                record = json.loads(line.strip())

                # Filter by date if provided
                if start_date or end_date:
                    timestamp = record.get('timestamp', '')
                    if start_date and timestamp < start_date:
                        continue
                    if end_date and timestamp > end_date:
                        continue

                records.append(record)
            except json.JSONDecodeError:
                continue

    if not records:
        logger.warning('No records to export')
        return 0

    # Get all unique keys from all records
    fieldnames = set()
    for record in records:
        fieldnames.update(record.keys())
    fieldnames = sorted(list(fieldnames))

    with open(output_file, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)

    logger.info(f'Exported {len(records)} LLM log records to {output_file}')
    return len(records)

