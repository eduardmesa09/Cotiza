"""Repositorios SQL: ida y vuelta entre el dominio y la base de datos."""

from datetime import date, time, timedelta
from decimal import Decimal as D

import pytest
from sqlalchemy import select

from app.adapters.sql_misc import SqlCustomerAdapter, SqlEventAdapter, SqlNotificationAdapter
from app.adapters.sql_repositories import SqlPricingRepository, SqlQuoteRepository
from app.domain.errors import PricingConfigError
from app.domain.events import EventType
from app.domain.pricing_engine import Evaluation, LineInput, LineStatus, ProductData, calculate_line
from app.domain.quote import Quote, QuoteLine
from app.domain.state_machine import QuoteState
from app.infra.models import Notificacion, Parametro, Usuario
from app.infra.seeds import DEMO_SKU
from tests.conftest import T0


@pytest.fixture
def ejecutivo_id(db) -> int:
    return db.scalars(select(Usuario.id).where(Usuario.usuario == "ejecutivo")).one()


def _calculated_line(db, cantidad=20, adicional="0.09") -> QuoteLine:
    pricing = SqlPricingRepository(db)
    product = ProductData(DEMO_SKU, "Portátil (demo)", "Portátiles", D("620.00"), D("800.00"))
    result = calculate_line(
        LineInput(DEMO_SKU, cantidad, D(adicional)),
        product,
        "Plata",
        date(2026, 10, 5),
        pricing.promotions_for(DEMO_SKU),
        150,
        0,
        pricing.get_params(),
    )
    return QuoteLine(DEMO_SKU, cantidad, D(adicional), resultado=result, disponible=150)


def _issued_quote(repo, canal_id, ejecutivo_id, comprometida, vigente_hasta, estado=QuoteState.EMITIDA) -> Quote:
    quote = Quote(canal_id=canal_id, ejecutivo_id=ejecutivo_id, recibida_en=T0, creada_en=T0)
    quote.lineas = [QuoteLine("PER-0001", 10, cantidad_comprometida=comprometida)]
    quote.estado = estado
    quote.emitida_en = T0
    quote.vigente_hasta = vigente_hasta
    return repo.add(quote)


# --- Cotizaciones ---------------------------------------------------------------------


def test_add_asigna_id_y_numero(db, demo_channel, ejecutivo_id):
    repo = SqlQuoteRepository(db)
    quote = repo.add(Quote.nueva(demo_channel.id, ejecutivo_id, T0, T0, [QuoteLine(DEMO_SKU, 20)]))
    assert quote.id is not None
    assert quote.numero == f"COT-{quote.id:06d}"


def test_una_version_nueva_conserva_el_numero(db, demo_channel, ejecutivo_id):
    repo = SqlQuoteRepository(db)
    primera = repo.add(Quote.nueva(demo_channel.id, ejecutivo_id, T0, T0))
    segunda = Quote.nueva(demo_channel.id, ejecutivo_id, T0, T0)
    segunda.numero, segunda.version, segunda.version_anterior_id = primera.numero, 2, primera.id
    segunda = repo.add(segunda)
    assert (segunda.numero, segunda.version) == (primera.numero, 2)
    assert repo.get(segunda.id).version_anterior_id == primera.id


def test_ida_y_vuelta_de_una_cotizacion_sin_calcular(db, demo_channel, ejecutivo_id):
    repo = SqlQuoteRepository(db)
    quote = repo.add(Quote.nueva(demo_channel.id, ejecutivo_id, T0 - timedelta(minutes=30), T0, [QuoteLine(DEMO_SKU, 20, D("0.05"))]))
    db.expire_all()

    loaded = repo.get(quote.id)
    assert loaded.estado is QuoteState.BORRADOR
    assert loaded.evaluacion is None and loaded.total is None
    assert loaded.recibida_en == T0 - timedelta(minutes=30)
    assert loaded.lineas == [QuoteLine(DEMO_SKU, 20, D("0.0500"))]
    assert loaded.lineas[0].resultado is None


