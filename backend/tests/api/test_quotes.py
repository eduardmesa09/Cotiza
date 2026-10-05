"""Cotizaciones por la API: validaciones, propiedad y permisos de la Tabla 32."""

from datetime import timedelta

import pytest
from sqlalchemy import select

from app.infra.models import Usuario
from app.infra.security import create_access_token, hash_password
from app.infra.seeds import DEMO_SKU
from tests.helpers import calculate, create_calculated, create_quote, issue, quote_body

OTROS_ROLES = ["aprobador", "gerente", "pricing", "admin"]


@pytest.fixture
def otro_ejecutivo(db, clock) -> dict:
    user = Usuario(
        usuario="ejecutivo2",
        nombre="Julián Mora",
        email="ejecutivo2@cotiza.example.com",
        password_hash=hash_password("Cotiza2026*"),
        rol="ejecutivo",
        activo=True,
        creado_en=clock.now(),
    )
    db.add(user)
    db.commit()
    return {"Authorization": f"Bearer {create_access_token(user.id, user.rol)}"}


# --- Crear ----------------------------------------------------------------------------


def test_crear_sin_lineas_queda_en_borrador(client, as_user, clock, demo_channel):
    quote = create_quote(client, as_user("ejecutivo"), clock, demo_channel.id, [])
    assert quote["estado"] == "BORRADOR"
    assert quote["version"] == 1
    assert quote["lineas"] == []
    assert quote["ejecutivo"]["nombre"] == "Camila Torres"
    assert quote["acciones_permitidas"] == ["CALCULAR", "EDITAR"]


def test_cada_cotizacion_recibe_un_numero_distinto(client, as_user, clock, demo_channel):
    ejecutivo = as_user("ejecutivo")
    a = create_quote(client, ejecutivo, clock, demo_channel.id, [])
    b = create_quote(client, ejecutivo, clock, demo_channel.id, [])
    assert a["numero"] != b["numero"]
    assert a["numero"] == f"COT-{a['id']:06d}"


def test_la_referencia_se_normaliza_a_mayusculas(client, as_user, clock, demo_channel):
    quote = create_quote(client, as_user("ejecutivo"), clock, demo_channel.id, [(DEMO_SKU.lower(), 1)])
    assert quote["lineas"][0]["referencia"] == DEMO_SKU


@pytest.mark.parametrize(
    "lineas",
    [
        [(DEMO_SKU, 0)],
        [(DEMO_SKU, -3)],
        [(DEMO_SKU, 1, "1")],
        [(DEMO_SKU, 1, "-0.1")],
        [(DEMO_SKU, 1), (DEMO_SKU, 2)],  # referencia repetida
    ],
)
def test_lineas_invalidas_se_rechazan(client, as_user, clock, demo_channel, lineas):
    response = client.post(
        "/api/cotizaciones", json=quote_body(clock, demo_channel.id, lineas), headers=as_user("ejecutivo")
    )
    assert response.status_code == 422


def test_canal_inexistente(client, as_user, clock):
    response = client.post("/api/cotizaciones", json=quote_body(clock, 999999, []), headers=as_user("ejecutivo"))
    assert response.status_code == 404


def test_la_hora_de_recepcion_no_puede_estar_en_el_futuro(client, as_user, clock, demo_channel):
    body = quote_body(clock, demo_channel.id, [])
    body["recibida_en"] = (clock.now() + timedelta(hours=1)).isoformat()
    response = client.post("/api/cotizaciones", json=body, headers=as_user("ejecutivo"))
    assert response.status_code == 422
    assert "futuro" in response.json()["detail"]


def test_la_hora_de_recepcion_exige_zona_horaria(client, as_user, clock, demo_channel):
    body = quote_body(clock, demo_channel.id, [])
    body["recibida_en"] = "2026-10-05T09:00:00"
    assert client.post("/api/cotizaciones", json=body, headers=as_user("ejecutivo")).status_code == 422


# --- Calcular y editar ----------------------------------------------------------------


def test_no_se_calcula_una_cotizacion_sin_lineas(client, as_user, clock, demo_channel):
    ejecutivo = as_user("ejecutivo")
    quote = create_quote(client, ejecutivo, clock, demo_channel.id, [])
    response = client.post(f"/api/cotizaciones/{quote['id']}/calcular", headers=ejecutivo)
    assert response.status_code == 422


def test_referencia_que_no_existe_en_el_catalogo(client, as_user, clock, demo_channel):
    ejecutivo = as_user("ejecutivo")
    quote = create_quote(client, ejecutivo, clock, demo_channel.id, [("NO-EXISTE", 1)])
    response = client.post(f"/api/cotizaciones/{quote['id']}/calcular", headers=ejecutivo)
    assert response.status_code == 422
    assert "NO-EXISTE" in response.json()["detail"]


