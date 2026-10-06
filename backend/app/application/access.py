"""Reglas de acceso a las cotizaciones (Tabla 32), compartidas por los casos de uso."""

from app.domain.errors import NotFoundError, PermissionDeniedError
from app.domain.parties import ROLES_THAT_SEE_ALL_QUOTES, Actor, Role
from app.domain.quote import Quote
from app.ports.repositories import QuoteRepository


def require_executive(actor: Actor) -> None:
    if actor.rol is not Role.EJECUTIVO:
        raise PermissionDeniedError("Solo un ejecutivo de cuenta puede crear, editar y emitir cotizaciones")


def load_quote(quotes: QuoteRepository, quote_id: int) -> Quote:
    quote = quotes.get(quote_id)
    if quote is None:
        raise NotFoundError(f"La cotización {quote_id} no existe")
    return quote


def load_own_quote(quotes: QuoteRepository, actor: Actor, quote_id: int) -> Quote:
    """La cotización, solo si el actor es el ejecutivo que la creó."""
    require_executive(actor)
    quote = load_quote(quotes, quote_id)
    if quote.ejecutivo_id != actor.id:
        raise PermissionDeniedError("Solo puede modificar sus propias cotizaciones")
    return quote


def can_view(actor: Actor, quote: Quote) -> bool:
    if actor.rol is Role.EJECUTIVO:
        return quote.ejecutivo_id == actor.id
    return actor.rol in ROLES_THAT_SEE_ALL_QUOTES
