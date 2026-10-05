"""Motor de reglas de precios: RN-01 a RN-08, RN-10, RN-14 y el caso obligatorio (6.6.3)."""

from datetime import date
from decimal import Decimal as D

import pytest

from app.domain.errors import InvalidLineError, PricingConfigError
from app.domain.pricing_engine import (
    Evaluation,
    LineInput,
    LineStatus,
    PricingParams,
    ProductData,
    Promotion,
    VolumeTier,
    calculate_line,
    evaluate_quote,
    net_available,
    quote_total,
    volume_discount,
)

HOY = date(2026, 10, 5)

PARAMS = PricingParams(
    descuentos_nivel={"Oro": D("0.06"), "Plata": D("0.04"), "Bronce": D("0.02")},
    escalas_volumen=(
        VolumeTier(10, 49, D("0.02")),
        VolumeTier(50, 99, D("0.04")),
        VolumeTier(100, None, D("0.06")),
    ),
    margenes_minimos={
        "Portátiles": D("0.08"),
        "Periféricos": D("0.12"),
        "Servidores": D("0.10"),
        "Redes": D("0.11"),
        "Impresión": D("0.09"),
    },
)

PORTATIL = ProductData("POR-DEMO01", "Portátil empresarial", "Portátiles", D("620.00"), D("800.00"))
PROMO_5 = Promotion("Promo fabricante", D("0.05"), date(2026, 9, 25), date(2026, 11, 4))


def calc(
    cantidad=1,
    adicional="0",
    product=PORTATIL,
    nivel="Plata",
    fecha=HOY,
    promociones=(),
    existencias=1000,
    comprometido=0,
    params=PARAMS,
):
    line = LineInput(product.referencia, cantidad, D(adicional))
    return calculate_line(line, product, nivel, fecha, promociones, existencias, comprometido, params)


def reglas(result) -> list[str]:
    return [r.regla for r in result.reglas_aplicadas]


# --- Caso de prueba obligatorio (Tabla 34) ---------------------------------------------


def test_caso_obligatorio_sin_aprobacion():
    r = calc(cantidad=20, promociones=[PROMO_5])
    assert r.precio_unitario == D("729.60")
    assert r.margen == D("0.1502")
    assert r.total == D("14592.00")
    assert r.estado is LineStatus.OK
    assert not r.requiere_aprobacion
    assert evaluate_quote([r]) is Evaluation.LISTA_PARA_EMITIR


def test_caso_obligatorio_variante_con_9_por_ciento_adicional_requiere_aprobacion():
    r = calc(cantidad=20, adicional="0.09", promociones=[PROMO_5])
    assert r.precio_unitario == D("663.94")
    assert r.margen == D("0.0662")
    assert r.estado is LineStatus.OK
    assert r.requiere_aprobacion
    assert evaluate_quote([r]) is Evaluation.REQUIERE_APROBACION


def test_caso_obligatorio_deja_el_rastro_de_reglas_con_precios_intermedios():
    r = calc(cantidad=20, promociones=[PROMO_5])
    pasos = {x.regla: x.precio_resultante for x in r.reglas_aplicadas if x.precio_resultante is not None}
    assert pasos == {"RN-01": D("800.00"), "RN-02": D("768.00"), "RN-04": D("729.60")}


# --- RN-01: precio base y referencias no cotizables ------------------------------------


def test_rn01_parte_del_precio_de_lista():
    r = calc(nivel="Bronce", params=PricingParams({"Bronce": D("0")}, (), PARAMS.margenes_minimos))
    assert r.precio_unitario == D("800.00")


@pytest.mark.parametrize(
    "costo, lista, faltante",
    [(None, D("800.00"), "costo"), (D("620.00"), None, "precio de lista"), (D("620.00"), D("0"), "precio de lista")],
)
def test_rn01_sin_costo_o_sin_lista_es_no_cotizable(costo, lista, faltante):
    r = calc(product=ProductData("X-1", "Sin datos", "Portátiles", costo, lista))
    assert r.estado is LineStatus.NO_COTIZABLE
    assert r.precio_unitario is None and r.total is None and r.margen is None
    assert reglas(r) == ["RN-01"]
    assert faltante in r.reglas_aplicadas[0].descripcion
    assert evaluate_quote([r]) is Evaluation.NO_EMITIBLE


# --- RN-02: descuento por nivel --------------------------------------------------------