def test_recalcular_toma_el_precio_de_lista_nuevo_mientras_no_se_haya_emitido(
    client, as_user, clock, demo_channel, erp
):
    ejecutivo = as_user("ejecutivo")
    quote = create_calculated(client, ejecutivo, clock, demo_channel.id, [(DEMO_SKU, 20)])
    assert quote["total"] == "14592.00"
    erp.set_list_price(DEMO_SKU, "900.00")
    assert calculate(client, ejecutivo, quote["id"])["lineas"][0]["precio_unitario"] == "820.80"


def test_editar_una_cotizacion_calculada_la_devuelve_a_borrador_y_borra_el_calculo(
    client, as_user, clock, demo_channel
):
    ejecutivo = as_user("ejecutivo")
    quote = create_calculated(client, ejecutivo, clock, demo_channel.id, [(DEMO_SKU, 20)])
    response = client.put(
        f"/api/cotizaciones/{quote['id']}",
        json=quote_body(clock, demo_channel.id, [(DEMO_SKU, 50), ("RED-0001", 1)]),
        headers=ejecutivo,
    )
    body = response.json()
    assert response.status_code == 200
    assert body["estado"] == "BORRADOR"
    assert body["total"] is None and body["evaluacion"] is None
    assert [l["cantidad"] for l in body["lineas"]] == [50, 1]
    assert all(l["precio_unitario"] is None for l in body["lineas"])


def test_rn13_una_cotizacion_emitida_no_se_edita_ni_se_recalcula_ni_se_reemite(
    client, as_user, clock, demo_channel
):
    ejecutivo = as_user("ejecutivo")
    quote = create_calculated(client, ejecutivo, clock, demo_channel.id, [(DEMO_SKU, 20)])
    issue(client, ejecutivo, quote["id"])

    url = f"/api/cotizaciones/{quote['id']}"
    editar = client.put(url, json=quote_body(clock, demo_channel.id, [(DEMO_SKU, 1)]), headers=ejecutivo)
    assert editar.status_code == 409
    assert client.post(f"{url}/calcular", headers=ejecutivo).status_code == 409
    assert client.post(f"{url}/emitir", headers=ejecutivo).status_code == 409
    assert client.get(url, headers=ejecutivo).json()["total"] == "14592.00"


def test_no_se_emite_un_borrador(client, as_user, clock, demo_channel):
    ejecutivo = as_user("ejecutivo")
    quote = create_quote(client, ejecutivo, clock, demo_channel.id, [(DEMO_SKU, 20)])
    assert client.post(f"/api/cotizaciones/{quote['id']}/emitir", headers=ejecutivo).status_code == 409


def test_rn07_no_se_emite_si_requiere_aprobacion(client, as_user, clock, demo_channel):
    ejecutivo = as_user("ejecutivo")
    quote = create_calculated(client, ejecutivo, clock, demo_channel.id, [(DEMO_SKU, 20, "0.09")])
    assert quote["evaluacion"] == "REQUIERE_APROBACION"
    assert quote["lineas"][0]["precio_unitario"] == "663.94"
    assert "EMITIR" not in quote["acciones_permitidas"]
    assert "SOLICITAR_APROBACION" in quote["acciones_permitidas"]
    response = client.post(f"/api/cotizaciones/{quote['id']}/emitir", headers=ejecutivo)
    assert response.status_code == 409
    assert "requiere aprobación" in response.json()["detail"]


def test_cotizacion_inexistente(client, as_user):
    assert client.get("/api/cotizaciones/999999", headers=as_user("ejecutivo")).status_code == 404


# --- Permisos (Tabla 32) --------------------------------------------------------------


@pytest.mark.parametrize("rol", OTROS_ROLES)
def test_solo_el_ejecutivo_crea_cotizaciones(client, as_user, clock, demo_channel, rol):
    response = client.post("/api/cotizaciones", json=quote_body(clock, demo_channel.id, []), headers=as_user(rol))
    assert response.status_code == 403


@pytest.mark.parametrize("rol", OTROS_ROLES)
def test_solo_el_ejecutivo_edita_calcula_y_emite(client, as_user, clock, demo_channel, rol):
    quote = create_calculated(client, as_user("ejecutivo"), clock, demo_channel.id, [(DEMO_SKU, 20)])
    url = f"/api/cotizaciones/{quote['id']}"
    headers = as_user(rol)
    assert client.put(url, json=quote_body(clock, demo_channel.id, []), headers=headers).status_code == 403
    assert client.post(f"{url}/calcular", headers=headers).status_code == 403
    assert client.post(f"{url}/emitir", headers=headers).status_code == 403


