# chat/views.py
from __future__ import annotations

from django.db import  IntegrityError, transaction

from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from challenges.models import FlagSolution, TextSolution  # adjust if app name differs
from .llm import call_coach_llm
from .serializers import ChatRequestSerializer

from django.utils import timezone

from django.db import DatabaseError
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from challenges.models import Challenge
from .models import ChatThread, ChatTurn
from .pagination import ChatTurnCursorPagination
from .serializers import ChatHistoryQuerySerializer, ChatTurnHistorySerializer



class ChatPracticeThrottle(UserRateThrottle):
    scope = "chat_practice"


# ----------------------------
# Safe response helpers
# ----------------------------
def safe_error(message: str, http_status: int = 400) -> Response:
    # Always DRF-friendly error key
    return Response({"detail": message}, status=http_status)


def safe_ok(reply: str, turn_id: str | None = None, created_at: str | None = None,
            percent: int | None = None) -> Response:
    payload = {"reply": reply}
    if turn_id is not None:
        payload["id"] = str(turn_id)
    if created_at is not None:
        payload["created_at"] = created_at
    if percent is not None:
        payload["percent_on_track"] = int(percent)
    return Response(payload, status=status.HTTP_200_OK)


def _get_challenge_blob(ch: Challenge) -> dict:
    return {
        "id": ch.id,
        "title": ch.title,
        "description": ch.description,
        "constraints": ch.constraints,
        "input_format": ch.input_format,
        "output_format": ch.output_format,
        "sample_input": ch.sample_input,
        "sample_output": ch.sample_output,
        "solution_type": getattr(ch.solution_type, "type", None) if ch.solution_type_id else None,
        "question_type": ch.question_type,
    }


def _get_solution_for_challenge(ch: Challenge) -> dict:
    """
    Retrieves correct solution used internally for coaching/grading.
    Must never be returned to user.
    """
    try:
        flag = (
            FlagSolution.objects.filter(challenges=ch)
            .values_list("value", flat=True)
            .first()
        )
        if flag:
            return {"type": "flag", "value": flag}

        text = (
            TextSolution.objects.filter(challenges=ch)
            .values_list("content", flat=True)
            .first()
        )
        if text:
            return {"type": "text", "value": text}
    except DatabaseError:
        # DB read error — fail safe
        return {"type": "none", "value": ""}

    return {"type": "none", "value": ""}


def _recent_turns(thread: ChatThread) -> list[dict]:
    try:
        qs = thread.turns.order_by("-created_at").only("role", "content")[:8]
        turns = list(qs)[::-1]
        return [{"role": t.role, "content": t.content} for t in turns]
    except DatabaseError:
        return []


def _user_can_access_challenge(user, ch: Challenge) -> bool:
    """
    Hook for your access control:
    - group_only challenges should check group membership here.
    """
    if not getattr(ch, "group_only", False):
        return True
    # TODO: implement real membership check
    return False


class PracticeChatView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [ChatPracticeThrottle]

    def post(self, request):
        """
        Never throws uncaught exceptions.
        Always returns user-friendly errors.
        """
        try:
            # 1) Validate input
            ser = ChatRequestSerializer(data=request.data)
            if not ser.is_valid():
                # return DRF validation errors (frontend already handles detail/message too)
                return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)

            user_text: str = (ser.validated_data["text"] or "").strip()
            challenge_id: int = ser.validated_data["challenge_id"]

            if not user_text:
                return safe_error("Please type a message so I can help.", 400)

            # hard cap again for safety
            user_text = user_text[:4000]

            # 2) Load challenge safely
            try:
                ch = (
                    Challenge.objects.select_related("solution_type")
                    .get(id=challenge_id, question_type="practice")
                )
            except Challenge.DoesNotExist:
                return safe_error("Challenge not found.", 404)
            except DatabaseError:
                return safe_error("Database error while loading challenge. Please try again.", 503)

            # 3) Permission check
            # if not _user_can_access_challenge(request.user, ch):
            #     return safe_error("This challenge is restricted.", 403)

            # 4) Retrieve ground truth solution (internal use only)
            solution = _get_solution_for_challenge(ch)
            if solution["type"] == "none":
                return safe_error("No solution configured for this challenge yet.", 409)

            # 5) Create thread + store turns (best-effort + atomic when possible)
            thread = None
            assistant_turn = None

            try:
                with transaction.atomic():
                    thread, _ = ChatThread.objects.select_for_update().get_or_create(
                        user=request.user,
                        challenge_id=challenge_id,
                    )
                    ChatTurn.objects.create(thread=thread, role="user", content=user_text)
                    recent = _recent_turns(thread)
            except IntegrityError:
                # race / unique constraint etc.
                thread = ChatThread.objects.filter(user=request.user, challenge_id=challenge_id).first()
                recent = _recent_turns(thread) if thread else []
            except DatabaseError:
                # If DB is down, we still try to provide AI response
                thread = None
                recent = []

            # 6) Call LLM (fully defensive)
            coach = call_coach_llm(
                user_text=user_text,
                challenge=_get_challenge_blob(ch),
                solution=solution,
                recent_turns=recent,
            )

            # 7) Save assistant turn (best effort)
            try:
                if thread:
                    assistant_turn = ChatTurn.objects.create(
                        thread=thread,
                        role="assistant",
                        content=coach.reply,
                        meta={"percent_on_track": coach.percent_on_track},
                    )
                    thread.updated_at = timezone.now()
                    thread.save(update_fields=["updated_at"])
            except DatabaseError:
                assistant_turn = None

            # 8) Respond
            if assistant_turn:
                return safe_ok(
                    reply=coach.reply,
                    turn_id=str(assistant_turn.id),
                    created_at=assistant_turn.created_at.isoformat(),
                    percent=coach.percent_on_track,
                )

            # If DB save failed, still return reply
            return safe_ok(
                reply=coach.reply,
                turn_id=str(int(timezone.now().timestamp())),
                created_at=timezone.now().isoformat(),
                percent=coach.percent_on_track,
            )

        except Exception:
            # Final catch-all: never leak internal errors
            return safe_error("Unexpected server error. Please try again.", 500)


