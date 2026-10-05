"""Plazos: RN-09 (SLA de aprobación), RN-11 (vigencia) y RN-12 (seguimiento)."""

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from app.domain.business_time import BusinessCalendar
from app.domain.deadlines import approval_due, follow_up_due, valid_until
from app.domain.errors import ExpiredPromotionError

BOGOTA = ZoneInfo("America/Bogota")
CAL = BusinessCalendar(time(9, 0), time(17, 0), frozenset({1, 2, 3, 4, 5}), BOGOTA)
RELOJ = BusinessCalendar(time(9, 0), time(17, 0), frozenset({1, 2, 3, 4, 5}), BOGOTA, activo=False)

SIETE_DIAS = 7 * 24 * 60
DOS_DIAS = 48 * 60


def bog(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, day, hour, minute, tzinfo=BOGOTA)


# --- RN-09 -----------------------------------------------------------------------------


def test_rn09_sla_de_una_hora_habil_dentro_de_la_jornada():
    assert approval_due(bog(5, 10), 60, CAL) == bog(5, 11)


def test_rn09_solicitud_al_final_del_dia_vence_al_dia_habil_siguiente():
    assert approval_due(bog(5, 16, 40), 60, CAL) == bog(6, 9, 40)


def test_rn09_solicitud_el_viernes_en_la_tarde_vence_el_lunes():
    assert approval_due(bog(9, 16, 30), 60, CAL) == bog(12, 9, 30)


def test_rn09_el_sla_es_configurable_en_minutos_para_la_demo():
    assert approval_due(bog(5, 10), 2, CAL) == bog(5, 10, 2)


def test_rn09_con_horario_habil_desactivado_corre_en_tiempo_de_reloj():
    assert approval_due(bog(9, 16, 30), 60, RELOJ) == bog(9, 17, 30)
    assert approval_due(bog(10, 23), 2, RELOJ) == bog(10, 23, 2)


# --- RN-11 -----------------------------------------------------------------------------


def test_rn11_sin_promocion_la_vigencia_es_de_siete_dias_calendario():
    assert valid_until(bog(5, 10), SIETE_DIAS, [], BOGOTA) == bog(12, 10)


def test_rn11_la_promocion_que_termina_antes_acota_la_vigencia_al_final_de_su_ultimo_dia():
    assert valid_until(bog(5, 10), SIETE_DIAS, [date(2026, 10, 8)], BOGOTA) == bog(9, 0)


def test_rn11_la_promocion_que_termina_despues_no_extiende_la_vigencia():
    assert valid_until(bog(5, 10), SIETE_DIAS, [date(2026, 11, 4)], BOGOTA) == bog(12, 10)


def test_rn11_con_varias_promociones_manda_la_que_termina_primero():
    fines = [date(2026, 10, 10), date(2026, 10, 7), date(2026, 11, 1)]
    assert valid_until(bog(5, 10), SIETE_DIAS, fines, BOGOTA) == bog(8, 0)


def test_rn11_promocion_que_termina_el_mismo_dia_de_la_emision():
    assert valid_until(bog(5, 10), SIETE_DIAS, [date(2026, 10, 5)], BOGOTA) == bog(6, 0)


def test_rn11_promocion_ya_terminada_al_emitir_obliga_a_recalcular():
    with pytest.raises(ExpiredPromotionError, match="2026-10-04"):
        valid_until(bog(5, 10), SIETE_DIAS, [date(2026, 10, 4)], BOGOTA)


def test_rn11_el_fin_de_la_promocion_se_mide_en_la_zona_de_la_operacion():
    # 02:00 UTC del 6 de octubre todavía es 5 de octubre (21:00) en Bogotá: la promoción sigue viva.
    emitida = datetime(2026, 10, 6, 2, 0, tzinfo=timezone.utc)
    assert valid_until(emitida, SIETE_DIAS, [date(2026, 10, 5)], BOGOTA) == bog(6, 0)


def test_rn11_la_vigencia_es_configurable_en_minutos_para_la_demo():
    assert valid_until(bog(5, 10), 5, [], BOGOTA) == bog(5, 10, 5)


# --- RN-12 -----------------------------------------------------------------------------


def test_rn12_el_seguimiento_se_programa_a_las_48_horas_de_reloj():
    # Viernes 15:00 -> domingo 15:00: no depende del horario hábil.
    assert follow_up_due(bog(9, 15), DOS_DIAS) == bog(11, 15)


def test_rn12_el_plazo_de_seguimiento_es_configurable():
    assert follow_up_due(bog(5, 10), 3) == bog(5, 10) + timedelta(minutes=3)


def test_rn12_el_seguimiento_ocurre_antes_de_que_venza_la_vigencia():
    emitida = bog(5, 10)
    assert follow_up_due(emitida, DOS_DIAS) < valid_until(emitida, SIETE_DIAS, [], BOGOTA)
