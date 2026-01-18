from __future__ import annotations

# chat/utils.py
import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol

from django.db import DatabaseError, IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from challenges.models import Challenge, FlagSolution, TextSolution
from chat.models import ChatThread, ChatTurn


class SolutionUtils:
    def __init__(self):
        self.Challenge = None

    def get_flag_solution_for_challenge(ch: Challenge) -> dict:
        try:
            flag = FlagSolution.objects.filter(challenges=ch).values_list("value", flat=True).first()
            return {"type": "flag", "value": flag}

        except DatabaseError:
            # DB read error — fail safe
            return {"type": None, "value": None}

    def get_text_solution_for_challenge(ch: Challenge) -> dict:
        try:
            text = TextSolution.objects.filter(challenges=ch).values_list("content", flat=True).first()

            return {"type": "text", "value": text}

        except DatabaseError:
            # DB read error — fail safe
            return {"type": None, "value": None}


# ----------------------------
# Shared helpers
# ----------------------------


def clamp_percent(n: Any) -> int:
    try:
        n = int(n)
    except Exception:
        return 50
    return max(0, min(100, n))


def _safe_json_loads(s: str) -> Optional[dict]:
    try:
        obj = json.loads(s)
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def safe_extract_json_from_text(text: str) -> Optional[dict]:
    """
    Accepts:
      - pure JSON string
      - text containing JSON object somewhere
    Returns dict or None.
    """
    if not text:
        return None
    text = text.strip()

    obj = _safe_json_loads(text)
    if obj:
        return obj

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = text[start : end + 1]
        obj = _safe_json_loads(candidate)
        if obj:
            return obj
    return None


# ----------------------------
# Provider interface + errors
# ----------------------------


class LLMClient(Protocol):
    def generate_text(self, messages: List[Dict[str, Any]]) -> str:
        """Return raw text from provider (should be JSON per prompt)."""
        ...


@dataclass
class LLMTransientError(Exception):
    code: str  # "timeout" | "rate_limited" | "transient"
    message: str = ""


# ----------------------------
# OpenAI implementation
# ----------------------------


class OpenAIClient:
    def __init__(self, *, timeout_s: int, model: Optional[str] = None):
        # Lazy import so project doesn't require openai unless used
        import httpx
        from openai import OpenAI

        self.model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not set")

        http_client = httpx.Client(timeout=httpx.Timeout(timeout_s, connect=10.0))
        self.client = OpenAI(api_key=api_key, http_client=http_client)

    def generate_text(self, messages: List[Dict[str, Any]]) -> str:
        try:
            resp = self.client.responses.create(
                model=self.model,
                input=messages,  # openai-python accepts role/content messages here
            )
            return (resp.output_text or "").strip()
        except Exception as e:
            name = e.__class__.__name__.lower()
            msg = str(e)
            if "timeout" in name:
                raise LLMTransientError(code="timeout", message="timeout")
            if "rate" in name or "429" in msg:
                raise LLMTransientError(code="rate_limited", message="rate limited")
            # treat as transient unless you want stricter behavior
            raise LLMTransientError(code="transient", message="openai transient")


# ----------------------------
# Gemini implementation (Google Gen AI SDK)
# ----------------------------


class GeminiClient:
    """
    Uses Google Gen AI SDK (google-genai), which is the recommended library. :contentReference[oaicite:2]{index=2}
    """

    def __init__(self, *, timeout_s: int, model: Optional[str] = None):
        # Lazy import so project doesn't require google-genai unless used
        from google import genai

        self.model = model or os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not set")

        # The SDK uses its own transport; timeout is best enforced at server/gunicorn level,
        # but we still keep timeout_s for symmetry/config.
        self.client = genai.Client(api_key=api_key)

    def generate_text(self, messages: List[Dict[str, Any]]) -> str:
        """
        Convert role/content messages into a single prompt block.
        (Gemini supports chat-style too, but this keeps a clean minimal adapter.)
        """
        # Build a single string prompt with role tags
        parts: List[str] = []
        for m in messages:
            role = (m.get("role") or "user").upper()
            content = m.get("content") or ""
            parts.append(f"{role}:\n{content}\n")
        prompt = "\n".join(parts).strip()

        try:
            resp = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
            )
            # SDK responses can vary; text property is commonly available
            text = getattr(resp, "text", None)
            if text is None:
                # fallback: try dict-like
                text = str(resp)
            return str(text).strip()
        except Exception as e:
            name = e.__class__.__name__.lower()
            msg = str(e)
            if "timeout" in name:
                raise LLMTransientError(code="timeout", message="timeout")
            if "429" in msg or "rate" in msg.lower():
                raise LLMTransientError(code="rate_limited", message="rate limited")
            raise LLMTransientError(code="transient", message="gemini transient")


