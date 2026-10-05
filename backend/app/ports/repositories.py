"""Puertos de persistencia: lo que los casos de uso necesitan guardar y consultar."""

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

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


class PricingRepository(Protocol):
    """Parámetros comerciales administrados por el rol de pricing."""

    def get_params(self) -> PricingParams: ...

    def promotions_for(self, referencia: str) -> Sequence[Promotion]:
        """Todas las promociones de la referencia, vigentes o no: el motor decide cuál aplica."""
        ...

    def get_settings(self) -> BusinessSettings: ...
