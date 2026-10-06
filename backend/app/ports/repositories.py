"""Puertos de persistencia: lo que los casos de uso necesitan guardar y consultar."""

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from app.domain.approval import ApprovalRequest
from app.domain.followup import FollowUpTask
from app.domain.pricing_engine import PricingParams, Promotion
from app.domain.quote import Quote
from app.domain.settings import BusinessSettings
from app.domain.state_machine import QuoteState


class QuoteRepository(Protocol):
    def add(self, quote: Quote) -> Quote:
        """Guarda una cotización nueva y le asigna id y número."""
        ...

    def get(self, quote_id: int) -> Quote | None: ...

    def save(self, quote: Quote) -> None: ...

    def list(self, ejecutivo_id: int | None = None, estado: QuoteState | None = None) -> Sequence[Quote]: ...

    def committed_quantity(self, referencia: str, ahora: datetime) -> int:
        """RN-10: unidades comprometidas en cotizaciones emitidas, vigentes y no reemplazadas."""
        ...

    def list_expired(self, ahora: datetime) -> Sequence[Quote]:
        """Emitidas o en seguimiento, no reemplazadas, cuya vigencia ya terminó."""
        ...

    def list_due_follow_up(self, ahora: datetime) -> Sequence[Quote]:
        """Emitidas o en seguimiento, no reemplazadas, con seguimiento programado ya cumplido."""
        ...


class PricingRepository(Protocol):
    """Parámetros comerciales administrados por el rol de pricing."""

    def get_params(self) -> PricingParams: ...

    def promotions_for(self, referencia: str) -> Sequence[Promotion]:
        """Todas las promociones de la referencia, vigentes o no: el motor decide cuál aplica."""
        ...

    def get_settings(self) -> BusinessSettings: ...


class ApprovalRepository(Protocol):
    def add(self, request: ApprovalRequest) -> ApprovalRequest: ...

    def get(self, request_id: int) -> ApprovalRequest | None: ...

    def save(self, request: ApprovalRequest) -> None: ...

    def latest_for_quote(self, quote_id: int) -> ApprovalRequest | None: ...

    def list_pending(self, solo_escaladas: bool = False) -> Sequence[ApprovalRequest]: ...

    def list_overdue(self, ahora: datetime) -> Sequence[ApprovalRequest]:
        """Pendientes, sin escalar, con el SLA vencido."""
        ...


class FollowUpRepository(Protocol):
    def add(self, task: FollowUpTask) -> FollowUpTask: ...

    def get(self, task_id: int) -> FollowUpTask | None: ...

    def save(self, task: FollowUpTask) -> None: ...

    def list_pending(self, ejecutivo_id: int | None = None) -> Sequence[FollowUpTask]: ...

    def pending_for_quote(self, quote_id: int) -> Sequence[FollowUpTask]: ...
