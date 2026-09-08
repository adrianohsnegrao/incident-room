from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .engine import evaluate_suite, investigate_incident
from .fixtures import INCIDENTS, INCIDENT_MAP
from .models import DecisionRequest, Incident, Investigation, TraceStep
from .skills import SKILLS, SKILL_MAP


app = FastAPI(
    title="Incident Room API",
    version="0.1.0",
    description="Central local para investigar incidentes com skills e um loop de hipóteses limitado.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5176", "http://localhost:5176"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

investigations: dict[str, Investigation] = {}
latest_by_incident: dict[str, str] = {}


def create_investigation(incident: Incident) -> Investigation:
    skill = SKILL_MAP[incident.skill_id]
    result = investigate_incident(incident, skill)
    investigations[result.id] = result
    latest_by_incident[incident.id] = result.id
    return result


for fixture_incident in INCIDENTS:
    create_investigation(fixture_incident)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "service": "incident-room", "version": "0.1.0"}


@app.get("/api/overview")
def overview() -> dict:
    latest = [investigations[latest_by_incident[item.id]] for item in INCIDENTS]
    return {
        "incidents": INCIDENTS,
        "investigations": latest,
        "skills": SKILLS,
        "evaluation": evaluate_suite(INCIDENTS, latest),
        "summary": {
            "open_incidents": len(INCIDENTS),
            "critical_incidents": sum(item.severity == "P1" for item in INCIDENTS),
            "awaiting_approval": sum(item.approval_status == "pending" for item in latest),
            "quarantined_evidence": sum(len(item.quarantined_evidence) for item in latest),
        },
    }


@app.get("/api/incidents")
def list_incidents() -> list[Incident]:
    return INCIDENTS


@app.get("/api/incidents/{incident_id}")
def get_incident(incident_id: str) -> dict:
    incident = INCIDENT_MAP.get(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incidente não encontrado.")
    latest_id = latest_by_incident.get(incident_id)
    return {"incident": incident, "investigation": investigations.get(latest_id) if latest_id else None}


@app.post("/api/incidents/{incident_id}/investigate", status_code=201)
def run_investigation(incident_id: str) -> Investigation:
    incident = INCIDENT_MAP.get(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incidente não encontrado.")
    return create_investigation(incident)


@app.get("/api/investigations/{investigation_id}")
def get_investigation(investigation_id: str) -> Investigation:
    investigation = investigations.get(investigation_id)
    if not investigation:
        raise HTTPException(status_code=404, detail="Investigação não encontrada.")
    return investigation


@app.post("/api/investigations/{investigation_id}/decision")
def decide(investigation_id: str, payload: DecisionRequest) -> Investigation:
    investigation = investigations.get(investigation_id)
    if not investigation:
        raise HTTPException(status_code=404, detail="Investigação não encontrada.")
    if investigation.approval_status != "pending":
        raise HTTPException(status_code=409, detail="Esta investigação não aguarda aprovação.")
    approved = payload.decision == "approve"
    decision_step = TraceStep(
        index=len(investigation.trace) + 1,
        node="human_decision",
        status="success" if approved else "warning",
        title="Mitigação aprovada" if approved else "Mitigação rejeitada",
        detail=f"{payload.reviewer}: {payload.justification}",
        duration_ms=0,
    )
    updated = investigation.model_copy(
        update={
            "approval_status": "approved" if approved else "rejected",
            "status": "mitigated" if approved else "rejected",
            "trace": [*investigation.trace, decision_step],
        }
    )
    investigations[investigation_id] = updated
    return updated


@app.get("/api/skills")
def list_skills():
    return SKILLS

