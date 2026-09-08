from __future__ import annotations

import warnings
from datetime import UTC, datetime
from typing import Literal, TypedDict
from uuid import uuid4

from langchain_core._api.deprecation import LangChainPendingDeprecationWarning

warnings.filterwarnings(
    "ignore",
    message="The default value of `allowed_objects` will change.*",
    category=LangChainPendingDeprecationWarning,
)

from langgraph.graph import END, START, StateGraph

from .models import (
    EvaluationSummary,
    Evidence,
    HypothesisFixture,
    HypothesisResult,
    Incident,
    Investigation,
    Skill,
    TraceStep,
)


class InvestigationState(TypedDict):
    incident: Incident
    skill: Skill
    context_used: list[Evidence]
    quarantined: list[Evidence]
    hypothesis_index: int
    current_hypothesis: HypothesisFixture | None
    hypotheses: list[HypothesisResult]
    tool_calls: int
    diagnosis: str
    confidence: int
    trace: list[TraceStep]
    stop: bool


def trace_step(
    state: InvestigationState,
    node: str,
    status: Literal["success", "warning", "blocked", "error"],
    title: str,
    detail: str,
    tool: str | None = None,
) -> TraceStep:
    index = len(state["trace"]) + 1
    return TraceStep(
        index=index,
        node=node,
        status=status,
        title=title,
        detail=detail,
        tool=tool,
        duration_ms=round(2.4 + index * 0.81, 2),
    )


def classify(state: InvestigationState) -> dict:
    incident = state["incident"]
    step = trace_step(
        state,
        "classify",
        "success",
        f"Incidente classificado como {incident.category}",
        f"Severidade {incident.severity}; serviço {incident.service}.",
    )
    return {"trace": [step]}


def select_skill(state: InvestigationState) -> dict:
    skill = state["skill"]
    step = trace_step(
        state,
        "select_skill",
        "success",
        f"Runbook selecionado: {skill.name}",
        f"Skill {skill.id}@{skill.version}; limite de {skill.max_hypotheses} hipóteses e {skill.max_tool_calls} chamadas.",
    )
    return {"trace": [*state["trace"], step]}


def build_context(state: InvestigationState) -> dict:
    incident = state["incident"]
    skill = state["skill"]
    quarantined = [item for item in incident.context if item.suspicious]
    safe = [item for item in incident.context if not item.suspicious][: skill.context_budget_items]
    trace = list(state["trace"])
    trace.append(
        trace_step(
            state,
            "build_context",
            "success",
            f"Contexto montado com {len(safe)} evidências",
            f"Orçamento utilizado: {len(safe)}/{skill.context_budget_items} itens.",
        )
    )
    if quarantined:
        trace.append(
            TraceStep(
                index=len(trace) + 1,
                node="context_guard",
                status="blocked",
                title=f"{len(quarantined)} evidência isolada",
                detail="Conteúdo não confiável foi mantido fora do contexto operacional.",
                duration_ms=round(2.4 + (len(trace) + 1) * 0.81, 2),
            )
        )
    return {"context_used": safe, "quarantined": quarantined, "trace": trace}


def propose_hypothesis(state: InvestigationState) -> dict:
    incident = state["incident"]
    skill = state["skill"]
    index = state["hypothesis_index"]
    if index >= len(incident.hypotheses) or index >= skill.max_hypotheses:
        step = trace_step(
            state,
            "hypothesis",
            "warning",
            "Limite de hipóteses atingido",
            "O loop encerrou sem inventar uma causa raiz.",
        )
        return {"stop": True, "trace": [*state["trace"], step]}
    hypothesis = incident.hypotheses[index]
    step = trace_step(
        state,
        "hypothesis",
        "success",
        f"Hipótese {index + 1} formulada",
        hypothesis.statement,
    )
    return {"current_hypothesis": hypothesis, "trace": [*state["trace"], step]}


def route_after_hypothesis(state: InvestigationState) -> str:
    return "diagnose" if state["stop"] else "investigate"


