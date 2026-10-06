"""Solicitud de aprobación de un descuento que deja el margen bajo el mínimo (RN-07, RN-09)."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.domain.errors import DomainError, InvalidTransitionError, PermissionDeniedError
from app.domain.parties import Actor, Role

RESOLVER_ROLES = frozenset({Role.APROBADOR, Role.GERENTE})


class CommentRequiredError(DomainError):
    """Aprobar o rechazar exige un comentario."""


class ApprovalStatus(StrEnum):
    PENDIENTE = "PENDIENTE"
    APROBADA = "APROBADA"
    RECHAZADA = "RECHAZADA"


@dataclass
class ApprovalRequest:
    cotizacion_id: int
    solicitante_id: int
    solicitada_en: datetime
    # Vencimiento del SLA en tiempo hábil; al pasar, la solicitud se escala al gerente.
    vence_en: datetime
    estado: ApprovalStatus = ApprovalStatus.PENDIENTE
    escalada: bool = False
    escalada_en: datetime | None = None
    resuelta_en: datetime | None = None
    resuelta_por_id: int | None = None
    comentario: str | None = None
    id: int | None = None

    @property
    def pendiente(self) -> bool:
        return self.estado is ApprovalStatus.PENDIENTE

    def debe_escalarse(self, ahora: datetime) -> bool:
        return self.pendiente and not self.escalada and ahora >= self.vence_en

    def escalar(self, ahora: datetime) -> None:
        if not self.pendiente or self.escalada:
            raise InvalidTransitionError("Solo se escala una solicitud pendiente que no haya sido escalada")
        self.escalada = True
        self.escalada_en = ahora

    def resolver(self, aprobar: bool, actor: Actor, comentario: str, ahora: datetime) -> None:
        if actor.rol not in RESOLVER_ROLES:
            raise PermissionDeniedError("Solo un aprobador o el gerente comercial pueden resolver aprobaciones")
        # Segregación de funciones: quien propone un descuento no puede aprobarlo.
        if actor.id == self.solicitante_id:
            raise PermissionDeniedError("Quien propone un descuento no puede aprobarlo ni rechazarlo")
        if not self.pendiente:
            raise InvalidTransitionError("La solicitud de aprobación ya fue resuelta")
        comentario = (comentario or "").strip()
        if not comentario:
            raise CommentRequiredError("El comentario es obligatorio para aprobar o rechazar")
        self.estado = ApprovalStatus.APROBADA if aprobar else ApprovalStatus.RECHAZADA
        self.resuelta_en = ahora
        self.resuelta_por_id = actor.id
        self.comentario = comentario

    def resuelta_dentro_del_sla(self) -> bool:
        return self.resuelta_en is not None and self.resuelta_en <= self.vence_en
