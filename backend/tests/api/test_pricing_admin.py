"""Administración de pricing: solo el rol pricing, y los cambios afectan el cálculo siguiente."""

import pytest

from app.infra.seeds import DEMO_SKU
from tests.helpers import calculate, create_calculated

RUTAS_DE_LECTURA = ["niveles", "escalas", "margenes", "promociones"]


def _promo(**cambios) -> dict:
    base = {
        "referencia": "RED-0001",
        "nombre": "Promo de octubre",
        "descuento": "0.05",
        "fecha_inicio": "2026-10-01",
        "fecha_fin": "2026-10-31",
    }
    return {**base, **cambios}


# --- Permisos -------------------------------------------------------------------------


@pytest.mark.parametrize("rol", ["ejecutivo", "aprobador", "gerente", "admin"])
@pytest.mark.parametrize("ruta", RUTAS_DE_LECTURA)
def test_solo_pricing_administra_reglas_y_promociones(client, as_user, rol, ruta):
    assert client.get(f"/api/pricing/{ruta}", headers=as_user(rol)).status_code == 403


@pytest.mark.parametrize("ruta", RUTAS_DE_LECTURA)
def test_pricing_consulta_todas_las_tablas(client, as_user, ruta):
    assert client.get(f"/api/pricing/{ruta}", headers=as_user("pricing")).status_code == 200


def test_otros_roles_no_modifican_reglas(client, as_user):
    ejecutivo = as_user("ejecutivo")
    assert client.put("/api/pricing/niveles/1", json={"descuento": "0.5"}, headers=ejecutivo).status_code == 403
    assert client.post("/api/pricing/promociones", json=_promo(), headers=ejecutivo).status_code == 403


# --- Niveles, escalas y márgenes ------------------------------------------------------


def test_valores_semilla(client, as_user):
    pricing = as_user("pricing")
    niveles = {n["nombre"]: n["descuento"] for n in client.get("/api/pricing/niveles", headers=pricing).json()}
    assert niveles == {"Oro": "0.0600", "Plata": "0.0400", "Bronce": "0.0200"}
    escalas = client.get("/api/pricing/escalas", headers=pricing).json()
    assert [(e["cantidad_min"], e["cantidad_max"], e["descuento"]) for e in escalas] == [
        (10, 49, "0.0200"),
        (50, 99, "0.0400"),
        (100, None, "0.0600"),
    ]
    assert len(client.get("/api/pricing/margenes", headers=pricing).json()) == 5


def test_cambiar_el_descuento_de_un_nivel_afecta_el_siguiente_calculo(client, as_user, clock, demo_channel):
    ejecutivo, pricing = as_user("ejecutivo"), as_user("pricing")
    quote = create_calculated(client, ejecutivo, clock, demo_channel.id, [(DEMO_SKU, 20)])
    assert quote["lineas"][0]["precio_unitario"] == "729.60"

    plata = next(n for n in client.get("/api/pricing/niveles", headers=pricing).json() if n["nombre"] == "Plata")
    response = client.put(f"/api/pricing/niveles/{plata['id']}", json={"descuento": "0.05"}, headers=pricing)
    assert response.status_code == 200 and response.json()["descuento"] == "0.0500"

    # Los parámetros son datos: el motor los toma sin redesplegar. 800 × 0,95 × 0,95 = 722,00.
    assert calculate(client, ejecutivo, quote["id"])["lineas"][0]["precio_unitario"] == "722.00"


def test_subir_el_margen_minimo_hace_que_la_cotizacion_requiera_aprobacion(client, as_user, clock, demo_channel):
    ejecutivo, pricing = as_user("ejecutivo"), as_user("pricing")
    quote = create_calculated(client, ejecutivo, clock, demo_channel.id, [(DEMO_SKU, 20)])
    assert quote["evaluacion"] == "LISTA_PARA_EMITIR"  # margen 15,02 %

    portatiles = next(
        m for m in client.get("/api/pricing/margenes", headers=pricing).json() if m["categoria"] == "Portátiles"
    )
    client.put(f"/api/pricing/margenes/{portatiles['id']}", json={"margen_minimo": "0.16"}, headers=pricing)

    assert calculate(client, ejecutivo, quote["id"])["evaluacion"] == "REQUIERE_APROBACION"


