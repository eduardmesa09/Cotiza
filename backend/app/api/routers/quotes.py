from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import (
    CurrentUser,
    get_approval_service,
    get_current_user,
    get_followup_service,
    get_quote_service,
)
from app.api.presenters import QuotePresenter, quote_detail
from app.api.schemas import CloseIn, EventOut, QuoteIn, QuoteOut, QuoteSummaryOut
from app.application.approvals import ApprovalService
from app.application.followup import FollowUpService
from app.application.quotes import QuoteService
from app.domain.followup import TaskOutcome
from app.domain.quote import QuoteLine
from app.domain.state_machine import QuoteState
from app.infra.db import get_session

router = APIRouter(prefix="/api/cotizaciones", tags=["Cotizaciones"])


def _lines_in(body: QuoteIn) -> list[QuoteLine]:
    return [QuoteLine(linea.referencia, linea.cantidad, linea.descuento_adicional) for linea in body.lineas]


@router.post("", response_model=QuoteOut, status_code=status.HTTP_201_CREATED)
def create_quote(
    body: QuoteIn,
    user: CurrentUser = Depends(get_current_user),
    service: QuoteService = Depends(get_quote_service),
    session: Session = Depends(get_session),
) -> QuoteOut:
    quote = service.create(user.actor, body.canal_id, body.recibida_en, _lines_in(body))
    session.commit()
    return quote_detail(session, quote)


@router.get("", response_model=list[QuoteSummaryOut])
def list_quotes(
    estado: QuoteState | None = Query(None),
    user: CurrentUser = Depends(get_current_user),
    service: QuoteService = Depends(get_quote_service),
    session: Session = Depends(get_session),
) -> list[dict]:
    quotes = service.list(user.actor, estado)
    presenter = QuotePresenter(session, quotes)
    return [presenter.summary(q) for q in quotes]


@router.get("/{quote_id}", response_model=QuoteOut)
def get_quote(
    quote_id: int,
    user: CurrentUser = Depends(get_current_user),
    service: QuoteService = Depends(get_quote_service),
    session: Session = Depends(get_session),
) -> QuoteOut:
    return quote_detail(session, service.get(user.actor, quote_id))


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
    return quote_detail(session, quote)


@router.post("/{quote_id}/calcular", response_model=QuoteOut)
def calculate_quote(
    quote_id: int,
    user: CurrentUser = Depends(get_current_user),
    service: QuoteService = Depends(get_quote_service),
    session: Session = Depends(get_session),
) -> QuoteOut:
    quote = service.calculate(user.actor, quote_id)
    session.commit()
    return quote_detail(session, quote)


@router.post("/{quote_id}/solicitar-aprobacion", response_model=QuoteOut)
def request_approval(
    quote_id: int,
    user: CurrentUser = Depends(get_current_user),
    service: ApprovalService = Depends(get_approval_service),
    session: Session = Depends(get_session),
) -> QuoteOut:
    """Envía a la cola de aprobación una cotización con margen bajo el mínimo (RN-07)."""
    quote = service.request(user.actor, quote_id)
    session.commit()
    return quote_detail(session, quote)


@router.post("/{quote_id}/emitir", response_model=QuoteOut)
def issue_quote(
    quote_id: int,
    user: CurrentUser = Depends(get_current_user),
    service: QuoteService = Depends(get_quote_service),
    session: Session = Depends(get_session),
) -> QuoteOut:
    quote = service.issue(user.actor, quote_id)
    session.commit()
    return quote_detail(session, quote)


@router.post("/{quote_id}/cerrar", response_model=QuoteOut)
def close_quote(
    quote_id: int,
    body: CloseIn,
    user: CurrentUser = Depends(get_current_user),
    service: FollowUpService = Depends(get_followup_service),
    session: Session = Depends(get_session),
) -> QuoteOut:
    """Cierra como ganada (orden recibida) o perdida (el canal declina)."""
    quote = service.close(user.actor, quote_id, TaskOutcome(body.resultado), body.nota)
    session.commit()
    return quote_detail(session, quote)


@router.post("/{quote_id}/nueva-version", response_model=QuoteOut, status_code=status.HTTP_201_CREATED)
def new_version(
    quote_id: int,
    user: CurrentUser = Depends(get_current_user),
    service: FollowUpService = Depends(get_followup_service),
    session: Session = Depends(get_session),
) -> QuoteOut:
    """RN-13: una cotización emitida no se modifica; se reemplaza por una versión nueva en borrador."""
    quote = service.new_version(user.actor, quote_id)
    session.commit()
    return quote_detail(session, quote)


@router.get("/{quote_id}/eventos", response_model=list[EventOut])
def quote_history(
    quote_id: int,
    user: CurrentUser = Depends(get_current_user),
    service: QuoteService = Depends(get_quote_service),
    session: Session = Depends(get_session),
) -> list[EventOut]:
    events = service.history(user.actor, quote_id)
    presenter = QuotePresenter(session, [])
    return [
        EventOut(
            id=e.id,
            tipo=e.tipo,
            ocurrido_en=e.ocurrido_en,
            # Los eventos sin usuario los generó el planificador.
            usuario=presenter.user_name(e.usuario_id) if e.usuario_id is not None else "Sistema",
            payload=e.payload,
        )
        for e in events
    ]