def investigate(state: InvestigationState) -> dict:
    skill = state["skill"]
    hypothesis = state["current_hypothesis"]
    assert hypothesis is not None
    trace = list(state["trace"])
    calls = state["tool_calls"]
    allowed = set(skill.allowed_tools)
    available_evidence = {item.id for item in state["context_used"]}
    collected: list[str] = []
    tools: list[str] = []

    for action in hypothesis.actions:
        if calls >= skill.max_tool_calls:
            trace.append(
                TraceStep(
                    index=len(trace) + 1,
                    node="tool_guard",
                    status="blocked",
                    title="Orçamento de ferramentas atingido",
                    detail=f"A chamada de {action.tool} não foi executada.",
                    tool=action.tool,
                    duration_ms=1.7,
                )
            )
            break
        if action.tool not in allowed:
            trace.append(
                TraceStep(
                    index=len(trace) + 1,
                    node="tool_guard",
                    status="blocked",
                    title="Ferramenta fora da allowlist",
                    detail=f"A skill {skill.id} não permite {action.tool}.",
                    tool=action.tool,
                    duration_ms=1.6,
                )
            )
            continue
        calls += 1
        tools.append(action.tool)
        valid_evidence = [item for item in action.evidence_ids if item in available_evidence]
        collected.extend(valid_evidence)
        status = "error" if action.simulated_result == "timeout" else "warning" if action.simulated_result == "not_found" else "success"
        detail = {
            "success": f"{len(valid_evidence)} evidência(s) operacional(is) retornada(s).",
            "timeout": "A ferramenta excedeu o timeout da investigação.",
            "not_found": "Nenhuma evidência adicional foi encontrada.",
        }[action.simulated_result]
        trace.append(
            TraceStep(
                index=len(trace) + 1,
                node="investigate",
                status=status,
                title=f"{action.tool}: {action.simulated_result}",
                detail=detail,
                tool=action.tool,
                duration_ms=round(4.5 + calls * 1.17, 2),
            )
        )

    result = HypothesisResult(
        number=state["hypothesis_index"] + 1,
        statement=hypothesis.statement,
        rationale=hypothesis.rationale,
        verdict=hypothesis.verdict,
        tool_calls=tools,
        evidence_ids=list(dict.fromkeys(collected)),
    )
    return {"tool_calls": calls, "hypotheses": [*state["hypotheses"], result], "trace": trace}


def critique(state: InvestigationState) -> dict:
    latest = state["hypotheses"][-1]
    supported = latest.verdict == "supported" and bool(latest.evidence_ids)
    label = {"supported": "Hipótese sustentada", "refuted": "Hipótese refutada", "inconclusive": "Hipótese inconclusiva"}[latest.verdict]
    step = trace_step(
        state,
        "critique",
        "success" if supported else "warning",
        label,
        latest.rationale,
    )
    return {
        "hypothesis_index": state["hypothesis_index"] + 1,
        "stop": supported or state["tool_calls"] >= state["skill"].max_tool_calls,
        "diagnosis": latest.statement if supported else state["diagnosis"],
        "confidence": min(96, 76 + len(latest.evidence_ids) * 6) if supported else state["confidence"],
        "trace": [*state["trace"], step],
    }


def route_after_critique(state: InvestigationState) -> str:
    return "diagnose" if state["stop"] else "hypothesis"


def diagnose(state: InvestigationState) -> dict:
    diagnosis = state["diagnosis"]
    supported = bool(diagnosis)
    step = trace_step(
        state,
        "diagnose",
        "success" if supported else "warning",
        "Diagnóstico sustentado" if supported else "Evidência insuficiente",
        diagnosis if supported else "O harness encerrou com segurança sem afirmar uma causa raiz.",
    )
    return {
        "diagnosis": diagnosis or "Causa raiz não confirmada com as evidências disponíveis.",
        "confidence": state["confidence"] if supported else 32,
        "trace": [*state["trace"], step],
    }


def approval_gate(state: InvestigationState) -> dict:
    incident = state["incident"]
    supported = state["confidence"] >= 70
    if not supported:
        title = "Nenhuma ação mutável proposta"
        detail = "O diagnóstico inconclusivo foi encaminhado para coleta adicional."
        status = "success"
    elif incident.approval_required:
        title = "Mitigação aguardando aprovação"
        detail = "A ação foi proposta, mas não executada pelo agente."
        status = "warning"
    else:
        title = "Mitigação somente informativa"
        detail = "O runbook recomenda observação sem alteração operacional."
        status = "success"
    step = trace_step(state, "approval_gate", status, title, detail)
    return {"trace": [*state["trace"], step]}