@pytest.mark.parametrize("nivel, precio", [("Oro", "752.00"), ("Plata", "768.00"), ("Bronce", "784.00")])
def test_rn02_descuento_por_nivel(nivel, precio):
    assert calc(nivel=nivel).precio_unitario == D(precio)


def test_rn02_nivel_sin_configurar_es_error_de_parametros():
    with pytest.raises(PricingConfigError, match="Platino"):
        calc(nivel="Platino")


# --- RN-03: escala por volumen ---------------------------------------------------------


@pytest.mark.parametrize(
    "cantidad, descuento",
    [(1, "0"), (9, "0"), (10, "0.02"), (49, "0.02"), (50, "0.04"), (99, "0.04"), (100, "0.06"), (5000, "0.06")],
)
def test_rn03_escala_por_volumen_en_los_limites(cantidad, descuento):
    assert volume_discount(cantidad, PARAMS.escalas_volumen) == D(descuento)


def test_rn03_la_escala_se_aplica_sobre_el_precio_con_descuento_de_nivel():
    r = calc(cantidad=50)  # 800 × 0,96 × 0,96
    assert r.precio_unitario == D("737.28")
    assert "RN-03" in reglas(r)


def test_rn03_sin_escala_no_deja_rastro_de_volumen():
    assert "RN-03" not in reglas(calc(cantidad=9))


# --- RN-04: vigencia de promociones ----------------------------------------------------


@pytest.mark.parametrize("fecha", [PROMO_5.fecha_inicio, HOY, PROMO_5.fecha_fin])
def test_rn04_promocion_aplica_dentro_de_la_vigencia_con_limites_incluidos(fecha):
    r = calc(fecha=fecha, promociones=[PROMO_5])
    assert r.precio_unitario == D("729.60")
    assert r.promocion_fin == PROMO_5.fecha_fin


def test_rn04_promocion_vencida_se_descarta_y_el_descarte_se_registra():
    vencida = Promotion("Promo de septiembre", D("0.10"), date(2026, 9, 1), date(2026, 10, 4))
    r = calc(promociones=[vencida])
    assert r.precio_unitario == D("768.00")
    assert r.promocion_fin is None
    descarte = next(x for x in r.reglas_aplicadas if x.regla == "RN-04")
    assert "descartada" in descarte.descripcion and "venció el 2026-10-04" in descarte.descripcion
    assert descarte.precio_resultante is None


def test_rn04_promocion_futura_tampoco_aplica():
    futura = Promotion("Promo de noviembre", D("0.10"), date(2026, 10, 6), date(2026, 11, 30))
    r = calc(promociones=[futura])
    assert r.precio_unitario == D("768.00")
    assert any(x.regla == "RN-04" and "inicia el 2026-10-06" in x.descripcion for x in r.reglas_aplicadas)


def test_rn04_con_varias_vigentes_gana_la_de_mayor_descuento():
    otra = Promotion("Promo mayor", D("0.08"), date(2026, 10, 1), date(2026, 10, 20))
    r = calc(promociones=[PROMO_5, otra])
    assert r.precio_unitario == D("706.56")  # 768 × 0,92
    assert r.promocion_fin == date(2026, 10, 20)


# --- RN-05: no acumulación entre volumen y promoción -----------------------------------


def test_rn05_gana_la_promocion_cuando_es_mayor_que_el_volumen():
    r = calc(cantidad=20, promociones=[PROMO_5])  # volumen 2 % < promoción 5 %
    assert r.precio_unitario == D("729.60")
    assert "RN-03" not in reglas(r)
    assert any(x.regla == "RN-05" and "no aplicada" in x.descripcion for x in r.reglas_aplicadas)


def test_rn05_gana_el_volumen_cuando_es_mayor_que_la_promocion():
    r = calc(cantidad=100, promociones=[PROMO_5])  # volumen 6 % > promoción 5 %
    assert r.precio_unitario == D("721.92")  # 768 × 0,94
    assert r.promocion_fin is None
    assert any(x.regla == "RN-05" and "Promoción" in x.descripcion for x in r.reglas_aplicadas)


def test_rn05_no_se_acumulan_volumen_y_promocion():
    acumulado = D("800") * D("0.96") * D("0.98") * D("0.95")
    assert calc(cantidad=20, promociones=[PROMO_5]).precio_unitario > acumulado


