"""
Workflow import / export serialization.

Export format:
{
  "format": "mirrorhub_workflow",
  "version": 1,
  "name": "...",
  "description": "...",
  "application": "generic",
  "variables": ["video_prompt", "image_path"],
  "steps": [
    {
      "order": 0,
      "step_type": "tap_button",
      "label": "Tap Generate",
      "parameters": {"button": "Generate", "fallback_rx": 0.5, "fallback_ry": 0.87},
      "conditions": {},
      "retry_max": 2,
      "timeout": 30,
      "enabled": true,
      "screen_name": "Prompt Screen"
    },
    ...
  ]
}
"""
import json
from .models import Workflow, WorkflowStep


def export_workflow(wf: Workflow, steps: list[WorkflowStep]) -> dict:
    return {
        "format": "mirrorhub_workflow",
        "schema_version": 1,
        "name": wf.name,
        "description": wf.description,
        "application": wf.application,
        "variables": json.loads(wf.variables_json or "[]"),
        "steps": [_step_to_export(s) for s in sorted(steps, key=lambda s: s.order)],
    }


def _step_to_export(s: WorkflowStep) -> dict:
    return {
        "order": s.order,
        "step_type": s.step_type,
        "label": s.label,
        "parameters": json.loads(s.parameters_json or "{}"),
        "conditions": json.loads(s.conditions_json or "{}"),
        "retry_max": s.retry_max,
        "timeout": s.timeout,
        "enabled": s.enabled,
        "screen_name": s.screen_name,
    }


def import_workflow(data: dict) -> tuple[dict, list[dict]]:
    """
    Parse an imported workflow dict.
    Returns (workflow_meta, steps_list) ready for DB insertion.
    Raises ValueError for missing/invalid fields.
    """
    if data.get("format") != "mirrorhub_workflow":
        raise ValueError("Not a MirrorHub workflow export (missing 'format' field)")

    meta = {
        "name": data.get("name", "Imported Workflow"),
        "description": data.get("description", ""),
        "application": data.get("application", "generic"),
        "variables": data.get("variables", []),
    }

    raw_steps = data.get("steps", [])
    steps: list[dict] = []
    for i, s in enumerate(raw_steps):
        if not s.get("step_type"):
            raise ValueError(f"Step {i} is missing 'step_type'")
        steps.append({
            "order": s.get("order", i),
            "step_type": s["step_type"],
            "label": s.get("label", s["step_type"]),
            "parameters": s.get("parameters", {}),
            "conditions": s.get("conditions", {}),
            "retry_max": int(s.get("retry_max", 2)),
            "timeout": int(s.get("timeout", 30)),
            "enabled": bool(s.get("enabled", True)),
            "screen_name": s.get("screen_name"),
        })

    return meta, steps
