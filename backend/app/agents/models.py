"""
AI Agent Layer DB models.

New tables — never modifies existing ones:
  agent_goals       User-submitted high-level goals
  agent_tasks       Individual work units dispatched by AgentManager
  agent_decisions   Full reasoning audit trail for every AI decision
  agent_memory      Persistent KV memory store keyed by category+key
"""
import json
from datetime import datetime, timezone
from sqlalchemy import Text, Integer, Float, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.models.database import Base


# ── Status constants ──────────────────────────────────────────────────────────

GOAL_PLANNING    = "PLANNING"
GOAL_RUNNING     = "RUNNING"
GOAL_PAUSED      = "PAUSED"
GOAL_COMPLETED   = "COMPLETED"
GOAL_FAILED      = "FAILED"
GOAL_CANCELLED   = "CANCELLED"

TASK_CREATED    = "CREATED"
TASK_QUEUED     = "QUEUED"
TASK_ASSIGNED   = "ASSIGNED"
TASK_RUNNING    = "RUNNING"
TASK_COMPLETED  = "COMPLETED"
TASK_FAILED     = "FAILED"
TASK_RECOVERED  = "RECOVERED"

# Task types
TASK_GENERATE_CONTENT = "GENERATE_CONTENT"
TASK_EXECUTE          = "EXECUTE"
TASK_RECOVER          = "RECOVER"
TASK_OPTIMIZE         = "OPTIMIZE"
TASK_PLAN             = "PLAN"

# Memory categories
MEM_CAMPAIGN     = "campaign"
MEM_DEVICE       = "device"
MEM_PLUGIN       = "plugin"
MEM_WORKFLOW     = "workflow"
MEM_OPTIMIZATION = "optimization"
MEM_PROMPT       = "prompt"


# ── AgentGoal ─────────────────────────────────────────────────────────────────

class AgentGoal(Base):
    """
    Top-level goal submitted by the user.

    One goal → one Campaign + N tasks.
    """
    __tablename__ = "agent_goals"
    __table_args__ = (
        Index("ix_agent_goals_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    goal_text: Mapped[str] = mapped_column(Text)           # raw user input
    platform: Mapped[str] = mapped_column(Text, default="tiktok")
    product: Mapped[str] = mapped_column(Text, default="")
    target_count: Mapped[int] = mapped_column(Integer, default=1)
    priority: Mapped[int] = mapped_column(Integer, default=2)  # 0=critical … 3=low
    status: Mapped[str] = mapped_column(Text, default=GOAL_PLANNING)
    campaign_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    plan_json: Mapped[str] = mapped_column(Text, default="{}")   # execution plan
    result_json: Mapped[str] = mapped_column(Text, default="{}") # completion summary
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    tasks_total: Mapped[int] = mapped_column(Integer, default=0)
    tasks_completed: Mapped[int] = mapped_column(Integer, default=0)
    tasks_failed: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "goal_text": self.goal_text,
            "platform": self.platform,
            "product": self.product,
            "target_count": self.target_count,
            "priority": self.priority,
            "status": self.status,
            "campaign_id": self.campaign_id,
            "plan": json.loads(self.plan_json or "{}"),
            "result": json.loads(self.result_json or "{}"),
            "error": self.error,
            "progress": {
                "total": self.tasks_total,
                "completed": self.tasks_completed,
                "failed": self.tasks_failed,
                "pct": round(self.tasks_completed / self.tasks_total * 100, 1) if self.tasks_total else 0.0,
            },
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# ── AgentTask ─────────────────────────────────────────────────────────────────

class AgentTask(Base):
    """Individual work unit dispatched and tracked by AgentManager."""
    __tablename__ = "agent_tasks"
    __table_args__ = (
        Index("ix_agent_tasks_goal_id", "goal_id"),
        Index("ix_agent_tasks_status", "status"),
        Index("ix_agent_tasks_task_type", "task_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    goal_id: Mapped[int] = mapped_column(Integer)
    task_type: Mapped[str] = mapped_column(Text)  # GENERATE_CONTENT / EXECUTE / RECOVER / …
    agent: Mapped[str] = mapped_column(Text)       # planner / content / execution / recovery / optimization
    status: Mapped[str] = mapped_column(Text, default=TASK_CREATED)
    input_json: Mapped[str] = mapped_column(Text, default="{}")
    output_json: Mapped[str] = mapped_column(Text, default="{}")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "goal_id": self.goal_id,
            "task_type": self.task_type,
            "agent": self.agent,
            "status": self.status,
            "input": json.loads(self.input_json or "{}"),
            "output": json.loads(self.output_json or "{}"),
            "error": self.error,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# ── AgentDecision ─────────────────────────────────────────────────────────────

class AgentDecision(Base):
    """
    Full reasoning record for every AI decision.

    Never deleted — provides the explainability audit trail.
    """
    __tablename__ = "agent_decisions"
    __table_args__ = (
        Index("ix_agent_decisions_goal_id", "goal_id"),
        Index("ix_agent_decisions_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    goal_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    task_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    agent: Mapped[str] = mapped_column(Text)
    decision: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    alternative: Mapped[str] = mapped_column(Text, default="")
    expected_result: Mapped[str] = mapped_column(Text, default="")
    was_failsafe: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "goal_id": self.goal_id,
            "task_id": self.task_id,
            "agent": self.agent,
            "decision": self.decision,
            "reason": self.reason,
            "confidence": round(self.confidence, 3),
            "confidence_pct": round(self.confidence * 100, 1),
            "alternative": self.alternative,
            "expected_result": self.expected_result,
            "was_failsafe": self.was_failsafe,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ── AgentMemoryEntry ──────────────────────────────────────────────────────────

class AgentMemoryEntry(Base):
    """Persistent KV memory for the agent layer."""
    __tablename__ = "agent_memory"
    __table_args__ = (
        Index("ix_agent_memory_category", "category"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(Text, unique=True)
    category: Mapped[str] = mapped_column(Text)       # campaign/device/plugin/workflow/optimization/prompt
    summary: Mapped[str] = mapped_column(Text, default="")  # one-line human-readable summary
    value_json: Mapped[str] = mapped_column(Text, default="{}")
    relevance_score: Mapped[float] = mapped_column(Float, default=1.0)
    access_count: Mapped[int] = mapped_column(Integer, default=0)
    last_used_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "key": self.key,
            "category": self.category,
            "summary": self.summary,
            "value": json.loads(self.value_json or "{}"),
            "relevance_score": self.relevance_score,
            "access_count": self.access_count,
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