class ChatThreadViewSet(viewsets.ViewSet):
    """
    Secure chat history:
    - Only authenticated users
    - Only the user's own thread for challenge_id
    - Cursor pagination (newest first)
    """
    permission_classes = [IsAuthenticated]
    pagination_class = ChatTurnCursorPagination

    def _validate_query(self, request):
        q = ChatHistoryQuerySerializer(data=request.query_params)
        if not q.is_valid():
            return None, Response(q.errors, status=status.HTTP_400_BAD_REQUEST)
        return q.validated_data, None

    def list(self, request):
        """
        GET /api/chat/thread/?challenge_id=123&cursor=...&page_size=20

        Response:
        {
          "thread_id": <int|null>,
          "challenge_id": <int>,
          "next": "<url|null>",
          "previous": "<url|null>",
          "messages": [ ... newest->oldest ... ]
        }
        """
        data, err = self._validate_query(request)
        if err:
            return err

        challenge_id = data["challenge_id"]

        # practice-only enforcement (matches PracticeChatView)
        try:
            Challenge.objects.only("id").get(id=challenge_id, question_type="practice")
        except Challenge.DoesNotExist:
            return safe_error("Challenge not found.", 404)
        except DatabaseError:
            return safe_error("Database error while loading challenge. Please try again.", 503)

        try:
            thread = (
                ChatThread.objects
                .filter(user=request.user, challenge_id=challenge_id)
                .only("id", "challenge_id")
                .first()
            )
        except DatabaseError:
            return safe_error("Database error while loading chat history. Please try again.", 503)

        if not thread:
            return Response(
                {"thread_id": None, "challenge_id": challenge_id, "next": None, "previous": None, "messages": []},
                status=status.HTTP_200_OK,
            )

        try:
            qs = ChatTurn.objects.filter(thread=thread).order_by("-created_at")
            paginator = self.pagination_class()
            page = paginator.paginate_queryset(qs, request, view=self)
            ser = ChatTurnHistorySerializer(page, many=True)
            paged = paginator.get_paginated_response(ser.data).data
        except DatabaseError:
            return safe_error("Database error while loading chat history. Please try again.", 503)

        return Response(
            {
                "thread_id": thread.id,
                "challenge_id": challenge_id,
                "next": paged.get("next"),
                "previous": paged.get("previous"),
                "messages": paged.get("results", []),
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["delete"], url_path="clear")
    def clear(self, request):
        """
        DELETE /api/chat/thread/clear/?challenge_id=123

        Clears only the requesting user's thread for that challenge.
        """
        data, err = self._validate_query(request)
        if err:
            return err

        challenge_id = data["challenge_id"]

        # practice-only enforcement
        try:
            Challenge.objects.only("id").get(id=challenge_id, question_type="practice")
        except Challenge.DoesNotExist:
            return safe_error("Challenge not found.", 404)
        except DatabaseError:
            return safe_error("Database error while loading challenge. Please try again.", 503)

        try:
            thread = ChatThread.objects.filter(user=request.user, challenge_id=challenge_id).first()
            if not thread:
                return Response({"cleared": False}, status=status.HTTP_200_OK)

            ChatTurn.objects.filter(thread=thread).delete()
            thread.delete()
            return Response({"cleared": True}, status=status.HTTP_200_OK)
        except DatabaseError:
            return safe_error("Database error while clearing chat. Please try again.", 503)

