"""Quiénes intervienen en el proceso: usuarios internos (por rol) y canales."""

from dataclasses import dataclass
from enum import StrEnum


class Role(StrEnum):
    EJECUTIVO = "ejecutivo"
    APROBADOR = "aprobador"
    GERENTE = "gerente"
    PRICING = "pricing"
    ADMIN = "admin"


# Tabla 32: roles que consultan todas las cotizaciones (el ejecutivo solo ve las suyas).
ROLES_THAT_SEE_ALL_QUOTES = frozenset({Role.APROBADOR, Role.GERENTE, Role.PRICING})


@dataclass(frozen=True)
class Actor:
    """Usuario autenticado que ejecuta un caso de uso."""

    id: int
    rol: Role


@dataclass(frozen=True)
class Channel:
    id: int
    nit: str
    nombre: str
    nivel: str
    ciudad: str
    contacto_nombre: str
    contacto_email: str
