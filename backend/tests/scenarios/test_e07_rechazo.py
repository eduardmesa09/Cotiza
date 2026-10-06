"""E7. Aprobación rechazada: el aprobador rechaza con comentario y la cotización vuelve a
estado calculada para que el ejecutivo ajuste (RN-07)."""

from app.infra.seeds import DEMO_SKU
from tests.helpers import (
    approval_queue,
    calculate,
    create_pending,
    event_types,
    issue,
    line,
    quote_body,
    request_approval,
    resolve,
)

BAJO_MARGEN = [(DEMO_SKU, 20, "0.09")]


def test_e7_rechazo_devuelve_a_calculada_y_el_ejecutivo_ajusta(client, as_user, clock, demo_channel, notifications):
    ejecutivo, aprobador = as_user("ejecutivo"), as_user("aprobador")
    quote = create_pending(client, ejecutivo, clock, demo_channel.id, BAJO_MARGEN)
    (solicitud,) = approval_queue(client, aprobador)

    clock.advance(minutes=15)
    rechazada = resolve(client, aprobador, solicitud["id"], "rechazar", "El 9 % es excesivo; máximo 5 %")
    assert rechazada["estado"] == "CALCULADA"
    assert rechazada["evaluacion"] == "REQUIERE_APROBACION"
    assert approval_queue(client, aprobador) == []

    # El ejecutivo recibe el motivo y ve la cotización lista para ajustar.
    assert notifications("ejecutivo")[0]["tipo"] == "APROBACION_RECHAZADA"
    assert "máximo 5 %" in notifications("ejecutivo")[0]["mensaje"]
    quote = client.get(f"/api/cotizaciones/{quote['id']}", headers=ejecutivo).json()
    assert quote["aprobacion"]["estado"] == "RECHAZADA"
    assert quote["aprobacion"]["comentario"] == "El 9 % es excesivo; máximo 5 %"
    assert "EDITAR" in quote["acciones_permitidas"] and "EMITIR" not in quote["acciones_permitidas"]

    # Ajusta el descuento a 5 %: 729,60 × 0,95 = 693,12, margen 10,55 % ≥ 8 %.
    editada = client.put(
        f"/api/cotizaciones/{quote['id']}",
        json=quote_body(clock, demo_channel.id, [(DEMO_SKU, 20, "0.05")]),
        headers=ejecutivo,
    )
    assert editada.json()["estado"] == "BORRADOR"
    recalculada = calculate(client, ejecutivo, quote["id"])
    assert recalculada["evaluacion"] == "LISTA_PARA_EMITIR"
    assert line(recalculada, DEMO_SKU)["precio_unitario"] == "693.12"
    assert issue(client, ejecutivo, quote["id"])["estado"] == "EMITIDA"

    assert event_types(client, ejecutivo, quote["id"]) == [
        "COTIZACION_CREADA",
        "COTIZACION_CALCULADA",
        "APROBACION_SOLICITADA",
        "APROBACION_RECHAZADA",
        "COTIZACION_EDITADA",
        "COTIZACION_CALCULADA",
        "COTIZACION_EMITIDA",
        "SEGUIMIENTO_PROGRAMADO",
    ]


def test_e7_una_cotizacion_rechazada_no_se_puede_emitir(client, as_user, clock, demo_channel):
    ejecutivo, aprobador = as_user("ejecutivo"), as_user("aprobador")
    quote = create_pending(client, ejecutivo, clock, demo_channel.id, BAJO_MARGEN)
    resolve(client, aprobador, approval_queue(client, aprobador)[0]["id"], "rechazar", "No procede")
    assert client.post(f"/api/cotizaciones/{quote['id']}/emitir", headers=ejecutivo).status_code == 409


def test_e7_tras_el_rechazo_se_puede_volver_a_solicitar_con_otro_descuento(client, as_user, clock, demo_channel):
    ejecutivo, aprobador = as_user("ejecutivo"), as_user("aprobador")
    quote = create_pending(client, ejecutivo, clock, demo_channel.id, BAJO_MARGEN)
    primera = approval_queue(client, aprobador)[0]
    resolve(client, aprobador, primera["id"], "rechazar", "Demasiado")

    # Baja a 8 %: 729,60 × 0,92 = 671,23, margen 7,63 %: todavía requiere aprobación.
    client.put(
        f"/api/cotizaciones/{quote['id']}",
        json=quote_body(clock, demo_channel.id, [(DEMO_SKU, 20, "0.08")]),
        headers=ejecutivo,
    )
    assert calculate(client, ejecutivo, quote["id"])["evaluacion"] == "REQUIERE_APROBACION"
    request_approval(client, ejecutivo, quote["id"])

    (segunda,) = approval_queue(client, aprobador)
    assert segunda["id"] != primera["id"]
    resolve(client, aprobador, segunda["id"], "aprobar", "Con 8 % sí")
    emitida = issue(client, ejecutivo, quote["id"])
    assert line(emitida, DEMO_SKU)["precio_unitario"] == "671.23"


def test_e7_la_aprobacion_de_una_solicitud_anterior_no_sirve_para_una_cotizacion_modificada(
    client, as_user, clock, demo_channel
):
    """Una aprobación ampara exactamente lo que se aprobó: tras rechazar y cambiar, hay que volver a pedirla."""
    ejecutivo, aprobador = as_user("ejecutivo"), as_user("aprobador")
    quote = create_pending(client, ejecutivo, clock, demo_channel.id, BAJO_MARGEN)
    resolve(client, aprobador, approval_queue(client, aprobador)[0]["id"], "rechazar", "No")
    client.put(
        f"/api/cotizaciones/{quote['id']}",
        json=quote_body(clock, demo_channel.id, [(DEMO_SKU, 20, "0.10")]),
        headers=ejecutivo,
    )
    calculate(client, ejecutivo, quote["id"])
    assert client.post(f"/api/cotizaciones/{quote['id']}/emitir", headers=ejecutivo).status_code == 409