def test_ida_y_vuelta_conserva_el_resultado_del_calculo_y_el_rastro_de_reglas(db, demo_channel, ejecutivo_id):
    repo = SqlQuoteRepository(db)
    quote = Quote.nueva(demo_channel.id, ejecutivo_id, T0, T0, [_calculated_line(db)])
    quote.calcular({DEMO_SKU: quote.lineas[0].resultado}, T0)
    original = quote.lineas[0].resultado
    repo.add(quote)
    db.expire_all()

    loaded = repo.get(quote.id)
    assert loaded.estado is QuoteState.CALCULADA
    assert loaded.evaluacion is Evaluation.REQUIERE_APROBACION
    assert loaded.total == D("13278.80")
    r = loaded.lineas[0].resultado
    assert r.estado is LineStatus.OK
    assert (r.precio_unitario, r.margen, r.margen_minimo) == (D("663.94"), D("0.0662"), D("0.0800"))
    assert r.requiere_aprobacion and r.promocion_fin == original.promocion_fin
    assert r.reglas_aplicadas == original.reglas_aplicadas
    assert loaded.aprobada is False


def test_save_reemplaza_las_lineas(db, demo_channel, ejecutivo_id):
    repo = SqlQuoteRepository(db)
    quote = repo.add(Quote.nueva(demo_channel.id, ejecutivo_id, T0, T0, [QuoteLine(DEMO_SKU, 20)]))
    quote.editar(demo_channel.id, T0, [QuoteLine("RED-0001", 3), QuoteLine("PER-0001", 1)], T0)
    repo.save(quote)
    db.expire_all()
    assert [(l.referencia, l.cantidad) for l in repo.get(quote.id).lineas] == [("RED-0001", 3), ("PER-0001", 1)]


def test_get_de_cotizacion_inexistente(db):
    assert SqlQuoteRepository(db).get(999999) is None


def test_list_filtra_por_ejecutivo_y_estado(db, demo_channel, ejecutivo_id):
    repo = SqlQuoteRepository(db)
    otro = db.scalars(select(Usuario.id).where(Usuario.usuario == "gerente")).one()
    mia = repo.add(Quote.nueva(demo_channel.id, ejecutivo_id, T0, T0))
    ajena = repo.add(Quote.nueva(demo_channel.id, otro, T0, T0))
    emitida = _issued_quote(repo, demo_channel.id, ejecutivo_id, 1, T0 + timedelta(days=7))

    assert {q.id for q in repo.list()} == {mia.id, ajena.id, emitida.id}
    assert {q.id for q in repo.list(ejecutivo_id=ejecutivo_id)} == {mia.id, emitida.id}
    assert [q.id for q in repo.list(estado=QuoteState.EMITIDA)] == [emitida.id]


# --- RN-10: inventario comprometido ---------------------------------------------------


def test_comprometido_suma_cotizaciones_emitidas_y_en_seguimiento_vigentes(db, demo_channel, ejecutivo_id):
    repo = SqlQuoteRepository(db)
    vigente = T0 + timedelta(days=7)
    _issued_quote(repo, demo_channel.id, ejecutivo_id, 4, vigente)
    _issued_quote(repo, demo_channel.id, ejecutivo_id, 3, vigente, QuoteState.EN_SEGUIMIENTO)
    assert repo.committed_quantity("PER-0001", T0) == 7
    assert repo.committed_quantity("OTRA-REF", T0) == 0


@pytest.mark.parametrize("estado", [QuoteState.BORRADOR, QuoteState.CALCULADA, QuoteState.PENDIENTE_APROBACION, QuoteState.GANADA, QuoteState.PERDIDA, QuoteState.VENCIDA])
def test_no_comprometen_las_no_emitidas_ni_las_cerradas(db, demo_channel, ejecutivo_id, estado):
    repo = SqlQuoteRepository(db)
    _issued_quote(repo, demo_channel.id, ejecutivo_id, 4, T0 + timedelta(days=7), estado)
    assert repo.committed_quantity("PER-0001", T0) == 0


