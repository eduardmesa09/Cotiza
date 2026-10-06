"""Cola de aprobaciones (M4), tareas de seguimiento (M6) y notificaciones dentro de la aplicación."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.api.deps import (
    CurrentUser,
    get_approval_service,
    get_current_user,
    get_followup_service,
)
from app.api.presenters import QuotePresenter, quote_detail
from app.api.schemas import (
    ApprovalQueueOut,
    NotificationListOut,
    QuoteOut,
    ResolutionIn,
    TaskOut,
    TaskResolutionIn,
)
from app.application.approvals import ApprovalService
from app.application.followup import FollowUpService
from app.domain.followup import TaskOutcome
from app.infra.db import get_session
from app.infra.models import Notificacion

router = APIRouter(prefix="/api")

# --- Aprobaciones ---------------------------------------------------------------------


@router.get("/aprobaciones", response_model=list[ApprovalQueueOut], tags=["Aprobaciones"])
def approval_queue(
    user: CurrentUser = Depends(get_current_user),
    service: ApprovalService = Depends(get_approval_service),
    session: Session = Depends(get_session),
) -> list[ApprovalQueueOut]:
    """Solicitudes pendientes con el contexto completo y el tiempo restante de SLA.
    El aprobador ve todas; el gerente, las que le fueron escaladas."""
    items = service.queue(user.actor)
    presenter = QuotePresenter(session, [item.cotizacion for item in items])
    return [
        ApprovalQueueOut(
            id=item.solicitud.id,
            solicitada_en=item.solicitud.solicitada_en,
            vence_en=item.solicitud.vence_en,
            escalada=item.solicitud.escalada,
            escalada_en=item.solicitud.escalada_en,
            sla_restante_segundos=item.sla_restante_segundos,
            sla_vencido=item.sla_restante_segundos <= 0,
            solicitante=presenter.user_name(item.solicitud.solicitante_id),
            cotizacion=presenter.detail(item.cotizacion),
        )
        for item in items
    ]


def _resolve(aprobar: bool, request_id: int, body: ResolutionIn, user, service, session) -> QuoteOut:
    quote = service.resolve(user.actor, request_id, aprobar, body.comentario)
    session.commit()
    return quote_detail(session, quote)


@router.post("/aprobaciones/{request_id}/aprobar", response_model=QuoteOut, tags=["Aprobaciones"])
def approve(
    request_id: int,
    body: ResolutionIn,
    user: CurrentUser = Depends(get_current_user),
    service: ApprovalService = Depends(get_approval_service),
    session: Session = Depends(get_session),
) -> QuoteOut:
    return _resolve(True, request_id, body, user, service, session)


@router.post("/aprobaciones/{request_id}/rechazar", response_model=QuoteOut, tags=["Aprobaciones"])
def reject(
    request_id: int,
    body: ResolutionIn,
    user: CurrentUser = Depends(get_current_user),
    service: ApprovalService = Depends(get_approval_service),
    session: Session = Depends(get_session),
) -> QuoteOut:
    return _resolve(False, request_id, body, user, service, session)


# --- Tareas de seguimiento ------------------------------------------------------------


@router.get("/seguimiento", response_model=list[TaskOut], tags=["Seguimiento"])
def follow_up_tasks(
    user: CurrentUser = Depends(get_current_user),
    service: FollowUpService = Depends(get_followup_service),
    session: Session = Depends(get_session),
) -> list[TaskOut]:
    items = service.pending_tasks(user.actor)
    presenter = QuotePresenter(session, [item.cotizacion for item in items])
    return [
        TaskOut(id=item.tarea.id, creada_en=item.tarea.creada_en, cotizacion=presenter.summary(item.cotizacion))
        for item in items
    ]


@router.post("/seguimiento/{task_id}/resolver", response_model=QuoteOut, tags=["Seguimiento"])
def resolve_task(
    task_id: int,
    body: TaskResolutionIn,
    user: CurrentUser = Depends(get_current_user),
    service: FollowUpService = Depends(get_followup_service),
    session: Session = Depends(get_session),
) -> QuoteOut:
    """Atiende la tarea: ganada, perdida o mantener en seguimiento."""
    quote = service.resolve_task(user.actor, task_id, TaskOutcome(body.accion), body.nota)
    session.commit()
    return quote_detail(session, quote)


# --- Notificaciones -------------------------------------------------------------------


@router.get("/notificaciones", response_model=NotificationListOut, tags=["Notificaciones"])
def my_notifications(
    user: CurrentUser = Depends(get_current_user), session: Session = Depends(get_session)
) -> dict:
    mine = Notificacion.usuario_id == user.id
    items = session.scalars(
        select(Notificacion).where(mine).order_by(Notificacion.creada_en.desc(), Notificacion.id.desc()).limit(50)
    )
    unread = session.scalar(select(func.count()).select_from(Notificacion).where(mine, Notificacion.leida.is_(False)))
    return {"no_leidas": unread, "items": list(items)}


@router.post("/notificaciones/leer-todas", status_code=status.HTTP_204_NO_CONTENT, tags=["Notificaciones"])
def mark_all_read(user: CurrentUser = Depends(get_current_user), session: Session = Depends(get_session)) -> None:
    session.execute(update(Notificacion).where(Notificacion.usuario_id == user.id).values(leida=True))
    session.commit()


@router.post("/notificaciones/{notification_id}/leer", status_code=status.HTTP_204_NO_CONTENT, tags=["Notificaciones"])
def mark_read(
    notification_id: int, user: CurrentUser = Depends(get_current_user), session: Session = Depends(get_session)
) -> None:
    row = session.get(Notificacion, notification_id)
    if row is None or row.usuario_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="La notificación no existe")
    row.leida = True
    session.commit()
