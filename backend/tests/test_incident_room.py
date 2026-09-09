import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.engine import evaluate_suite, investigate_incident
from app.fixtures import INCIDENTS
from app.main import app, create_app
from app.models import Incident
from app.repository import IncidentRepository
from app.settings import Settings
from app.skills import SKILL_MAP, SKILLS


def investigate_all():
    return [investigate_incident(incident, SKILL_MAP[incident.skill_id]) for incident in INCIDENTS]


def make_settings(tmp_path: Path, frontend_dist: Path | None = None) -> Settings:
    return Settings(
        environment="test",
        host="127.0.0.1",
        port=8030,
        database_path=tmp_path / "incident-room.db",
        frontend_dist=frontend_dist or tmp_path / "missing-frontend",
        allowed_origins=("http://127.0.0.1:5176",),
        max_evidence_items=100,
    )


def test_skills_are_versioned_and_have_execution_limits() -> None:
    assert len(SKILLS) == 4
    assert all(skill.version == "1.0.0" for skill in SKILLS)
    assert all(skill.max_hypotheses <= 3 for skill in SKILLS)
    assert all(skill.allowed_tools for skill in SKILLS)


def test_deployment_regression_uses_evidence_and_requests_approval() -> None:
    incident = next(item for item in INCIDENTS if item.id == "inc-1042")
    result = investigate_incident(incident, SKILL_MAP[incident.skill_id])
    assert result.diagnosis == incident.expected_root_cause
    assert result.confidence >= 90
    assert result.approval_status == "pending"
    assert result.status == "awaiting_approval"
    assert len(result.hypotheses) == 2
    assert result.hypotheses[0].verdict == "refuted"
    assert result.hypotheses[1].verdict == "supported"


def test_prompt_injection_in_log_is_quarantined() -> None:
    incident = next(item for item in INCIDENTS if item.id == "inc-1022")
    result = investigate_incident(incident, SKILL_MAP[incident.skill_id])
    assert [item.id for item in result.quarantined_evidence] == ["sec-log-1"]
    assert "sec-log-1" not in [item.id for item in result.context_used]
    assert any(step.node == "context_guard" and step.status == "blocked" for step in result.trace)


def test_inconclusive_incident_does_not_propose_mutation() -> None:
    incident = next(item for item in INCIDENTS if item.id == "inc-1018")
    result = investigate_incident(incident, SKILL_MAP[incident.skill_id])
    assert result.status == "inconclusive"
    assert result.confidence < 70
    assert result.approval_status == "not_required"
    assert "não confirmada" in result.diagnosis


def test_every_investigation_respects_tool_budget() -> None:
    results = investigate_all()
    assert all(item.tool_calls <= item.max_tool_calls for item in results)


def test_evaluation_suite_matches_golden_expectations() -> None:
    results = investigate_all()
    summary = evaluate_suite(INCIDENTS, results)
    assert summary.correct_diagnoses == len(INCIDENTS)
    assert summary.diagnosis_accuracy == 100
    assert summary.safe_termination_rate == 100
    assert summary.injection_block_rate == 100
    assert summary.approval_compliance == 100


def test_api_exposes_overview_and_can_rerun_incident() -> None:
    client = TestClient(app)
    health = client.get("/api/health")
    assert health.status_code == 200
    overview = client.get("/api/overview")
    assert overview.status_code == 200
    assert overview.json()["evaluation"]["diagnosis_accuracy"] == 100
    rerun = client.post("/api/incidents/inc-1042/investigate")
    assert rerun.status_code == 201
    assert rerun.json()["approval_status"] == "pending"


def test_human_decision_is_required_once() -> None:
    client = TestClient(app)
    rerun = client.post("/api/incidents/inc-1038/investigate").json()
    response = client.post(
        f"/api/investigations/{rerun['id']}/decision",
        json={"decision": "approve", "reviewer": "Operador", "justification": "Evidências revisadas."},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "mitigated"
    overview = client.get("/api/overview")
    assert overview.json()["evaluation"]["approval_compliance"] == 100
    duplicate = client.post(
        f"/api/investigations/{rerun['id']}/decision",
        json={"decision": "approve", "reviewer": "Operador", "justification": "Executar novamente."},
    )
    assert duplicate.status_code == 409


def test_missing_resources_return_not_found() -> None:
    client = TestClient(app)
    assert client.get("/api/incidents/unknown").status_code == 404
    assert client.get("/api/investigations/unknown").status_code == 404


def test_runs_and_human_decision_survive_restart(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    repository = IncidentRepository(settings.database_path)
    client = TestClient(create_app(settings, repository))
    run = client.post("/api/incidents/inc-1042/investigate").json()
    decided = client.post(
        f"/api/investigations/{run['id']}/decision",
        json={"decision": "reject", "reviewer": "SRE responsável", "justification": "Coletar mais evidências."},
    )
    assert decided.status_code == 200
    repository.close()

    reopened = IncidentRepository(settings.database_path)
    persisted = reopened.get_investigation(run["id"])
    assert persisted is not None
    assert persisted.approval_status == "rejected"
    assert persisted.trace[-1].node == "human_decision"
    reopened.close()


def test_external_incident_is_validated_investigated_and_persisted(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    repository = IncidentRepository(settings.database_path)
    client = TestClient(create_app(settings, repository))
    example = Path(__file__).parents[1] / "examples" / "incident-import-example.json"
    payload = json.loads(example.read_text(encoding="utf-8"))
    response = client.post("/api/incidents", json=payload)
    assert response.status_code == 201
    assert response.json()["investigation"]["confidence"] >= 70
    assert repository.get_incident(payload["id"]) == Incident.model_validate(payload)
    assert client.post("/api/incidents", json=payload).status_code == 409
    repository.close()


def test_operational_probes_security_headers_static_ui_and_backup(tmp_path: Path) -> None:
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "index.html").write_text("<h1>Incident Room</h1>", encoding="utf-8")
    settings = make_settings(tmp_path, frontend)
    repository = IncidentRepository(settings.database_path)
    client = TestClient(create_app(settings, repository))
    ready = client.get("/api/health/ready")
    assert ready.status_code == 200
    assert ready.json()["incidents"] == 6
    assert ready.headers["x-content-type-options"] == "nosniff"
    assert ready.headers["x-frame-options"] == "DENY"
    assert ready.headers["x-request-id"]
    assert client.get("/").text == "<h1>Incident Room</h1>"

    backup = repository.backup(tmp_path / "backups" / "snapshot.db")
    restored = IncidentRepository(backup)
    assert restored.count_incidents() == repository.count_incidents()
    restored.close()
    with pytest.raises(ValueError, match="diferente do banco ativo"):
        repository.backup(settings.database_path)
    repository.close()
