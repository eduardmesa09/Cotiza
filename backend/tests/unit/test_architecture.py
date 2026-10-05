"""Regla de puertos y adaptadores: el núcleo no depende de infraestructura."""

import ast
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[2] / "app"
CORE_PACKAGES = ("domain", "application", "ports")
FORBIDDEN = ("fastapi", "sqlalchemy", "httpx", "weasyprint", "apscheduler", "app.infra", "app.adapters", "app.api")

CORE_FILES = sorted(f for package in CORE_PACKAGES for f in (APP / package).rglob("*.py"))


def imported_modules(path: Path) -> set[str]:
    modules = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


@pytest.mark.parametrize("path", CORE_FILES, ids=lambda p: str(p.relative_to(APP)))
def test_el_nucleo_no_importa_infraestructura(path):
    prohibidos = {
        m for m in imported_modules(path) if any(m == f or m.startswith(f + ".") for f in FORBIDDEN)
    }
    assert not prohibidos, f"{path.relative_to(APP)} importa {sorted(prohibidos)}"


def test_el_dominio_no_lee_el_reloj():
    """El tiempo entra siempre como argumento (ClockPort), nunca con datetime.now()."""
    for path in (APP / "domain").rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert ".now(" not in source and ".today(" not in source and ".utcnow(" not in source, path.name
