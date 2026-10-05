"""E5. Precio bajo el costo: la cotización queda no emitible hasta corregir (RN-08).

(La imposibilidad de solicitar aprobación por la API se agrega en la fase 4; la regla ya
está cubierta en la máquina de estados.)
"""

from app.infra.seeds import DEMO_SKU
from tests.helpers import calculate, create_calculated, issue, line, quote_body


def test_e5_precio_bajo_el_costo_no_es_emitible(client, as_user, clock, demo_channel):
    ejecutivo = as_user("ejecutivo")

    # 800 × 0,96 × 0,95 × 0,80 = 583,68, por debajo del costo de 620.
    quote = create_calculated(client, ejecutivo, clock, demo_channel.id, [(DEMO_SKU, 20, "0.20")])
    linea = line(quote, DEMO_SKU)
    assert linea["precio_unitario"] == "583.68"
    assert linea["estado"] == "BAJO_COSTO"
    assert any(r["regla"] == "RN-08" for r in linea["reglas_aplicadas"])
    assert quote["evaluacion"] == "NO_EMITIBLE"
    # Ni emitir ni pedir aprobación: solo corregir.
    assert quote["acciones_permitidas"] == ["CALCULAR", "EDITAR"]

    response = client.post(f"/api/cotizaciones/{quote['id']}/emitir", headers=ejecutivo)
    assert response.status_code == 409
    assert "no es emitible" in response.json()["detail"]
    assert client.get(f"/api/cotizaciones/{quote['id']}", headers=ejecutivo).json()["estado"] == "CALCULADA"


def test_e5_al_corregir_el_descuento_la_cotizacion_vuelve_a_ser_emitible(client, as_user, clock, demo_channel):
    ejecutivo = as_user("ejecutivo")
    quote = create_calculated(client, ejecutivo, clock, demo_channel.id, [(DEMO_SKU, 20, "0.20")])

    response = client.put(
        f"/api/cotizaciones/{quote['id']}",
        json=quote_body(clock, demo_channel.id, [(DEMO_SKU, 20, "0.02")]),
        headers=ejecutivo,
    )
    assert response.status_code == 200
    assert response.json()["estado"] == "BORRADOR"
    assert response.json()["evaluacion"] is None

    quote = calculate(client, ejecutivo, quote["id"])
    assert quote["evaluacion"] == "LISTA_PARA_EMITIR"
    assert issue(client, ejecutivo, quote["id"])["estado"] == "EMITIDA"


def test_e5_una_linea_bajo_costo_bloquea_toda_la_cotizacion(client, as_user, clock, demo_channel):
    quote = create_calculated(
        client, as_user("ejecutivo"), clock, demo_channel.id, [(DEMO_SKU, 20, "0.20"), ("RED-0001", 10)]
    )
    assert line(quote, "RED-0001")["estado"] == "OK"
    assert quote["evaluacion"] == "NO_EMITIBLE"


def test_rn01_referencia_sin_costo_es_no_cotizable_y_bloquea_la_emision(client, as_user, clock, demo_channel):
    ejecutivo = as_user("ejecutivo")
    quote = create_calculated(client, ejecutivo, clock, demo_channel.id, [(DEMO_SKU, 20), ("SIN-COSTO", 2)])
    linea = line(quote, "SIN-COSTO")
    assert linea["estado"] == "NO_COTIZABLE"
    assert linea["precio_unitario"] is None
    assert quote["evaluacion"] == "NO_EMITIBLE"
    # El total solo suma las líneas con precio.
    assert quote["total"] == "14592.00"
    assert client.post(f"/api/cotizaciones/{quote['id']}/emitir", headers=ejecutivo).status_code == 409
