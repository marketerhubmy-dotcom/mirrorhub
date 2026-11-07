"""
Structured AI reasoning engine.

Every agent decision passes through reason() which:
  1. Calls GPT-4o-mini with a structured JSON prompt
  2. Returns a Reasoning dataclass with decision / reason / confidence / alternative / expected_result
  3. If confidence < FAILSAFE_THRESHOLD, sets was_failsafe=True (caller decides whether to act)

Callers MUST record decisions via repository.record_decision().
"""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass

from app.core.config import settings

logger = logging.getLogger(__name__)

FAILSAFE_THRESHOLD = 0.60  # below this → return failsafe flag


@dataclass
class Reasoning:
    decision: str
    reason: str
    confidence: float        # 0.0 – 1.0
    alternative: str
    expected_result: str
    was_failsafe: bool = False


# ── Public API ────────────────────────────────────────────────────────────────

async def reason(
    context: str,
    options: list[str],
    *,
    agent_name: str = "agent",
) -> Reasoning:
    """
    Ask GPT to choose among `options` given `context`.

    Parameters
    ----------
    context:
        A plain-text description of the situation and relevant data.
    options:
        List of candidate decisions (strings).
    agent_name:
        Used in logging only.

    Returns a Reasoning. If GPT call fails, returns a FAILSAFE with confidence 0.
    """
    if not settings.openai_api_key:
        return Reasoning(
            decision=options[0] if options else "no_action",
            reason="OpenAI API key not set — cannot reason",
            confidence=0.0,
            alternative="Set OPENAI_API_KEY to enable AI reasoning",
            expected_result="Unknown",
            was_failsafe=True,
        )

    prompt = _build_prompt(context, options)
    try:
        result = await asyncio.to_thread(_call_openai, prompt)
        r = _parse_response(result, options)
        if r.confidence < FAILSAFE_THRESHOLD:
            r.was_failsafe = True
            logger.warning(
                "%s: low confidence %.2f for decision '%s' — flagging as failsafe",
                agent_name, r.confidence, r.decision,
            )
        return r
    except Exception as exc:
        logger.exception("%s: reasoning call failed: %s", agent_name, exc)
        return Reasoning(
            decision=options[0] if options else "no_action",
            reason=f"Reasoning engine error: {exc}",
            confidence=0.0,
            alternative="Manual review required",
            expected_result="Unknown",
            was_failsafe=True,
        )


# ── Prompt construction ───────────────────────────────────────────────────────

def _build_prompt(context: str, options: list[str]) -> str:
    options_str = "\n".join(f"- {o}" for o in options)
    return f"""You are an AI decision-making agent for a content automation platform.

CONTEXT:
{context}

AVAILABLE DECISIONS:
{options_str}

Respond with a JSON object containing:
- "decision": one of the available decisions (exact string)
- "reason": 1-2 sentences explaining why this decision was chosen
- "confidence": float between 0.0 and 1.0 (your confidence in this decision)
- "alternative": the next-best decision if primary fails
- "expected_result": 1 sentence describing what outcome you expect

JSON only. No extra text."""


def _call_openai(prompt: str) -> str:
    from app.services.ai_generator import _client
    resp = _client().chat.completions.create(
        model=settings.openai_model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=300,
        temperature=0.3,
        response_format={"type": "json_object"},
    )
    return resp.choices[0].message.content


def _parse_response(raw: str, options: list[str]) -> Reasoning:
    try:
        data = json.loads(raw)
        decision = data.get("decision", options[0] if options else "no_action")
        # Validate decision is in options
        if options and decision not in options:
            decision = options[0]
        return Reasoning(
            decision=decision,
            reason=str(data.get("reason", "")),
            confidence=float(data.get("confidence", 0.5)),
            alternative=str(data.get("alternative", "")),
            expected_result=str(data.get("expected_result", "")),
        )
    except Exception:
        return Reasoning(
            decision=options[0] if options else "no_action",
            reason="Could not parse reasoning response",
            confidence=0.0,
            alternative="Manual review",
            expected_result="Unknown",
            was_failsafe=True,
        )