def test_rn05_en_empate_gana_el_volumen_y_la_vigencia_no_se_acorta():
    promo_4 = Promotion("Promo igual", D("0.04"), date(2026, 10, 1), date(2026, 10, 7))
    r = calc(cantidad=50, promociones=[promo_4])
    assert r.precio_unitario == D("737.28")
    assert r.promocion_fin is None


def test_rn05_el_descuento_de_nivel_si_se_acumula():
    oro = calc(cantidad=20, nivel="Oro", promociones=[PROMO_5])
    assert oro.precio_unitario == D("714.40")  # 800 × 0,94 × 0,95


# --- RN-06: descuento adicional --------------------------------------------------------


def test_rn06_descuento_adicional_se_aplica_al_final_y_reevalua_el_margen():
    sin = calc(cantidad=20, promociones=[PROMO_5])
    con = calc(cantidad=20, adicional="0.03", promociones=[PROMO_5])
    assert con.precio_unitario == D("707.71")  # 729,60 × 0,97 = 707,712
    assert con.margen < sin.margen
    assert "RN-06" in reglas(con) and "RN-06" not in reglas(sin)


@pytest.mark.parametrize("adicional", ["-0.01", "1", "1.5"])
def test_rn06_descuento_adicional_fuera_de_rango_es_invalido(adicional):
    with pytest.raises(InvalidLineError):
        calc(adicional=adicional)


@pytest.mark.parametrize("cantidad", [0, -5])
def test_cantidad_no_positiva_es_invalida(cantidad):
    with pytest.raises(InvalidLineError):
        calc(cantidad=cantidad)


# --- RN-07: margen mínimo por categoría ------------------------------------------------


def test_rn07_margen_igual_al_minimo_no_requiere_aprobacion():
    # costo 92, precio 100 -> margen exactamente 8 %
    producto = ProductData("X-2", "Justo en el mínimo", "Portátiles", D("92.00"), D("100.00"))
    r = calc(product=producto, params=PricingParams({"Plata": D("0")}, (), PARAMS.margenes_minimos))
    assert r.margen == D("0.0800")
    assert not r.requiere_aprobacion


def test_rn07_margen_bajo_el_minimo_requiere_aprobacion_y_lo_registra():
    producto = ProductData("X-3", "Margen corto", "Portátiles", D("92.01"), D("100.00"))
    r = calc(product=producto, params=PricingParams({"Plata": D("0")}, (), PARAMS.margenes_minimos))
    assert r.margen == D("0.0799")
    assert r.requiere_aprobacion
    assert r.estado is LineStatus.OK
    assert "RN-07" in reglas(r)


def test_rn07_el_minimo_depende_de_la_categoria():
    # Mismo costo y lista: margen 11,46 % tras el 4 % de Plata. Pasa en Redes (11 %), no en Periféricos (12 %).
    def producto(categoria):
        return ProductData("X-4", "Genérico", categoria, D("85.00"), D("100.00"))

    assert not calc(product=producto("Redes")).requiere_aprobacion
    assert calc(product=producto("Periféricos")).requiere_aprobacion
    assert calc(product=producto("Periféricos")).margen_minimo == D("0.12")


def test_rn07_categoria_sin_margen_configurado_es_error_de_parametros():
    with pytest.raises(PricingConfigError, match="Audio"):
        calc(product=ProductData("X-5", "Otra", "Audio", D("10.00"), D("20.00")))


def test_rn07_una_sola_linea_bajo_margen_basta_para_requerir_aprobacion():
    ok = calc(cantidad=20, promociones=[PROMO_5])
    baja = calc(cantidad=20, adicional="0.09", promociones=[PROMO_5])
    assert evaluate_quote([ok, baja]) is Evaluation.REQUIERE_APROBACION


# --- RN-08: piso absoluto --------------------------------------------------------------


def test_rn08_precio_bajo_el_costo_es_no_emitible_ni_con_aprobacion():
    r = calc(adicional="0.25")  # 768 × 0,75 = 576 < 620
    assert r.precio_unitario == D("576.00")
    assert r.estado is LineStatus.BAJO_COSTO
    assert r.margen < 0
    assert "RN-08" in reglas(r)
    # Aunque también incumple el margen, la cotización no pasa a aprobación: no es emitible.
    assert evaluate_quote([r]) is Evaluation.NO_EMITIBLE


