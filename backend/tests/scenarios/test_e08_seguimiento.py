"""E8. Sin respuesta del canal: a las 48 horas de la emisión sin cierre se crea una tarea de
seguimiento asignada al ejecutivo (RN-12)."""

from datetime import timedelta

import pytest

from app.infra.models import Parametro
from app.infra.seeds import DEMO_SKU
from tests.helpers import create_issued, event_types, get_quote, tasks

ESTANDAR = [(DEMO_SKU, 20)]


def test_e8_a_las_48_horas_sin_cierre_se_crea_la_tarea_de_seguimiento(
    client, as_user, clock, demo_channel, run_deadlines, notifications
):
    ejecutivo = as_user("ejecutivo")
    quote = create_issued(client, ejecutivo, clock, demo_channel.id, ESTANDAR)
    assert tasks(client, ejecutivo) == []

    # Un minuto antes de las 48 h todavía no pasa nada.
    clock.advance(hours=47, minutes=59)
    assert run_deadlines().seguimientos == 0
    assert get_quote(client, ejecutivo, quote["id"])["estado"] == "EMITIDA"

    clock.advance(minutes=1)
    assert run_deadlines().seguimientos == 1

    assert get_quote(client, ejecutivo, quote["id"])["estado"] == "EN_SEGUIMIENTO"
    (tarea,) = tasks(client, ejecutivo)
    assert tarea["cotizacion"]["id"] == quote["id"]
    assert tarea["cotizacion"]["numero"] == quote["numero"]
    assert notifications("ejecutivo")[0]["tipo"] == "SEGUIMIENTO"

    eventos = client.get(f"/api/cotizaciones/{quote['id']}/eventos", headers=ejecutivo).json()
    assert eventos[-1]["tipo"] == "SEGUIMIENTO_INICIADO"
    assert eventos[-1]["usuario"] == "Sistema"
    assert eventos[-1]["payload"]["tarea_id"] == tarea["id"]


def test_e8_la_tarea_se_crea_una_sola_vez(client, as_user, clock, demo_channel, run_deadlines):
    ejecutivo = as_user("ejecutivo")
    create_issued(client, ejecutivo, clock, demo_channel.id, ESTANDAR)
    clock.advance(hours=49)
    assert run_deadlines().seguimientos == 1
    clock.advance(hours=5)
    assert run_deadlines().seguimientos == 0
    assert len(tasks(client, ejecutivo)) == 1


def test_e8_una_cotizacion_ganada_antes_de_las_48_horas_no_genera_tarea(
    client, as_user, clock, demo_channel, run_deadlines
):
    ejecutivo = as_user("ejecutivo")
    quote = create_issued(client, ejecutivo, clock, demo_channel.id, ESTANDAR)
    clock.advance(hours=3)
    ganada = client.post(f"/api/cotizaciones/{quote['id']}/cerrar", json={"resultado": "GANADA"}, headers=ejecutivo)
    assert ganada.status_code == 200 and ganada.json()["estado"] == "GANADA"

    clock.advance(hours=60)
    assert run_deadlines().total == 0
    assert tasks(client, ejecutivo) == []
    assert event_types(client, ejecutivo, quote["id"])[-1] == "COTIZACION_GANADA"


@pytest.mark.parametrize(
    "accion, estado, evento",
    [("GANADA", "GANADA", "COTIZACION_GANADA"), ("PERDIDA", "PERDIDA", "COTIZACION_PERDIDA")],
)
def test_e8_el_ejecutivo_atiende_la_tarea_como_ganada_o_perdida(
    client, as_user, clock, demo_channel, run_deadlines, accion, estado, evento
):
    ejecutivo = as_user("ejecutivo")
    quote = create_issued(client, ejecutivo, clock, demo_channel.id, ESTANDAR)
    clock.advance(hours=48)
    run_deadlines()
    (tarea,) = tasks(client, ejecutivo)

    clock.advance(hours=2)
    response = client.post(
        f"/api/seguimiento/{tarea['id']}/resolver", json={"accion": accion, "nota": "Respuesta del canal"}, headers=ejecutivo
    )
    assert response.status_code == 200
    cerrada = response.json()
    assert cerrada["estado"] == estado
    assert cerrada["cerrada_en"] is not None
    assert cerrada["acciones_permitidas"] == []
    assert tasks(client, ejecutivo) == []

    eventos = client.get(f"/api/cotizaciones/{quote['id']}/eventos", headers=ejecutivo).json()
    assert eventos[-1]["tipo"] == evento
    assert eventos[-1]["payload"]["nota"] == "Respuesta del canal"
    assert eventos[-1]["payload"]["estado_anterior"] == "EN_SEGUIMIENTO"