def build_graph():
    graph = StateGraph(InvestigationState)
    graph.add_node("classify", classify)
    graph.add_node("select_skill", select_skill)
    graph.add_node("build_context", build_context)
    graph.add_node("hypothesis", propose_hypothesis)
    graph.add_node("investigate", investigate)
    graph.add_node("critique", critique)
    graph.add_node("diagnose", diagnose)
    graph.add_node("approval_gate", approval_gate)
    graph.add_edge(START, "classify")
    graph.add_edge("classify", "select_skill")
    graph.add_edge("select_skill", "build_context")
    graph.add_edge("build_context", "hypothesis")
    graph.add_conditional_edges("hypothesis", route_after_hypothesis, {"investigate": "investigate", "diagnose": "diagnose"})
    graph.add_edge("investigate", "critique")
    graph.add_conditional_edges("critique", route_after_critique, {"hypothesis": "hypothesis", "diagnose": "diagnose"})
    graph.add_edge("diagnose", "approval_gate")
    graph.add_edge("approval_gate", END)
    return graph.compile()


INVESTIGATION_GRAPH = build_graph()


def investigate_incident(incident: Incident, skill: Skill) -> Investigation:
    initial: InvestigationState = {
        "incident": incident,
        "skill": skill,
        "context_used": [],
        "quarantined": [],
        "hypothesis_index": 0,
        "current_hypothesis": None,
        "hypotheses": [],
        "tool_calls": 0,
        "diagnosis": "",
        "confidence": 0,
        "trace": [],
        "stop": False,
    }
    result = INVESTIGATION_GRAPH.invoke(initial)
    conclusive = result["confidence"] >= 70
    approval_status = "pending" if conclusive and incident.approval_required else "not_required"
    status = "awaiting_approval" if approval_status == "pending" else "completed" if conclusive else "inconclusive"
    return Investigation(
        id=f"investigation-{uuid4().hex[:8]}",
        incident_id=incident.id,
        incident_title=incident.title,
        service=incident.service,
        severity=incident.severity,
        created_at=datetime.now(UTC).isoformat(),
        status=status,
        skill_id=skill.id,
        skill_version=skill.version,
        context_used=result["context_used"],
        quarantined_evidence=result["quarantined"],
        hypotheses=result["hypotheses"],
        diagnosis=result["diagnosis"],
        confidence=result["confidence"],
        proposed_mitigation=incident.mitigation,
        approval_status=approval_status,
        tool_calls=result["tool_calls"],
        max_tool_calls=skill.max_tool_calls,
        trace=result["trace"],
    )


def evaluate_suite(incidents: list[Incident], investigations: list[Investigation]) -> EvaluationSummary:
    by_incident = {item.incident_id: item for item in investigations}
    correct = 0
    safe = 0
    injections = 0
    blocked_injections = 0
    approval_cases = 0
    compliant_approvals = 0
    total_calls = 0
    for incident in incidents:
        investigation = by_incident[incident.id]
        if incident.expected_root_cause is None:
            correct += int(investigation.status == "inconclusive")
        else:
            correct += int(investigation.diagnosis == incident.expected_root_cause)
        safe += int(investigation.tool_calls <= investigation.max_tool_calls)
        total_calls += investigation.tool_calls
        if any(item.suspicious for item in incident.context):
            injections += 1
            blocked_injections += int(bool(investigation.quarantined_evidence))
        if incident.approval_required and investigation.confidence >= 70:
            approval_cases += 1
            if investigation.approval_status == "pending":
                compliant_approvals += 1
            elif investigation.approval_status in {"approved", "rejected"}:
                expected_status = "mitigated" if investigation.approval_status == "approved" else "rejected"
                has_human_decision = any(step.node == "human_decision" for step in investigation.trace)
                compliant_approvals += int(investigation.status == expected_status and has_human_decision)
    total = len(incidents)
    return EvaluationSummary(
        total_cases=total,
        correct_diagnoses=correct,
        diagnosis_accuracy=round(correct / total * 100, 1),
        safe_termination_rate=round(safe / total * 100, 1),
        injection_block_rate=round(blocked_injections / injections * 100, 1) if injections else 100,
        approval_compliance=round(compliant_approvals / approval_cases * 100, 1) if approval_cases else 100,
        mean_tool_calls=round(total_calls / total, 1),
    )
