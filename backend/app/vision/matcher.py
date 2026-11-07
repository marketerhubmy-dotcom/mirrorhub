from .state import ScreenAnalysis, ButtonTarget

# Common automation action labels
COMMON_ACTIONS = {
    "generate", "continue", "done", "next", "share", "cancel", "retry",
    "back", "ok", "confirm", "allow", "deny", "post", "draft", "schedule",
    "export", "save", "close", "dismiss", "skip", "add", "select",
    "new project", "create", "gallery", "media", "script",
}


def find_button(analysis: ScreenAnalysis, *candidates: str) -> ButtonTarget | None:
    """Find the best matching button from candidates (exact match, then partial)."""
    lower_candidates = {c.lower() for c in candidates}

    # Exact match
    for btn in analysis.buttons:
        if btn.text.lower() in lower_candidates:
            return btn

    # Partial match (candidate substring in button text)
    for btn in analysis.buttons:
        for c in lower_candidates:
            if c in btn.text.lower():
                return btn

    # Partial match (button text substring in candidate)
    for btn in analysis.buttons:
        for c in lower_candidates:
            if btn.text.lower() in c:
                return btn

    return None


def find_all_buttons(analysis: ScreenAnalysis, *candidates: str) -> list[ButtonTarget]:
    """Return all buttons matching any candidate."""
    lower_candidates = {c.lower() for c in candidates}
    result = []
    for btn in analysis.buttons:
        if any(c in btn.text.lower() or btn.text.lower() in c for c in lower_candidates):
            result.append(btn)
    return result


def score_button(btn: ButtonTarget, target: str) -> float:
    """0–1 relevance score for a button vs a target string."""
    target_lower = target.lower()
    text_lower = btn.text.lower()
    if text_lower == target_lower:
        return btn.confidence
    if target_lower in text_lower or text_lower in target_lower:
        return btn.confidence * 0.7
    return 0.0


def best_button(analysis: ScreenAnalysis, *candidates: str) -> ButtonTarget | None:
    """Return the button with the highest combined score across all candidates."""
    scored = []
    for btn in analysis.buttons:
        score = max(score_button(btn, c) for c in candidates)
        if score > 0:
            scored.append((score, btn))
    if not scored:
        return None
    scored.sort(key=lambda t: t[0], reverse=True)
    return scored[0][1]