def test_cambiar_una_escala_de_volumen(client, as_user, clock, demo_channel):
    ejecutivo, pricing = as_user("ejecutivo"), as_user("pricing")
    primera = client.get("/api/pricing/escalas", headers=pricing).json()[0]
    client.put(f"/api/pricing/escalas/{primera['id']}", json={"descuento": "0.03"}, headers=pricing)
    quote = create_calculated(client, ejecutivo, clock, demo_channel.id, [("RED-0001", 10)])
    assert quote["lineas"][0]["precio_unitario"] == "116.40"  # 125 × 0,96 × 0,97


@pytest.mark.parametrize("valor", ["-0.01", "1", "1.5", "abc"])
def test_porcentajes_fuera_de_rango_se_rechazan(client, as_user, valor):
    pricing = as_user("pricing")
    nivel = client.get("/api/pricing/niveles", headers=pricing).json()[0]
    response = client.put(f"/api/pricing/niveles/{nivel['id']}", json={"descuento": valor}, headers=pricing)
    assert response.status_code == 422


def test_registro_inexistente(client, as_user):
    pricing = as_user("pricing")
    assert client.put("/api/pricing/niveles/9999", json={"descuento": "0.1"}, headers=pricing).status_code == 404
    assert client.put("/api/pricing/promociones/9999", json=_promo(), headers=pricing).status_code == 404
    assert client.delete("/api/pricing/promociones/9999", headers=pricing).status_code == 404


# --- Promociones ----------------------------------------------------------------------


def test_crud_de_promociones(client, as_user):
    pricing = as_user("pricing")
    creada = client.post("/api/pricing/promociones", json=_promo(referencia="red-0001"), headers=pricing)
    assert creada.status_code == 201
    promo = creada.json()
    assert promo["referencia"] == "RED-0001"  # se normaliza

    filtradas = client.get("/api/pricing/promociones", params={"referencia": "RED-0001"}, headers=pricing).json()
    assert [p["id"] for p in filtradas] == [promo["id"]]

    editada = client.put(
        f"/api/pricing/promociones/{promo['id']}", json=_promo(descuento="0.07", fecha_fin="2026-11-15"), headers=pricing
    )
    assert editada.status_code == 200
    assert editada.json()["descuento"] == "0.0700" and editada.json()["fecha_fin"] == "2026-11-15"

    assert client.delete(f"/api/pricing/promociones/{promo['id']}", headers=pricing).status_code == 204
    assert client.get("/api/pricing/promociones", params={"referencia": "RED-0001"}, headers=pricing).json() == []


def test_una_promocion_nueva_se_aplica_en_el_siguiente_calculo(client, as_user, clock, demo_channel):
    ejecutivo, pricing = as_user("ejecutivo"), as_user("pricing")
    quote = create_calculated(client, ejecutivo, clock, demo_channel.id, [("RED-0001", 5)])
    assert quote["lineas"][0]["precio_unitario"] == "120.00"

    client.post("/api/pricing/promociones", json=_promo(), headers=pricing)

    recalculada = calculate(client, ejecutivo, quote["id"])
    assert recalculada["lineas"][0]["precio_unitario"] == "114.00"
    assert recalculada["lineas"][0]["promocion_fin"] == "2026-10-31"


@pytest.mark.parametrize(
    "inicio, fin",
    [
        ("2026-10-15", "2026-11-15"),  # se cruza al final
        ("2026-09-15", "2026-10-01"),  # comparte solo el primer día
        ("2026-10-31", "2026-11-30"),  # comparte solo el último día
        ("2026-10-10", "2026-10-12"),  # contenida
        ("2026-09-01", "2026-12-31"),  # la contiene
    ],
)
def test_no_se_permiten_promociones_superpuestas_para_la_misma_referencia(client, as_user, inicio, fin):
    pricing = as_user("pricing")
    client.post("/api/pricing/promociones", json=_promo(), headers=pricing)
    response = client.post(
        "/api/pricing/promociones", json=_promo(nombre="Otra", fecha_inicio=inicio, fecha_fin=fin), headers=pricing
    )
    assert response.status_code == 422
    assert "se superpone" in response.json()["detail"]


