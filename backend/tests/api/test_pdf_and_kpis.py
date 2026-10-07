"""Documento de la cotización y tablero de indicadores por la API."""

from datetime import datetime, timedelta

import pytest

from app.infra.seeds import DEMO_SKU
from tests.helpers import (
    approval_queue,
    create_calculated,
    create_issued,
    create_pending,
    issue,
    resolve,
)

ESTANDAR = [(DEMO_SKU, 20)]


def kpi(dashboard: dict, codigo: str) -> dict:
    return next(k for k in dashboard["indicadores"] if k["codigo"] == codigo)


# --- Documento PDF (A6) ---------------------------------------------------------------


def test_e1_al_emitir_se_genera_el_pdf_con_plantilla_unica_y_queda_disponible(
    client, as_user, clock, demo_channel, documents, storage
):
    """Parte de E1: la emisión genera el documento, lo almacena y permite descargarlo."""
    ejecutivo = as_user("ejecutivo")
    quote = create_calculated(client, ejecutivo, clock, demo_channel.id, ESTANDAR)
    assert quote["tiene_pdf"] is False

    emitida = issue(client, ejecutivo, quote["id"])
    assert emitida["tiene_pdf"] is True

    # El documento recibe lo que ve el canal: líneas, precio final, condiciones y vigencia.
    (datos,) = documents.rendered
    assert (datos["numero"], datos["version"]) == (quote["numero"], 1)
    assert datos["canal"]["nombre"] == demo_channel.nombre
    assert datos["ejecutivo"] == "Camila Torres"
    assert str(datos["total"]) == "14592.00"
    assert datos["vigente_hasta"] == clock.now() + timedelta(days=7)
    assert len(datos["condiciones"]) >= 3
    (linea,) = datos["lineas"]
    assert (linea["referencia"], linea["cantidad"], str(linea["precio_unitario"])) == (DEMO_SKU, 20, "729.60")
    # El costo y el margen son internos: nunca salen en el documento.
    assert "costo" not in linea and "margen" not in linea

    nombre = f"{quote['numero']}-v1.pdf"
    assert nombre in storage.files

    response = client.get(f"/api/cotizaciones/{quote['id']}/pdf", headers=ejecutivo)
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert nombre in response.headers["content-disposition"]
    assert response.content == storage.files[nombre]

    eventos = client.get(f"/api/cotizaciones/{quote['id']}/eventos", headers=ejecutivo).json()
    emision = next(e for e in eventos if e["tipo"] == "COTIZACION_EMITIDA")
    assert emision["payload"]["documento"] == nombre


def test_el_documento_marca_las_lineas_bajo_pedido(client, as_user, clock, demo_channel, documents):
    create_issued(client, as_user("ejecutivo"), clock, demo_channel.id, [("PER-0001", 8), (DEMO_SKU, 1)])
    estado = {l["referencia"]: l["bajo_pedido"] for l in documents.rendered[0]["lineas"]}
    assert estado == {"PER-0001": True, DEMO_SKU: False}


def test_la_fecha_del_documento_va_en_la_hora_de_la_operacion(client, as_user, clock, demo_channel, documents):
    create_issued(client, as_user("ejecutivo"), clock, demo_channel.id, ESTANDAR)
    emitida_en = documents.rendered[0]["emitida_en"]
    assert emitida_en.utcoffset() == timedelta(hours=-5)  # Bogotá
    assert (emitida_en.hour, emitida_en.minute) == (10, 0)


def test_una_cotizacion_sin_emitir_no_tiene_documento(client, as_user, clock, demo_channel):
    ejecutivo = as_user("ejecutivo")
    quote = create_calculated(client, ejecutivo, clock, demo_channel.id, ESTANDAR)
    response = client.get(f"/api/cotizaciones/{quote['id']}/pdf", headers=ejecutivo)
    assert response.status_code == 404
    assert "se genera al emitirla" in response.json()["detail"]


def test_si_falla_la_generacion_del_documento_la_cotizacion_no_queda_emitida(
    client, as_user, clock, demo_channel, documents, monkeypatch
):
    ejecutivo = as_user("ejecutivo")
    quote = create_calculated(client, ejecutivo, clock, demo_channel.id, ESTANDAR)

    def falla(datos):
        raise RuntimeError("sin fuentes")

    monkeypatch.setattr(documents, "render_quote", falla)
    with pytest.raises(RuntimeError):
        client.post(f"/api/cotizaciones/{quote['id']}/emitir", headers=ejecutivo)
    monkeypatch.undo()

    # No se guardó nada a medias: sigue calculada, sin documento, y la emisión puede reintentarse.
    despues = client.get(f"/api/cotizaciones/{quote['id']}", headers=ejecutivo).json()
    assert (despues["estado"], despues["tiene_pdf"], despues["emitida_en"]) == ("CALCULADA", False, None)
    assert issue(client, ejecutivo, quote["id"])["estado"] == "EMITIDA"


