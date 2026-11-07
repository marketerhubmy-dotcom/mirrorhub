"""
YouTube Create-specific screen fingerprints.

These complement the generic Vision Engine screen types with finer-grained
detection for screens that only exist inside the YouTube Create app.
They use visible_text intersection, not pixel matching.
"""

# Text signatures for each known YTC screen.
# Keys are short internal names used by the plugin state machine.
SCREEN_SIGNATURES: dict[str, frozenset[str]] = {
    "home":              frozenset({"new project", "create", "my videos"}),
    "project_type":      frozenset({"ai video", "short video", "slideshow"}),
    "script_input":      frozenset({"script", "tap to enter text", "voiceover"}),
    "media_picker":      frozenset({"gallery", "camera roll", "photos"}),
    "generating":        frozenset({"generating", "creating your video", "please wait"}),
    "generation_done":   frozenset({"continue", "preview", "your video is ready"}),
    "export_options":    frozenset({"export", "resolution", "1080p", "720p"}),
    "export_progress":   frozenset({"exporting", "saving"}),
    "share_sheet":       frozenset({"share", "tiktok", "instagram", "copy link"}),
    "error":             frozenset({"failed", "error", "try again", "couldn't create"}),
}

# Text that indicates a hard error requiring abort
ERROR_KEYWORDS = frozenset({
    "failed", "error", "couldn't", "sorry", "try again",
    "problem", "unable", "not available",
})

# Text that confirms generation has finished and the next action is available
GENERATION_DONE_BUTTONS = frozenset({"continue", "preview", "export", "done"})


def detect_ytc_screen(visible_text: list[str]) -> str | None:
    """
    Return the YouTube Create-specific screen name if identifiable, else None.
    Picks the screen whose signature has the most matching tokens.
    """
    text_lower = {t.lower() for t in visible_text}
    best_name: str | None = None
    best_score = 0
    for name, sigs in SCREEN_SIGNATURES.items():
        score = len(sigs & text_lower)
        if score > best_score:
            best_score = score
            best_name = name
    return best_name if best_score > 0 else None


def is_generation_complete(visible_text: list[str], buttons: list) -> bool:
    btn_text = {
        (b.text.lower() if hasattr(b, "text") else str(b).lower())
        for b in buttons
    }
    return bool(GENERATION_DONE_BUTTONS & btn_text)


def has_error_indicator(visible_text: list[str]) -> bool:
    combined = " ".join(visible_text).lower()
    return any(w in combined for w in ERROR_KEYWORDS)