def test_promociones_contiguas_o_de_otra_referencia_si_se_permiten(client, as_user):
    pricing = as_user("pricing")
    client.post("/api/pricing/promociones", json=_promo(), headers=pricing)
    contigua = _promo(nombre="Noviembre", fecha_inicio="2026-11-01", fecha_fin="2026-11-30")
    assert client.post("/api/pricing/promociones", json=contigua, headers=pricing).status_code == 201
    otra_referencia = _promo(referencia="PER-0001")
    assert client.post("/api/pricing/promociones", json=otra_referencia, headers=pricing).status_code == 201


def test_editar_una_promocion_no_choca_consigo_misma_pero_si_con_otras(client, as_user):
    pricing = as_user("pricing")
    octubre = client.post("/api/pricing/promociones", json=_promo(), headers=pricing).json()
    client.post(
        "/api/pricing/promociones",
        json=_promo(nombre="Noviembre", fecha_inicio="2026-11-01", fecha_fin="2026-11-30"),
        headers=pricing,
    )
    url = f"/api/pricing/promociones/{octubre['id']}"
    assert client.put(url, json=_promo(fecha_fin="2026-10-20"), headers=pricing).status_code == 200
    assert client.put(url, json=_promo(fecha_fin="2026-11-05"), headers=pricing).status_code == 422


@pytest.mark.parametrize(
    "cambios",
    [
        {"fecha_inicio": "2026-11-01", "fecha_fin": "2026-10-01"},  # fechas invertidas
        {"descuento": "0"},
        {"descuento": "1"},
        {"nombre": ""},
        {"fecha_fin": "no-es-fecha"},
    ],
)
def test_promociones_invalidas_se_rechazan(client, as_user, cambios):
    response = client.post("/api/pricing/promociones", json=_promo(**cambios), headers=as_user("pricing"))
    assert response.status_code == 422


# --- Parámetros -----------------------------------------------------------------------


@pytest.mark.parametrize("rol", ["pricing", "admin"])
def test_pricing_y_admin_ajustan_los_parametros_de_plazos(client, as_user, rol):
    headers = as_user(rol)
    parametros = {p["clave"]: p["valor"] for p in client.get("/api/pricing/parametros", headers=headers).json()}
    assert parametros["sla_aprobacion_minutos"] == "60"

    response = client.put("/api/pricing/parametros/sla_aprobacion_minutos", json={"valor": "2"}, headers=headers)
    assert response.status_code == 200 and response.json()["valor"] == "2"


@pytest.mark.parametrize("rol", ["ejecutivo", "aprobador", "gerente"])
def test_otros_roles_no_ven_los_parametros(client, as_user, rol):
    assert client.get("/api/pricing/parametros", headers=as_user(rol)).status_code == 403


@pytest.mark.parametrize(
    "clave, valor",
    [
        ("sla_aprobacion_minutos", "0"),
        ("sla_aprobacion_minutos", "-5"),
        ("vigencia_minutos", "siete"),
        ("horario_habil_inicio", "25:00"),
        ("horario_habil_fin", "08:00"),  # termina antes de empezar (09:00)
        ("horario_habil_dias", "1,2,9"),
        ("zona_horaria", "Marte/Olympus"),
    ],
)
def test_un_parametro_invalido_se_rechaza_y_no_se_guarda(client, as_user, clave, valor):
    pricing = as_user("pricing")
    antes = {p["clave"]: p["valor"] for p in client.get("/api/pricing/parametros", headers=pricing).json()}
    response = client.put(f"/api/pricing/parametros/{clave}", json={"valor": valor}, headers=pricing)
    assert response.status_code == 422
    despues = {p["clave"]: p["valor"] for p in client.get("/api/pricing/parametros", headers=pricing).json()}
    assert despues == antes


def test_parametro_inexistente(client, as_user):
    response = client.put("/api/pricing/parametros/no_existe", json={"valor": "1"}, headers=as_user("pricing"))
    assert response.status_code == 404
