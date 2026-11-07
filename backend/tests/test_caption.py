"""Tests for TikTok caption builder."""
import pytest
from app.apps.tiktok.caption import (
    resolve_variables,
    format_hashtags,
    build_caption,
    split_for_input,
)


def test_resolve_variables_basic():
    text = "Hello {{name}}, buy {{product}} now!"
    result = resolve_variables(text, {"name": "Alice", "product": "shoes"})
    assert result == "Hello Alice, buy shoes now!"


def test_resolve_variables_missing_key():
    # Missing keys should be left as-is
    text = "Hello {{name}}"
    result = resolve_variables(text, {})
    assert "{{name}}" in result


def test_format_hashtags_basic():
    result = format_hashtags(["fyp", "viral", "trending"])
    assert result == "#fyp #viral #trending"


def test_format_hashtags_empty():
    assert format_hashtags([]) == ""


def test_format_hashtags_strips_hash_prefix():
    result = format_hashtags(["#fyp", "viral"])
    assert "#fyp" in result


def test_build_caption_append():
    result = build_caption("Check this out", ["fyp", "viral"], {})
    assert result.startswith("Check this out")
    assert "#fyp" in result
    assert "#viral" in result


def test_build_caption_empty_hashtags():
    result = build_caption("Just a caption", [], {})
    assert result == "Just a caption"


def test_build_caption_with_variables():
    result = build_caption("Buy {{item}} now", ["deals"], {"item": "shoes"})
    assert "Buy shoes now" in result


def test_split_for_input_multiline():
    result = split_for_input("Line one\nLine two")
    assert len(result) == 2
    assert result[0] == "Line one"


def test_split_for_input_single_line():
    result = split_for_input("No newlines here")
    assert result == ["No newlines here"]
