def build_screen_analysis_prompt(task: str, expected_screen: str) -> str:
    return f"""You are an Android screen analyzer for automation.

Current task: {task}
Expected screen: {expected_screen}

Analyze the screenshot and respond ONLY with valid JSON (no markdown):
{{
  "screen_name": "short name of what is on screen",
  "screen_type": "Home|Loading|Permission Dialog|Gallery Picker|Share Sheet|Export Screen|Generation Screen|Error Dialog|Confirmation Dialog|Unknown",
  "confidence": 0.0,
  "visible_buttons": ["list of tap-able button texts you can see"],
  "dialogs": ["list of dialog/popup text if any"],
  "is_loading": false,
  "errors": ["list of error messages visible, or empty"],
  "progress_percent": null,
  "suggested_action": "what to tap or do next to complete the task",
  "is_expected_screen": true
}}"""


def build_wait_validation_prompt(task: str, expected_button: str) -> str:
    return f"""You are validating if a specific UI element is visible.

Task: {task}
Looking for button/element: "{expected_button}"

Analyze the screenshot. Respond ONLY with valid JSON:
{{
  "found": true,
  "button_text": "exact text visible",
  "confidence": 0.9,
  "alternative": "closest alternative button if not found exactly"
}}"""
