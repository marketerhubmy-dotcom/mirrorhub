from collections import defaultdict
from .state import ScreenAnalysis

MAX_HISTORY = 20

_history: dict[str, list[ScreenAnalysis]] = defaultdict(list)
_latest: dict[str, ScreenAnalysis] = {}


def put(device_id: str, analysis: ScreenAnalysis) -> None:
    _latest[device_id] = analysis
    history = _history[device_id]
    history.append(analysis)
    if len(history) > MAX_HISTORY:
        history.pop(0)


def get(device_id: str) -> ScreenAnalysis | None:
    return _latest.get(device_id)


def get_history(device_id: str, n: int = MAX_HISTORY) -> list[ScreenAnalysis]:
    return _history.get(device_id, [])[-n:]


def clear(device_id: str) -> None:
    _history.pop(device_id, None)
    _latest.pop(device_id, None)
