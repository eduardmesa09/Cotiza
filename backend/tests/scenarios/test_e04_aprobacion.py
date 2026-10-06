"""E4. Descuento bajo el margen mínimo: bloquea la emisión, crea la solicitud de aprobación
con contexto y activa el temporizador de SLA (RN-07, RN-09)."""

from datetime import datetime, timedelta

import pytest

from app.infra.seeds import DEMO_SKU
from tests.helpers import (
    approval_queue,
    create_calculated,
    create_pending,
    event_types,
    issue,
    line,
    request_approval,
    resolve,
)

# La variante del ejemplo del informe: 9 % adicional deja el margen en 6,62 %, bajo el 8 % de Portátiles.
BAJO_MARGEN = [(DEMO_SKU, 20, "0.09")]


def test_e4_descuento_bajo_el_margen_minimo_bloquea_y_crea_la_solicitud(
    client, as_user, clock, demo_channel, notifications
):
    ejecutivo, aprobador = as_user("ejecutivo"), as_user("aprobador")

    quote = create_calculated(client, ejecutivo, clock, demo_channel.id, BAJO_MARGEN)
    assert quote["evaluacion"] == "REQUIERE_APROBACION"
    assert line(quote, DEMO_SKU)["margen"] == "0.0662"

    # La emisión está bloqueada: no hay forma de saltarse la aprobación.
    bloqueo = client.post(f"/api/cotizaciones/{quote['id']}/emitir", headers=ejecutivo)
    assert bloqueo.status_code == 409

    quote = request_approval(client, ejecutivo, quote["id"])
    assert quote["estado"] == "PENDIENTE_APROBACION"
    # Lo único posible ahora es resolver o escalar: nada que el ejecutivo pueda hacer.
    assert quote["acciones_permitidas"] == ["APROBAR", "ESCALAR", "RECHAZAR"]
    assert quote["aprobacion"]["estado"] == "PENDIENTE"
    # RN-09: el temporizador vence en una hora hábil.
    assert datetime.fromisoformat(quote["aprobacion"]["vence_en"]) == clock.now() + timedelta(hours=1)

    # Sigue bloqueada mientras no haya resolución.
    sin_resolver = client.post(f"/api/cotizaciones/{quote['id']}/emitir", headers=ejecutivo)
    assert sin_resolver.status_code == 409
    assert "no ha sido aprobada" in sin_resolver.json()["detail"]

    # La solicitud llega a la cola del aprobador con todo el contexto de la negociación.
    (solicitud,) = approval_queue(client, aprobador)
    assert solicitud["solicitante"] == "Camila Torres"
    assert solicitud["sla_restante_segundos"] == 3600
    assert solicitud["sla_vencido"] is False and solicitud["escalada"] is False
    contexto = solicitud["cotizacion"]
    assert contexto["numero"] == quote["numero"]
    assert contexto["canal"]["nivel"] == "Plata"
    linea = line(contexto, DEMO_SKU)
    assert (linea["costo"], linea["precio_lista"], linea["precio_unitario"]) == ("620.00", "800.00", "663.94")
    assert (linea["margen"], linea["margen_minimo"]) == ("0.0662", "0.0800")
    assert [r["regla"] for r in linea["reglas_aplicadas"]][-2:] == ["RN-06", "RN-07"]

    # Notificación al aprobador y evento con las líneas que incumplen el margen.
    assert notifications("aprobador")[0]["tipo"] == "APROBACION_SOLICITADA"
    eventos = client.get(f"/api/cotizaciones/{quote['id']}/eventos", headers=ejecutivo).json()
    assert eventos[-1]["tipo"] == "APROBACION_SOLICITADA"
    assert eventos[-1]["payload"]["lineas_bajo_margen"] == [
        {"referencia": DEMO_SKU, "descuento_adicional": "0.0900", "margen": "0.0662", "margen_minimo": "0.0800"}
    ]


def test_e4_aprobada_y_confirmada_por_el_ejecutivo_se_emite_con_los_precios_aprobados(
    client, as_user, clock, demo_channel, notifications
):
    ejecutivo, aprobador = as_user("ejecutivo"), as_user("aprobador")
    quote = create_pending(client, ejecutivo, clock, demo_channel.id, BAJO_MARGEN)
    (solicitud,) = approval_queue(client, aprobador)

    clock.advance(minutes=20)
    aprobada = resolve(client, aprobador, solicitud["id"], "aprobar", "Cliente estratégico, se autoriza")
    # Aprobar no emite: la cotización sigue pendiente hasta que el ejecutivo confirme.
    assert aprobada["estado"] == "PENDIENTE_APROBACION"
    assert aprobada["aprobacion"]["estado"] == "APROBADA"
    assert aprobada["aprobacion"]["resuelta_por"] == "Andrés Pardo"
    assert approval_queue(client, aprobador) == []

    pendiente = client.get(f"/api/cotizaciones/{quote['id']}", headers=ejecutivo).json()
    assert pendiente["acciones_permitidas"] == ["EMITIR"]
    assert notifications("ejecutivo")[0]["tipo"] == "APROBACION_APROBADA"

    emitida = issue(client, ejecutivo, quote["id"])
    assert emitida["estado"] == "EMITIDA"
    assert line(emitida, DEMO_SKU)["precio_unitario"] == "663.94"

    eventos = client.get(f"/api/cotizaciones/{quote['id']}/eventos", headers=ejecutivo).json()
    assert [e["tipo"] for e in eventos] == [
        "COTIZACION_CREADA",
        "COTIZACION_CALCULADA",
        "APROBACION_SOLICITADA",
        "APROBACION_APROBADA",
        "COTIZACION_EMITIDA",
        "SEGUIMIENTO_PROGRAMADO",
    ]
    aprobacion = eventos[3]
    assert aprobacion["usuario"] == "Andrés Pardo"
    assert aprobacion["payload"]["espera_segundos"] == 20 * 60
    assert aprobacion["payload"]["dentro_del_sla"] is True
    assert aprobacion["payload"]["comentario"] == "Cliente estratégico, se autoriza"


