"""AI explain chat: a per-user, per-case conversation grounded in the case evidence (see copilot.py).

A turn is persisted only after the LLM answered and passed validation, so a failed call leaves no dangling
question. Earlier turns are sent back to the model so follow-up questions ("and the second account?") work."""

from __future__ import annotations

from typing import Any

from trace.application import copilot
from trace.infrastructure.container import Container

HISTORY_LIMIT = 100


def _turns(messages: list[dict[str, Any]]) -> list[dict[str, str]]:
    out = []
    for m in messages:
        body = m["content"]
        text = body.get("text") if m["role"] == "user" else (body.get("answer") or {}).get("answer")
        if text:
            out.append({"role": m["role"], "content": str(text)})
    return out


def present(m: dict[str, Any]) -> dict[str, Any]:
    body = m["content"]
    return {"id": m["id"], "role": m["role"], "created_at": m["created_at"],
            "text": body.get("text") if m["role"] == "user" else None,
            "answer": body.get("answer") if m["role"] == "assistant" else None}


def history(c: Container, case_id: str, username: str) -> list[dict[str, Any]]:
    return [present(m) for m in c.chat.history(case_id, username, HISTORY_LIMIT)]


def ask(c: Container, case: dict[str, Any], message: str, username: str) -> dict[str, Any]:
    """Returns the saved assistant message. Raises LlmError / CopilotError without saving anything."""
    prior = c.chat.history(case["id"], username, HISTORY_LIMIT)
    answer = copilot.ask(c, case, message, c.llm, username, history=_turns(prior))
    c.chat.add(case["id"], username, "user", {"text": message.strip()})
    saved = c.chat.add(case["id"], username, "assistant", {"answer": answer})
    return present(saved)


def clear(c: Container, case_id: str, username: str) -> None:
    c.chat.clear(case_id, username)
    c.audit.append(case_id, username, "clear_chat", {})
