"""Tarea de seguimiento de una cotización emitida sin respuesta del canal (RN-12)."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.domain.errors import InvalidTransitionError


class TaskStatus(StrEnum):
    PENDIENTE = "PENDIENTE"
    CERRADA = "CERRADA"


class TaskOutcome(StrEnum):
    GANADA = "GANADA"
    PERDIDA = "PERDIDA"
    MANTENER = "MANTENER"  # sigue en seguimiento: se programa un nuevo recordatorio
    VENCIDA = "VENCIDA"  # la cerró el sistema al vencer la vigencia
    REEMPLAZADA = "REEMPLAZADA"  # la cerró el sistema al crearse una nueva versión


@dataclass
class FollowUpTask:
    cotizacion_id: int
    ejecutivo_id: int
    creada_en: datetime
    estado: TaskStatus = TaskStatus.PENDIENTE
    cerrada_en: datetime | None = None
    resultado: TaskOutcome | None = None
    nota: str | None = None
    id: int | None = None

    def cerrar(self, resultado: TaskOutcome, ahora: datetime, nota: str | None = None) -> None:
        if self.estado is not TaskStatus.PENDIENTE:
            raise InvalidTransitionError("La tarea de seguimiento ya está cerrada")
        self.estado = TaskStatus.CERRADA
        self.cerrada_en = ahora
        self.resultado = resultado
        self.nota = (nota or "").strip() or None
