"""E9. Vigencia vencida: al terminar la vigencia sin orden de compra, la cotización se cierra
como vencida y libera el inventario comprometido (RN-11, RN-12)."""

from app.infra.models import Parametro
from app.infra.seeds import DEMO_SKU
from tests.helpers import create_calculated, create_issued, event_types, get_quote, line, tasks

ESTANDAR = [(DEMO_SKU, 20)]


def _disponible(client, headers, clock, canal_id) -> int:
    """Disponibilidad neta de la referencia de demo vista por una cotización nueva."""
    return line(create_calculated(client, headers, clock, canal_id, [(DEMO_SKU, 1)]), DEMO_SKU)["disponible"]


def test_e9_al_vencer_la_vigencia_pasa_a_vencida_y_libera_el_inventario(
    client, as_user, clock, demo_channel, run_deadlines, notifications
):
    ejecutivo = as_user("ejecutivo")
    quote = create_issued(client, ejecutivo, clock, demo_channel.id, ESTANDAR)
    # Mientras está vigente, sus 20 unidades no están disponibles para otros.
    assert _disponible(client, ejecutivo, clock, demo_channel.id) == 130

    # A las 48 h entra en seguimiento; sigue comprometiendo inventario.
    clock.advance(hours=48)
    run_deadlines()
    assert _disponible(client, ejecutivo, clock, demo_channel.id) == 130

    # Un minuto antes de cumplirse los 7 días sigue vigente.
    clock.advance(days=5, minutes=-1)
    assert run_deadlines().vencidas == 0

    clock.advance(minutes=1)
    assert run_deadlines().vencidas == 1

    vencida = get_quote(client, ejecutivo, quote["id"])
    assert vencida["estado"] == "VENCIDA"
    assert vencida["cerrada_en"] is not None
    assert vencida["acciones_permitidas"] == []
    # Los precios emitidos se conservan como registro.
    assert vencida["total"] == "14592.00"

    # Inventario liberado y tarea de seguimiento cerrada por el sistema.
    assert _disponible(client, ejecutivo, clock, demo_channel.id) == 150
    assert tasks(client, ejecutivo) == []
    assert notifications("ejecutivo")[0]["tipo"] == "COTIZACION_VENCIDA"

    eventos = client.get(f"/api/cotizaciones/{quote['id']}/eventos", headers=ejecutivo).json()
    assert eventos[-1]["tipo"] == "COTIZACION_VENCIDA"
    assert eventos[-1]["usuario"] == "Sistema"
    assert eventos[-1]["payload"]["estado_anterior"] == "EN_SEGUIMIENTO"
    assert eventos[-1]["payload"]["inventario_liberado"] == {DEMO_SKU: 20}


def test_e9_una_emitida_que_nunca_entro_en_seguimiento_tambien_vence(client, as_user, clock, demo_channel, run_deadlines):
    """Si el planificador estuvo detenido, al volver vence la cotización sin crear una tarea inútil."""
    ejecutivo = as_user("ejecutivo")
    quote = create_issued(client, ejecutivo, clock, demo_channel.id, ESTANDAR)
    clock.advance(days=8)

    report = run_deadlines()
    assert (report.vencidas, report.seguimientos) == (1, 0)
    assert get_quote(client, ejecutivo, quote["id"])["estado"] == "VENCIDA"
    assert tasks(client, ejecutivo) == []
    assert event_types(client, ejecutivo, quote["id"])[-1] == "COTIZACION_VENCIDA"


def test_e9_vencer_ocurre_una_sola_vez(client, as_user, clock, demo_channel, run_deadlines):
    create_issued(client, as_user("ejecutivo"), clock, demo_channel.id, ESTANDAR)
    clock.advance(days=8)
    assert run_deadlines().vencidas == 1
    clock.advance(days=1)
    assert run_deadlines().total == 0


def test_e9_una_cotizacion_vencida_no_se_puede_ganar_ni_versionar(client, as_user, clock, demo_channel, run_deadlines):
    ejecutivo = as_user("ejecutivo")
    quote = create_issued(client, ejecutivo, clock, demo_channel.id, ESTANDAR)
    clock.advance(days=8)
    run_deadlines()
    url = f"/api/cotizaciones/{quote['id']}"
    assert client.post(f"{url}/cerrar", json={"resultado": "GANADA"}, headers=ejecutivo).status_code == 409
    assert client.post(f"{url}/nueva-version", headers=ejecutivo).status_code == 409


def test_e9_una_cotizacion_ganada_no_vence_y_tambien_libera_inventario(
    client, as_user, clock, demo_channel, run_deadlines
):
    ejecutivo = as_user("ejecutivo")
    quote = create_issued(client, ejecutivo, clock, demo_channel.id, ESTANDAR)
    client.post(f"/api/cotizaciones/{quote['id']}/cerrar", json={"resultado": "GANADA"}, headers=ejecutivo)
    # La orden sale del alcance del MVP: la cotización deja de comprometer inventario al cerrarse.
    assert _disponible(client, ejecutivo, clock, demo_channel.id) == 150
    clock.advance(days=8)
    assert run_deadlines().vencidas == 0
    assert get_quote(client, ejecutivo, quote["id"])["estado"] == "GANADA"


def test_e9_el_inventario_se_libera_al_cumplirse_la_vigencia_aunque_el_planificador_no_haya_corrido(
    client, as_user, clock, demo_channel
):
    ejecutivo = as_user("ejecutivo")
    create_issued(client, ejecutivo, clock, demo_channel.id, ESTANDAR)
    clock.advance(days=7, minutes=1)
    assert _disponible(client, ejecutivo, clock, demo_channel.id) == 150


def test_e9_la_vigencia_es_configurable_para_la_demo(client, as_user, clock, demo_channel, run_deadlines, db):
    db.get(Parametro, "vigencia_minutos").valor = "5"
    db.get(Parametro, "seguimiento_minutos").valor = "2"
    db.commit()
    ejecutivo = as_user("ejecutivo")
    quote = create_issued(client, ejecutivo, clock, demo_channel.id, ESTANDAR)

    clock.advance(minutes=2)
    assert run_deadlines().seguimientos == 1
    clock.advance(minutes=3)
    assert run_deadlines().vencidas == 1
    assert event_types(client, ejecutivo, quote["id"])[-2:] == ["SEGUIMIENTO_INICIADO", "COTIZACION_VENCIDA"]
