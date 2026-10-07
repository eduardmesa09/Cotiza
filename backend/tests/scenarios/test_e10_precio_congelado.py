"""E10. Cambio de precio de lista después de la emisión: el precio emitido se mantiene
congelado; una modificación genera una nueva versión recalculada (RN-13)."""

from app.infra.seeds import DEMO_SKU
from tests.helpers import calculate, create_calculated, create_issued, event_types, get_quote, issue, line, tasks

ESTANDAR = [(DEMO_SKU, 20)]


def test_e10_el_precio_emitido_no_cambia_aunque_cambie_la_lista(client, as_user, clock, demo_channel, erp):
    ejecutivo = as_user("ejecutivo")
    emitida = create_issued(client, ejecutivo, clock, demo_channel.id, ESTANDAR)
    assert line(emitida, DEMO_SKU)["precio_unitario"] == "729.60"

    # El ERP sube el precio de lista de 800 a 900 durante la vigencia.
    erp.set_list_price(DEMO_SKU, "900.00")
    clock.advance(hours=4)

    despues = get_quote(client, ejecutivo, emitida["id"])
    linea = line(despues, DEMO_SKU)
    assert linea["precio_lista"] == "800.00"
    assert linea["precio_unitario"] == "729.60"
    assert despues["total"] == "14592.00"

    # No hay forma de recalcularla: una emitida no se modifica.
    assert client.post(f"/api/cotizaciones/{emitida['id']}/calcular", headers=ejecutivo).status_code == 409


def test_e10_una_modificacion_genera_una_nueva_version_recalculada(client, as_user, clock, demo_channel, erp):
    ejecutivo = as_user("ejecutivo")
    v1 = create_issued(client, ejecutivo, clock, demo_channel.id, ESTANDAR)
    assert v1["puede_crear_version"] is True
    erp.set_list_price(DEMO_SKU, "900.00")
    clock.advance(hours=4)

    response = client.post(f"/api/cotizaciones/{v1['id']}/nueva-version", headers=ejecutivo)
    assert response.status_code == 201
    v2 = response.json()

    # La nueva versión: mismo número, versión siguiente, en borrador y sin precios.
    assert v2["id"] != v1["id"]
    assert (v2["numero"], v2["version"]) == (v1["numero"], 2)
    assert v2["version_anterior_id"] == v1["id"]
    assert v2["estado"] == "BORRADOR"
    assert [(l["referencia"], l["cantidad"], l["precio_unitario"]) for l in v2["lineas"]] == [(DEMO_SKU, 20, None)]

    # Se recalcula completa con la lista vigente: 900 × 0,96 × 0,95 = 820,80.
    v2 = calculate(client, ejecutivo, v2["id"])
    assert line(v2, DEMO_SKU)["precio_lista"] == "900.00"
    assert line(v2, DEMO_SKU)["precio_unitario"] == "820.80"
    assert issue(client, ejecutivo, v2["id"])["estado"] == "EMITIDA"

    # La versión anterior conserva sus precios congelados y queda marcada como reemplazada.
    v1 = get_quote(client, ejecutivo, v1["id"])
    assert v1["reemplazada"] is True
    assert v1["version_siguiente_id"] == v2["id"] and v2["version_siguiente_id"] is None
    assert v1["estado"] == "EMITIDA"
    assert line(v1, DEMO_SKU)["precio_unitario"] == "729.60"
    assert v1["acciones_permitidas"] == [] and v1["puede_crear_version"] is False

    # Trazabilidad en ambas versiones.
    assert event_types(client, ejecutivo, v1["id"])[-1] == "COTIZACION_REEMPLAZADA"
    assert event_types(client, ejecutivo, v2["id"]) == [
        "NUEVA_VERSION_CREADA",
        "COTIZACION_CALCULADA",
        "COTIZACION_EMITIDA",
        "SEGUIMIENTO_PROGRAMADO",
    ]


