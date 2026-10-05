"""E3. Disponibilidad insuficiente: la línea se marca bajo pedido con alerta, sin bloquear la emisión (RN-10)."""

from tests.helpers import create_calculated, issue, line


def test_e3_cantidad_sobre_lo_disponible_marca_bajo_pedido_y_permite_emitir(client, as_user, clock, demo_channel):
    ejecutivo = as_user("ejecutivo")

    # PER-0001 tiene 5 unidades y se piden 8.
    quote = create_calculated(client, ejecutivo, clock, demo_channel.id, [("PER-0001", 8)])
    linea = line(quote, "PER-0001")
    assert linea["bajo_pedido"] is True
    assert linea["disponible"] == 5
    assert linea["estado"] == "OK"
    assert any(r["regla"] == "RN-10" for r in linea["reglas_aplicadas"])
    # No bloquea: sigue lista para emitir.
    assert quote["evaluacion"] == "LISTA_PARA_EMITIR"
    assert "EMITIR" in quote["acciones_permitidas"]

    emitida = issue(client, ejecutivo, quote["id"])
    assert emitida["estado"] == "EMITIDA"
    # Solo compromete lo que realmente hay.
    assert line(emitida, "PER-0001")["cantidad_comprometida"] == 5

    eventos = client.get(f"/api/cotizaciones/{quote['id']}/eventos", headers=ejecutivo).json()
    calculada = next(e for e in eventos if e["tipo"] == "COTIZACION_CALCULADA")
    assert calculada["payload"]["lineas_bajo_pedido"] == ["PER-0001"]


def test_e3_referencia_sin_existencias(client, as_user, clock, demo_channel):
    quote = create_calculated(client, as_user("ejecutivo"), clock, demo_channel.id, [("SRV-0001", 1)])
    linea = line(quote, "SRV-0001")
    assert linea["bajo_pedido"] is True and linea["disponible"] == 0
    assert quote["evaluacion"] == "LISTA_PARA_EMITIR"


def test_e3_la_disponibilidad_es_neta_descuenta_lo_comprometido_por_otra_cotizacion(
    client, as_user, clock, demo_channel
):
    ejecutivo = as_user("ejecutivo")
    # La primera cotización se lleva 4 de las 5 unidades.
    primera = create_calculated(client, ejecutivo, clock, demo_channel.id, [("PER-0001", 4)])
    assert line(primera, "PER-0001")["bajo_pedido"] is False
    issue(client, ejecutivo, primera["id"])

    # Las existencias del ERP siguen en 5, pero para la segunda solo queda 1 disponible.
    segunda = create_calculated(client, ejecutivo, clock, demo_channel.id, [("PER-0001", 3)])
    linea = line(segunda, "PER-0001")
    assert linea["disponible"] == 1
    assert linea["bajo_pedido"] is True


def test_e3_al_emitir_se_compromete_segun_la_disponibilidad_de_ese_momento(client, as_user, clock, demo_channel, erp):
    ejecutivo = as_user("ejecutivo")
    quote = create_calculated(client, ejecutivo, clock, demo_channel.id, [("PER-0001", 4)])
    assert line(quote, "PER-0001")["bajo_pedido"] is False

    # Entre el cálculo y la emisión el ERP baja las existencias a 2.
    erp.stocks["PER-0001"] = 2
    emitida = issue(client, ejecutivo, quote["id"])
    linea = line(emitida, "PER-0001")
    assert linea["cantidad_comprometida"] == 2
    assert linea["bajo_pedido"] is True
    # El precio no cambia por eso.
    assert linea["precio_unitario"] == "60.00"
