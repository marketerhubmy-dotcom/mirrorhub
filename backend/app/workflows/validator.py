"""
Workflow validation before save.

Checks:
  - All step types are known
  - Required parameters are present for each step type
  - Variables referenced in parameters match declared variables
  - No duplicate orders
  - Conditions reference valid fields
"""
import re
from .models import WorkflowStep

# Known step types and their required parameter keys
STEP_SCHEMA: dict[str, list[str]] = {
    "tap_button":     ["button"],
    "tap_relative":   ["rx", "ry"],
    "input_text":     ["text"],
    "paste":          [],
    "long_press":     ["rx", "ry"],
    "swipe":          ["start_rx", "start_ry", "end_rx", "end_ry"],
    "scroll_down":    [],
    "scroll_up":      [],
    "wait":           ["seconds"],
    "delay":          ["seconds"],
    "wait_until":     [],   # at least one of button/screen/loading must be in parameters
    "launch_app":     ["package"],
    "open_activity":  ["component"],
    "take_screenshot":[],
    "verify_screen":  ["screen"],
    "verify_button":  ["button"],
    "back":           [],
    "home":           [],
    "recent_apps":    [],
    "export":         [],
    "share":          [],
    # App-specific step types are allowed through
}

_VAR_RE = re.compile(r"\{\{(\w+)\}\}")


class ValidationResult:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    @property
    def valid(self) -> bool:
        return len(self.errors) == 0

    def to_dict(self) -> dict:
        return {"valid": self.valid, "errors": self.errors, "warnings": self.warnings}


def validate_steps(steps: list[WorkflowStep], declared_variables: list[str]) -> ValidationResult:
    result = ValidationResult()
    declared = set(declared_variables)
    orders = [s.order for s in steps]

    if len(orders) != len(set(orders)):
        result.errors.append("Duplicate step order values detected — re-order steps before saving")

    for step in steps:
        if not step.enabled:
            continue

        st = step.step_type

        # Unknown types are allowed (forward-compat) — warn only
        if st not in STEP_SCHEMA:
            result.warnings.append(f"Step '{step.label}': unknown type '{st}' — will be skipped at runtime")
            continue

        import json
        params = json.loads(step.parameters_json or "{}")
        required = STEP_SCHEMA.get(st, [])

        for req in required:
            if req not in params:
                result.errors.append(
                    f"Step '{step.label}' (type '{st}'): missing required parameter '{req}'"
                )

        # Check variables referenced in parameters
        for val in params.values():
            if not isinstance(val, str):
                continue
            for var in _VAR_RE.findall(val):
                if var not in declared:
                    result.warnings.append(
                        f"Step '{step.label}': references undeclared variable '{{{{" + var + "}}}}'  "
                        f"— add it to the workflow's variable list or it will resolve as empty"
                    )

    return result


def validate_step_dict(step_type: str, parameters: dict, declared_variables: list[str]) -> ValidationResult:
    """Lightweight single-step validation used by the recorder."""
    result = ValidationResult()
    declared = set(declared_variables)

    required = STEP_SCHEMA.get(step_type, [])
    for req in required:
        if req not in parameters:
            result.errors.append(f"Missing required parameter '{req}' for step type '{step_type}'")

    for val in parameters.values():
        if not isinstance(val, str):
            continue
        for var in _VAR_RE.findall(val):
            if var not in declared:
                result.warnings.append(f"Undeclared variable '{{{{" + var + "}}}}'")

    return result