@pytest.mark.parametrize("rol, esperado", [("aprobador", 200), ("gerente", 200), ("pricing", 200), ("admin", 403)])
def test_descarga_del_pdf_segun_el_rol(client, as_user, clock, demo_channel, rol, esperado):
    quote = create_issued(client, as_user("ejecutivo"), clock, demo_channel.id, ESTANDAR)
    assert client.get(f"/api/cotizaciones/{quote['id']}/pdf", headers=as_user(rol)).status_code == esperado


def test_cada_version_tiene_su_propio_documento(client, as_user, clock, demo_channel, storage):
    ejecutivo = as_user("ejecutivo")
    v1 = create_issued(client, ejecutivo, clock, demo_channel.id, ESTANDAR)
    v2 = client.post(f"/api/cotizaciones/{v1['id']}/nueva-version", headers=ejecutivo).json()
    client.post(f"/api/cotizaciones/{v2['id']}/calcular", headers=ejecutivo)
    issue(client, ejecutivo, v2["id"])
    assert sorted(storage.files) == [f"{v1['numero']}-v1.pdf", f"{v1['numero']}-v2.pdf"]
    # El documento de la versión reemplazada se conserva.
    assert client.get(f"/api/cotizaciones/{v1['id']}/pdf", headers=ejecutivo).status_code == 200


def test_si_el_archivo_se_perdio_el_documento_se_regenera_identico(client, as_user, clock, demo_channel, documents, storage):
    """En un alojamiento con disco efímero los PDF desaparecen al reiniciar; la descarga no debe fallar."""
    ejecutivo = as_user("ejecutivo")
    quote = create_issued(client, ejecutivo, clock, demo_channel.id, ESTANDAR)
    nombre = f"{quote['numero']}-v1.pdf"
    original = storage.files.pop(nombre)
    clock.advance(days=3)

    response = client.get(f"/api/cotizaciones/{quote['id']}/pdf", headers=ejecutivo)

    assert response.status_code == 200
    assert response.content == original
    assert documents.rendered[1] == documents.rendered[0]  # mismos datos congelados, no la fecha de hoy
    assert storage.files[nombre] == original


# --- Tablero de indicadores -----------------------------------------------------------


def test_tablero_vacio_muestra_linea_base_y_meta(client, as_user):
    dashboard = client.get("/api/kpis", headers=as_user("gerente")).json()
    assert dashboard["alcance"] == "todos"
    assert dashboard["totales"]["emitidas"] == 0
    k2 = kpi(dashboard, "K2")
    assert (k2["valor"], k2["linea_base"], k2["meta"], k2["unidad"]) == (None, 24.0, 7.0, "min")
    assert (kpi(dashboard, "K3")["linea_base"], kpi(dashboard, "K4")["linea_base"]) == (6.4, 58.0)
    assert kpi(dashboard, "K11")["linea_base"] == 5.2


