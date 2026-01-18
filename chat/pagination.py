# chat/pagination.py
from __future__ import annotations

from rest_framework.pagination import CursorPagination


class ChatTurnCursorPagination(CursorPagination):
    """
    Newest-first cursor pagination.
    - First page: latest messages
    - next: older messages
    """

    page_size = 20
    ordering = "-created_at"
    cursor_query_param = "cursor"
    page_size_query_param = "page_size"
    max_page_size = 100
