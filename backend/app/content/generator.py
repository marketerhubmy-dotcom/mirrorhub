"""
AI generation for Content Pipeline — MVP 0.6.

All functions accept a context dict built from ProductContentContext.
Synchronous; callers wrap in asyncio.to_thread().
"""
import json

from app.services.ai_generator import _client
from app.content.prompts import (
    build_brief_prompt,
    build_video_prompt_prompt,
    build_cover_hook_prompt,
    build_caption_prompt,
    build_hashtags_prompt,
)


def generate_brief(ctx: dict) -> dict:
    """Return {hook, story, cta}."""
    resp = _client().chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": build_brief_prompt(ctx)}],
        max_tokens=400,
        temperature=0.8,
        response_format={"type": "json_object"},
    )
    try:
        data = json.loads(resp.choices[0].message.content)
        return {
            "hook": data.get("hook", ""),
            "story": data.get("story", ""),
            "cta": data.get("cta", ""),
        }
    except Exception:
        return {"hook": "", "story": "", "cta": ""}


def generate_video_prompt(ctx: dict) -> str:
    resp = _client().chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": build_video_prompt_prompt(ctx)}],
        max_tokens=350,
        temperature=0.7,
    )
    return resp.choices[0].message.content.strip()


def generate_cover_hook(ctx: dict) -> str:
    resp = _client().chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": build_cover_hook_prompt(ctx)}],
        max_tokens=80,
        temperature=0.9,
    )
    return resp.choices[0].message.content.strip()


def generate_caption(ctx: dict) -> str:
    resp = _client().chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": build_caption_prompt(ctx)}],
        max_tokens=200,
        temperature=0.8,
    )
    return resp.choices[0].message.content.strip()


def generate_hashtags(ctx: dict) -> list[str]:
    resp = _client().chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": build_hashtags_prompt(ctx)}],
        max_tokens=120,
        temperature=0.6,
        response_format={"type": "json_object"},
    )
    try:
        data = json.loads(resp.choices[0].message.content)
        tags = data.get("hashtags", [])
        # Keep only 3–5 valid hashtags
        valid = [t for t in tags if t.startswith("#")][:5]
        return valid
    except Exception:
        return []