def test_no_comprometen_las_de_vigencia_vencida_ni_las_reemplazadas(db, demo_channel, ejecutivo_id):
    repo = SqlQuoteRepository(db)
    _issued_quote(repo, demo_channel.id, ejecutivo_id, 4, T0 - timedelta(minutes=1))
    reemplazada = _issued_quote(repo, demo_channel.id, ejecutivo_id, 5, T0 + timedelta(days=7))
    reemplazada.reemplazada = True
    repo.save(reemplazada)
    assert repo.committed_quantity("PER-0001", T0) == 0


# --- Parámetros comerciales -----------------------------------------------------------


def test_get_params_lee_los_valores_semilla(db):
    params = SqlPricingRepository(db).get_params()
    assert params.descuentos_nivel == {"Oro": D("0.06"), "Plata": D("0.04"), "Bronce": D("0.02")}
    assert [(t.cantidad_min, t.cantidad_max, t.descuento) for t in params.escalas_volumen] == [
        (10, 49, D("0.02")),
        (50, 99, D("0.04")),
        (100, None, D("0.06")),
    ]
    assert params.margenes_minimos["Periféricos"] == D("0.12")


def test_promotions_for(db):
    repo = SqlPricingRepository(db)
    (promo,) = repo.promotions_for(DEMO_SKU)
    assert promo.descuento == D("0.05")
    assert repo.promotions_for("SIN-PROMO") == []


def test_get_settings_interpreta_plazos_y_calendario(db):
    settings = SqlPricingRepository(db).get_settings()
    assert settings.sla_aprobacion_minutos == 60
    assert settings.sla_respuesta_minutos == 240
    assert settings.seguimiento_minutos == 48 * 60
    assert settings.vigencia_minutos == 7 * 24 * 60
    assert (settings.calendar.inicio, settings.calendar.fin) == (time(9, 0), time(17, 0))
    assert settings.calendar.dias == {1, 2, 3, 4, 5}
    assert settings.calendar.tz.key == "America/Bogota"
    assert settings.calendar.activo is True


def test_get_settings_con_parametro_ilegible_es_error_de_configuracion(db):
    db.get(Parametro, "sla_aprobacion_minutos").valor = "una hora"
    db.flush()
    with pytest.raises(PricingConfigError):
        SqlPricingRepository(db).get_settings()


# --- Canales, eventos y notificaciones ------------------------------------------------


def test_canales(db, demo_channel):
    customers = SqlCustomerAdapter(db)
    channel = customers.get(demo_channel.id)
    assert channel.nivel == "Plata" and channel.nit == demo_channel.nit
    assert customers.get(999999) is None
    assert len(customers.list()) == 40


def test_eventos_se_registran_y_se_leen_en_orden(db, demo_channel, ejecutivo_id):
    quote = SqlQuoteRepository(db).add(Quote.nueva(demo_channel.id, ejecutivo_id, T0, T0))
    events = SqlEventAdapter(db)
    events.record(EventType.COTIZACION_CALCULADA, T0 + timedelta(minutes=2), quote.id, ejecutivo_id, {"total": "10.00"})
    events.record(EventType.COTIZACION_CREADA, T0, quote.id, ejecutivo_id)
    events.record(EventType.SEGUIMIENTO_PROGRAMADO, T0 + timedelta(minutes=2), quote.id)

    history = events.list_for_quote(quote.id)
    assert [e.tipo for e in history] == [
        EventType.COTIZACION_CREADA,
        EventType.COTIZACION_CALCULADA,
        EventType.SEGUIMIENTO_PROGRAMADO,
    ]
    assert history[1].payload == {"total": "10.00"}
    assert history[2].usuario_id is None
    assert events.list_for_quote(999999) == []


def test_notificacion_dentro_de_la_aplicacion(db, ejecutivo_id):
    SqlNotificationAdapter(db).notify(ejecutivo_id, "PRUEBA", "Mensaje de prueba", T0)
    (row,) = db.scalars(select(Notificacion)).all()
    assert (row.usuario_id, row.mensaje, row.leida) == (ejecutivo_id, "Mensaje de prueba", False)
