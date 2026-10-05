"""Modelos ORM (SQLAlchemy 2.x). Son detalle de infraestructura: el dominio no los importa.

Convenciones:
- Porcentajes como fracción (0.0400 = 4 %) en Numeric(6, 4).
- Dinero en USD con dos decimales (RN-14) en Numeric(14, 2).
- Fechas y horas siempre con zona horaria.
"""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

Percent = Numeric(6, 4)
Money = Numeric(14, 2)
Timestamp = DateTime(timezone=True)


class Base(DeclarativeBase):
    # Nombres de restricciones deterministas: las migraciones quedan estables y legibles.
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(column_0_label)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


# --- Usuarios -------------------------------------------------------------------------


class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario: Mapped[str] = mapped_column(String(50), unique=True)
    nombre: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(100))
    # ejecutivo | aprobador | gerente | pricing | admin
    rol: Mapped[str] = mapped_column(String(20))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    creado_en: Mapped[datetime] = mapped_column(Timestamp)


# --- Parámetros comerciales (los administra el rol de pricing) -------------------------


class NivelCanal(Base):
    """RN-02: descuento asociado al nivel del canal."""

    __tablename__ = "niveles_canal"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(30), unique=True)
    descuento: Mapped[Decimal] = mapped_column(Percent)


class Canal(Base):
    __tablename__ = "canales"

    id: Mapped[int] = mapped_column(primary_key=True)
    nit: Mapped[str] = mapped_column(String(20), unique=True)
    nombre: Mapped[str] = mapped_column(String(160))
    ciudad: Mapped[str] = mapped_column(String(80))
    contacto_nombre: Mapped[str] = mapped_column(String(120))
    contacto_email: Mapped[str] = mapped_column(String(120))
    nivel_id: Mapped[int] = mapped_column(ForeignKey("niveles_canal.id"))

    nivel: Mapped[NivelCanal] = relationship()


class EscalaVolumen(Base):
    """RN-03: descuento por cantidad de la línea. cantidad_max nula = sin tope."""

    __tablename__ = "escalas_volumen"

    id: Mapped[int] = mapped_column(primary_key=True)
    cantidad_min: Mapped[int] = mapped_column(Integer, unique=True)
    cantidad_max: Mapped[int | None] = mapped_column(Integer)
    descuento: Mapped[Decimal] = mapped_column(Percent)


class MargenCategoria(Base):
    """RN-07: margen mínimo por categoría."""

    __tablename__ = "margenes_categoria"

    id: Mapped[int] = mapped_column(primary_key=True)
    categoria: Mapped[str] = mapped_column(String(40), unique=True)
    margen_minimo: Mapped[Decimal] = mapped_column(Percent)


class Promocion(Base):
    """RN-04: promoción de fabricante por referencia, con vigencia (ambas fechas inclusive)."""

    __tablename__ = "promociones"

    id: Mapped[int] = mapped_column(primary_key=True)
    referencia: Mapped[str] = mapped_column(String(30), index=True)
    nombre: Mapped[str] = mapped_column(String(160))
    descuento: Mapped[Decimal] = mapped_column(Percent)
    fecha_inicio: Mapped[date] = mapped_column(Date)
    fecha_fin: Mapped[date] = mapped_column(Date)
    creada_en: Mapped[datetime] = mapped_column(Timestamp)


class Parametro(Base):
    """Parámetros generales: plazos de SLA, seguimiento y vigencia, y horario hábil."""

    __tablename__ = "parametros"

    clave: Mapped[str] = mapped_column(String(60), primary_key=True)
    valor: Mapped[str] = mapped_column(String(120))
    descripcion: Mapped[str] = mapped_column(String(255))


# --- Cotizaciones ---------------------------------------------------------------------


