from __future__ import annotations

from pathlib import Path

from .models import Skill


SKILLS_DIRECTORY = Path(__file__).parents[1] / "skills"


def load_skills(directory: Path = SKILLS_DIRECTORY) -> list[Skill]:
    skills = [Skill.model_validate_json(path.read_text(encoding="utf-8")) for path in sorted(directory.glob("*.json"))]
    if not skills:
        raise RuntimeError(f"Nenhuma skill encontrada em {directory}.")
    ids = [skill.id for skill in skills]
    if len(ids) != len(set(ids)):
        raise RuntimeError("Existem skills com identificadores duplicados.")
    return skills


SKILLS = load_skills()
SKILL_MAP = {skill.id: skill for skill in SKILLS}

