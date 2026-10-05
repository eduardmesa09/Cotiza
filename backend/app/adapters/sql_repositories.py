"""Repositorios sobre PostgreSQL. Traducen entre los modelos ORM y las entidades de dominio."""

from collections.abc import Sequence
from datetime import datetime, time
from decimal import Decimal
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.domain.business_time import BusinessCalendar
from app.domain.errors import PricingConfigError
from app.domain.pricing_engine import (
    AppliedRule,
    Evaluation,
    LineResult,
    LineStatus,
    PricingParams,
    Promotion,
    VolumeTier,
)
from app.domain.quote import Quote, QuoteLine
from app.domain.settings import BusinessSettings
from app.domain.state_machine import COMMITTING_STATES, QuoteState
from app.infra.models import (
    Cotizacion,
    EscalaVolumen,
    LineaCotizacion,
    MargenCategoria,
    NivelCanal,
    Parametro,
    Promocion,
    SolicitudAprobacion,
)

# --- Cotizaciones ---------------------------------------------------------------------


def _decimal_or_none(value: str | None) -> Decimal | None:
    return Decimal(value) if value is not None else None


def _str_or_none(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def _line_to_row(linea: QuoteLine, orden: int) -> LineaCotizacion:
    row = LineaCotizacion(
        orden=orden,
        referencia=linea.referencia,
        cantidad=linea.cantidad,
        descuento_adicional=linea.descuento_adicional,
        bajo_pedido=linea.bajo_pedido,
        disponible=linea.disponible,
        cantidad_comprometida=linea.cantidad_comprometida,
        requiere_aprobacion=False,
    )
    r = linea.resultado
    if r is not None:
        row.descripcion = r.descripcion
        row.categoria = r.categoria
        row.costo = r.costo
        row.precio_lista = r.precio_lista
        row.precio_unitario = r.precio_unitario
        row.total = r.total
        row.margen = r.margen
        row.margen_minimo = r.margen_minimo
        row.estado = r.estado
        row.requiere_aprobacion = r.requiere_aprobacion
        row.promocion_fin = r.promocion_fin
        row.reglas_aplicadas = [
            {
                "regla": regla.regla,
                "descripcion": regla.descripcion,
                "valor": _str_or_none(regla.valor),
                "precio_resultante": _str_or_none(regla.precio_resultante),
            }
            for regla in r.reglas_aplicadas
        ]
    return row


def _row_to_line(row: LineaCotizacion) -> QuoteLine:
    resultado = None
    if row.estado is not None:
        resultado = LineResult(
            referencia=row.referencia,
            cantidad=row.cantidad,
            descuento_adicional=row.descuento_adicional,
            descripcion=row.descripcion or "",
            categoria=row.categoria or "",
            estado=LineStatus(row.estado),
            reglas_aplicadas=tuple(
                AppliedRule(
                    r["regla"], r["descripcion"], _decimal_or_none(r["valor"]), _decimal_or_none(r["precio_resultante"])
                )
                for r in (row.reglas_aplicadas or [])
            ),
            costo=row.costo,
            precio_lista=row.precio_lista,
            precio_unitario=row.precio_unitario,
            total=row.total,
            margen=row.margen,
            margen_minimo=row.margen_minimo,
            requiere_aprobacion=row.requiere_aprobacion,
            bajo_pedido=row.bajo_pedido,
            disponible=row.disponible,
            cantidad_comprometible=min(row.cantidad, row.disponible or 0),
            promocion_fin=row.promocion_fin,
        )
    return QuoteLine(
        referencia=row.referencia,
        cantidad=row.cantidad,
        descuento_adicional=row.descuento_adicional,
        resultado=resultado,
        cantidad_comprometida=row.cantidad_comprometida,
        disponible=row.disponible,
        bajo_pedido=row.bajo_pedido,
    )


_SCALAR_FIELDS = (
    "numero",
    "version",
    "version_anterior_id",
    "reemplazada",
    "canal_id",
    "ejecutivo_id",
    "total",
    "recibida_en",
    "creada_en",
    "calculada_en",
    "emitida_en",
    "vigente_hasta",
    "proximo_seguimiento_en",
    "cerrada_en",
    "pdf_ruta",
)


class SqlQuoteRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def _copy_to_row(self, quote: Quote, row: Cotizacion) -> None:
        for name in _SCALAR_FIELDS:
            setattr(row, name, getattr(quote, name))
        row.estado = quote.estado
        row.evaluacion = quote.evaluacion
        # Las líneas se reemplazan completas: no tienen identidad propia fuera de la cotización.
        row.lineas = [_line_to_row(linea, orden) for orden, linea in enumerate(quote.lineas, start=1)]

    def _to_domain(self, row: Cotizacion) -> Quote:
        estado = QuoteState(row.estado)
        return Quote(
            id=row.id,
            estado=estado,
            evaluacion=Evaluation(row.evaluacion) if row.evaluacion else None,
            lineas=[_row_to_line(linea) for linea in row.lineas],
            aprobada=estado is QuoteState.PENDIENTE_APROBACION and self._last_request_state(row.id) == "APROBADA",
            **{name: getattr(row, name) for name in _SCALAR_FIELDS},
        )

    def _last_request_state(self, quote_id: int) -> str | None:
        return self.session.scalar(
            select(SolicitudAprobacion.estado)
            .where(SolicitudAprobacion.cotizacion_id == quote_id)
            .order_by(SolicitudAprobacion.id.desc())
            .limit(1)
        )

    def add(self, quote: Quote) -> Quote:
        row = Cotizacion()
        self._copy_to_row(quote, row)
        if not quote.numero:
            # Marcador único provisional: el número definitivo se deriva del id tras insertar.
            row.numero = f"TMP-{uuid4().hex[:12]}"
        self.session.add(row)
        self.session.flush()
        if not quote.numero:
            # Una versión nueva conserva el número de la anterior; una cotización nueva estrena uno.
            row.numero = f"COT-{row.id:06d}"
            self.session.flush()
        quote.id = row.id
        quote.numero = row.numero
        return quote

    def get(self, quote_id: int) -> Quote | None:
        row = self.session.get(Cotizacion, quote_id)
        return self._to_domain(row) if row else None

    def save(self, quote: Quote) -> None:
        row = self.session.get(Cotizacion, quote.id)
        self._copy_to_row(quote, row)
        self.session.flush()

    def list(self, ejecutivo_id: int | None = None, estado: QuoteState | None = None) -> Sequence[Quote]:
        query = select(Cotizacion).options(selectinload(Cotizacion.lineas)).order_by(Cotizacion.creada_en.desc(), Cotizacion.id.desc())
        if ejecutivo_id is not None:
            query = query.where(Cotizacion.ejecutivo_id == ejecutivo_id)
        if estado is not None:
            query = query.where(Cotizacion.estado == estado)
        return [self._to_domain(row) for row in self.session.scalars(query)]

    def committed_quantity(self, referencia: str, ahora: datetime) -> int:
        return self.session.scalar(
            select(func.coalesce(func.sum(LineaCotizacion.cantidad_comprometida), 0))
            .join(Cotizacion, Cotizacion.id == LineaCotizacion.cotizacion_id)
            .where(
                LineaCotizacion.referencia == referencia,
                Cotizacion.estado.in_(COMMITTING_STATES),
                Cotizacion.reemplazada.is_(False),
                Cotizacion.vigente_hasta > ahora,
            )
        )


# --- Parámetros comerciales -----------------------------------------------------------


class SqlPricingRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_params(self) -> PricingParams:
        return PricingParams(
            descuentos_nivel={n.nombre: n.descuento for n in self.session.scalars(select(NivelCanal))},
            escalas_volumen=tuple(
                VolumeTier(e.cantidad_min, e.cantidad_max, e.descuento)
                for e in self.session.scalars(select(EscalaVolumen).order_by(EscalaVolumen.cantidad_min))
            ),
            margenes_minimos={m.categoria: m.margen_minimo for m in self.session.scalars(select(MargenCategoria))},
        )

    def promotions_for(self, referencia: str) -> Sequence[Promotion]:
        rows = self.session.scalars(
            select(Promocion).where(Promocion.referencia == referencia).order_by(Promocion.fecha_inicio)
        )
        return [Promotion(p.nombre, p.descuento, p.fecha_inicio, p.fecha_fin) for p in rows]

    def get_settings(self) -> BusinessSettings:
        values = {p.clave: p.valor for p in self.session.scalars(select(Parametro))}
        try:
            return BusinessSettings(
                sla_aprobacion_minutos=int(values["sla_aprobacion_minutos"]),
                sla_respuesta_minutos=int(values["sla_respuesta_minutos"]),
                seguimiento_minutos=int(values["seguimiento_minutos"]),
                vigencia_minutos=int(values["vigencia_minutos"]),
                calendar=BusinessCalendar(
                    inicio=time.fromisoformat(values["horario_habil_inicio"]),
                    fin=time.fromisoformat(values["horario_habil_fin"]),
                    dias=frozenset(int(d) for d in values["horario_habil_dias"].split(",")),
                    tz=ZoneInfo(values["zona_horaria"]),
                    activo=values["horario_habil_activo"].strip().lower() == "true",
                ),
            )
        except (KeyError, ValueError) as exc:
            raise PricingConfigError(f"Parámetro de configuración faltante o inválido: {exc}") from exc
