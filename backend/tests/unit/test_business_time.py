from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from app.domain.business_time import BusinessCalendar, add_business_time, business_time_between

BOGOTA = ZoneInfo("America/Bogota")
CAL = BusinessCalendar(time(9, 0), time(17, 0), frozenset({1, 2, 3, 4, 5}), BOGOTA)
RELOJ = BusinessCalendar(time(9, 0), time(17, 0), frozenset({1, 2, 3, 4, 5}), BOGOTA, activo=False)


def bog(day: int, hour: int, minute: int = 0) -> datetime:
    """Octubre de 2026 en hora de Bogotá. El 5 es lunes; el 9, viernes; 10 y 11, fin de semana."""
    return datetime(2026, 10, day, hour, minute, tzinfo=BOGOTA)


# --- business_time_between -------------------------------------------------------------


def test_dentro_de_la_misma_jornada():
    assert business_time_between(bog(5, 10), bog(5, 11, 30), CAL) == timedelta(minutes=90)


def test_no_cuenta_antes_de_abrir_ni_despues_de_cerrar():
    assert business_time_between(bog(5, 7), bog(5, 10), CAL) == timedelta(hours=1)
    assert business_time_between(bog(5, 16), bog(5, 20), CAL) == timedelta(hours=1)
    assert business_time_between(bog(5, 18), bog(5, 23), CAL) == timedelta(0)


def test_cruza_la_noche():
    # Lunes 16:00 -> martes 10:00: una hora del lunes y una del martes.
    assert business_time_between(bog(5, 16), bog(6, 10), CAL) == timedelta(hours=2)


def test_cruza_el_fin_de_semana():
    # Viernes 16:30 -> lunes 09:30.
    assert business_time_between(bog(9, 16, 30), bog(12, 9, 30), CAL) == timedelta(hours=1)


def test_fin_de_semana_completo_no_cuenta():
    assert business_time_between(bog(10, 8), bog(11, 20), CAL) == timedelta(0)


def test_semana_completa_son_cinco_jornadas_de_ocho_horas():
    assert business_time_between(bog(5, 0), bog(12, 0), CAL) == timedelta(hours=40)


def test_fin_anterior_o_igual_al_inicio_es_cero():
    assert business_time_between(bog(5, 12), bog(5, 12), CAL) == timedelta(0)
    assert business_time_between(bog(5, 12), bog(5, 10), CAL) == timedelta(0)


def test_convierte_desde_utc_a_la_zona_de_la_operacion():
    # 15:00 UTC = 10:00 en Bogotá.
    inicio = datetime(2026, 10, 5, 15, 0, tzinfo=timezone.utc)
    fin = datetime(2026, 10, 5, 23, 0, tzinfo=timezone.utc)  # 18:00 en Bogotá
    assert business_time_between(inicio, fin, CAL) == timedelta(hours=7)


def test_calendario_inactivo_cuenta_tiempo_de_reloj():
    assert business_time_between(bog(9, 16), bog(12, 10), RELOJ) == timedelta(days=2, hours=18)


def test_rechaza_fechas_sin_zona_horaria():
    with pytest.raises(ValueError, match="zona horaria"):
        business_time_between(datetime(2026, 10, 5, 10), bog(5, 11), CAL)


# --- add_business_time -----------------------------------------------------------------


def test_suma_dentro_de_la_jornada():
    assert add_business_time(bog(5, 10), timedelta(hours=1), CAL) == bog(5, 11)


def test_suma_que_termina_justo_al_cierre():
    assert add_business_time(bog(5, 16), timedelta(hours=1), CAL) == bog(5, 17)


def test_suma_que_pasa_al_dia_siguiente():
    assert add_business_time(bog(5, 16, 30), timedelta(hours=1), CAL) == bog(6, 9, 30)


def test_suma_desde_fuera_de_horario_empieza_al_abrir():
    assert add_business_time(bog(5, 20), timedelta(hours=1), CAL) == bog(6, 10)
    assert add_business_time(bog(5, 6), timedelta(minutes=30), CAL) == bog(5, 9, 30)


def test_suma_que_salta_el_fin_de_semana():
    assert add_business_time(bog(9, 16, 30), timedelta(hours=1), CAL) == bog(12, 9, 30)
    assert add_business_time(bog(10, 12), timedelta(hours=1), CAL) == bog(12, 10)


def test_suma_de_varias_jornadas():
    # 20 horas hábiles desde el lunes a las 09:00: 8 + 8 + 4 -> miércoles 13:00.
    assert add_business_time(bog(5, 9), timedelta(hours=20), CAL) == bog(7, 13)


def test_suma_conserva_la_zona_horaria_de_entrada():
    inicio = datetime(2026, 10, 5, 15, 0, tzinfo=timezone.utc)
    resultado = add_business_time(inicio, timedelta(hours=1), CAL)
    assert resultado == datetime(2026, 10, 5, 16, 0, tzinfo=timezone.utc)
    assert resultado.utcoffset() == timedelta(0)


def test_suma_con_calendario_inactivo_es_tiempo_de_reloj():
    assert add_business_time(bog(9, 16, 30), timedelta(hours=1), RELOJ) == bog(9, 17, 30)


def test_suma_y_diferencia_son_coherentes():
    inicio = bog(8, 15, 20)
    for minutos in (1, 59, 100, 480, 1234):
        fin = add_business_time(inicio, timedelta(minutes=minutos), CAL)
        assert business_time_between(inicio, fin, CAL) == timedelta(minutes=minutos)


def test_duracion_negativa_es_invalida():
    with pytest.raises(ValueError):
        add_business_time(bog(5, 10), timedelta(minutes=-1), CAL)


# --- Validación del calendario ---------------------------------------------------------


def test_calendario_con_jornada_invertida_es_invalido():
    with pytest.raises(ValueError):
        BusinessCalendar(time(17, 0), time(9, 0), frozenset({1}), BOGOTA)


@pytest.mark.parametrize("dias", [frozenset(), frozenset({0}), frozenset({8})])
def test_calendario_con_dias_invalidos(dias):
    with pytest.raises(ValueError):
        BusinessCalendar(time(9, 0), time(17, 0), dias, BOGOTA)
