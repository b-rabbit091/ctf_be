import logging
import time
import json
import sys
import traceback
from django.utils.deprecation import MiddlewareMixin
from django.urls import resolve
from django.core.serializers.json import DjangoJSONEncoder
from backend.integration.teams import send_teams_exception, should_report_status


logger = logging.getLogger('monitoring')
request_logger = logging.getLogger('django.request')
exception_logger = logging.getLogger('backend')


class RequestLoggingMiddleware(MiddlewareMixin):
    """
    Middleware to log all HTTP requests and responses with detailed metrics.
    Integrates with Prometheus for monitoring.
    Logs EVERY detail including request/response bodies.
    """

    SENSITIVE_KEYS = [
        'password', 'token', 'secret', 'api_key', 'access_token',
        'refresh_token', 'authorization', 'auth', 'csrf', 'session'
    ]

    MAX_BODY_LOG_SIZE = 5000  # Max characters to log for request/response body

    def process_request(self, request):
        """Log request start with full details."""
        request._start_time = time.time()
        request._request_id = self._generate_request_id(request)

        # Extract request metadata
        request_data = {
            'request_id': request._request_id,
            'method': request.method,
            'path': request.path,
            'full_path': request.get_full_path(),
            'content_type': request.content_type,
            'user_agent': request.META.get('HTTP_USER_AGENT', ''),
            'remote_addr': self._get_client_ip(request),
            'user': str(request.user) if hasattr(request, 'user') else 'Anonymous',
            'user_id': request.user.id if hasattr(request, 'user') and hasattr(request.user, 'id') else None,
            'event': 'request_started',
        }

        # Log query parameters (sanitized)
        if request.GET:
            request_data['query_params'] = self._sanitize_data(dict(request.GET))

        # Log request headers (sanitized)
        headers = {}
        for key, value in request.META.items():
            if key.startswith('HTTP_'):
                header_name = key[5:].replace('_', '-').title()
                if any(sensitive in header_name.lower() for sensitive in self.SENSITIVE_KEYS):
                    headers[header_name] = '***REDACTED***'
                else:
                    headers[header_name] = value
        request_data['headers'] = headers

        # Log request body (sanitized)
        if request.method in ['POST', 'PUT', 'PATCH', 'DELETE']:
            try:
                if request.content_type == 'application/json':
                    body = json.loads(request.body.decode('utf-8'))
                    request_data['request_body'] = self._sanitize_data(body)
                elif request.content_type == 'application/x-www-form-urlencoded':
                    request_data['request_body'] = self._sanitize_data(dict(request.POST))
                else:
                    body_preview = request.body[:self.MAX_BODY_LOG_SIZE].decode('utf-8', errors='ignore')
                    request_data['request_body_preview'] = body_preview
                    request_data['request_body_size'] = len(request.body)
            except Exception as e:
                request_data['request_body_error'] = str(e)

        logger.info('HTTP Request Started', extra=request_data)

        # Increment in-progress counter
        endpoint = self._get_endpoint_name(request)


    def process_response(self, request, response):
        """Log response with full details."""
        duration = time.time() - getattr(request, '_start_time', time.time())
        endpoint = self._get_endpoint_name(request)
        status_code = response.status_code


        # Prepare response log data
        response_data = {
            'request_id': getattr(request, '_request_id', 'unknown'),
            'method': request.method,
            'path': request.path,
            'endpoint': endpoint,
            'status_code': status_code,
            'status_text': self._get_status_text(status_code),
            'duration_ms': round(duration * 1000, 2),
            'duration_seconds': round(duration, 3),
            'user': str(request.user) if hasattr(request, 'user') else 'Anonymous',
            'user_id': request.user.id if hasattr(request, 'user') and hasattr(request.user, 'id') else None,
            'remote_addr': self._get_client_ip(request),
            'event': 'request_completed',
        }

        # Log response headers
        response_headers = {}
        for key, value in response.items():
            if any(sensitive in key.lower() for sensitive in self.SENSITIVE_KEYS):
                response_headers[key] = '***REDACTED***'
            else:
                response_headers[key] = value
        response_data['response_headers'] = response_headers

        # Log response body (sanitized and truncated)
        try:
            content_type = response.get('Content-Type', '')
            if hasattr(response, 'content'):
                content_length = len(response.content)
                response_data['response_size'] = content_length

                if 'application/json' in content_type:
                    try:
                        body = json.loads(response.content.decode('utf-8'))
                        sanitized_body = self._sanitize_data(body)
                        # Truncate large responses
                        body_str = json.dumps(sanitized_body, cls=DjangoJSONEncoder)
                        if len(body_str) > self.MAX_BODY_LOG_SIZE:
                            response_data['response_body_preview'] = body_str[:self.MAX_BODY_LOG_SIZE] + '...'
                            response_data['response_body_truncated'] = True
                        else:
                            response_data['response_body'] = sanitized_body
                    except:
                        pass
                elif 'text/' in content_type:
                    text_content = response.content[:self.MAX_BODY_LOG_SIZE].decode('utf-8', errors='ignore')
                    response_data['response_body_preview'] = text_content
                    if content_length > self.MAX_BODY_LOG_SIZE:
                        response_data['response_body_truncated'] = True
        except Exception as e:
            response_data['response_body_error'] = str(e)

        # Log with appropriate level
        if status_code >= 500:
            logger.error('HTTP Request Failed', extra=response_data)
        elif status_code >= 400:
            logger.warning('HTTP Request Error', extra=response_data)
        else:
            logger.info('HTTP Request Completed', extra=response_data)

        return response

    def process_exception(self, request, exception):
        """Log exceptions with full traceback and context."""
        duration = time.time() - getattr(request, '_start_time', time.time())
        endpoint = self._get_endpoint_name(request)


        # Get full traceback
        exc_type, exc_value, exc_traceback = sys.exc_info()
        tb_lines = traceback.format_exception(exc_type, exc_value, exc_traceback)
        full_traceback = ''.join(tb_lines)

        # Get local variables from the exception frame
        local_vars = {}
        if exc_traceback:
            frame = exc_traceback.tb_frame
            local_vars = {k: str(v)[:200] for k, v in frame.f_locals.items()
                         if not k.startswith('_')}

        exception_data = {
            'request_id': getattr(request, '_request_id', 'unknown'),
            'method': request.method,
            'path': request.path,
            'endpoint': endpoint,
            'exception_type': type(exception).__name__,
            'exception_message': str(exception),
            'exception_module': exception.__class__.__module__,
            'traceback': full_traceback,
            'local_variables': self._sanitize_data(local_vars),
            'duration_ms': round(duration * 1000, 2),
            'user': str(request.user) if hasattr(request, 'user') else 'Anonymous',
            'user_id': request.user.id if hasattr(request, 'user') and hasattr(request.user, 'id') else None,
            'remote_addr': self._get_client_ip(request),
            'event': 'request_exception',
        }

        # Add request details
        if request.method in ['POST', 'PUT', 'PATCH']:
            try:
                if hasattr(request, 'body'):
                    body_preview = request.body[:500].decode('utf-8', errors='ignore')
                    exception_data['request_body_preview'] = body_preview
            except:
                pass

        exception_logger.error(
            f'HTTP Request Exception: {type(exception).__name__}',
            extra=exception_data,
            exc_info=True
        )

        # Let the exception propagate
        return None

    def _sanitize_data(self, data):
        """Recursively sanitize sensitive data from dictionaries."""
        if isinstance(data, dict):
            sanitized = {}
            for key, value in data.items():
                if any(sensitive in str(key).lower() for sensitive in self.SENSITIVE_KEYS):
                    sanitized[key] = '***REDACTED***'
                elif isinstance(value, (dict, list)):
                    sanitized[key] = self._sanitize_data(value)
                else:
                    # Truncate long values
                    value_str = str(value)
                    if len(value_str) > 500:
                        sanitized[key] = value_str[:500] + '...'
                    else:
                        sanitized[key] = value
            return sanitized
        elif isinstance(data, list):
            return [self._sanitize_data(item) for item in data[:50]]  # Limit list size
        else:
            return data

    def _get_status_text(self, status_code):
        """Get human-readable status text."""
        status_texts = {
            200: 'OK', 201: 'Created', 204: 'No Content',
            400: 'Bad Request', 401: 'Unauthorized', 403: 'Forbidden',
            404: 'Not Found', 405: 'Method Not Allowed', 429: 'Too Many Requests',
            500: 'Internal Server Error', 502: 'Bad Gateway', 503: 'Service Unavailable'
        }
        return status_texts.get(status_code, 'Unknown')

    @staticmethod
    def _generate_request_id(request):
        """Generate a unique request ID."""
        import uuid
        return request.META.get('HTTP_X_REQUEST_ID', str(uuid.uuid4()))

    @staticmethod
    def _get_client_ip(request):
        """Extract client IP address."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR', '')
        return ip

    @staticmethod
    def _get_endpoint_name(request):
        """Get a normalized endpoint name for metrics."""
        try:
            resolver_match = resolve(request.path)
            if resolver_match:
                return f"{resolver_match.app_name}:{resolver_match.url_name}" if resolver_match.app_name else resolver_match.url_name or request.path
        except Exception:
            pass
        return request.path


class TeamsExceptionMiddleware(MiddlewareMixin):
    """
    Middleware to report exceptions and error responses to Microsoft Teams.
    """

    def process_exception(self, request, exception):
        send_teams_exception(
            "Unhandled Server Exception",
            exception,
            request=request,
            status_code=500,
            source="middleware_exception",
        )
        setattr(request, "_teams_reported", True)
        return None

    def process_response(self, request, response):
        status = getattr(response, "status_code", None)
        if should_report_status(status) and not getattr(request, "_teams_reported", False):
            send_teams_exception(
                "HTTP Error Response",
                exception=None,
                request=request,
                status_code=status,
                source="middleware_response",
            )
            setattr(request, "_teams_reported", True)
        return response