# ----------------------------
# Factory (single place to choose provider)
# ----------------------------


def get_llm_client(*, provider: str, timeout_s: int, model: Optional[str]) -> LLMClient:
    provider = (provider or "openai").lower().strip()

    if provider == "openai":
        return OpenAIClient(timeout_s=timeout_s, model=model)

    if provider == "gemini":
        return GeminiClient(timeout_s=timeout_s, model=model)

    raise ValueError(f"Unknown LLM_PROVIDER '{provider}'. Use 'openai' or 'gemini'.")


class LlmUtils:
    def __init__(self):
        self.Challenge = Challenge

    def get_or_create_thread_safely(*, user, challenge_id: int) -> ChatThread | None:
        """
        Creates or fetches the thread for (user, challenge_id).
        Uses atomic + select_for_update for correctness, with fallback for race conditions.
        Returns None on DB failure.
        """
        try:
            with transaction.atomic():
                thread, _ = ChatThread.objects.select_for_update().get_or_create(
                    user=user,
                    challenge_id=challenge_id,
                )
                return thread
        except IntegrityError:
            # Unique constraint race: fetch existing
            try:
                return ChatThread.objects.filter(user=user, challenge_id=challenge_id).first()
            except DatabaseError:
                return None
        except DatabaseError:
            return None

    def append_turn_best_effort(*, thread: ChatThread, role: str, content: str, meta: dict | None = None) -> ChatTurn | None:
        """
        Best-effort DB write for a turn.
        """
        try:
            return ChatTurn.objects.create(
                thread=thread,
                role=role,
                content=content,
                meta=meta or {},
            )
        except DatabaseError:
            return None

    def touch_thread_best_effort(thread: ChatThread) -> None:
        try:
            thread.updated_at = timezone.now()
            thread.save(update_fields=["updated_at"])
        except DatabaseError:
            pass


def get_challenge_blob(ch: Challenge) -> dict:
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


def parse_iso_dt(value: Optional[str], field_name: str) -> Optional[timezone.datetime]:
    """
    Accepts ISO strings like:
      - 2026-01-16T00:00:00Z
      - 2026-01-16T00:00:00+00:00
    Returns aware datetime or None.
    """
    if not value:
        return None
    try:
        dt = timezone.datetime.fromisoformat(value.replace("Z", "+00:00"))
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt, timezone.get_current_timezone())
        return dt
    except Exception:
        raise ValidationError({field_name: f"Invalid datetime format: {value}. Use ISO like 2026-01-16T00:00:00Z"})


def apply_time_window(qs, dt_from: Optional[timezone.datetime], dt_to: Optional[timezone.datetime]):
    if dt_from:
        qs = qs.filter(submitted_at__gte=dt_from)
    if dt_to:
        qs = qs.filter(submitted_at__lte=dt_to)
    return qs


def get_solution_label(challenge: Challenge) -> str:
    """
    Normalizes SolutionType.type into one of: flag | procedure | both
    """
    raw = (getattr(getattr(challenge, "solution_type", None), "type", "") or "").strip().lower()
    if raw in {"flag", "procedure", "flag and procedure"}:
        return raw
    # safest default: treat unknown as both? NO — deny by forcing caller to decide.
    return raw


def one_correct_solution(challenge: Challenge) -> Dict[str, Any]:
    """
    Admin-only payload (should never be returned to normal users).
    Returns ONE correct solution for each type if available.
    """
    sol = get_solution_label(challenge)

    flag_val = None
    proc_val = None

    if sol in ("flag", "flag and procedure"):
        flag_val = FlagSolution.objects.filter(challenges=challenge).values_list("value", flat=True).first()

    if sol in ("procedure", "flag and procedure"):
        proc_val = TextSolution.objects.filter(challenges=challenge).values_list("content", flat=True).first()

    return {
        "solution_type": sol,
        "flag_solution": flag_val,
        "procedure_solution": proc_val,
    }


def safe_status_str(status_obj) -> Optional[str]:
    try:
        return getattr(status_obj, "status", None)
    except Exception:
        return None


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


def latest_attempt(attempts: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not attempts:
        return None
    # submitted_at is always present; fall back to now (shouldn't happen)
    return max(attempts, key=lambda a: a.get("submitted_at") or timezone.now())


def best_score(attempts: List[Dict[str, Any]]) -> int:
    if not attempts:
        return 0
    return max(safe_int(a.get("score"), 0) for a in attempts)


def to_user_entity(user_obj) -> Dict[str, Any]:
    return {
        "username": user_obj.username,
    }


def to_group_entity(group_obj) -> Dict[str, Any]:
    # assumes Group has `id` and `name`
    return {
        "name": getattr(group_obj, "name", str(group_obj.id)),
    }
