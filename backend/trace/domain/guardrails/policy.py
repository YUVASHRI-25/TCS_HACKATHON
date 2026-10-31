"""Guardrails: language policy and the non-negotiable notice text.

The notice strings are product policy (from the brief), not data.
"""

from __future__ import annotations

import re

GUARDRAIL_NOTICE = ("Decision support only. No determination has been made. "
                    "This network requires human investigation; a human investigator makes the final decision.")
DOSSIER_FOOTER = "Decision support only. No determination has been made."
DRAFT_WATERMARK = "DRAFT - Requires human review. Not submitted. No determination made."

BANNED_TERMS = ("guilty", "criminal", "fraudster", "confirmed fraud", "launderer")
_BANNED_RE = re.compile(r"\b(" + "|".join(re.escape(t) for t in BANNED_TERMS) + r")s?\b", re.I)

# Human workflow. "Escalated" means escalated to a senior investigator inside the institution;
# nothing is filed, frozen or submitted by TRACE.
REVIEW_ACTIONS = ("start_review", "escalate", "resolve", "reopen")
RESOLUTIONS = ("no_further_action", "false_positive", "referred_for_further_investigation")


class GuardrailViolation(ValueError):
    pass


def banned_terms_in(text: str) -> list[str]:
    return sorted({m.group(1).lower() for m in _BANNED_RE.finditer(text or "")})


def assert_clean(text: str) -> str:
    found = banned_terms_in(text)
    if found:
        raise GuardrailViolation(f"generated text contains banned terms: {found}")
    return text


def scrub(text: str) -> tuple[str, list[str]]:
    """Remove sentences containing banned terms (used for LLM output). Returns (text, removed)."""
    sentences = re.split(r"(?<=[.!?])\s+", text or "")
    kept, removed = [], []
    for s in sentences:
        (removed if banned_terms_in(s) else kept).append(s)
    return " ".join(kept), removed
