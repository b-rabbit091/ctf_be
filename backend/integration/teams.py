import traceback
import requests
from django.conf import settings

from backend.metrics import teams_notifications_total

MAX_TRACEBACK_CHARS = 3500


def _safe_str(value):
    try:
        return "" if value is None else str(value)
    except Exception:
        return repr(value)


def _get_request_facts(request, status_code, exception, source):
    path = request.get_full_path() if request else ""
    method = request.method if request else ""
    user = ""
    if request and hasattr(request, "user"):
        try:
            user = _safe_str(request.user)
        except Exception:
            user = ""

    remote_addr = ""
    if request:
        try:
            remote_addr = _safe_str(request.META.get("REMOTE_ADDR", ""))
        except Exception:
            remote_addr = ""

    facts = [
        {"title": "Path", "value": _safe_str(path)},
        {"title": "Method", "value": _safe_str(method)},
        {"title": "Status", "value": _safe_str(status_code)},
        {"title": "Exception", "value": _safe_str(_format_exception_line(exception))},
        {"title": "User", "value": _safe_str(user)},
        {"title": "Remote", "value": _safe_str(remote_addr)},
        {"title": "Source", "value": _safe_str(source)},
    ]
    return facts


def _format_exception_line(exception):
    if exception is None:
        return ""
    return f"{type(exception).__name__}: {exception}"


def _format_traceback(exception):
    if exception is None:
        return ""
    tb = "".join(traceback.format_exception(type(exception), exception, exception.__traceback__))
    return tb[:MAX_TRACEBACK_CHARS]


def _build_card(title, facts, traceback_text):
    return {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.3",
        "body": [
            {"type": "TextBlock", "size": "Large", "weight": "Bolder", "text": title},
            {"type": "FactSet", "facts": facts},
            {"type": "TextBlock", "text": traceback_text, "wrap": True, "fontType": "Monospace"},
        ],
    }


def _post_card(card):
    url = getattr(settings, "TEAMS_WEBHOOK_URL", "")
    if not url:
        return

    title = card.get("body", [{}])[0].get("text", "")
    facts = card.get("body", [{}, {}])[1].get("facts", [])

    status = next((f["value"] for f in facts if f["title"] == "Status"), "")
    path = next((f["value"] for f in facts if f["title"] == "Path"), "")
    method = next((f["value"] for f in facts if f["title"] == "Method"), "")
    exception = next((f["value"] for f in facts if f["title"] == "Exception"), "")

    message = f"""🚨 {title}

Status: {status}
Method: {method}
Path: {path}
Issue: {exception}
"""

    payload = {
        "message": message.strip()
    }

    try:
        requests.post(url, json=payload, timeout=5)
        teams_notifications_total.labels(source="teams", status=str(r.status_code)).inc()

    except Exception:
        teams_notifications_total.labels(source="teams", status="exception").inc()
        pass


def should_report_status(status_code):
    return status_code is not None and status_code >= 400


def send_teams_exception(title, exception=None, request=None, status_code=None, source="exception"):
    if not should_report_status(status_code) and exception is None:
        return

    facts = _get_request_facts(request, status_code, exception, source)
    tb = _format_traceback(exception)
    card = _build_card(title, facts, tb)
    _post_card(card)


from rest_framework.views import exception_handler as drf_default_exception_handler


def drf_exception_handler(exc, context):
    response = drf_default_exception_handler(exc, context)

    req = context.get("request")
    status = getattr(response, "status_code", None)

    if should_report_status(status):
        send_teams_exception("API Exception", exc, request=req, status_code=status, source="drf")
        if req is not None:
            setattr(req, "_teams_reported", True)

    return response