@pytest.mark.parametrize("accion", ["aprobar", "rechazar"])
@pytest.mark.parametrize("comentario", ["", "   "])
def test_e4_el_comentario_es_obligatorio_para_aprobar_o_rechazar(
    client, as_user, clock, demo_channel, accion, comentario
):
    create_pending(client, as_user("ejecutivo"), clock, demo_channel.id, BAJO_MARGEN)
    aprobador = as_user("aprobador")
    (solicitud,) = approval_queue(client, aprobador)
    response = client.post(f"/api/aprobaciones/{solicitud['id']}/{accion}", json={"comentario": comentario}, headers=aprobador)
    assert response.status_code == 422
    assert "comentario es obligatorio" in response.json()["detail"]
    assert len(approval_queue(client, aprobador)) == 1


@pytest.mark.parametrize("rol", ["ejecutivo", "pricing", "admin"])
def test_e4_solo_aprobador_y_gerente_ven_la_cola_y_resuelven(client, as_user, clock, demo_channel, rol):
    create_pending(client, as_user("ejecutivo"), clock, demo_channel.id, BAJO_MARGEN)
    (solicitud,) = approval_queue(client, as_user("aprobador"))
    headers = as_user(rol)
    assert client.get("/api/aprobaciones", headers=headers).status_code == 403
    for accion in ("aprobar", "rechazar"):
        response = client.post(f"/api/aprobaciones/{solicitud['id']}/{accion}", json={"comentario": "x"}, headers=headers)
        assert response.status_code == 403


def test_e4_segregacion_quien_propone_el_descuento_no_puede_aprobarlo(client, as_user, clock, demo_channel):
    """El ejecutivo que propuso el descuento no aprueba su propia solicitud, ni conociendo su id."""
    ejecutivo = as_user("ejecutivo")
    create_pending(client, ejecutivo, clock, demo_channel.id, BAJO_MARGEN)
    (solicitud,) = approval_queue(client, as_user("aprobador"))
    response = client.post(f"/api/aprobaciones/{solicitud['id']}/aprobar", json={"comentario": "me apruebo"}, headers=ejecutivo)
    assert response.status_code == 403


def test_e4_una_solicitud_resuelta_no_se_resuelve_dos_veces(client, as_user, clock, demo_channel):
    create_pending(client, as_user("ejecutivo"), clock, demo_channel.id, BAJO_MARGEN)
    aprobador = as_user("aprobador")
    (solicitud,) = approval_queue(client, aprobador)
    resolve(client, aprobador, solicitud["id"], "aprobar")
    otra_vez = client.post(f"/api/aprobaciones/{solicitud['id']}/rechazar", json={"comentario": "cambio de idea"}, headers=aprobador)
    assert otra_vez.status_code == 409


def test_e4_no_se_solicita_aprobacion_si_el_margen_cumple(client, as_user, clock, demo_channel):
    ejecutivo = as_user("ejecutivo")
    quote = create_calculated(client, ejecutivo, clock, demo_channel.id, [(DEMO_SKU, 20)])
    response = client.post(f"/api/cotizaciones/{quote['id']}/solicitar-aprobacion", headers=ejecutivo)
    assert response.status_code == 409
    assert "no requiere aprobación" in response.json()["detail"]


def test_e5_no_se_puede_solicitar_aprobacion_de_un_precio_bajo_el_costo(client, as_user, clock, demo_channel):
    """E5 (RN-08): ni siquiera con aprobación; hay que corregir primero."""
    ejecutivo = as_user("ejecutivo")
    quote = create_calculated(client, ejecutivo, clock, demo_channel.id, [(DEMO_SKU, 20, "0.20")])
    response = client.post(f"/api/cotizaciones/{quote['id']}/solicitar-aprobacion", headers=ejecutivo)
    assert response.status_code == 409
    assert "corrija" in response.json()["detail"]
    assert approval_queue(client, as_user("aprobador")) == []


def test_e4_la_cola_se_ordena_por_antiguedad_y_luego_por_monto(client, as_user, clock, demo_channel):
    ejecutivo = as_user("ejecutivo")
    antigua = create_pending(client, ejecutivo, clock, demo_channel.id, [(DEMO_SKU, 10, "0.09")])
    clock.advance(minutes=10)
    # Dos solicitudes en el mismo instante: primero la de mayor monto.
    menor = create_pending(client, ejecutivo, clock, demo_channel.id, [(DEMO_SKU, 12, "0.11")])
    mayor = create_pending(client, ejecutivo, clock, demo_channel.id, [(DEMO_SKU, 40, "0.11")])

    cola = approval_queue(client, as_user("aprobador"))
    assert [s["cotizacion"]["id"] for s in cola] == [antigua["id"], mayor["id"], menor["id"]]
    assert cola[0]["sla_restante_segundos"] == 50 * 60


def test_e4_una_cotizacion_pendiente_no_se_edita_ni_se_recalcula(client, as_user, clock, demo_channel):
    ejecutivo = as_user("ejecutivo")
    quote = create_pending(client, ejecutivo, clock, demo_channel.id, BAJO_MARGEN)
    assert client.post(f"/api/cotizaciones/{quote['id']}/calcular", headers=ejecutivo).status_code == 409
    assert event_types(client, ejecutivo, quote["id"])[-1] == "APROBACION_SOLICITADA"
