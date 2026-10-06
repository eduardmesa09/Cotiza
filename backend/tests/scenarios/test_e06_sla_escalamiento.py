"""E6. SLA de aprobación vencido: transcurrida una hora hábil sin resolución, la solicitud
se escala a la gerencia comercial y se notifica al aprobador (RN-09)."""

from datetime import datetime, timezone

from app.infra.models import Parametro
from app.infra.seeds import DEMO_SKU
from tests.helpers import approval_queue, create_pending, issue, resolve

BAJO_MARGEN = [(DEMO_SKU, 20, "0.09")]


def test_e6_sla_vencido_escala_al_gerente_y_notifica(client, as_user, clock, demo_channel, run_deadlines, notifications):
    ejecutivo, aprobador, gerente = as_user("ejecutivo"), as_user("aprobador"), as_user("gerente")
    quote = create_pending(client, ejecutivo, clock, demo_channel.id, BAJO_MARGEN)

    # Mientras el SLA corre, el gerente no tiene nada en su cola.
    clock.advance(minutes=59)
    assert run_deadlines().escaladas == 0
    assert approval_queue(client, gerente) == []
    assert approval_queue(client, aprobador)[0]["sla_restante_segundos"] == 60

    # Se cumple la hora hábil: el planificador escala.
    clock.advance(minutes=1)
    assert run_deadlines().escaladas == 1

    (escalada,) = approval_queue(client, gerente)
    assert escalada["escalada"] is True
    assert escalada["sla_vencido"] is True and escalada["sla_restante_segundos"] == 0
    assert datetime.fromisoformat(escalada["escalada_en"]) == clock.now()
    assert escalada["cotizacion"]["id"] == quote["id"]

    # Se notifica al gerente y al aprobador original.
    assert notifications("gerente")[0]["tipo"] == "APROBACION_ESCALADA"
    assert "escalada a usted" in notifications("gerente")[0]["mensaje"]
    assert notifications("aprobador")[0]["tipo"] == "APROBACION_ESCALADA"
    assert "gerencia comercial" in notifications("aprobador")[0]["mensaje"]

    # La cotización sigue pendiente; el evento lo generó el sistema.
    eventos = client.get(f"/api/cotizaciones/{quote['id']}/eventos", headers=ejecutivo).json()
    assert eventos[-1]["tipo"] == "APROBACION_ESCALADA"
    assert eventos[-1]["usuario"] == "Sistema"
    assert client.get(f"/api/cotizaciones/{quote['id']}", headers=ejecutivo).json()["estado"] == "PENDIENTE_APROBACION"


def test_e6_el_escalamiento_ocurre_una_sola_vez(client, as_user, clock, demo_channel, run_deadlines, notifications):
    create_pending(client, as_user("ejecutivo"), clock, demo_channel.id, BAJO_MARGEN)
    clock.advance(hours=2)
    assert run_deadlines().escaladas == 1
    clock.advance(hours=3)
    assert run_deadlines().escaladas == 0
    assert len([n for n in notifications("gerente") if n["tipo"] == "APROBACION_ESCALADA"]) == 1


def test_e6_el_gerente_resuelve_la_solicitud_escalada(client, as_user, clock, demo_channel, run_deadlines):
    ejecutivo, gerente = as_user("ejecutivo"), as_user("gerente")
    quote = create_pending(client, ejecutivo, clock, demo_channel.id, BAJO_MARGEN)
    clock.advance(minutes=90)
    run_deadlines()

    (escalada,) = approval_queue(client, gerente)
    resolve(client, gerente, escalada["id"], "aprobar", "Autorizado por gerencia")
    assert approval_queue(client, gerente) == []
    assert issue(client, ejecutivo, quote["id"])["estado"] == "EMITIDA"

    eventos = client.get(f"/api/cotizaciones/{quote['id']}/eventos", headers=ejecutivo).json()
    aprobada = next(e for e in eventos if e["tipo"] == "APROBACION_APROBADA")
    assert aprobada["usuario"] == "Patricia Gómez"
    # Queda registrado que se resolvió fuera del SLA y tras escalar: alimenta el indicador K11b.
    assert aprobada["payload"]["dentro_del_sla"] is False
    assert aprobada["payload"]["escalada"] is True
    assert aprobada["payload"]["espera_segundos"] == 90 * 60


def test_e6_el_aprobador_todavia_puede_resolver_una_solicitud_escalada(
    client, as_user, clock, demo_channel, run_deadlines
):
    create_pending(client, as_user("ejecutivo"), clock, demo_channel.id, BAJO_MARGEN)
    clock.advance(hours=2)
    run_deadlines()
    aprobador = as_user("aprobador")
    (solicitud,) = approval_queue(client, aprobador)
    assert solicitud["escalada"] is True
    resolve(client, aprobador, solicitud["id"], "rechazar", "Margen insuficiente")
    assert approval_queue(client, as_user("gerente")) == []


def test_e6_una_solicitud_resuelta_a_tiempo_no_se_escala(client, as_user, clock, demo_channel, run_deadlines):
    create_pending(client, as_user("ejecutivo"), clock, demo_channel.id, BAJO_MARGEN)
    aprobador = as_user("aprobador")
    clock.advance(minutes=30)
    resolve(client, aprobador, approval_queue(client, aprobador)[0]["id"], "aprobar")
    clock.advance(hours=5)
    assert run_deadlines().escaladas == 0


def test_e6_el_sla_cuenta_solo_tiempo_habil(client, as_user, clock, demo_channel, run_deadlines):
    """Solicitud el viernes a las 16:30 (Bogotá): la hora hábil se cumple el lunes a las 09:30."""
    clock.current = datetime(2026, 10, 9, 21, 30, tzinfo=timezone.utc)  # viernes 16:30 en Bogotá
    create_pending(client, as_user("ejecutivo"), clock, demo_channel.id, BAJO_MARGEN)

    clock.current = datetime(2026, 10, 11, 20, 0, tzinfo=timezone.utc)  # domingo
    assert run_deadlines().escaladas == 0
    assert approval_queue(client, as_user("aprobador"))[0]["sla_restante_segundos"] == 30 * 60

    clock.current = datetime(2026, 10, 12, 14, 29, tzinfo=timezone.utc)  # lunes 09:29
    assert run_deadlines().escaladas == 0
    clock.current = datetime(2026, 10, 12, 14, 30, tzinfo=timezone.utc)  # lunes 09:30
    assert run_deadlines().escaladas == 1


def test_e6_sla_configurable_en_minutos_y_en_tiempo_de_reloj_para_la_demo(
    client, as_user, clock, demo_channel, run_deadlines, db
):
    db.get(Parametro, "sla_aprobacion_minutos").valor = "2"
    db.get(Parametro, "horario_habil_activo").valor = "false"
    db.commit()

    clock.current = datetime(2026, 10, 10, 3, 0, tzinfo=timezone.utc)  # sábado de madrugada
    create_pending(client, as_user("ejecutivo"), clock, demo_channel.id, BAJO_MARGEN)
    clock.advance(minutes=1, seconds=59)
    assert run_deadlines().escaladas == 0
    clock.advance(seconds=1)
    assert run_deadlines().escaladas == 1
