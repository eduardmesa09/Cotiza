"""Indicadores calculados desde el registro de eventos (sección 6.7)."""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.domain.business_time import BusinessCalendar
from app.domain.events import Event, EventType as T
from app.domain.kpis import compute_kpis, quote_owners

BOGOTA = ZoneInfo("America/Bogota")
CAL = BusinessCalendar(time(9, 0), time(17, 0), frozenset({1, 2, 3, 4, 5}), BOGOTA)
RELOJ = BusinessCalendar(time(9, 0), time(17, 0), frozenset({1, 2, 3, 4, 5}), BOGOTA, activo=False)
SLA_4H = 240

# Lunes 5 de octubre de 2026, 10:00 en Bogotá.
T0 = datetime(2026, 10, 5, 10, 0, tzinfo=BOGOTA)
VIERNES_MEDIODIA = datetime(2026, 10, 2, 12, 0, tzinfo=BOGOTA)


def ev(tipo, minuto, quote_id, usuario=1, **payload) -> Event:
    return Event(tipo=tipo, ocurrido_en=T0 + timedelta(minutes=minuto), cotizacion_id=quote_id, usuario_id=usuario, payload=payload)


def emitida(minuto, quote_id, recibida: datetime) -> list[Event]:
    return [
        ev(T.COTIZACION_EMITIDA, minuto, quote_id, recibida_en=recibida.isoformat()),
        ev(T.SEGUIMIENTO_PROGRAMADO, minuto, quote_id, usuario=None),
    ]


def kpi(report, codigo):
    return next(k for k in report.indicadores if k.codigo == codigo)


@pytest.fixture
def escenario() -> list[Event]:
    return [
        # Cotización 1: estándar. Recibida 09:30, creada 10:00, emitida 10:06. Luego ganada.
        ev(T.COTIZACION_CREADA, 0, 1),
        ev(T.COTIZACION_CALCULADA, 2, 1),
        *emitida(6, 1, T0 - timedelta(minutes=30)),
        ev(T.COTIZACION_GANADA, 300, 1),
        # Cotización 2: con aprobación de 30 min. Recibida 09:00, creada 10:00, emitida 10:37. Luego perdida.
        ev(T.COTIZACION_CREADA, 0, 2),
        ev(T.APROBACION_SOLICITADA, 4, 2),
        ev(T.APROBACION_APROBADA, 34, 2, usuario=2, dentro_del_sla=True),
        *emitida(37, 2, T0 - timedelta(minutes=60)),
        ev(T.SEGUIMIENTO_INICIADO, 400, 2, usuario=None),
        ev(T.COTIZACION_PERDIDA, 420, 2),
        # Cotización 3: recibida el viernes al mediodía, atendida el lunes; luego reemplazada.
        ev(T.COTIZACION_CREADA, 0, 3),
        *emitida(10, 3, VIERNES_MEDIODIA),
        ev(T.COTIZACION_REEMPLAZADA, 200, 3),
        # Cotización 4: quedó en borrador.
        ev(T.COTIZACION_CREADA, 50, 4),
    ]


def test_k2_tiempo_de_elaboracion_descuenta_el_tiempo_en_aprobacion(escenario):
    k2 = kpi(compute_kpis(escenario, CAL, SLA_4H), "K2")
    # 6 min, 37 − 30 = 7 min y 10 min.
    assert k2.valor == pytest.approx(7.67)
    assert (k2.unidad, k2.muestra, k2.linea_base, k2.meta, k2.sentido) == ("min", 3, 24.0, 7.0, "menor")


def test_k3_tiempo_de_respuesta_en_horas_habiles(escenario):
    k3 = kpi(compute_kpis(escenario, CAL, SLA_4H), "K3")
    # 0,6 h; 1,617 h; y viernes 12–17 (5 h) + lunes 09:00–10:10 (1,167 h) = 6,167 h.
    assert k3.valor == pytest.approx((0.6 + 97 / 60 + 5 + 70 / 60) / 3, abs=0.01)
    assert (k3.linea_base, k3.meta) == (6.4, 1.5)


def test_k4_cumplimiento_del_sla_de_respuesta(escenario):
    k4 = kpi(compute_kpis(escenario, CAL, SLA_4H), "K4")
    assert k4.valor == 66.7  # dos de tres dentro de las 4 h
    assert (k4.linea_base, k4.meta, k4.sentido) == (58.0, 92.0, "mayor")
    assert "4 h" in k4.nombre


def test_k4_respuesta_justo_en_el_limite_cumple():
    events = [ev(T.COTIZACION_CREADA, 0, 1), *emitida(0, 1, T0 - timedelta(minutes=60))]
    assert kpi(compute_kpis(events, CAL, 60), "K4").valor == 100.0
    assert kpi(compute_kpis(events, CAL, 59), "K4").valor == 0.0


def test_k11_espera_por_aprobacion_y_k11b_dentro_del_sla(escenario):
    report = compute_kpis(escenario, CAL, SLA_4H)
    assert kpi(report, "K11").valor == 0.5
    assert (kpi(report, "K11").linea_base, kpi(report, "K11").meta) == (5.2, 1.0)
    assert kpi(report, "K11b").valor == 100.0
    assert kpi(report, "K11b").muestra == 1


def test_k11_con_rechazo_y_segunda_solicitud_fuera_del_sla():
    events = [
        ev(T.COTIZACION_CREADA, 0, 1),
        ev(T.APROBACION_SOLICITADA, 5, 1),
        ev(T.APROBACION_RECHAZADA, 25, 1, usuario=2, dentro_del_sla=True),  # 20 min
        ev(T.APROBACION_SOLICITADA, 30, 1),
        ev(T.APROBACION_ESCALADA, 90, 1, usuario=None),
        ev(T.APROBACION_APROBADA, 130, 1, usuario=3, dentro_del_sla=False),  # 100 min
        *emitida(135, 1, T0),
    ]
    report = compute_kpis(events, CAL, SLA_4H)
    assert kpi(report, "K11").valor == 1.0  # promedio de 20 y 100 minutos
    assert kpi(report, "K11b").valor == 50.0
    # Elaboración: 135 min de ciclo − 120 min esperando aprobación.
    assert kpi(report, "K2").valor == 15.0
    assert kpi(report, "K10").valor == 100.0


