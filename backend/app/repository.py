from __future__ import annotations

import sqlite3
from pathlib import Path
from threading import RLock

from .models import Incident, Investigation, TraceStep


class IncidentRepository:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._lock = RLock()
        self._connection = sqlite3.connect(path, check_same_thread=False)
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA foreign_keys=ON")
        self._connection.execute("PRAGMA busy_timeout=5000")
        self._migrate()

    def _migrate(self) -> None:
        with self._connection:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS incidents (
                    id TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS investigations (
                    id TEXT PRIMARY KEY,
                    incident_id TEXT NOT NULL REFERENCES incidents(id),
                    created_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS latest_investigations (
                    incident_id TEXT PRIMARY KEY REFERENCES incidents(id),
                    investigation_id TEXT NOT NULL REFERENCES investigations(id)
                );
                CREATE INDEX IF NOT EXISTS idx_investigations_incident_created
                    ON investigations(incident_id, created_at DESC);
                INSERT OR IGNORE INTO schema_migrations(version, name)
                    VALUES (1, 'persistent-incidents-investigations-decisions');
                """
            )

    def save_incident(self, incident: Incident, *, source: str, replace: bool = False) -> Incident:
        statement = "INSERT OR REPLACE" if replace else "INSERT"
        with self._lock, self._connection:
            self._connection.execute(
                f"{statement} INTO incidents(id, source, started_at, payload_json) VALUES (?, ?, ?, ?)",
                (incident.id, source, incident.started_at, incident.model_dump_json()),
            )
        return incident

    def get_incident(self, incident_id: str) -> Incident | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT payload_json FROM incidents WHERE id = ?", (incident_id,)
            ).fetchone()
        return Incident.model_validate_json(row[0]) if row else None

    def list_incidents(self) -> list[Incident]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT payload_json FROM incidents ORDER BY started_at DESC"
            ).fetchall()
        return [Incident.model_validate_json(row[0]) for row in rows]

    def count_incidents(self) -> int:
        with self._lock:
            return int(self._connection.execute("SELECT COUNT(*) FROM incidents").fetchone()[0])

    def save_investigation(self, investigation: Investigation) -> Investigation:
        with self._lock, self._connection:
            self._connection.execute(
                "INSERT INTO investigations(id, incident_id, created_at, payload_json) VALUES (?, ?, ?, ?)",
                (investigation.id, investigation.incident_id, investigation.created_at, investigation.model_dump_json()),
            )
            self._connection.execute(
                "INSERT OR REPLACE INTO latest_investigations(incident_id, investigation_id) VALUES (?, ?)",
                (investigation.incident_id, investigation.id),
            )
        return investigation

    def get_investigation(self, investigation_id: str) -> Investigation | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT payload_json FROM investigations WHERE id = ?", (investigation_id,)
            ).fetchone()
        return Investigation.model_validate_json(row[0]) if row else None

    def latest_for(self, incident_id: str) -> Investigation | None:
        with self._lock:
            row = self._connection.execute(
                """
                SELECT i.payload_json FROM investigations i
                JOIN latest_investigations l ON l.investigation_id = i.id
                WHERE l.incident_id = ?
                """,
                (incident_id,),
            ).fetchone()
        return Investigation.model_validate_json(row[0]) if row else None

    def latest_all(self) -> list[Investigation]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT i.payload_json FROM investigations i
                JOIN latest_investigations l ON l.investigation_id = i.id
                ORDER BY i.created_at DESC
                """
            ).fetchall()
        return [Investigation.model_validate_json(row[0]) for row in rows]

    def record_decision(
        self,
        investigation_id: str,
        *,
        approved: bool,
        reviewer: str,
        justification: str,
    ) -> Investigation | None:
        with self._lock, self._connection:
            row = self._connection.execute(
                "SELECT payload_json FROM investigations WHERE id = ?", (investigation_id,)
            ).fetchone()
            if not row:
                return None
            investigation = Investigation.model_validate_json(row[0])
            if investigation.approval_status != "pending":
                raise ValueError("Esta investigação não aguarda aprovação.")
            step = TraceStep(
                index=len(investigation.trace) + 1,
                node="human_decision",
                status="success" if approved else "warning",
                title="Mitigação aprovada" if approved else "Mitigação rejeitada",
                detail=f"{reviewer}: {justification}",
                duration_ms=0,
            )
            updated = investigation.model_copy(
                update={
                    "approval_status": "approved" if approved else "rejected",
                    "status": "mitigated" if approved else "rejected",
                    "trace": [*investigation.trace, step],
                }
            )
            self._connection.execute(
                "UPDATE investigations SET payload_json = ? WHERE id = ?",
                (updated.model_dump_json(), investigation_id),
            )
            return updated

    def ready(self) -> bool:
        with self._lock:
            return self._connection.execute("PRAGMA quick_check").fetchone() == ("ok",)

    def backup(self, destination: Path) -> Path:
        destination = destination.resolve()
        if destination == self.path.resolve():
            raise ValueError("O destino do backup deve ser diferente do banco ativo.")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            target = sqlite3.connect(destination)
            try:
                self._connection.backup(target)
                if target.execute("PRAGMA quick_check").fetchone() != ("ok",):
                    raise RuntimeError("A verificação de integridade do backup falhou.")
            finally:
                target.close()
        return destination

    def close(self) -> None:
        with self._lock:
            self._connection.close()
