# chat/utils.py
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol

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



# chat/services.py

from django.db import DatabaseError, IntegrityError, transaction
from django.utils import timezone

from challenges.models import Challenge
from .models import ChatThread, ChatTurn


def get_practice_challenge_or_none(challenge_id: int) -> Challenge | None:
    """
    Strictly mirrors PracticeChatView: practice-only challenge.
    """
    try:
        return (
            Challenge.objects
            .select_related("solution_type")
            .only("id", "title", "description", "question_type", "solution_type")
            .get(id=challenge_id, question_type="practice")
        )
    except Challenge.DoesNotExist:
        return None


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
