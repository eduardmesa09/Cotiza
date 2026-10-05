from collections.abc import Sequence

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_user, get_quote_service
from app.api.schemas import EventOut, LineOut, PartyRef, QuoteIn, QuoteOut, QuoteSummaryOut
from app.application.quotes import QuoteService
from app.domain.quote import Quote, QuoteLine
from app.domain.state_machine import QuoteState
from app.infra.db import get_session
from app.infra.models import Canal, Usuario

router = APIRouter(prefix="/api/cotizaciones", tags=["Cotizaciones"])


# --- Presentación ---------------------------------------------------------------------


def _lines_in(body: QuoteIn) -> list[QuoteLine]:
    return [QuoteLine(linea.referencia, linea.cantidad, linea.descuento_adicional) for linea in body.lineas]


def _line_out(linea: QuoteLine) -> LineOut:
    r = linea.resultado
    data = dict(
        referencia=linea.referencia,
        cantidad=linea.cantidad,
        descuento_adicional=linea.descuento_adicional,
        bajo_pedido=linea.bajo_pedido,
        disponible=linea.disponible,
        cantidad_comprometida=linea.cantidad_comprometida,
    )
    if r is not None:
        data.update(
            descripcion=r.descripcion,
            categoria=r.categoria,
            estado=r.estado,
            costo=r.costo,
            precio_lista=r.precio_lista,
            precio_unitario=r.precio_unitario,
            total=r.total,
            margen=r.margen,
            margen_minimo=r.margen_minimo,
            requiere_aprobacion=r.requiere_aprobacion,
            promocion_fin=r.promocion_fin,
            reglas_aplicadas=[vars(regla) for regla in r.reglas_aplicadas],
        )
    return LineOut(**data)


class _Names:
    """Nombres de canales y ejecutivos para mostrar; se cargan una vez por respuesta."""

    def __init__(self, session: Session, quotes: Sequence[Quote]) -> None:
        canal_ids = {q.canal_id for q in quotes}
        user_ids = {q.ejecutivo_id for q in quotes}
        self.canales = {c.id: c for c in session.scalars(select(Canal).where(Canal.id.in_(canal_ids)))}
        self.usuarios = {u.id: u for u in session.scalars(select(Usuario).where(Usuario.id.in_(user_ids)))}

    def summary(self, quote: Quote) -> dict:
        canal = self.canales[quote.canal_id]
        return dict(
            id=quote.id,
            numero=quote.numero,
            version=quote.version,
            estado=quote.estado,
            evaluacion=quote.evaluacion,
            total=quote.total,
            canal=PartyRef(id=canal.id, nombre=canal.nombre, nivel=canal.nivel.nombre),
            ejecutivo=PartyRef(id=quote.ejecutivo_id, nombre=self.usuarios[quote.ejecutivo_id].nombre),
            recibida_en=quote.recibida_en,
            creada_en=quote.creada_en,
            calculada_en=quote.calculada_en,
            emitida_en=quote.emitida_en,
            vigente_hasta=quote.vigente_hasta,
            cerrada_en=quote.cerrada_en,
            reemplazada=quote.reemplazada,
            lineas_count=len(quote.lineas),
        )

    def detail(self, quote: Quote) -> QuoteOut:
        return QuoteOut(
            **self.summary(quote),
            lineas=[_line_out(linea) for linea in quote.lineas],
            acciones_permitidas=sorted(quote.acciones_permitidas),
        )


def _detail(session: Session, quote: Quote) -> QuoteOut:
    return _Names(session, [quote]).detail(quote)


# --- Rutas ----------------------------------------------------------------------------


@router.post("", response_model=QuoteOut, status_code=status.HTTP_201_CREATED)
def create_quote(
    body: QuoteIn,
    user: CurrentUser = Depends(get_current_user),
    service: QuoteService = Depends(get_quote_service),
    session: Session = Depends(get_session),
) -> QuoteOut:
    quote = service.create(user.actor, body.canal_id, body.recibida_en, _lines_in(body))
    session.commit()
    return _detail(session, quote)


@router.get("", response_model=list[QuoteSummaryOut])
def list_quotes(
    estado: QuoteState | None = Query(None),
    user: CurrentUser = Depends(get_current_user),
    service: QuoteService = Depends(get_quote_service),
    session: Session = Depends(get_session),
) -> list[dict]:
    quotes = service.list(user.actor, estado)
    names = _Names(session, quotes)
    return [names.summary(q) for q in quotes]


@router.get("/{quote_id}", response_model=QuoteOut)
def get_quote(
    quote_id: int,
    user: CurrentUser = Depends(get_current_user),
    service: QuoteService = Depends(get_quote_service),
    session: Session = Depends(get_session),
) -> QuoteOut:
    return _detail(session, service.get(user.actor, quote_id))


@router.put("/{quote_id}", response_model=QuoteOut)
def update_quote(
    quote_id: int,
    body: QuoteIn,
    user: CurrentUser = Depends(get_current_user),
    service: QuoteService = Depends(get_quote_service),
    session: Session = Depends(get_session),
) -> QuoteOut:
    quote = service.update(user.actor, quote_id, body.canal_id, body.recibida_en, _lines_in(body))
    session.commit()
    return _detail(session, quote)


@router.post("/{quote_id}/calcular", response_model=QuoteOut)
def calculate_quote(
    quote_id: int,
    user: CurrentUser = Depends(get_current_user),
    service: QuoteService = Depends(get_quote_service),
    session: Session = Depends(get_session),
) -> QuoteOut:
    quote = service.calculate(user.actor, quote_id)
    session.commit()
    return _detail(session, quote)


@router.post("/{quote_id}/emitir", response_model=QuoteOut)
def issue_quote(
    quote_id: int,
    user: CurrentUser = Depends(get_current_user),
    service: QuoteService = Depends(get_quote_service),
    session: Session = Depends(get_session),
) -> QuoteOut:
    quote = service.issue(user.actor, quote_id)
    session.commit()
    return _detail(session, quote)


@router.get("/{quote_id}/eventos", response_model=list[EventOut])
def quote_history(
    quote_id: int,
    user: CurrentUser = Depends(get_current_user),
    service: QuoteService = Depends(get_quote_service),
    session: Session = Depends(get_session),
) -> list[EventOut]:
    events = service.history(user.actor, quote_id)
    user_ids = {e.usuario_id for e in events if e.usuario_id is not None}
    names = {u.id: u.nombre for u in session.scalars(select(Usuario).where(Usuario.id.in_(user_ids)))}
    return [
        EventOut(
            id=e.id,
            tipo=e.tipo,
            ocurrido_en=e.ocurrido_en,
            # Los eventos sin usuario los generó el planificador.
            usuario=names.get(e.usuario_id) if e.usuario_id is not None else "Sistema",
            payload=e.payload,
        )
        for e in events
    ]
