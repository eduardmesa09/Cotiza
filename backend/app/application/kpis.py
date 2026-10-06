"""Tablero de indicadores (M7): quién ve qué (Tabla 32) y con qué datos se calcula."""

from dataclasses import dataclass
from datetime import datetime

from app.domain.errors import PermissionDeniedError
from app.domain.kpis import KpiReport, compute_kpis, quote_owners
from app.domain.parties import ROLES_THAT_SEE_ALL_QUOTES, Actor, Role
from app.ports.external import ClockPort, EventPort
from app.ports.repositories import PricingRepository


@dataclass(frozen=True)
class Dashboard:
    alcance: str  # "propios" (ejecutivo) o "todos"
    generado_en: datetime
    reporte: KpiReport


class KpiService:
    def __init__(self, events: EventPort, pricing: PricingRepository, clock: ClockPort) -> None:
        self.events = events
        self.pricing = pricing
        self.clock = clock

    def dashboard(self, actor: Actor) -> Dashboard:
        if actor.rol is not Role.EJECUTIVO and actor.rol not in ROLES_THAT_SEE_ALL_QUOTES:
            raise PermissionDeniedError("Su rol no consulta el tablero de indicadores")
        events = self.events.list_all()
        alcance = "todos"
        if actor.rol is Role.EJECUTIVO:
            # El ejecutivo ve solo los indicadores de sus propias cotizaciones.
            owners = quote_owners(events)
            events = [e for e in events if owners.get(e.cotizacion_id) == actor.id]
            alcance = "propios"
        settings = self.pricing.get_settings()
        reporte = compute_kpis(events, settings.calendar, settings.sla_respuesta_minutos)
        return Dashboard(alcance, self.clock.now(), reporte)
