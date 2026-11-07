"""Pydantic request/response models for the Workflow API."""
from pydantic import BaseModel


class StepCreate(BaseModel):
    step_type: str
    label: str = ""
    parameters: dict = {}
    conditions: dict = {}
    retry_max: int = 2
    timeout: int = 30
    enabled: bool = True
    screen_name: str | None = None
    order: int | None = None  # if omitted, appended at end


class StepUpdate(BaseModel):
    step_type: str | None = None
    label: str | None = None
    parameters: dict | None = None
    conditions: dict | None = None
    retry_max: int | None = None
    timeout: int | None = None
    enabled: bool | None = None
    screen_name: str | None = None


class StepReorder(BaseModel):
    step_ids: list[int]  # ordered list of step IDs defining new order


class WorkflowCreate(BaseModel):
    name: str
    description: str = ""
    application: str = "generic"
    variables: list[str] = []


class WorkflowUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    application: str | None = None
    variables: list[str] | None = None


class VersionCreate(BaseModel):
    notes: str | None = None


class PlayRequest(BaseModel):
    device_id: str
    variables: dict = {}   # {variable_name: value}
    simulate: bool = False


class RecorderStartRequest(BaseModel):
    device_id: str
    name: str = "New Recording"


class RecorderStepRequest(BaseModel):
    step_type: str
    label: str = ""
    parameters: dict = {}
    conditions: dict = {}
    capture_screen: bool = True  # snapshot Vision state when adding step


class RecorderStopRequest(BaseModel):
    name: str | None = None  # override session name
    description: str = ""
    application: str = "generic"
    save: bool = True


class ImportRequest(BaseModel):
    workflow_json: dict  # full workflow export dict