def test_los_indicadores_se_calculan_desde_los_eventos_del_flujo_real(client, as_user, clock, demo_channel, run_deadlines):
    ejecutivo, aprobador, gerente = as_user("ejecutivo"), as_user("aprobador"), as_user("gerente")

    # Cotización A: recibida hace 30 min, elaborada en 6 min, luego ganada.
    a = create_calculated(client, ejecutivo, clock, demo_channel.id, ESTANDAR)
    clock.advance(minutes=6)
    issue(client, ejecutivo, a["id"])

    # Cotización B: 4 min de elaboración, 20 min esperando aprobación, 1 min para confirmar.
    b = create_calculated(client, ejecutivo, clock, demo_channel.id, [(DEMO_SKU, 20, "0.09")])
    clock.advance(minutes=4)
    client.post(f"/api/cotizaciones/{b['id']}/solicitar-aprobacion", headers=ejecutivo)
    clock.advance(minutes=20)
    resolve(client, aprobador, approval_queue(client, aprobador)[0]["id"], "aprobar", "Autorizado")
    clock.advance(minutes=1)
    issue(client, ejecutivo, b["id"])

    client.post(f"/api/cotizaciones/{a['id']}/cerrar", json={"resultado": "GANADA"}, headers=ejecutivo)
    # B se reemplaza por una nueva versión (retrabajo), que queda en borrador.
    client.post(f"/api/cotizaciones/{b['id']}/nueva-version", headers=ejecutivo)

    dashboard = client.get("/api/kpis", headers=gerente).json()
    assert dashboard["totales"] == {
        "creadas": 3,
        "emitidas": 2,
        "aprobaciones_resueltas": 1,
        "ganadas": 1,
        "perdidas": 0,
        "vencidas": 0,
        "reemplazadas": 1,
    }
    assert kpi(dashboard, "K2")["valor"] == 5.5  # (6 + 5) / 2 minutos
    # A: 30 + 6 = 36 min. B: recibida 30 min antes de crearse, emitida 25 min después = 55 min.
    assert kpi(dashboard, "K3")["valor"] == pytest.approx((36 + 55) / 2 / 60, abs=0.01)
    assert kpi(dashboard, "K4")["valor"] == 100.0
    assert kpi(dashboard, "K11")["valor"] == pytest.approx(20 / 60, abs=0.01)
    assert kpi(dashboard, "K11b")["valor"] == 100.0
    assert kpi(dashboard, "K8")["valor"] == 50.0
    assert kpi(dashboard, "K13")["valor"] == 100.0
    assert kpi(dashboard, "K14")["valor"] == 100.0
    assert datetime.fromisoformat(dashboard["generado_en"]) == clock.now()


def test_el_ejecutivo_ve_solo_los_indicadores_de_sus_cotizaciones(client, as_user, clock, demo_channel, db):
    from app.infra.models import Usuario
    from app.infra.security import create_access_token, hash_password

    otro = Usuario(usuario="ejecutivo2", nombre="Julián Mora", email="e2@cotiza.example.com",
                   password_hash=hash_password("Cotiza2026*"), rol="ejecutivo", activo=True, creado_en=clock.now())  # fmt: skip
    db.add(otro)
    db.commit()
    otro_ejecutivo = {"Authorization": f"Bearer {create_access_token(otro.id, otro.rol)}"}

    ejecutivo = as_user("ejecutivo")
    create_issued(client, ejecutivo, clock, demo_channel.id, ESTANDAR)
    create_issued(client, ejecutivo, clock, demo_channel.id, [(DEMO_SKU, 5)])
    create_issued(client, otro_ejecutivo, clock, demo_channel.id, [(DEMO_SKU, 3)])

    propios = client.get("/api/kpis", headers=ejecutivo).json()
    assert propios["alcance"] == "propios"
    assert propios["totales"]["emitidas"] == 2
    assert client.get("/api/kpis", headers=otro_ejecutivo).json()["totales"]["emitidas"] == 1
    assert client.get("/api/kpis", headers=as_user("gerente")).json()["totales"]["emitidas"] == 3


@pytest.mark.parametrize("rol", ["aprobador", "gerente", "pricing"])
def test_aprobador_gerente_y_pricing_ven_el_tablero_completo(client, as_user, clock, demo_channel, rol):
    create_issued(client, as_user("ejecutivo"), clock, demo_channel.id, ESTANDAR)
    dashboard = client.get("/api/kpis", headers=as_user(rol)).json()
    assert dashboard["alcance"] == "todos" and dashboard["totales"]["emitidas"] == 1


def test_el_administrador_no_consulta_el_tablero(client, as_user):
    assert client.get("/api/kpis", headers=as_user("admin")).status_code == 403
    assert client.get("/api/kpis").status_code == 401


def test_k11b_refleja_una_aprobacion_resuelta_fuera_del_sla(client, as_user, clock, demo_channel, run_deadlines):
    ejecutivo, gerente = as_user("ejecutivo"), as_user("gerente")
    create_pending(client, ejecutivo, clock, demo_channel.id, [(DEMO_SKU, 20, "0.09")])
    clock.advance(minutes=90)
    run_deadlines()
    resolve(client, gerente, approval_queue(client, gerente)[0]["id"], "rechazar", "Fuera de política")

    dashboard = client.get("/api/kpis", headers=gerente).json()
    assert kpi(dashboard, "K11")["valor"] == 1.5
    assert kpi(dashboard, "K11b")["valor"] == 0.0
