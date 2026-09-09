from __future__ import annotations

import sqlite3
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .engine import evaluate_suite, investigate_incident
from .fixtures import INCIDENTS
from .models import DecisionRequest, Incident, Investigation
from .repository import IncidentRepository
from .settings import Settings, load_settings
from .skills import SKILLS, SKILL_MAP


def create_app(
    settings: Settings | None = None,
    repository: IncidentRepository | None = None,
) -> FastAPI:
    config = settings or load_settings()
    store = repository or IncidentRepository(config.database_path)

    def create_investigation(incident: Incident) -> Investigation:
        skill = SKILL_MAP.get(incident.skill_id)
        if not skill:
            raise HTTPException(status_code=422, detail=f"A skill {incident.skill_id} não está instalada.")
        return store.save_investigation(investigate_incident(incident, skill))

    if store.count_incidents() == 0:
        for fixture in INCIDENTS:
            store.save_incident(fixture, source="bundled")
            create_investigation(fixture)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        if repository is None:
            store.close()

    application = FastAPI(
        title="Incident Room API",
        version="1.0.0",
        description="Central persistente para investigação limitada, auditável e orientada por evidências.",
        lifespan=lifespan,
    )
    application.state.repository = store
    application.state.settings = config
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(config.allowed_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-Request-Id"],
    )

    @application.middleware("http")
    async def operational_controls(request: Request, call_next):
        content_length = request.headers.get("content-length")
        try:
            oversized = bool(content_length and int(content_length) > 5 * 1024 * 1024)
        except ValueError:
            oversized = False
        response = (
            JSONResponse(status_code=413, content={"detail": "A requisição excede o limite de 5 MB."})
            if oversized
            else await call_next(request)
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'; "
            "img-src 'self' data:; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'"
        )
        response.headers["X-Request-Id"] = request.headers.get("x-request-id", str(uuid4()))[:128]
        return response

    @application.get("/api/health")
    @application.get("/api/health/live")
    def health() -> dict:
        return {"status": "ok", "service": "incident-room", "version": "1.0.0"}

    @application.get("/api/health/ready")
    def readiness() -> dict:
        if not store.ready():
            raise HTTPException(status_code=503, detail="Persistência indisponível.")
        return {"status": "ready", "database": "ok", "incidents": store.count_incidents()}

    @application.get("/api/overview")
    def overview() -> dict:
        incidents = store.list_incidents()
        latest = store.latest_all()
        latest_map = {item.incident_id: item for item in latest}
        ordered_latest = [latest_map[item.id] for item in incidents if item.id in latest_map]
        golden_ids = {item.id for item in INCIDENTS}
        golden_incidents = [item for item in INCIDENTS if item.id in latest_map]
        golden_runs = [latest_map[item.id] for item in golden_incidents]
        return {
            "incidents": incidents,
            "investigations": ordered_latest,
            "skills": SKILLS,
            "evaluation": evaluate_suite(golden_incidents, golden_runs),
            "summary": {
                "open_incidents": len(incidents),
                "custom_incidents": sum(item.id not in golden_ids for item in incidents),
                "critical_incidents": sum(item.severity == "P1" for item in incidents),
                "awaiting_approval": sum(item.approval_status == "pending" for item in ordered_latest),
                "quarantined_evidence": sum(len(item.quarantined_evidence) for item in ordered_latest),
            },
        }

    @application.get("/api/incidents")
    def list_incidents() -> list[Incident]:
        return store.list_incidents()

    @application.post("/api/incidents", status_code=201)
    def create_incident(incident: Incident) -> dict:
        if incident.skill_id not in SKILL_MAP:
            raise HTTPException(status_code=422, detail=f"A skill {incident.skill_id} não está instalada.")
        if len(incident.context) > config.max_evidence_items:
            raise HTTPException(
                status_code=422,
                detail=f"O limite configurado é de {config.max_evidence_items} evidências por incidente.",
            )
        try:
            store.save_incident(incident, source="external")
        except sqlite3.IntegrityError as error:
            raise HTTPException(status_code=409, detail="Já existe um incidente com este identificador.") from error
        investigation = create_investigation(incident)
        return {"incident": incident, "investigation": investigation}

    @application.get("/api/incidents/{incident_id}")
    def get_incident(incident_id: str) -> dict:
        incident = store.get_incident(incident_id)
        if not incident:
            raise HTTPException(status_code=404, detail="Incidente não encontrado.")
        return {"incident": incident, "investigation": store.latest_for(incident_id)}

    @application.post("/api/incidents/{incident_id}/investigate", status_code=201)
    def run_investigation(incident_id: str) -> Investigation:
        incident = store.get_incident(incident_id)
        if not incident:
            raise HTTPException(status_code=404, detail="Incidente não encontrado.")
        return create_investigation(incident)

    @application.get("/api/investigations/{investigation_id}")
    def get_investigation(investigation_id: str) -> Investigation:
        investigation = store.get_investigation(investigation_id)
        if not investigation:
            raise HTTPException(status_code=404, detail="Investigação não encontrada.")
        return investigation

    @application.post("/api/investigations/{investigation_id}/decision")
    def decide(investigation_id: str, payload: DecisionRequest) -> Investigation:
        try:
            updated = store.record_decision(
                investigation_id,
                approved=payload.decision == "approve",
                reviewer=payload.reviewer,
                justification=payload.justification,
            )
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        if not updated:
            raise HTTPException(status_code=404, detail="Investigação não encontrada.")
        return updated

    @application.get("/api/skills")
    def list_skills():
        return SKILLS

    if config.frontend_dist.joinpath("index.html").is_file():
        application.mount("/", StaticFiles(directory=config.frontend_dist, html=True), name="frontend")

    return application


app = create_app()
