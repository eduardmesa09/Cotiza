"""Escenario de demo: recrea semanas de operación con los casos de uso reales."""

from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.domain.errors import DomainError
from app.infra.demo import DAYS_BACK, run_demo
from app.infra.models import Cotizacion, Evento, Notificacion, Usuario
from tests.conftest import T0


@pytest.fixture
def summary(db, erp, documents, storage):
    # Catálogo más amplio que el de los escenarios, con existencias holgadas.
    for i in range(1, 25):
        categoria = ["Portátiles", "Periféricos", "Servidores", "Redes", "Impresión"][i % 5]
        costo = 80 + i * 37
        erp.add(f"DEM-{i:03d}", categoria, f"{costo}.00", f"{costo / 0.80:.2f}", existencias=5000, descripcion=f"Producto demo {i}")
    return run_demo(db, erp, erp, documents, storage, T0)


def kpi(summary, codigo):
    return next(k for k in summary["indicadores"].indicadores if k.codigo == codigo)


def test_genera_un_volumen_representativo_en_varios_estados(summary):
    assert summary["cotizaciones"] >= 60
    estados = summary["estados"]
    # Hay de todo: cerradas de las tres formas y abiertas recientes.
    for estado in ("GANADA", "PERDIDA", "VENCIDA"):
        assert estados.get(estado, 0) >= 3, estado
    assert estados.get("EMITIDA", 0) + estados.get("EN_SEGUIMIENTO", 0) >= 3


def test_los_indicadores_quedan_cerca_de_las_metas_sin_ser_perfectos(summary):
    assert 5.0 <= kpi(summary, "K2").valor <= 9.5  # meta 7 min, línea base 24
    assert 0.8 <= kpi(summary, "K3").valor <= 2.5  # meta 1,5 h, línea base 6,4
    assert 80 <= kpi(summary, "K4").valor < 100  # algunas respuestas incumplen las 4 h
    assert 0.2 <= kpi(summary, "K11").valor <= 1.0
    assert 60 <= kpi(summary, "K11b").valor < 100  # algunas aprobaciones se escalan
    assert 0 < kpi(summary, "K8").valor <= 12  # hay retrabajo, por debajo de la línea base
    assert 25 <= kpi(summary, "K13").valor <= 75
    assert kpi(summary, "K14").valor == 100.0
    assert kpi(summary, "K11").muestra >= 5


def test_todos_los_eventos_ocurren_en_el_pasado_simulado_y_no_en_el_futuro(summary, db):
    primero, ultimo = db.execute(select(func.min(Evento.ocurrido_en), func.max(Evento.ocurrido_en))).one()
    assert primero >= T0 - timedelta(days=DAYS_BACK)
    assert ultimo <= T0


def test_cada_cotizacion_emitida_tiene_su_documento(summary, db, storage):
    emitidas = db.scalars(select(Cotizacion).where(Cotizacion.emitida_en.is_not(None))).all()
    assert emitidas
    assert all(q.pdf_ruta in storage.files for q in emitidas)


def test_reparte_el_trabajo_entre_dos_ejecutivos(summary, db):
    por_ejecutivo = dict(
        db.execute(
            select(Usuario.usuario, func.count(Cotizacion.id)).join(Cotizacion, Cotizacion.ejecutivo_id == Usuario.id).group_by(Usuario.usuario)
        ).all()
    )
    assert set(por_ejecutivo) == {"ejecutivo", "ejecutivo2"}
    assert min(por_ejecutivo.values()) >= 20


def test_solo_quedan_sin_leer_las_notificaciones_recientes(summary, db):
    viejas_sin_leer = db.scalar(
        select(func.count()).select_from(Notificacion).where(Notificacion.leida.is_(False), Notificacion.creada_en < T0 - timedelta(days=1))
    )
    assert viejas_sin_leer == 0
    assert db.scalar(select(func.count()).select_from(Notificacion)) > 0


def test_solo_corre_sobre_una_base_sin_cotizaciones(summary, db, erp, documents, storage):
    antes = db.scalar(select(func.count()).select_from(Cotizacion))
    with pytest.raises(DomainError, match="base limpia"):
        run_demo(db, erp, erp, documents, storage, T0)
    assert db.scalar(select(func.count()).select_from(Cotizacion)) == antes