def test_rn08_precio_igual_al_costo_no_es_bajo_costo_pero_requiere_aprobacion():
    producto = ProductData("X-6", "Al costo", "Portátiles", D("100.00"), D("100.00"))
    r = calc(product=producto, params=PricingParams({"Plata": D("0")}, (), PARAMS.margenes_minimos))
    assert r.estado is LineStatus.OK
    assert r.margen == D("0.0000")
    assert r.requiere_aprobacion


def test_rn08_tiene_prioridad_sobre_las_lineas_que_requieren_aprobacion():
    baja = calc(cantidad=20, adicional="0.09", promociones=[PROMO_5])
    bajo_costo = calc(adicional="0.25")
    assert evaluate_quote([baja, bajo_costo]) is Evaluation.NO_EMITIBLE


def test_descuento_extremo_que_redondea_a_cero_no_rompe_el_calculo():
    producto = ProductData("X-7", "Barato", "Portátiles", D("0.01"), D("0.02"))
    r = calc(product=producto, adicional="0.99")
    assert r.precio_unitario == D("0.00")
    assert r.estado is LineStatus.BAJO_COSTO


# --- RN-10: disponibilidad neta --------------------------------------------------------


def test_rn10_disponible_es_existencias_menos_comprometido():
    assert net_available(100, 30) == 70
    assert net_available(10, 25) == 0  # nunca negativo


def test_rn10_cantidad_dentro_de_lo_disponible():
    r = calc(cantidad=70, existencias=100, comprometido=30)
    assert r.disponible == 70
    assert not r.bajo_pedido
    assert r.cantidad_comprometible == 70


def test_rn10_cantidad_sobre_lo_disponible_marca_bajo_pedido_sin_bloquear():
    r = calc(cantidad=20, existencias=25, comprometido=10, promociones=[PROMO_5])
    assert r.disponible == 15
    assert r.bajo_pedido
    assert r.cantidad_comprometible == 15  # solo se compromete lo que hay
    assert "RN-10" in reglas(r)
    assert r.estado is LineStatus.OK
    assert evaluate_quote([r]) is Evaluation.LISTA_PARA_EMITIR


def test_rn10_sin_existencias():
    r = calc(cantidad=1, existencias=0)
    assert r.bajo_pedido and r.disponible == 0 and r.cantidad_comprometible == 0


# --- RN-14: moneda y redondeo ----------------------------------------------------------


def test_rn14_redondea_una_sola_vez_al_final_mitad_hacia_arriba():
    # 30,06 × 0,96 × 0,95 = 27,41472 -> 27,41.
    # Redondeando en cada paso sería 28,86 × 0,95 = 27,417 -> 27,42: un centavo de más.
    producto = ProductData("X-8", "Redondeo", "Portátiles", D("20.00"), D("30.06"))
    promo = Promotion("P", D("0.05"), date(2026, 10, 1), date(2026, 10, 31))
    r = calc(product=producto, promociones=[promo])
    assert r.precio_unitario == D("27.41")


def test_rn14_mitad_exacta_sube():
    # 100,25 × 0,98 (Bronce) = 98,245 -> 98,25 (HALF_UP); el redondeo bancario daría 98,24.
    producto = ProductData("X-9", "Mitad", "Portátiles", D("50.00"), D("100.25"))
    assert calc(product=producto, nivel="Bronce").precio_unitario == D("98.25")


def test_rn14_precio_y_total_siempre_con_dos_decimales():
    r = calc(cantidad=3, adicional="0.0333", promociones=[PROMO_5])
    assert r.precio_unitario.as_tuple().exponent == -2
    assert r.total.as_tuple().exponent == -2
    assert r.total == r.precio_unitario * 3


# --- Evaluación y total de la cotización -----------------------------------------------


def test_cotizacion_sin_lineas_no_es_emitible():
    assert evaluate_quote([]) is Evaluation.NO_EMITIBLE


def test_total_suma_las_lineas_con_precio_e_ignora_las_no_cotizables():
    a = calc(cantidad=20, promociones=[PROMO_5])
    b = calc(cantidad=1)
    sin_costo = calc(product=ProductData("X-1", "Sin costo", "Portátiles", None, D("10.00")))
    assert quote_total([a, b, sin_costo]) == D("14592.00") + D("768.00")
    assert quote_total([]) == D("0")


def test_el_motor_es_determinista():
    assert calc(cantidad=20, promociones=[PROMO_5]) == calc(cantidad=20, promociones=[PROMO_5])
