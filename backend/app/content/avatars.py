"""
Avatar / character presets for video-prompt generation.
Each preset provides a visual description that the AI uses when building the
YouTube Create / Sora video prompt.
"""

AVATAR_PRESETS: dict[str, str] = {
    "Malaysian Mother": (
        "A modest Malaysian mother in her 30s wearing a simple long-sleeve baju kurung "
        "or plain long-sleeve top with hijab in neutral colours, natural home or kitchen setting, "
        "warm and relatable expression."
    ),
    "Malaysian Father": (
        "A Malaysian father in his 30s-40s wearing a casual collared shirt or polo, "
        "relaxed indoor or outdoor setting, trustworthy and calm expression."
    ),
    "Female Student": (
        "A Malaysian female university student in her early 20s wearing a casual modern outfit "
        "or baju kurung, campus or home-study background, energetic and curious expression."
    ),
    "Male Student": (
        "A Malaysian male university student in his early 20s wearing a casual t-shirt or hoodie, "
        "campus or bedroom background, relaxed and confident expression."
    ),
    "Young Adult Woman": (
        "A Malaysian young woman in her mid-20s wearing a trendy but modest outfit, "
        "clean minimal background or lifestyle setting, confident and aspirational expression."
    ),
    "Young Adult Man": (
        "A Malaysian young man in his mid-20s wearing smart casual attire, "
        "urban or home setting, energetic and friendly expression."
    ),
    "Primary School Child": (
        "A Malaysian primary school child aged 7-10 in school uniform or casual clothes, "
        "home or classroom setting, playful and innocent expression."
    ),
    "Secondary School Student": (
        "A Malaysian secondary school student aged 13-17 in school uniform or casual clothes, "
        "home or school setting, curious and youthful expression."
    ),
    "Product Only": (
        "No human character. Focus entirely on the product — clean white or gradient background, "
        "macro and wide shots, professional studio lighting."
    ),
    "Hands Only": (
        "No face shown. Close-up of hands (light brown Malaysian skin tone) interacting with "
        "the product, neutral background, soft natural lighting."
    ),
    "Custom": "",  # filled by user at runtime
}


def get_avatar_description(avatar_name: str, custom_text: str = "") -> str:
    """Return the visual description for a named avatar preset."""
    if avatar_name == "Custom":
        return custom_text.strip()
    return AVATAR_PRESETS.get(avatar_name, "")


def list_presets() -> list[str]:
    return list(AVATAR_PRESETS.keys())
