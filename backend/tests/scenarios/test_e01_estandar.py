"""E1. Cotización estándar: todas las líneas con margen sobre el mínimo y disponibilidad suficiente.

Calcula, habilita la emisión, compromete inventario y programa el seguimiento.
(La generación del PDF se agrega a este escenario en la fase 5.)
"""

from datetime import datetime, timedelta

from app.infra.seeds import DEMO_SKU
from tests.helpers import calculate, create_calculated, create_quote, event_types, issue, line


def test_e1_cotizacion_estandar(client, as_user, clock, demo_channel):
    ejecutivo = as_user("ejecutivo")

    # El ejecutivo registra la solicitud: canal Plata, 20 portátiles con promoción vigente del 5 %.
    quote = create_quote(client, ejecutivo, clock, demo_channel.id, [(DEMO_SKU, 20)])
    assert quote["estado"] == "BORRADOR"
    assert quote["numero"].startswith("COT-")
    assert quote["canal"]["nivel"] == "Plata"

    # Calcular: el motor resuelve el precio del ejemplo del informe.
    quote = calculate(client, ejecutivo, quote["id"])
    assert quote["estado"] == "CALCULADA"
    assert quote["evaluacion"] == "LISTA_PARA_EMITIR"
    assert quote["total"] == "14592.00"
    linea = line(quote, DEMO_SKU)
    assert linea["precio_unitario"] == "729.60"
    assert linea["margen"] == "0.1502"
    assert linea["estado"] == "OK"
    assert not linea["requiere_aprobacion"] and not linea["bajo_pedido"]
    assert [r["regla"] for r in linea["reglas_aplicadas"]] == ["RN-01", "RN-02", "RN-05", "RN-04"]
    assert "EMITIR" in quote["acciones_permitidas"]
    assert "SOLICITAR_APROBACION" not in quote["acciones_permitidas"]

    # Emitir cinco minutos después.
    emitida_en = clock.advance(minutes=5)
    quote = issue(client, ejecutivo, quote["id"])
    assert quote["estado"] == "EMITIDA"
    assert datetime.fromisoformat(quote["emitida_en"]) == emitida_en
    # RN-11: la promoción termina después, así que la vigencia son los 7 días calendario.
    assert datetime.fromisoformat(quote["vigente_hasta"]) == emitida_en + timedelta(days=7)
    # RN-10: compromete las 20 unidades.
    assert line(quote, DEMO_SKU)["cantidad_comprometida"] == 20
    # Los precios quedaron tal cual se calcularon.
    assert quote["total"] == "14592.00"
    assert quote["acciones_permitidas"] == ["GANAR", "INICIAR_SEGUIMIENTO", "VENCER"]

    # Trazabilidad: un evento por transición, más el seguimiento programado a 48 h.
    response = client.get(f"/api/cotizaciones/{quote['id']}/eventos", headers=ejecutivo)
    eventos = response.json()
    assert [e["tipo"] for e in eventos] == [
        "COTIZACION_CREADA",
        "COTIZACION_CALCULADA",
        "COTIZACION_EMITIDA",
        "SEGUIMIENTO_PROGRAMADO",
    ]
    assert eventos[0]["usuario"] == "Camila Torres"
    assert eventos[3]["usuario"] == "Sistema"
    programado = datetime.fromisoformat(eventos[3]["payload"]["programado_para"])
    assert programado == emitida_en + timedelta(hours=48)


def test_e1_el_inventario_comprometido_reduce_la_disponibilidad_de_la_siguiente_cotizacion(
    client, as_user, clock, demo_channel
):
    ejecutivo = as_user("ejecutivo")
    primera = create_calculated(client, ejecutivo, clock, demo_channel.id, [(DEMO_SKU, 20)])
    assert line(primera, DEMO_SKU)["disponible"] == 150
    issue(client, ejecutivo, primera["id"])

    segunda = create_calculated(client, ejecutivo, clock, demo_channel.id, [(DEMO_SKU, 10)])
    assert line(segunda, DEMO_SKU)["disponible"] == 130


def test_e1_una_cotizacion_solo_calculada_no_compromete_inventario(client, as_user, clock, demo_channel):
    ejecutivo = as_user("ejecutivo")
    create_calculated(client, ejecutivo, clock, demo_channel.id, [(DEMO_SKU, 20)])
    otra = create_calculated(client, ejecutivo, clock, demo_channel.id, [(DEMO_SKU, 10)])
    assert line(otra, DEMO_SKU)["disponible"] == 150


def test_e1_cotizacion_de_varias_lineas(client, as_user, clock, demo_channel):
    ejecutivo = as_user("ejecutivo")
    quote = create_calculated(client, ejecutivo, clock, demo_channel.id, [(DEMO_SKU, 20), ("RED-0001", 100)])
    assert quote["evaluacion"] == "LISTA_PARA_EMITIR"
    # RED-0001: 125 × 0,96 (Plata) × 0,94 (≥100 u) = 112,80; × 100 u.
    assert line(quote, "RED-0001")["precio_unitario"] == "112.80"
    assert quote["total"] == "25872.00"
    assert event_types(client, ejecutivo, quote["id"]) == ["COTIZACION_CREADA", "COTIZACION_CALCULADA"]
