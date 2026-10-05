"""La entidad cotización: validaciones, edición, cálculo y emisión."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal as D

import pytest

from app.domain.errors import InvalidLineError, InvalidTransitionError
from app.domain.pricing_engine import (
    Evaluation,
    LineInput,
    PricingParams,
    ProductData,
    Promotion,
    VolumeTier,
    calculate_line,
)
from app.domain.promotions import InvalidPromotionError, overlaps, validate_promotion
from app.domain.quote import Quote, QuoteLine, validate_lines
from app.domain.state_machine import Action, QuoteState

NOW = datetime(2026, 10, 5, 15, 0, tzinfo=timezone.utc)
PARAMS = PricingParams({"Plata": D("0.04")}, (VolumeTier(10, 49, D("0.02")),), {"Portátiles": D("0.08")})
PRODUCT = ProductData("POR-1", "Portátil", "Portátiles", D("620.00"), D("800.00"))
PROMO = Promotion("Promo", D("0.05"), date(2026, 9, 25), date(2026, 11, 4))


def result(cantidad=20, adicional="0", existencias=150):
    line = LineInput("POR-1", cantidad, D(adicional))
    return calculate_line(line, PRODUCT, "Plata", date(2026, 10, 5), [PROMO], existencias, 0, PARAMS)


def new_quote(lineas=None) -> Quote:
    return Quote.nueva(1, 7, NOW - timedelta(minutes=30), NOW, lineas if lineas is not None else [QuoteLine("POR-1", 20)])


def calculated(adicional="0") -> Quote:
    quote = new_quote([QuoteLine("POR-1", 20, D(adicional))])
    quote.calcular({"POR-1": result(adicional=adicional)}, NOW)
    return quote


# --- Creación y validación de líneas --------------------------------------------------


def test_nueva_cotizacion_nace_en_borrador_sin_calculo():
    quote = new_quote()
    assert quote.estado is QuoteState.BORRADOR
    assert quote.evaluacion is None and quote.total is None
    assert quote.version == 1 and not quote.reemplazada
    assert quote.acciones_permitidas == {Action.EDITAR, Action.CALCULAR}


def test_recepcion_en_el_futuro_es_invalida():
    with pytest.raises(InvalidLineError, match="futuro"):
        Quote.nueva(1, 7, NOW + timedelta(seconds=1), NOW)


@pytest.mark.parametrize(
    "lineas, mensaje",
    [
        ([QuoteLine("", 1)], "referencia"),
        ([QuoteLine("A", 0)], "mayor que cero"),
        ([QuoteLine("A", 1, D("1"))], "descuento adicional"),
        ([QuoteLine("A", 1, D("-0.01"))], "descuento adicional"),
        ([QuoteLine("A", 1), QuoteLine("A", 2)], "repetida"),
    ],
)
def test_lineas_invalidas(lineas, mensaje):
    with pytest.raises(InvalidLineError, match=mensaje):
        validate_lines(lineas)


def test_lineas_validas():
    validate_lines([QuoteLine("A", 1), QuoteLine("B", 500, D("0.9999"))])


# --- Calcular -------------------------------------------------------------------------


def test_calcular_registra_resultado_evaluacion_y_total():
    quote = calculated()
    assert quote.estado is QuoteState.CALCULADA
    assert quote.evaluacion is Evaluation.LISTA_PARA_EMITIR
    assert quote.total == D("14592.00")
    assert quote.calculada_en == NOW
    assert quote.lineas[0].disponible == 150 and not quote.lineas[0].bajo_pedido
    assert Action.EMITIR in quote.acciones_permitidas


def test_rn06_proponer_descuento_adicional_reevalua_el_margen():
    quote = calculated(adicional="0.09")
    assert quote.evaluacion is Evaluation.REQUIERE_APROBACION
    assert Action.EMITIR not in quote.acciones_permitidas
    assert Action.SOLICITAR_APROBACION in quote.acciones_permitidas


# --- Editar ---------------------------------------------------------------------------


def test_editar_una_calculada_la_devuelve_a_borrador_y_descarta_el_calculo():
    quote = calculated()
    quote.editar(2, NOW - timedelta(hours=1), [QuoteLine("POR-1", 5), QuoteLine("OTRA", 1)], NOW)
    assert quote.estado is QuoteState.BORRADOR
    assert quote.canal_id == 2
    assert quote.evaluacion is None and quote.total is None and quote.calculada_en is None
    assert all(linea.resultado is None for linea in quote.lineas)


def test_editar_con_lineas_invalidas_no_cambia_nada():
    quote = calculated()
    with pytest.raises(InvalidLineError):
        quote.editar(1, NOW, [QuoteLine("POR-1", 0)], NOW)
    assert quote.estado is QuoteState.CALCULADA and quote.total == D("14592.00")


# --- Emitir ---------------------------------------------------------------------------


def emitir(quote: Quote, disponible=150) -> None:
    quote.emitir(NOW, NOW + timedelta(days=7), NOW + timedelta(hours=48), {"POR-1": disponible})


def test_emitir_fija_fechas_y_compromete_inventario():
    quote = calculated()
    emitir(quote)
    assert quote.estado is QuoteState.EMITIDA
    assert quote.emitida_en == NOW
    assert quote.vigente_hasta == NOW + timedelta(days=7)
    assert quote.proximo_seguimiento_en == NOW + timedelta(hours=48)
    assert quote.lineas[0].cantidad_comprometida == 20


def test_rn10_al_emitir_solo_se_compromete_lo_disponible():
    quote = calculated()
    emitir(quote, disponible=12)
    assert quote.lineas[0].cantidad_comprometida == 12
    assert quote.lineas[0].bajo_pedido and quote.lineas[0].disponible == 12


def test_rn13_emitir_no_toca_los_precios_calculados():
    quote = calculated()
    antes = quote.lineas[0].resultado
    emitir(quote, disponible=0)
    assert quote.lineas[0].resultado is antes
    assert quote.total == D("14592.00")


def test_rn07_no_se_emite_si_requiere_aprobacion_y_nada_cambia():
    quote = calculated(adicional="0.09")
    with pytest.raises(InvalidTransitionError):
        emitir(quote)
    assert quote.estado is QuoteState.CALCULADA
    assert quote.emitida_en is None and quote.lineas[0].cantidad_comprometida == 0


def test_rn13_una_emitida_no_se_edita_ni_se_recalcula():
    quote = calculated()
    emitir(quote)
    with pytest.raises(InvalidTransitionError):
        quote.editar(1, NOW, [QuoteLine("POR-1", 1)], NOW)
    with pytest.raises(InvalidTransitionError):
        quote.calcular({"POR-1": result()}, NOW)
    assert quote.total == D("14592.00")


def test_pendiente_aprobada_se_puede_emitir():
    quote = calculated(adicional="0.09")
    quote.estado = QuoteState.PENDIENTE_APROBACION
    with pytest.raises(InvalidTransitionError, match="no ha sido aprobada"):
        emitir(quote)
    quote.aprobada = True
    emitir(quote)
    assert quote.estado is QuoteState.EMITIDA


# --- Promociones: calidad de datos (Tabla 45) -----------------------------------------


@pytest.mark.parametrize(
    "a, b, esperado",
    [
        ((1, 10), (11, 20), False),  # contiguas
        ((1, 10), (10, 20), True),  # comparten un día
        ((5, 6), (1, 30), True),  # contenida
        ((1, 30), (5, 6), True),
        ((20, 25), (1, 19), False),
    ],
)
def test_superposicion_de_vigencias(a, b, esperado):
    def d(day):
        return date(2026, 10, day)

    assert overlaps(d(a[0]), d(a[1]), d(b[0]), d(b[1])) is esperado


def test_validacion_de_promocion():
    validate_promotion(D("0.05"), date(2026, 10, 1), date(2026, 10, 1))
    with pytest.raises(InvalidPromotionError):
        validate_promotion(D("0.05"), date(2026, 10, 2), date(2026, 10, 1))
    for descuento in ("0", "1", "-0.1"):
        with pytest.raises(InvalidPromotionError):
            validate_promotion(D(descuento), date(2026, 10, 1), date(2026, 10, 31))
