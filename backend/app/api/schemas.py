"""Esquemas de entrada y salida de la API (Pydantic v2).

Los porcentajes viajan como fracción (0.04 = 4 %) y los importes como texto decimal, para no
perder precisión en JSON.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from app.domain.parties import Role

Fraction = Annotated[Decimal, Field(ge=0, lt=1, max_digits=6, decimal_places=4)]

# --- Autenticación y usuarios ---------------------------------------------------------


class LoginIn(BaseModel):
    usuario: str
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    usuario: str
    nombre: str
    rol: Role


class UserAdminOut(UserOut):
    email: str
    activo: bool


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    usuario: UserOut


class UserCreateIn(BaseModel):
    usuario: str = Field(min_length=3, max_length=50, pattern=r"^[a-z0-9._-]+$")
    nombre: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=3, max_length=120)
    rol: Role
    password: str = Field(min_length=8, max_length=72)


class UserUpdateIn(BaseModel):
    nombre: str | None = Field(default=None, min_length=1, max_length=120)
    email: str | None = Field(default=None, min_length=3, max_length=120)
    rol: Role | None = None
    activo: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=72)


# --- Catálogo y canales ---------------------------------------------------------------


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    referencia: str
    descripcion: str
    categoria: str
    costo: Decimal | None
    precio_lista: Decimal | None
    cotizable: bool


class ChannelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nit: str
    nombre: str
    nivel: str
    ciudad: str


# --- Cotizaciones ---------------------------------------------------------------------


class LineIn(BaseModel):
    referencia: str = Field(min_length=1, max_length=30)
    cantidad: int = Field(gt=0, le=1_000_000)
    descuento_adicional: Fraction = Decimal("0")

    @field_validator("referencia")
    @classmethod
    def normalize_reference(cls, value: str) -> str:
        return value.strip().upper()


class QuoteIn(BaseModel):
    canal_id: int
    # Con zona horaria obligatoria: es la base del tiempo de respuesta al canal (K3).
    recibida_en: AwareDatetime
    lineas: list[LineIn] = Field(default_factory=list, max_length=200)


class AppliedRuleOut(BaseModel):
    regla: str
    descripcion: str
    valor: Decimal | None
    precio_resultante: Decimal | None


class LineOut(BaseModel):
    referencia: str
    cantidad: int
    descuento_adicional: Decimal
    descripcion: str | None = None
    categoria: str | None = None
    estado: str | None = None
    costo: Decimal | None = None
    precio_lista: Decimal | None = None
    precio_unitario: Decimal | None = None
    total: Decimal | None = None
    margen: Decimal | None = None
    margen_minimo: Decimal | None = None
    requiere_aprobacion: bool = False
    bajo_pedido: bool = False
    disponible: int | None = None
    cantidad_comprometida: int = 0
    promocion_fin: date | None = None
    reglas_aplicadas: list[AppliedRuleOut] = Field(default_factory=list)


class PartyRef(BaseModel):
    id: int
    nombre: str
    nivel: str | None = None


class QuoteSummaryOut(BaseModel):
    id: int
    numero: str
    version: int
    estado: str
    evaluacion: str | None
    total: Decimal | None
    canal: PartyRef
    ejecutivo: PartyRef
    recibida_en: datetime
    creada_en: datetime
    calculada_en: datetime | None
    emitida_en: datetime | None
    vigente_hasta: datetime | None
    cerrada_en: datetime | None
    reemplazada: bool
    lineas_count: int


class QuoteOut(QuoteSummaryOut):
    lineas: list[LineOut]
    # Lo que el usuario puede hacer ahora con la cotización; la interfaz habilita botones con esto.
    acciones_permitidas: list[str]


class EventOut(BaseModel):
    id: int
    tipo: str
    ocurrido_en: datetime
    usuario: str | None
    payload: dict


# --- Administración de pricing --------------------------------------------------------


class LevelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str
    descuento: Decimal


class DiscountIn(BaseModel):
    descuento: Fraction


class VolumeTierOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    cantidad_min: int
    cantidad_max: int | None
    descuento: Decimal


class MarginOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    categoria: str
    margen_minimo: Decimal


class MarginIn(BaseModel):
    margen_minimo: Fraction


class PromotionIn(BaseModel):
    referencia: str = Field(min_length=1, max_length=30)
    nombre: str = Field(min_length=1, max_length=160)
    descuento: Decimal = Field(gt=0, lt=1, max_digits=6, decimal_places=4)
    fecha_inicio: date
    fecha_fin: date

    @field_validator("referencia")
    @classmethod
    def normalize_reference(cls, value: str) -> str:
        return value.strip().upper()


class PromotionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    referencia: str
    nombre: str
    descuento: Decimal
    fecha_inicio: date
    fecha_fin: date


class ParameterOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    clave: str
    valor: str
    descripcion: str


class ParameterIn(BaseModel):
    valor: str = Field(min_length=1, max_length=120)