def test_e8_mantener_en_seguimiento_cierra_la_tarea_y_programa_otra(
    client, as_user, clock, demo_channel, run_deadlines
):
    ejecutivo = as_user("ejecutivo")
    quote = create_issued(client, ejecutivo, clock, demo_channel.id, ESTANDAR)
    clock.advance(hours=48)
    run_deadlines()
    (primera,) = tasks(client, ejecutivo)

    clock.advance(hours=1)
    response = client.post(
        f"/api/seguimiento/{primera['id']}/resolver", json={"accion": "MANTENER", "nota": "Decide el viernes"}, headers=ejecutivo
    )
    assert response.status_code == 200
    assert response.json()["estado"] == "EN_SEGUIMIENTO"
    assert tasks(client, ejecutivo) == []

    # El nuevo recordatorio llega con el mismo plazo, contado desde que se atendió la tarea.
    clock.advance(hours=47)
    assert run_deadlines().seguimientos == 0
    clock.advance(hours=1)
    assert run_deadlines().seguimientos == 1
    (segunda,) = tasks(client, ejecutivo)
    assert segunda["id"] != primera["id"]

    tipos = event_types(client, ejecutivo, quote["id"])
    assert tipos[-3:] == ["SEGUIMIENTO_INICIADO", "SEGUIMIENTO_MANTENIDO", "SEGUIMIENTO_INICIADO"]


def test_e8_perdida_solo_se_registra_desde_seguimiento(client, as_user, clock, demo_channel):
    """Figura 8: una cotización recién emitida puede ganarse, pero 'el canal declina' llega por el seguimiento."""
    ejecutivo = as_user("ejecutivo")
    quote = create_issued(client, ejecutivo, clock, demo_channel.id, ESTANDAR)
    response = client.post(f"/api/cotizaciones/{quote['id']}/cerrar", json={"resultado": "PERDIDA"}, headers=ejecutivo)
    assert response.status_code == 409


def test_e8_el_plazo_de_seguimiento_es_configurable_para_la_demo(client, as_user, clock, demo_channel, run_deadlines, db):
    db.get(Parametro, "seguimiento_minutos").valor = "3"
    db.commit()
    ejecutivo = as_user("ejecutivo")
    create_issued(client, ejecutivo, clock, demo_channel.id, ESTANDAR)
    clock.advance(minutes=2)
    assert run_deadlines().seguimientos == 0
    clock.advance(minutes=1)
    assert run_deadlines().seguimientos == 1


@pytest.mark.parametrize("rol", ["aprobador", "gerente", "pricing", "admin"])
def test_e8_las_tareas_son_del_ejecutivo(client, as_user, clock, demo_channel, run_deadlines, rol):
    ejecutivo = as_user("ejecutivo")
    quote = create_issued(client, ejecutivo, clock, demo_channel.id, ESTANDAR)
    clock.advance(hours=48)
    run_deadlines()
    (tarea,) = tasks(client, ejecutivo)

    headers = as_user(rol)
    assert client.get("/api/seguimiento", headers=headers).status_code == 403
    resolver = client.post(f"/api/seguimiento/{tarea['id']}/resolver", json={"accion": "GANADA"}, headers=headers)
    assert resolver.status_code == 403
    cerrar = client.post(f"/api/cotizaciones/{quote['id']}/cerrar", json={"resultado": "GANADA"}, headers=headers)
    assert cerrar.status_code == 403


def test_e8_tarea_inexistente_o_accion_invalida(client, as_user, clock, demo_channel, run_deadlines):
    ejecutivo = as_user("ejecutivo")
    assert client.post("/api/seguimiento/999999/resolver", json={"accion": "GANADA"}, headers=ejecutivo).status_code == 404
    create_issued(client, ejecutivo, clock, demo_channel.id, ESTANDAR)
    clock.advance(hours=48)
    run_deadlines()
    (tarea,) = tasks(client, ejecutivo)
    invalida = client.post(f"/api/seguimiento/{tarea['id']}/resolver", json={"accion": "VENCIDA"}, headers=ejecutivo)
    assert invalida.status_code == 422
