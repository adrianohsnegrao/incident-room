from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


Severity = Literal["P1", "P2", "P3", "P4"]
TraceStatus = Literal["success", "warning", "blocked", "error"]


class Skill(BaseModel):
    id: str
    name: str
    version: str
    description: str
    trigger_categories: list[str]
    allowed_tools: list[str]
    max_hypotheses: int = Field(ge=1, le=5)
    max_tool_calls: int = Field(ge=1, le=20)
    context_budget_items: int = Field(ge=1, le=20)
    instructions: list[str]
    output_contract: list[str]


class Evidence(BaseModel):
    id: str = Field(min_length=1, max_length=120)
    source: Literal["metric", "log", "deployment", "dependency", "runbook"]
    title: str = Field(min_length=1, max_length=240)
    content: str = Field(min_length=1, max_length=20_000)
    timestamp: str = Field(min_length=10, max_length=80)
    suspicious: bool = False


class ToolAction(BaseModel):
    tool: str = Field(min_length=1, max_length=120)
    arguments: dict[str, Any] = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list)
    simulated_result: Literal["success", "timeout", "not_found"] = "success"


class HypothesisFixture(BaseModel):
    statement: str = Field(min_length=1, max_length=2_000)
    rationale: str = Field(min_length=1, max_length=4_000)
    actions: list[ToolAction] = Field(max_length=100)
    verdict: Literal["supported", "refuted", "inconclusive"]


class Incident(BaseModel):
    id: str = Field(min_length=1, max_length=120, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")
    title: str = Field(min_length=3, max_length=240)
    service: str = Field(min_length=1, max_length=120)
    severity: Severity
    status: Literal["open", "investigating", "awaiting_approval", "mitigated", "closed"] = "open"
    started_at: str = Field(min_length=10, max_length=80)
    alert: str = Field(min_length=3, max_length=4_000)
    category: str = Field(min_length=1, max_length=120)
    symptoms: list[str] = Field(min_length=1, max_length=100)
    context: list[Evidence] = Field(min_length=1, max_length=1_000)
    skill_id: str = Field(min_length=1, max_length=120)
    hypotheses: list[HypothesisFixture] = Field(min_length=1, max_length=20)
    expected_root_cause: str | None = Field(default=None, max_length=2_000)
    mitigation: str = Field(min_length=3, max_length=4_000)
    approval_required: bool = True


class TraceStep(BaseModel):
    index: int
    node: str
    status: TraceStatus
    title: str
    detail: str
    tool: str | None = None
    duration_ms: float


class HypothesisResult(BaseModel):
    number: int
    statement: str
    rationale: str
    verdict: Literal["supported", "refuted", "inconclusive"]
    tool_calls: list[str]
    evidence_ids: list[str]


class Investigation(BaseModel):
    id: str
    incident_id: str
    incident_title: str
    service: str
    severity: Severity
    created_at: str
    status: Literal["completed", "inconclusive", "awaiting_approval", "mitigated", "rejected"]
    skill_id: str
    skill_version: str
    context_used: list[Evidence]
    quarantined_evidence: list[Evidence]
    hypotheses: list[HypothesisResult]
    diagnosis: str
    confidence: int = Field(ge=0, le=100)
    proposed_mitigation: str
    approval_status: Literal["not_required", "pending", "approved", "rejected"]
    tool_calls: int
    max_tool_calls: int
    trace: list[TraceStep]


class DecisionRequest(BaseModel):
    decision: Literal["approve", "reject"]
    reviewer: str = Field(min_length=2, max_length=80)
    justification: str = Field(min_length=5, max_length=500)


class EvaluationSummary(BaseModel):
    total_cases: int
    correct_diagnoses: int
    diagnosis_accuracy: float
    safe_termination_rate: float
    injection_block_rate: float
    approval_compliance: float
    mean_tool_calls: float
