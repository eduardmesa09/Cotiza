"""Motor de reglas de precios (sección 6.6 del informe).

Módulo puro: no hace I/O, no lee el reloj y no conoce la base de datos. Recibe los datos
maestros y los parámetros comerciales como argumentos y devuelve el resultado del cálculo,
de modo que el mismo insumo produce siempre el mismo resultado.

El orden de aplicación de las reglas es parte de la política comercial:

    precio = lista
    precio *= (1 - nivel)                       RN-02
    precio *= (1 - max(volumen, promoción))     RN-03, RN-04, RN-05
    precio *= (1 - adicional)                   RN-06
    redondear a 2 decimales                     RN-14
    margen = (precio - costo) / precio
    evaluar piso absoluto y margen mínimo       RN-08, RN-07
    disponibilidad neta                         RN-10
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

from app.domain.errors import InvalidLineError, PricingConfigError

CENT = Decimal("0.01")
MARGIN_PRECISION = Decimal("0.0001")
ZERO = Decimal("0")
ONE = Decimal("1")


class LineStatus(StrEnum):
    OK = "OK"
    NO_COTIZABLE = "NO_COTIZABLE"
    BAJO_COSTO = "BAJO_COSTO"


class Evaluation(StrEnum):
    """Resultado de evaluar la cotización completa. No es un estado del ciclo de vida."""

    LISTA_PARA_EMITIR = "LISTA_PARA_EMITIR"
    REQUIERE_APROBACION = "REQUIERE_APROBACION"
    NO_EMITIBLE = "NO_EMITIBLE"


# --- Parámetros comerciales (vienen de la base de datos) --------------------------------


@dataclass(frozen=True)
class VolumeTier:
    cantidad_min: int
    cantidad_max: int | None  # None = sin tope
    descuento: Decimal


@dataclass(frozen=True)
class PricingParams:
    descuentos_nivel: Mapping[str, Decimal]
    escalas_volumen: Sequence[VolumeTier]
    margenes_minimos: Mapping[str, Decimal]


@dataclass(frozen=True)
class Promotion:
    nombre: str
    descuento: Decimal
    fecha_inicio: date
    fecha_fin: date  # inclusive


# --- Entradas y salidas del cálculo -----------------------------------------------------


@dataclass(frozen=True)
class ProductData:
    referencia: str
    descripcion: str
    categoria: str
    costo: Decimal | None
    precio_lista: Decimal | None


@dataclass(frozen=True)
class LineInput:
    referencia: str
    cantidad: int
    descuento_adicional: Decimal = ZERO


@dataclass(frozen=True)
class AppliedRule:
    """Rastro de auditoría: qué regla intervino, con qué valor y qué precio dejó."""

    regla: str
    descripcion: str
    valor: Decimal | None = None
    precio_resultante: Decimal | None = None


@dataclass(frozen=True)
class LineResult:
    referencia: str
    cantidad: int
    descuento_adicional: Decimal
    descripcion: str
    categoria: str
    estado: LineStatus
    reglas_aplicadas: tuple[AppliedRule, ...]
    costo: Decimal | None = None
    precio_lista: Decimal | None = None
    precio_unitario: Decimal | None = None
    total: Decimal | None = None
    margen: Decimal | None = None  # fracción con 4 decimales: 0.1502 = 15,02 %
    margen_minimo: Decimal | None = None
    requiere_aprobacion: bool = False
    bajo_pedido: bool = False
    disponible: int | None = None
    # Unidades que la línea comprometería del inventario al emitirse (RN-10).
    cantidad_comprometible: int = 0
    # Fin de la promoción aplicada, si la hubo: limita la vigencia de la cotización (RN-11).
    promocion_fin: date | None = None


# --- Funciones auxiliares ---------------------------------------------------------------


def round_money(value: Decimal) -> Decimal:
    """RN-14: dos decimales, redondeo comercial (mitad hacia arriba)."""
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def _pct(fraction: Decimal) -> str:
    """0.04 -> '4 %', 0.1502 -> '15,02 %' (formato del informe)."""
    return f"{(fraction * 100).normalize():f}".replace(".", ",") + " %"


def volume_discount(cantidad: int, escalas: Sequence[VolumeTier]) -> Decimal:
    """RN-03: descuento de la escala en la que cae la cantidad; 0 si no cae en ninguna."""
    for tier in escalas:
        if cantidad >= tier.cantidad_min and (tier.cantidad_max is None or cantidad <= tier.cantidad_max):
            return tier.descuento
    return ZERO


def net_available(existencias: int, comprometido: int) -> int:
    """RN-10: existencias menos lo comprometido en cotizaciones emitidas y vigentes."""
    return max(existencias - comprometido, 0)


# --- Cálculo ----------------------------------------------------------------------------


def calculate_line(
    line: LineInput,
    product: ProductData,
    nivel: str,
    fecha: date,
    promociones: Sequence[Promotion],
    existencias: int,
    comprometido: int,
    params: PricingParams,
) -> LineResult:
    """Calcula una línea. `promociones` son las registradas para la referencia, vigentes o no:
    el motor decide cuál aplica según `fecha` y deja constancia de las descartadas."""
    if line.cantidad <= 0:
        raise InvalidLineError(f"La cantidad de {line.referencia} debe ser mayor que cero")
    if not ZERO <= line.descuento_adicional < ONE:
        raise InvalidLineError(f"El descuento adicional de {line.referencia} debe estar entre 0 % y menos de 100 %")

    base = dict(
        referencia=line.referencia,
        cantidad=line.cantidad,
        descuento_adicional=line.descuento_adicional,
        descripcion=product.descripcion,
        categoria=product.categoria,
        costo=product.costo,
        precio_lista=product.precio_lista,
    )

    # RN-01
    if product.costo is None or product.precio_lista is None or product.precio_lista <= ZERO:
        faltante = "costo" if product.costo is None else "precio de lista"
        rule = AppliedRule("RN-01", f"Referencia sin {faltante}: no es cotizable")
        return LineResult(**base, estado=LineStatus.NO_COTIZABLE, reglas_aplicadas=(rule,))

    if nivel not in params.descuentos_nivel:
        raise PricingConfigError(f"El nivel de canal '{nivel}' no tiene descuento configurado")
    if product.categoria not in params.margenes_minimos:
        raise PricingConfigError(f"La categoría '{product.categoria}' no tiene margen mínimo configurado")
    margen_minimo = params.margenes_minimos[product.categoria]

    rules: list[AppliedRule] = []

    def record(regla: str, descripcion: str, valor: Decimal | None = None, precio: Decimal | None = None) -> None:
        rules.append(AppliedRule(regla, descripcion, valor, round_money(precio) if precio is not None else None))

    precio = product.precio_lista
    record("RN-01", "Precio de lista vigente", precio=precio)

    # RN-02
    d_nivel = params.descuentos_nivel[nivel]
    precio *= ONE - d_nivel
    record("RN-02", f"Descuento por nivel {nivel} ({_pct(d_nivel)})", d_nivel, precio)

    # RN-03
    d_volumen = volume_discount(line.cantidad, params.escalas_volumen)

    # RN-04
    vigentes = []
    for promo in promociones:
        if fecha > promo.fecha_fin:
            record("RN-04", f"Promoción '{promo.nombre}' descartada: venció el {promo.fecha_fin.isoformat()}", promo.descuento)
        elif fecha < promo.fecha_inicio:
            record("RN-04", f"Promoción '{promo.nombre}' descartada: inicia el {promo.fecha_inicio.isoformat()}", promo.descuento)
        else:
            vigentes.append(promo)
    promo = max(vigentes, key=lambda p: p.descuento, default=None)

    # RN-05: entre volumen y promoción, solo el mayor. En caso de empate gana el volumen,
    # porque no acorta la vigencia de la cotización (RN-11).
    promocion_fin = None
    if promo is not None and promo.descuento > d_volumen:
        precio *= ONE - promo.descuento
        promocion_fin = promo.fecha_fin
        if d_volumen > ZERO:
            record("RN-05", f"Escala por volumen ({_pct(d_volumen)}) no aplicada: la promoción es mayor", d_volumen)
        record("RN-04", f"Promoción vigente '{promo.nombre}' ({_pct(promo.descuento)})", promo.descuento, precio)
    else:
        if promo is not None:
            record("RN-05", f"Promoción '{promo.nombre}' ({_pct(promo.descuento)}) no aplicada: no supera la escala por volumen", promo.descuento)
        if d_volumen > ZERO:
            precio *= ONE - d_volumen
            record("RN-03", f"Escala por volumen para {line.cantidad} u ({_pct(d_volumen)})", d_volumen, precio)

    # RN-06
    if line.descuento_adicional > ZERO:
        precio *= ONE - line.descuento_adicional
        record("RN-06", f"Descuento adicional propuesto ({_pct(line.descuento_adicional)})", line.descuento_adicional, precio)

    # RN-14: único redondeo del algoritmo.
    precio = round_money(precio)
    if precio > ZERO:
        margen = ((precio - product.costo) / precio).quantize(MARGIN_PRECISION, rounding=ROUND_HALF_UP)
    else:
        # Un descuento extremo puede redondear el precio a 0,00: se trata como pérdida total.
        margen = -ONE

    # RN-08
    estado = LineStatus.OK
    if precio < product.costo:
        estado = LineStatus.BAJO_COSTO
        record("RN-08", f"Precio {precio} inferior al costo {product.costo}: no emitible", precio=precio)

    # RN-07: se compara el margen ya redondeado, que es el que ve el usuario.
    requiere_aprobacion = margen < margen_minimo
    if requiere_aprobacion:
        record("RN-07", f"Margen {_pct(margen)} inferior al mínimo de {product.categoria} ({_pct(margen_minimo)})", margen)

    # RN-10
    disponible = net_available(existencias, comprometido)
    bajo_pedido = line.cantidad > disponible
    if bajo_pedido:
        record("RN-10", f"Bajo pedido: se solicitan {line.cantidad} u y hay {disponible} disponibles")

    return LineResult(
        **base,
        estado=estado,
        reglas_aplicadas=tuple(rules),
        precio_unitario=precio,
        total=round_money(precio * line.cantidad),
        margen=margen,
        margen_minimo=margen_minimo,
        requiere_aprobacion=requiere_aprobacion,
        bajo_pedido=bajo_pedido,
        disponible=disponible,
        cantidad_comprometible=min(line.cantidad, disponible),
        promocion_fin=promocion_fin,
    )


def evaluate_quote(lines: Sequence[LineResult]) -> Evaluation:
    """Función estado_cotización del informe. Una cotización sin líneas no es emitible."""
    if not lines or any(line.estado is not LineStatus.OK for line in lines):
        return Evaluation.NO_EMITIBLE
    if any(line.requiere_aprobacion for line in lines):
        return Evaluation.REQUIERE_APROBACION
    return Evaluation.LISTA_PARA_EMITIR


def quote_total(lines: Sequence[LineResult]) -> Decimal:
    """Suma de las líneas con precio; las no cotizables no aportan."""
    return sum((line.total for line in lines if line.total is not None), ZERO)
