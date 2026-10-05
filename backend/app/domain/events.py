"""Eventos de dominio. Cada transición de la cotización registra uno, inmutable (A8)."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class EventType(StrEnum):
    COTIZACION_CREADA = "COTIZACION_CREADA"
    COTIZACION_EDITADA = "COTIZACION_EDITADA"
    COTIZACION_CALCULADA = "COTIZACION_CALCULADA"
    APROBACION_SOLICITADA = "APROBACION_SOLICITADA"
    APROBACION_APROBADA = "APROBACION_APROBADA"
    APROBACION_RECHAZADA = "APROBACION_RECHAZADA"
    APROBACION_ESCALADA = "APROBACION_ESCALADA"
    COTIZACION_EMITIDA = "COTIZACION_EMITIDA"
    SEGUIMIENTO_PROGRAMADO = "SEGUIMIENTO_PROGRAMADO"
    SEGUIMIENTO_INICIADO = "SEGUIMIENTO_INICIADO"
    SEGUIMIENTO_MANTENIDO = "SEGUIMIENTO_MANTENIDO"
    COTIZACION_GANADA = "COTIZACION_GANADA"
    COTIZACION_PERDIDA = "COTIZACION_PERDIDA"
    COTIZACION_VENCIDA = "COTIZACION_VENCIDA"
    COTIZACION_REEMPLAZADA = "COTIZACION_REEMPLAZADA"
    NUEVA_VERSION_CREADA = "NUEVA_VERSION_CREADA"


@dataclass(frozen=True)
class Event:
    tipo: EventType
    ocurrido_en: datetime
    cotizacion_id: int | None = None
    usuario_id: int | None = None  # None: lo generó el sistema (planificador)
    payload: dict = field(default_factory=dict)
    id: int | None = None