def test_un_ejecutivo_no_ve_ni_modifica_cotizaciones_de_otro(client, as_user, clock, demo_channel, otro_ejecutivo):
    quote = create_calculated(client, as_user("ejecutivo"), clock, demo_channel.id, [(DEMO_SKU, 20)])
    url = f"/api/cotizaciones/{quote['id']}"
    assert client.get(url, headers=otro_ejecutivo).status_code == 403
    assert client.get(f"{url}/eventos", headers=otro_ejecutivo).status_code == 403
    assert client.post(f"{url}/emitir", headers=otro_ejecutivo).status_code == 403
    assert client.get("/api/cotizaciones", headers=otro_ejecutivo).json() == []


@pytest.mark.parametrize("rol", ["aprobador", "gerente", "pricing"])
def test_aprobador_gerente_y_pricing_consultan_todas_las_cotizaciones(client, as_user, clock, demo_channel, rol):
    quote = create_quote(client, as_user("ejecutivo"), clock, demo_channel.id, [(DEMO_SKU, 20)])
    headers = as_user(rol)
    assert client.get(f"/api/cotizaciones/{quote['id']}", headers=headers).status_code == 200
    assert client.get(f"/api/cotizaciones/{quote['id']}/eventos", headers=headers).status_code == 200
    assert [q["id"] for q in client.get("/api/cotizaciones", headers=headers).json()] == [quote["id"]]


def test_el_administrador_no_participa_del_proceso_comercial(client, as_user, clock, demo_channel):
    quote = create_quote(client, as_user("ejecutivo"), clock, demo_channel.id, [])
    admin = as_user("admin")
    assert client.get("/api/cotizaciones", headers=admin).status_code == 403
    assert client.get(f"/api/cotizaciones/{quote['id']}", headers=admin).status_code == 403


# --- Listado --------------------------------------------------------------------------


def test_listado_filtrable_por_estado_y_con_lo_mas_reciente_primero(client, as_user, clock, demo_channel):
    ejecutivo = as_user("ejecutivo")
    borrador = create_quote(client, ejecutivo, clock, demo_channel.id, [])
    clock.advance(minutes=1)
    calculada = create_calculated(client, ejecutivo, clock, demo_channel.id, [(DEMO_SKU, 20)])
    clock.advance(minutes=1)
    emitida = create_calculated(client, ejecutivo, clock, demo_channel.id, [(DEMO_SKU, 5)])
    issue(client, ejecutivo, emitida["id"])

    todas = client.get("/api/cotizaciones", headers=ejecutivo).json()
    assert [q["id"] for q in todas] == [emitida["id"], calculada["id"], borrador["id"]]
    assert todas[1]["lineas_count"] == 1 and "lineas" not in todas[1]

    solo_emitidas = client.get("/api/cotizaciones", params={"estado": "EMITIDA"}, headers=ejecutivo).json()
    assert [q["id"] for q in solo_emitidas] == [emitida["id"]]
    assert client.get("/api/cotizaciones", params={"estado": "INVENTADO"}, headers=ejecutivo).status_code == 422


# --- Catálogo y canales ---------------------------------------------------------------


def test_buscador_de_catalogo_por_codigo_o_descripcion(client, as_user):
    ejecutivo = as_user("ejecutivo")
    por_codigo = client.get("/api/catalogo", params={"q": "red-00"}, headers=ejecutivo).json()
    assert [p["referencia"] for p in por_codigo] == ["RED-0001"]
    por_descripcion = client.get("/api/catalogo", params={"q": "monitor"}, headers=ejecutivo).json()
    assert por_descripcion[0]["referencia"] == "PER-0001"
    assert por_descripcion[0]["cotizable"] is True


def test_el_buscador_marca_las_referencias_no_cotizables(client, as_user):
    resultado = client.get("/api/catalogo", params={"q": "sin-costo"}, headers=as_user("ejecutivo")).json()
    assert resultado[0]["cotizable"] is False
    assert resultado[0]["costo"] is None


def test_listado_de_canales_con_su_nivel(client, as_user):
    canales = client.get("/api/canales", headers=as_user("ejecutivo")).json()
    assert len(canales) == 40
    assert {c["nivel"] for c in canales} == {"Oro", "Plata", "Bronce"}
    assert [c["nombre"] for c in canales] == sorted(c["nombre"] for c in canales)
