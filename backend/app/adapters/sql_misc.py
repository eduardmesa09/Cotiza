"""Adaptadores MVP sobre PostgreSQL: canales semilla, registro de eventos y notificaciones."""

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.domain.events import Event, EventType
from app.domain.parties import Channel, Role
from app.infra.models import Canal, Evento, Notificacion, Usuario


class SqlCustomerAdapter:
    """CustomerPort: los canales son datos semilla; en producción vendrían del CRM."""

    def __init__(self, session: Session) -> None:
        self.session = session

    @staticmethod
    def _to_domain(row: Canal) -> Channel:
        return Channel(
            id=row.id,
            nit=row.nit,
            nombre=row.nombre,
            nivel=row.nivel.nombre,
            ciudad=row.ciudad,
            contacto_nombre=row.contacto_nombre,
            contacto_email=row.contacto_email,
        )

    def get(self, canal_id: int) -> Channel | None:
        row = self.session.get(Canal, canal_id)
        return self._to_domain(row) if row else None

    def list(self) -> Sequence[Channel]:
        rows = self.session.scalars(select(Canal).options(joinedload(Canal.nivel)).order_by(Canal.nombre))
        return [self._to_domain(row) for row in rows]


class SqlEventAdapter:
    """EventPort: tabla de eventos de solo inserción."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def record(
        self,
        tipo: EventType,
        ocurrido_en: datetime,
        cotizacion_id: int | None = None,
        usuario_id: int | None = None,
        payload: dict | None = None,
    ) -> None:
        self.session.add(
            Evento(tipo=tipo, ocurrido_en=ocurrido_en, cotizacion_id=cotizacion_id, usuario_id=usuario_id, payload=payload or {})
        )
        self.session.flush()

    def list_for_quote(self, cotizacion_id: int) -> Sequence[Event]:
        rows = self.session.scalars(
            select(Evento).where(Evento.cotizacion_id == cotizacion_id).order_by(Evento.ocurrido_en, Evento.id)
        )
        return [
            Event(
                id=row.id,
                tipo=EventType(row.tipo),
                ocurrido_en=row.ocurrido_en,
                cotizacion_id=row.cotizacion_id,
                usuario_id=row.usuario_id,
                payload=row.payload,
            )
            for row in rows
        ]


class SqlNotificationAdapter:
    """NotificationPort: notificaciones dentro de la aplicación."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def notify(self, usuario_id: int, tipo: str, mensaje: str, ahora: datetime, cotizacion_id: int | None = None) -> None:
        self.session.add(
            Notificacion(usuario_id=usuario_id, tipo=tipo, mensaje=mensaje, cotizacion_id=cotizacion_id, leida=False, creada_en=ahora)
        )
        self.session.flush()


class SqlUserDirectory:
    """UserDirectoryPort: usuarios activos por rol, para dirigir las notificaciones."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def ids_with_role(self, rol: Role) -> Sequence[int]:
        return list(
            self.session.scalars(
                select(Usuario.id).where(Usuario.rol == rol, Usuario.activo.is_(True)).order_by(Usuario.id)
            )
        )
