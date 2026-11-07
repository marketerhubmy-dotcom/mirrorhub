"""
Caption and hashtag builder for TikTok posts.

Responsibilities:
- Assemble the final caption string from raw caption + hashtag list
- Resolve {{variable}} placeholders
- Preserve emoji, UTF-8 characters, and line breaks
- Support configurable hashtag ordering (append / prepend)
"""
import re

from .constants import HASHTAG_SEPARATOR, HASHTAG_ORDER

_VAR_RE = re.compile(r"\{\{(\w+)\}\}")


def resolve_variables(text: str, variables: dict[str, str]) -> str:
    """Replace {{var_name}} tokens with values from variables dict."""
    def _replace(m: re.Match) -> str:
        return variables.get(m.group(1), m.group(0))
    return _VAR_RE.sub(_replace, text)


def format_hashtags(hashtags: list[str]) -> str:
    """
    Convert a list like ["fyp", "viral", "tiktok"] to "#fyp #viral #tiktok".
    Strips leading # if already present to avoid doubling.
    """
    tags = [
        f"#{t.lstrip('#').strip()}"
        for t in hashtags
        if t and t.strip()
    ]
    return HASHTAG_SEPARATOR.join(tags)


def build_caption(
    caption: str,
    hashtags: list[str],
    variables: dict[str, str] | None = None,
) -> str:
    """
    Assemble the final TikTok caption.

    Args:
        caption:   Raw caption text (may contain {{variables}} and emoji).
        hashtags:  List of hashtag strings (with or without leading #).
        variables: Optional dict for {{placeholder}} resolution.

    Returns:
        UTF-8 caption string ready to paste into TikTok.
    """
    caption = caption.strip()

    if variables:
        caption = resolve_variables(caption, variables)

    tag_str = format_hashtags(hashtags)

    if not tag_str:
        return caption

    if HASHTAG_ORDER == "prepend":
        parts = [tag_str, caption] if caption else [tag_str]
    else:
        parts = [caption, tag_str] if caption else [tag_str]

    return "\n\n".join(p for p in parts if p)


def split_for_input(caption: str) -> list[str]:
    """
    Split the caption into lines suitable for ADB input text.

    TikTok's caption field handles newlines when entered via 'input text',
    so we just split on \\n and return non-empty segments.
    """
    return [line for line in caption.split("\n") if line.strip()]
