"""Puertos hacia sistemas externos y servicios técnicos.

En el MVP los implementan el ERP simulado, los datos semilla, WeasyPrint y el disco local;
en la arquitectura objetivo, el ERP real, el CRM y los servicios de AWS (sección 7.3).
"""

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from app.domain.events import Event, EventType
from app.domain.parties import Channel, Role
from app.domain.pricing_engine import ProductData


class CatalogPort(Protocol):
    """Datos maestros: costo, precio de lista y categoría por referencia."""

    def get(self, referencia: str) -> ProductData | None: ...

    def search(self, texto: str, limite: int = 20) -> Sequence[ProductData]: ...


class InventoryPort(Protocol):
    """Existencias por referencia (sin descontar lo comprometido)."""

    def stock(self, referencia: str) -> int: ...


class CustomerPort(Protocol):
    """Canales de distribución y su nivel comercial."""

    def get(self, canal_id: int) -> Channel | None: ...

    def list(self) -> Sequence[Channel]: ...


class DocumentPort(Protocol):
    """Genera el documento de la cotización a partir de datos ya resueltos."""

    def render_quote(self, datos: dict) -> bytes: ...


class StoragePort(Protocol):
    """Guarda y recupera archivos (los PDF emitidos)."""

    def save(self, nombre: str, contenido: bytes) -> str: ...

    def read(self, ruta: str) -> bytes: ...


class NotificationPort(Protocol):
    def notify(self, usuario_id: int, tipo: str, mensaje: str, ahora: datetime, cotizacion_id: int | None = None) -> None: ...


class EventPort(Protocol):
    """Registro inmutable de eventos: solo se agregan y se consultan."""

    def record(
        self,
        tipo: EventType,
        ocurrido_en: datetime,
        cotizacion_id: int | None = None,
        usuario_id: int | None = None,
        payload: dict | None = None,
    ) -> None: ...

    def list_for_quote(self, cotizacion_id: int) -> Sequence[Event]: ...

    def list_all(self) -> Sequence[Event]:
        """Todos los eventos en orden cronológico: la fuente de los indicadores."""
        ...


class ClockPort(Protocol):
    """Única fuente de la hora actual, para que los plazos sean verificables en pruebas."""

    def now(self) -> datetime: ...


class UserDirectoryPort(Protocol):
    """Usuarios internos: a quién avisar (activos por rol) y cómo se llaman."""

    def ids_with_role(self, rol: Role) -> Sequence[int]: ...

    def name_of(self, usuario_id: int) -> str | None: ...
