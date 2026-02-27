"""
Prometheus metrics configuration and custom metrics for the CTF backend.
"""
from prometheus_client import Counter, Histogram, Gauge, Info
import time


# Request metrics
http_requests_total = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status_code']
)

http_request_duration_seconds = Histogram(
    'http_request_duration_seconds',
    'HTTP request latency in seconds',
    ['method', 'endpoint'],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)

http_requests_in_progress = Gauge(
    'http_requests_in_progress',
    'Number of HTTP requests in progress',
    ['method', 'endpoint']
)

# Error metrics
http_exceptions_total = Counter(
    'http_exceptions_total',
    'Total HTTP exceptions',
    ['method', 'endpoint', 'exception_type', 'status_code']
)

# LLM metrics
llm_requests_total = Counter(
    'llm_requests_total',
    'Total LLM API requests',
    ['provider', 'model', 'app', 'status']
)

llm_request_duration_seconds = Histogram(
    'llm_request_duration_seconds',
    'LLM request duration in seconds',
    ['provider', 'model', 'app'],
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 30.0, 60.0]
)

llm_tokens_used = Counter(
    'llm_tokens_used',
    'Total tokens used in LLM requests',
    ['provider', 'model', 'app', 'token_type']  # token_type: prompt, completion, total
)

llm_errors_total = Counter(
    'llm_errors_total',
    'Total LLM errors',
    ['provider', 'model', 'app', 'error_type']
)

llm_retry_attempts = Counter(
    'llm_retry_attempts',
    'Total LLM retry attempts',
    ['provider', 'model', 'app']
)

# Database metrics
db_query_duration_seconds = Histogram(
    'db_query_duration_seconds',
    'Database query duration in seconds',
    ['query_type'],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0]
)

db_connections_total = Gauge(
    'db_connections_total',
    'Total database connections',
    ['state']  # state: active, idle
)

# Authentication metrics
auth_attempts_total = Counter(
    'auth_attempts_total',
    'Total authentication attempts',
    ['method', 'status']  # status: success, failure
)

auth_active_sessions = Gauge(
    'auth_active_sessions',
    'Number of active user sessions'
)

# Challenge metrics
challenge_submissions_total = Counter(
    'challenge_submissions_total',
    'Total challenge submissions',
    ['challenge_id', 'status']  # status: correct, incorrect
)

challenge_attempts_per_user = Histogram(
    'challenge_attempts_per_user',
    'Number of attempts per user per challenge',
    ['challenge_id'],
    buckets=[1, 2, 3, 5, 10, 20, 50, 100]
)

challenge_solve_time_seconds = Histogram(
    'challenge_solve_time_seconds',
    'Time taken to solve a challenge in seconds',
    ['challenge_id'],
    buckets=[60, 300, 600, 1800, 3600, 7200, 14400, 86400]  # 1m to 1 day
)

# Chat metrics
chat_messages_total = Counter(
    'chat_messages_total',
    'Total chat messages',
    ['user_type']  # user_type: user, assistant
)

chat_session_duration_seconds = Histogram(
    'chat_session_duration_seconds',
    'Chat session duration in seconds',
    buckets=[60, 300, 600, 1800, 3600, 7200]
)

# Teams notification metrics
teams_notifications_total = Counter(
    'teams_notifications_total',
    'Total Teams notifications sent',
    ['source', 'status']  # status: success, failure
)

# Application info
app_info = Info('app_info', 'Application information')
app_info.info({
    'app': 'ctf_backend',
    'version': '1.0.0',
})

# System metrics
app_uptime_seconds = Gauge(
    'app_uptime_seconds',
    'Application uptime in seconds'
)

# File upload metrics
file_uploads_total = Counter(
    'file_uploads_total',
    'Total file uploads',
    ['file_type', 'status']  # status: success, failure
)

file_upload_size_bytes = Histogram(
    'file_upload_size_bytes',
    'File upload size in bytes',
    ['file_type'],
    buckets=[1024, 10240, 102400, 1048576, 10485760, 104857600]  # 1KB to 100MB
)


# Helper class for timing contexts
class MetricsTimer:
    """Context manager for timing operations."""

    def __init__(self, histogram, *labels):
        self.histogram = histogram
        self.labels = labels
        self.start_time = None

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.time() - self.start_time
        if self.labels:
            self.histogram.labels(*self.labels).observe(duration)
        else:
            self.histogram.observe(duration)
        return False


# Helper functions
def record_http_request(method, endpoint, status_code, duration):
    """Record HTTP request metrics."""
    http_requests_total.labels(
        method=method,
        endpoint=endpoint,
        status_code=status_code
    ).inc()

    http_request_duration_seconds.labels(
        method=method,
        endpoint=endpoint
    ).observe(duration)


def record_llm_request(provider, model, app, status, duration,
                      prompt_tokens=0, completion_tokens=0, total_tokens=0,
                      error_type=None):
    """Record LLM request metrics."""
    llm_requests_total.labels(
        provider=provider,
        model=model,
        app=app,
        status=status
    ).inc()

    llm_request_duration_seconds.labels(
        provider=provider,
        model=model,
        app=app
    ).observe(duration)

    if prompt_tokens > 0:
        llm_tokens_used.labels(
            provider=provider,
            model=model,
            app=app,
            token_type='prompt'
        ).inc(prompt_tokens)

    if completion_tokens > 0:
        llm_tokens_used.labels(
            provider=provider,
            model=model,
            app=app,
            token_type='completion'
        ).inc(completion_tokens)

    if total_tokens > 0:
        llm_tokens_used.labels(
            provider=provider,
            model=model,
            app=app,
            token_type='total'
        ).inc(total_tokens)

    if error_type:
        llm_errors_total.labels(
            provider=provider,
            model=model,
            app=app,
            error_type=error_type
        ).inc()


def record_exception(method, endpoint, exception_type, status_code):
    """Record exception metrics."""
    http_exceptions_total.labels(
        method=method,
        endpoint=endpoint,
        exception_type=exception_type,
        status_code=status_code
    ).inc()

