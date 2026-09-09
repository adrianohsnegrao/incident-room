from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from .repository import IncidentRepository
from .settings import load_settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="incident-room", description="Operações locais do Incident Room.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    backup = subparsers.add_parser("backup", help="Cria uma cópia íntegra do banco da central.")
    backup.add_argument("--output", type=Path, help="Arquivo de destino opcional.")
    args = parser.parse_args(argv)

    if args.command == "backup":
        settings = load_settings()
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        destination = args.output or settings.database_path.parent / "backups" / f"incident-room-{timestamp}.db"
        repository = IncidentRepository(settings.database_path)
        try:
            print(repository.backup(destination).resolve())
        finally:
            repository.close()
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
