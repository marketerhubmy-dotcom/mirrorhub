# TEST QUARANTINE (2026-11-08)

Tests that target internals which no longer exist. They are **skipped with a reason, not deleted**, so they show in every report as `s`. Each must be rewritten against the current API when the AI-agent / campaign layer is promoted out of experimental (post Desktop V1).

| Test | Why stale |
|---|---|
| `tests/integration/test_agent_tick.py::test_agent_tick_opens_multiple_sessions` | AgentManager._run_read_phase was removed in the tick-loop refactor; test patches a non-existent method |
| `tests/integration/test_agent_tick.py::test_agent_tick_does_not_call_openai_directly` | AgentManager._run_read_phase was removed in the tick-loop refactor; test patches a non-existent method |
| `tests/integration/test_agent_tick.py::test_correlation_id_set_at_tick_start` | AgentManager._run_read_phase was removed in the tick-loop refactor; test patches a non-existent method |
| `tests/performance/test_agent_query_count.py::test_batch_aggregation_query_count_constant` | constructs AgentGoal(device_id=...) / DeviceProfile(platform=...); those columns no longer exist |
| `tests/performance/test_agent_query_count.py::test_device_load_aggregation_uses_group_by` | constructs AgentGoal(device_id=...) / DeviceProfile(platform=...); those columns no longer exist |
| `tests/recovery/test_job_reassignment.py::test_recovery_agent_idle_when_no_stalled_jobs` | patches RecoveryAgent._find_stalled_jobs / recovery_agent.is_device_busy, both removed |
| `tests/recovery/test_job_reassignment.py::test_running_job_on_disconnected_device_is_reset` | patches RecoveryAgent._find_stalled_jobs / recovery_agent.is_device_busy, both removed |
| `tests/recovery/test_job_reassignment.py::test_recovery_does_not_touch_completed_jobs` | patches RecoveryAgent._find_stalled_jobs / recovery_agent.is_device_busy, both removed |
| `tests/recovery/test_job_reassignment.py::test_max_retry_limit_is_respected` | patches RecoveryAgent._find_stalled_jobs / recovery_agent.is_device_busy, both removed |
| `tests/unit/test_agents.py::test_planner_generates_steps_from_ai_response` | patches planner/optimization `openai_client` and RecoveryAgent internals that no longer exist |
| `tests/unit/test_agents.py::test_planner_handles_invalid_ai_json` | patches planner/optimization `openai_client` and RecoveryAgent internals that no longer exist |
| `tests/unit/test_agents.py::test_recovery_agent_retry_on_stall` | patches planner/optimization `openai_client` and RecoveryAgent internals that no longer exist |
| `tests/unit/test_agents.py::test_recovery_agent_abort_unrecoverable` | patches planner/optimization `openai_client` and RecoveryAgent internals that no longer exist |
| `tests/unit/test_agents.py::test_optimization_agent_emits_recommendations` | patches planner/optimization `openai_client` and RecoveryAgent internals that no longer exist |

Rewritten (not quarantined): `test_mirror_async.py`, `test_execution_queue.py`, memory tests -> `tests/unit/test_agent_memory.py`.
Fixed in code: campaign FK (`campaign_jobs.campaign_id` -> `campaigns.id`), tz-aware `Campaign.created_at`, `assign_device(exclude_device_id=...)`, duplicate ADB path helpers.
