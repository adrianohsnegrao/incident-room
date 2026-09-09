from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _csv(name: str, default: str = "") -> tuple[str, ...]:
    return tuple(item.strip() for item in os.getenv(name, default).split(",") if item.strip())


@dataclass(frozen=True)
class Settings:
    environment: str
    host: str
    port: int
    database_path: Path
    frontend_dist: Path
    allowed_origins: tuple[str, ...]
    max_evidence_items: int


def load_settings() -> Settings:
    environment = os.getenv("INCIDENT_ROOM_ENV", "development").strip().lower()
    port = int(os.getenv("PORT", "8030"))
    max_evidence_items = int(os.getenv("INCIDENT_ROOM_MAX_EVIDENCE", "100"))
    if not 1 <= port <= 65535:
        raise ValueError("PORT deve estar entre 1 e 65535.")
    if not 1 <= max_evidence_items <= 1_000:
        raise ValueError("INCIDENT_ROOM_MAX_EVIDENCE deve estar entre 1 e 1000.")
    return Settings(
        environment=environment,
        host=os.getenv("HOST", "127.0.0.1" if environment != "production" else "0.0.0.0"),
        port=port,
        database_path=Path(os.getenv("INCIDENT_ROOM_DB", str(ROOT / ".local" / "incident-room.db"))).resolve(),
        frontend_dist=Path(os.getenv("INCIDENT_ROOM_FRONTEND_DIST", str(ROOT / "frontend" / "dist"))).resolve(),
        allowed_origins=_csv("INCIDENT_ROOM_ALLOWED_ORIGINS", "http://127.0.0.1:5176,http://localhost:5176"),
        max_evidence_items=max_evidence_items,
    )