class Cotizacion(Base):
    __tablename__ = "cotizaciones"
    __table_args__ = (UniqueConstraint("numero", "version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    # El número identifica la cotización frente al canal; cada modificación tras la emisión
    # crea una fila nueva con el mismo número y la versión siguiente (RN-13).
    numero: Mapped[str] = mapped_column(String(20), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    version_anterior_id: Mapped[int | None] = mapped_column(ForeignKey("cotizaciones.id"))
    reemplazada: Mapped[bool] = mapped_column(Boolean, default=False)

    canal_id: Mapped[int] = mapped_column(ForeignKey("canales.id"))
    ejecutivo_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), index=True)

    # BORRADOR | CALCULADA | PENDIENTE_APROBACION | EMITIDA | EN_SEGUIMIENTO | GANADA | PERDIDA | VENCIDA
    estado: Mapped[str] = mapped_column(String(30), index=True)
    # Resultado del último cálculo: LISTA_PARA_EMITIR | REQUIERE_APROBACION | NO_EMITIBLE
    evaluacion: Mapped[str | None] = mapped_column(String(30))
    total: Mapped[Decimal | None] = mapped_column(Money)

    # Momento en que el canal hizo la solicitud; base del tiempo de respuesta (K3).
    recibida_en: Mapped[datetime] = mapped_column(Timestamp)
    creada_en: Mapped[datetime] = mapped_column(Timestamp)
    calculada_en: Mapped[datetime | None] = mapped_column(Timestamp)
    emitida_en: Mapped[datetime | None] = mapped_column(Timestamp)
    vigente_hasta: Mapped[datetime | None] = mapped_column(Timestamp)
    proximo_seguimiento_en: Mapped[datetime | None] = mapped_column(Timestamp)
    cerrada_en: Mapped[datetime | None] = mapped_column(Timestamp)

    pdf_ruta: Mapped[str | None] = mapped_column(String(255))

    canal: Mapped[Canal] = relationship()
    ejecutivo: Mapped[Usuario] = relationship()
    lineas: Mapped[list["LineaCotizacion"]] = relationship(
        back_populates="cotizacion", cascade="all, delete-orphan", order_by="LineaCotizacion.orden"
    )


class LineaCotizacion(Base):
    __tablename__ = "lineas_cotizacion"

    id: Mapped[int] = mapped_column(primary_key=True)
    cotizacion_id: Mapped[int] = mapped_column(ForeignKey("cotizaciones.id", ondelete="CASCADE"), index=True)
    orden: Mapped[int] = mapped_column(Integer)

    referencia: Mapped[str] = mapped_column(String(30), index=True)
    cantidad: Mapped[int] = mapped_column(Integer)
    descuento_adicional: Mapped[Decimal] = mapped_column(Percent, default=Decimal("0"))

    # Todo lo que sigue es una foto del momento del cálculo. Tras la emisión no se vuelve a
    # consultar el catálogo: así los precios quedan congelados (RN-13).
    descripcion: Mapped[str | None] = mapped_column(String(255))
    categoria: Mapped[str | None] = mapped_column(String(40))
    costo: Mapped[Decimal | None] = mapped_column(Money)
    precio_lista: Mapped[Decimal | None] = mapped_column(Money)
    precio_unitario: Mapped[Decimal | None] = mapped_column(Money)
    total: Mapped[Decimal | None] = mapped_column(Money)
    margen: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    margen_minimo: Mapped[Decimal | None] = mapped_column(Percent)

    # OK | NO_COTIZABLE | BAJO_COSTO
    estado: Mapped[str | None] = mapped_column(String(20))
    requiere_aprobacion: Mapped[bool] = mapped_column(Boolean, default=False)
    bajo_pedido: Mapped[bool] = mapped_column(Boolean, default=False)
    disponible: Mapped[int | None] = mapped_column(Integer)
    # Unidades que esta línea compromete del inventario mientras la cotización esté vigente (RN-10).
    cantidad_comprometida: Mapped[int] = mapped_column(Integer, default=0)
    # Fin de la promoción efectivamente aplicada, si la hubo; limita la vigencia (RN-11).
    promocion_fin: Mapped[date | None] = mapped_column(Date)
    reglas_aplicadas: Mapped[list | None] = mapped_column(JSONB)

    cotizacion: Mapped[Cotizacion] = relationship(back_populates="lineas")


# --- Aprobaciones, seguimiento y notificaciones ----------------------------------------


class SolicitudAprobacion(Base):
    __tablename__ = "solicitudes_aprobacion"

    id: Mapped[int] = mapped_column(primary_key=True)
    cotizacion_id: Mapped[int] = mapped_column(ForeignKey("cotizaciones.id"), index=True)
    solicitante_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    # PENDIENTE | APROBADA | RECHAZADA
    estado: Mapped[str] = mapped_column(String(20), index=True)
    solicitada_en: Mapped[datetime] = mapped_column(Timestamp)
    # Vencimiento del SLA (RN-09), calculado en tiempo hábil al crear la solicitud.
    vence_en: Mapped[datetime] = mapped_column(Timestamp)
    escalada: Mapped[bool] = mapped_column(Boolean, default=False)
    escalada_en: Mapped[datetime | None] = mapped_column(Timestamp)
    resuelta_en: Mapped[datetime | None] = mapped_column(Timestamp)
    resuelta_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    comentario: Mapped[str | None] = mapped_column(Text)

    cotizacion: Mapped[Cotizacion] = relationship()
    solicitante: Mapped[Usuario] = relationship(foreign_keys=[solicitante_id])
    resuelta_por: Mapped[Usuario | None] = relationship(foreign_keys=[resuelta_por_id])


class TareaSeguimiento(Base):
    __tablename__ = "tareas_seguimiento"

    id: Mapped[int] = mapped_column(primary_key=True)
    cotizacion_id: Mapped[int] = mapped_column(ForeignKey("cotizaciones.id"), index=True)
    ejecutivo_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), index=True)
    # PENDIENTE | CERRADA
    estado: Mapped[str] = mapped_column(String(20), index=True)
    creada_en: Mapped[datetime] = mapped_column(Timestamp)
    cerrada_en: Mapped[datetime | None] = mapped_column(Timestamp)
    # GANADA | PERDIDA | MANTENER | VENCIDA
    resultado: Mapped[str | None] = mapped_column(String(20))
    nota: Mapped[str | None] = mapped_column(Text)

    cotizacion: Mapped[Cotizacion] = relationship()


class Notificacion(Base):
    """Notificaciones dentro de la aplicación (adaptador MVP de NotificationPort)."""

    __tablename__ = "notificaciones"

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), index=True)
    cotizacion_id: Mapped[int | None] = mapped_column(ForeignKey("cotizaciones.id"))
    tipo: Mapped[str] = mapped_column(String(40))
    mensaje: Mapped[str] = mapped_column(String(500))
    leida: Mapped[bool] = mapped_column(Boolean, default=False)
    creada_en: Mapped[datetime] = mapped_column(Timestamp)


# --- Registro de eventos --------------------------------------------------------------


class Evento(Base):
    """Evento inmutable por cada transición. Fuente de los KPIs y pista de auditoría.

    Un disparador en la base de datos (ver migración inicial) rechaza UPDATE y DELETE.
    """

    __tablename__ = "eventos"
    __table_args__ = (Index("ix_eventos_tipo_ocurrido_en", "tipo", "ocurrido_en"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tipo: Mapped[str] = mapped_column(String(40))
    cotizacion_id: Mapped[int | None] = mapped_column(ForeignKey("cotizaciones.id"), index=True)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    ocurrido_en: Mapped[datetime] = mapped_column(Timestamp)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
