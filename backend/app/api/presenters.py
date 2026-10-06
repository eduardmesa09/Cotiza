"""Convierte entidades de dominio en las respuestas de la API, resolviendo los nombres a mostrar."""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import ApprovalBrief, LineOut, PartyRef, QuoteOut
from app.domain.quote import Quote, QuoteLine
from app.infra.models import Canal, SolicitudAprobacion, Usuario


def line_out(linea: QuoteLine) -> LineOut:
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


class QuotePresenter:
    """Carga una sola vez los nombres de canales y usuarios de un conjunto de cotizaciones."""

    def __init__(self, session: Session, quotes: Sequence[Quote]) -> None:
        self.session = session
        canal_ids = {q.canal_id for q in quotes}
        self.canales = {c.id: c for c in session.scalars(select(Canal).where(Canal.id.in_(canal_ids)))}
        self._usuarios: dict[int, str] = {}
        self._load_users({q.ejecutivo_id for q in quotes})

    def _load_users(self, ids: set[int]) -> None:
        missing = ids - self._usuarios.keys()
        if missing:
            rows = self.session.execute(select(Usuario.id, Usuario.nombre).where(Usuario.id.in_(missing)))
            self._usuarios.update({row.id: row.nombre for row in rows})

    def user_name(self, user_id: int | None) -> str | None:
        if user_id is None:
            return None
        self._load_users({user_id})
        return self._usuarios.get(user_id)

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
            ejecutivo=PartyRef(id=quote.ejecutivo_id, nombre=self.user_name(quote.ejecutivo_id)),
            recibida_en=quote.recibida_en,
            creada_en=quote.creada_en,
            calculada_en=quote.calculada_en,
            emitida_en=quote.emitida_en,
            vigente_hasta=quote.vigente_hasta,
            cerrada_en=quote.cerrada_en,
            reemplazada=quote.reemplazada,
            lineas_count=len(quote.lineas),
        )

    def _approval(self, quote_id: int) -> ApprovalBrief | None:
        """La solicitud más reciente: el ejecutivo ve aquí el comentario de la decisión."""
        row = self.session.scalar(
            select(SolicitudAprobacion)
            .where(SolicitudAprobacion.cotizacion_id == quote_id)
            .order_by(SolicitudAprobacion.id.desc())
            .limit(1)
        )
        if row is None:
            return None
        return ApprovalBrief(
            id=row.id,
            estado=row.estado,
            solicitada_en=row.solicitada_en,
            vence_en=row.vence_en,
            escalada=row.escalada,
            resuelta_en=row.resuelta_en,
            resuelta_por=self.user_name(row.resuelta_por_id),
            comentario=row.comentario,
        )

    def detail(self, quote: Quote) -> QuoteOut:
        return QuoteOut(
            **self.summary(quote),
            lineas=[line_out(linea) for linea in quote.lineas],
            acciones_permitidas=sorted(quote.acciones_permitidas),
            puede_crear_version=quote.puede_versionarse,
            version_anterior_id=quote.version_anterior_id,
            aprobacion=self._approval(quote.id),
        )


def quote_detail(session: Session, quote: Quote) -> QuoteOut:
    return QuotePresenter(session, [quote]).detail(quote)
