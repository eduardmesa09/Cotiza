"""Administración de pricing (M7): niveles de canal, escalas, márgenes mínimos, promociones y parámetros.

Es gestión de datos sin flujo de proceso, por eso estas rutas trabajan directo con el ORM;
las reglas de calidad de las promociones sí viven en el dominio.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.sql_repositories import SqlPricingRepository
from app.api.deps import CurrentUser, get_clock, require_roles
from app.api.schemas import (
    DiscountIn,
    LevelOut,
    MarginIn,
    MarginOut,
    ParameterIn,
    ParameterOut,
    PromotionIn,
    PromotionOut,
    VolumeTierOut,
)
from app.domain.errors import DomainError
from app.domain.parties import Role
from app.domain.promotions import InvalidPromotionError, overlaps, validate_promotion
from app.infra.db import get_session
from app.infra.models import EscalaVolumen, MargenCategoria, NivelCanal, Parametro, Promocion
from app.ports.external import ClockPort

router = APIRouter(prefix="/api/pricing", tags=["Administración de pricing"])

pricing_only = require_roles(Role.PRICING)
# Los parámetros de plazos y horario también los ajusta el administrador del sistema (Tabla 31).
pricing_or_admin = require_roles(Role.PRICING, Role.ADMIN)


def _get_or_404(session: Session, model, key, nombre: str):
    row = session.get(model, key)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{nombre} no existe")
    return row


# --- Niveles de canal (RN-02) ---------------------------------------------------------


@router.get("/niveles", response_model=list[LevelOut])
def list_levels(session: Session = Depends(get_session), _: CurrentUser = Depends(pricing_only)) -> list:
    return list(session.scalars(select(NivelCanal).order_by(NivelCanal.descuento.desc())))


@router.put("/niveles/{level_id}", response_model=LevelOut)
def update_level(
    level_id: int, body: DiscountIn, session: Session = Depends(get_session), _: CurrentUser = Depends(pricing_only)
) -> NivelCanal:
    row = _get_or_404(session, NivelCanal, level_id, "El nivel")
    row.descuento = body.descuento
    session.commit()
    session.refresh(row)
    return row


# --- Escalas por volumen (RN-03) ------------------------------------------------------


@router.get("/escalas", response_model=list[VolumeTierOut])
def list_tiers(session: Session = Depends(get_session), _: CurrentUser = Depends(pricing_only)) -> list:
    return list(session.scalars(select(EscalaVolumen).order_by(EscalaVolumen.cantidad_min)))


@router.put("/escalas/{tier_id}", response_model=VolumeTierOut)
def update_tier(
    tier_id: int, body: DiscountIn, session: Session = Depends(get_session), _: CurrentUser = Depends(pricing_only)
) -> EscalaVolumen:
    row = _get_or_404(session, EscalaVolumen, tier_id, "La escala")
    row.descuento = body.descuento
    session.commit()
    session.refresh(row)
    return row


# --- Márgenes mínimos por categoría (RN-07) -------------------------------------------


@router.get("/margenes", response_model=list[MarginOut])
def list_margins(session: Session = Depends(get_session), _: CurrentUser = Depends(pricing_only)) -> list:
    return list(session.scalars(select(MargenCategoria).order_by(MargenCategoria.categoria)))


@router.put("/margenes/{margin_id}", response_model=MarginOut)
def update_margin(
    margin_id: int, body: MarginIn, session: Session = Depends(get_session), _: CurrentUser = Depends(pricing_only)
) -> MargenCategoria:
    row = _get_or_404(session, MargenCategoria, margin_id, "El margen")
    row.margen_minimo = body.margen_minimo
    session.commit()
    session.refresh(row)
    return row


# --- Promociones (RN-04) --------------------------------------------------------------


def _validate_promotion(session: Session, body: PromotionIn, exclude_id: int | None = None) -> None:
    validate_promotion(body.descuento, body.fecha_inicio, body.fecha_fin)
    others = session.scalars(select(Promocion).where(Promocion.referencia == body.referencia))
    for other in others:
        if other.id != exclude_id and overlaps(body.fecha_inicio, body.fecha_fin, other.fecha_inicio, other.fecha_fin):
            raise InvalidPromotionError(
                f"La vigencia se superpone con la promoción '{other.nombre}' "
                f"({other.fecha_inicio.isoformat()} a {other.fecha_fin.isoformat()}) de la misma referencia"
            )


@router.get("/promociones", response_model=list[PromotionOut])
def list_promotions(
    referencia: str | None = None, session: Session = Depends(get_session), _: CurrentUser = Depends(pricing_only)
) -> list:
    query = select(Promocion).order_by(Promocion.fecha_fin.desc(), Promocion.id)
    if referencia:
        query = query.where(Promocion.referencia == referencia.strip().upper())
    return list(session.scalars(query))


@router.post("/promociones", response_model=PromotionOut, status_code=status.HTTP_201_CREATED)
def create_promotion(
    body: PromotionIn,
    session: Session = Depends(get_session),
    clock: ClockPort = Depends(get_clock),
    _: CurrentUser = Depends(pricing_only),
) -> Promocion:
    _validate_promotion(session, body)
    row = Promocion(**body.model_dump(), creada_en=clock.now())
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


@router.put("/promociones/{promotion_id}", response_model=PromotionOut)
def update_promotion(
    promotion_id: int,
    body: PromotionIn,
    session: Session = Depends(get_session),
    _: CurrentUser = Depends(pricing_only),
) -> Promocion:
    row = _get_or_404(session, Promocion, promotion_id, "La promoción")
    _validate_promotion(session, body, exclude_id=promotion_id)
    for field, value in body.model_dump().items():
        setattr(row, field, value)
    session.commit()
    session.refresh(row)
    return row


@router.delete("/promociones/{promotion_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_promotion(
    promotion_id: int, session: Session = Depends(get_session), _: CurrentUser = Depends(pricing_only)
) -> None:
    # Las cotizaciones ya emitidas no se afectan: guardan una foto de sus precios (RN-13).
    session.delete(_get_or_404(session, Promocion, promotion_id, "La promoción"))
    session.commit()


# --- Parámetros de plazos y horario ---------------------------------------------------


@router.get("/parametros", response_model=list[ParameterOut])
def list_parameters(session: Session = Depends(get_session), _: CurrentUser = Depends(pricing_or_admin)) -> list:
    return list(session.scalars(select(Parametro).order_by(Parametro.clave)))


@router.put("/parametros/{clave}", response_model=ParameterOut)
def update_parameter(
    clave: str, body: ParameterIn, session: Session = Depends(get_session), _: CurrentUser = Depends(pricing_or_admin)
) -> Parametro:
    row = _get_or_404(session, Parametro, clave, "El parámetro")
    row.valor = body.valor.strip()
    session.flush()
    # Un valor que deje la configuración ilegible rompería todos los plazos: se valida antes de confirmar.
    try:
        settings = SqlPricingRepository(session).get_settings()
        plazos = (
            settings.sla_aprobacion_minutos,
            settings.sla_respuesta_minutos,
            settings.seguimiento_minutos,
            settings.vigencia_minutos,
        )
        if clave.endswith("_minutos") or clave.endswith("_segundos"):
            if int(row.valor) <= 0 or min(plazos) <= 0:
                raise ValueError("debe ser un entero mayor que cero")
    except (DomainError, ValueError) as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Valor inválido para {clave}: {exc}"
        ) from exc
    session.commit()
    session.refresh(row)
    return row