def test_una_solicitud_aun_pendiente_no_cuenta_como_resuelta():
    events = [ev(T.COTIZACION_CREADA, 0, 1), ev(T.APROBACION_SOLICITADA, 5, 1)]
    report = compute_kpis(events, CAL, SLA_4H)
    assert kpi(report, "K11").valor is None and kpi(report, "K11b").muestra == 0


def test_k8_retrabajo(escenario):
    k8 = kpi(compute_kpis(escenario, CAL, SLA_4H), "K8")
    assert k8.valor == 33.3  # una de las tres emitidas tuvo nueva versión
    assert (k8.linea_base, k8.meta) == (12.0, 4.0)


def test_k13_conversion(escenario):
    k13 = kpi(compute_kpis(escenario, CAL, SLA_4H), "K13")
    assert k13.valor == 50.0  # una ganada y una perdida
    assert k13.muestra == 2
    assert (k13.linea_base, k13.meta) == (31.0, 36.0)


def test_k13_las_vencidas_cuentan_como_no_convertidas():
    events = [
        ev(T.COTIZACION_CREADA, 0, 1), *emitida(5, 1, T0), ev(T.COTIZACION_GANADA, 60, 1),
        ev(T.COTIZACION_CREADA, 0, 2), *emitida(5, 2, T0), ev(T.COTIZACION_VENCIDA, 9000, 2, usuario=None),
        ev(T.COTIZACION_CREADA, 0, 3), *emitida(5, 3, T0), ev(T.COTIZACION_VENCIDA, 9000, 3, usuario=None),
        ev(T.COTIZACION_CREADA, 0, 4), *emitida(5, 4, T0),  # todavía abierta: no entra en el cálculo
    ]  # fmt: skip
    report = compute_kpis(events, CAL, SLA_4H)
    assert kpi(report, "K13").valor == 33.3
    assert report.totales["vencidas"] == 2


def test_k14_cotizaciones_con_seguimiento(escenario):
    k14 = kpi(compute_kpis(escenario, CAL, SLA_4H), "K14")
    assert k14.valor == 100.0
    assert (k14.linea_base, k14.meta) == (54.0, 100.0)


def test_k14_detecta_una_emitida_sin_ningun_seguimiento():
    events = [
        ev(T.COTIZACION_CREADA, 0, 1),
        ev(T.COTIZACION_EMITIDA, 5, 1, recibida_en=T0.isoformat()),  # sin seguimiento programado
        ev(T.COTIZACION_CREADA, 0, 2),
        *emitida(5, 2, T0),
    ]
    assert kpi(compute_kpis(events, CAL, SLA_4H), "K14").valor == 50.0


def test_k10_cotizaciones_que_requieren_aprobacion(escenario):
    assert kpi(compute_kpis(escenario, CAL, SLA_4H), "K10").valor == 25.0  # una de cuatro creadas


def test_totales(escenario):
    assert compute_kpis(escenario, CAL, SLA_4H).totales == {
        "creadas": 4,
        "emitidas": 3,
        "aprobaciones_resueltas": 1,
        "ganadas": 1,
        "perdidas": 1,
        "vencidas": 0,
        "reemplazadas": 1,
    }


def test_sin_eventos_no_hay_valores_pero_si_linea_base_y_meta():
    report = compute_kpis([], CAL, SLA_4H)
    assert [k.codigo for k in report.indicadores] == ["K2", "K3", "K4", "K11", "K11b", "K8", "K13", "K14", "K10"]
    assert all(k.valor is None and k.muestra == 0 for k in report.indicadores)
    assert kpi(report, "K2").linea_base == 24.0
    assert set(report.totales.values()) == {0}


def test_una_version_nueva_mide_su_elaboracion_desde_que_se_creo():
    events = [ev(T.NUEVA_VERSION_CREADA, 100, 7), *emitida(104, 7, T0 + timedelta(minutes=100))]
    report = compute_kpis(events, CAL, SLA_4H)
    assert kpi(report, "K2").valor == 4.0
    assert report.totales["creadas"] == 1


def test_con_horario_habil_desactivado_se_mide_en_tiempo_de_reloj(escenario):
    # La cotización 3 pasa de 6,17 h hábiles a casi tres días de reloj.
    habil = kpi(compute_kpis(escenario, CAL, SLA_4H), "K3").valor
    reloj = kpi(compute_kpis(escenario, RELOJ, SLA_4H), "K3").valor
    assert reloj > 20 > habil


def test_el_orden_de_llegada_de_los_eventos_no_altera_el_resultado(escenario):
    assert compute_kpis(list(reversed(escenario)), CAL, SLA_4H) == compute_kpis(escenario, CAL, SLA_4H)


def test_dueno_de_cada_cotizacion():
    events = [
        ev(T.COTIZACION_CREADA, 0, 1, usuario=10),
        ev(T.COTIZACION_EMITIDA, 5, 1, usuario=10),
        ev(T.APROBACION_APROBADA, 3, 1, usuario=20),  # quien aprueba no es el dueño
        ev(T.NUEVA_VERSION_CREADA, 9, 2, usuario=11),
        ev(T.COTIZACION_VENCIDA, 9, 3, usuario=None),
    ]
    assert quote_owners(events) == {1: 10, 2: 11}