def test_e10_la_version_reemplazada_libera_su_inventario(client, as_user, clock, demo_channel):
    ejecutivo = as_user("ejecutivo")
    v1 = create_issued(client, ejecutivo, clock, demo_channel.id, ESTANDAR)
    v2 = client.post(f"/api/cotizaciones/{v1['id']}/nueva-version", headers=ejecutivo).json()

    # Con v1 reemplazada y v2 aún en borrador, nadie compromete las 20 unidades.
    v2 = calculate(client, ejecutivo, v2["id"])
    assert line(v2, DEMO_SKU)["disponible"] == 150
    # Al emitir v2, las compromete ella: no se cuentan dos veces.
    issue(client, ejecutivo, v2["id"])
    otra = create_calculated(client, ejecutivo, clock, demo_channel.id, [(DEMO_SKU, 1)])
    assert line(otra, DEMO_SKU)["disponible"] == 130


def test_e10_la_version_reemplazada_no_genera_seguimiento_ni_vence(client, as_user, clock, demo_channel, run_deadlines):
    ejecutivo = as_user("ejecutivo")
    v1 = create_issued(client, ejecutivo, clock, demo_channel.id, ESTANDAR)
    client.post(f"/api/cotizaciones/{v1['id']}/nueva-version", headers=ejecutivo)

    clock.advance(days=10)
    assert run_deadlines().total == 0
    assert get_quote(client, ejecutivo, v1["id"])["estado"] == "EMITIDA"
    assert tasks(client, ejecutivo) == []


def test_e10_versionar_una_cotizacion_en_seguimiento_cierra_su_tarea(client, as_user, clock, demo_channel, run_deadlines):
    ejecutivo = as_user("ejecutivo")
    v1 = create_issued(client, ejecutivo, clock, demo_channel.id, ESTANDAR)
    clock.advance(hours=48)
    run_deadlines()
    assert len(tasks(client, ejecutivo)) == 1

    assert client.post(f"/api/cotizaciones/{v1['id']}/nueva-version", headers=ejecutivo).status_code == 201
    assert tasks(client, ejecutivo) == []


def test_e10_no_se_versiona_dos_veces_la_misma_ni_una_que_no_se_ha_emitido(client, as_user, clock, demo_channel):
    ejecutivo = as_user("ejecutivo")
    calculada = create_calculated(client, ejecutivo, clock, demo_channel.id, ESTANDAR)
    assert client.post(f"/api/cotizaciones/{calculada['id']}/nueva-version", headers=ejecutivo).status_code == 409

    v1 = issue(client, ejecutivo, calculada["id"])
    assert client.post(f"/api/cotizaciones/{v1['id']}/nueva-version", headers=ejecutivo).status_code == 201
    assert client.post(f"/api/cotizaciones/{v1['id']}/nueva-version", headers=ejecutivo).status_code == 409


def test_e10_una_version_reemplazada_no_se_puede_ganar(client, as_user, clock, demo_channel):
    ejecutivo = as_user("ejecutivo")
    v1 = create_issued(client, ejecutivo, clock, demo_channel.id, ESTANDAR)
    client.post(f"/api/cotizaciones/{v1['id']}/nueva-version", headers=ejecutivo)
    response = client.post(f"/api/cotizaciones/{v1['id']}/cerrar", json={"resultado": "GANADA"}, headers=ejecutivo)
    assert response.status_code == 409
    assert "reemplazada" in response.json()["detail"]


def test_e10_solo_el_ejecutivo_dueno_crea_versiones(client, as_user, clock, demo_channel):
    v1 = create_issued(client, as_user("ejecutivo"), clock, demo_channel.id, ESTANDAR)
    for rol in ("aprobador", "gerente", "pricing", "admin"):
        assert client.post(f"/api/cotizaciones/{v1['id']}/nueva-version", headers=as_user(rol)).status_code == 403
