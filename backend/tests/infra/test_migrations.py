from datetime import datetime, timezone

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect, text
from sqlalchemy.exc import DBAPIError

from app.infra.models import Base, Evento

EXPECTED_TABLES = {
    "usuarios",
    "niveles_canal",
    "canales",
    "escalas_volumen",
    "margenes_categoria",
    "promociones",
    "parametros",
    "cotizaciones",
    "lineas_cotizacion",
    "solicitudes_aprobacion",
    "tareas_seguimiento",
    "notificaciones",
    "eventos",
}


def test_las_migraciones_crean_todas_las_tablas(engine):
    assert EXPECTED_TABLES <= set(inspect(engine).get_table_names())


def test_las_migraciones_coinciden_con_los_modelos(engine):
    """Si alguien cambia un modelo sin crear la migración, esta prueba falla."""
    with engine.connect() as connection:
        context = MigrationContext.configure(connection, opts={"compare_type": True})
        assert compare_metadata(context, Base.metadata) == []


def _nuevo_evento(session) -> Evento:
    evento = Evento(tipo="PRUEBA", ocurrido_en=datetime.now(timezone.utc), payload={"origen": "test"})
    session.add(evento)
    session.flush()
    return evento


def test_los_eventos_no_se_pueden_modificar(session):
    evento = _nuevo_evento(session)
    with pytest.raises(DBAPIError, match="inmutables"):
        session.execute(text("UPDATE eventos SET tipo = 'OTRO' WHERE id = :id"), {"id": evento.id})


def test_los_eventos_no_se_pueden_eliminar(session):
    evento = _nuevo_evento(session)
    with pytest.raises(DBAPIError, match="inmutables"):
        session.execute(text("DELETE FROM eventos WHERE id = :id"), {"id": evento.id})
