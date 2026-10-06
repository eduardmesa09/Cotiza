from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.infra.models import (
    Canal,
    EscalaVolumen,
    MargenCategoria,
    NivelCanal,
    Parametro,
    Promocion,
    Usuario,
)
from app.infra.security import verify_password
from app.infra.seeds import DEFAULT_PASSWORD, DEMO_CHANNEL_NIT, DEMO_SKU, seed_all

NOW = datetime(2026, 10, 5, 15, 0, tzinfo=timezone.utc)
TODAY = NOW.date()

# Catálogo mínimo con la forma que devuelve el ERP simulado.
PRODUCTS = (
    [{"sku": DEMO_SKU, "costo": "620.00", "precio_lista": "800.00"}]
    + [{"sku": f"REF-{i:03d}", "costo": "100.00", "precio_lista": "120.00"} for i in range(100)]
    + [{"sku": "SIN-COSTO", "costo": None, "precio_lista": "50.00"}]
)


@pytest.fixture
def seeded(session):
    counts = seed_all(session, PRODUCTS, NOW)
    return session, counts


def test_conteos(seeded):
    _, counts = seeded
    assert counts == {
        "usuarios": 5,
        "niveles_canal": 3,
        "canales": 40,
        "escalas_volumen": 3,
        "margenes_categoria": 5,
        "promociones": 61,
        "parametros": 10,
    }


def test_es_idempotente(seeded):
    session, counts = seeded
    assert seed_all(session, PRODUCTS, NOW) == counts


def test_un_usuario_por_rol_con_la_contrasena_documentada(seeded):
    session, _ = seeded
    users = session.scalars(select(Usuario)).all()
    assert sorted(u.rol for u in users) == ["admin", "aprobador", "ejecutivo", "gerente", "pricing"]
    assert all(verify_password(DEFAULT_PASSWORD, u.password_hash) for u in users)


def test_descuentos_por_nivel_rn02(seeded):
    session, _ = seeded
    levels = {n.nombre: n.descuento for n in session.scalars(select(NivelCanal))}
    assert levels == {"Oro": Decimal("0.06"), "Plata": Decimal("0.04"), "Bronce": Decimal("0.02")}


def test_escalas_por_volumen_rn03(seeded):
    session, _ = seeded
    tiers = [
        (t.cantidad_min, t.cantidad_max, t.descuento)
        for t in session.scalars(select(EscalaVolumen).order_by(EscalaVolumen.cantidad_min))
    ]
    assert tiers == [(10, 49, Decimal("0.02")), (50, 99, Decimal("0.04")), (100, None, Decimal("0.06"))]


def test_margenes_minimos_por_categoria_rn07(seeded):
    session, _ = seeded
    margins = {m.categoria: m.margen_minimo for m in session.scalars(select(MargenCategoria))}
    assert margins == {
        "Portátiles": Decimal("0.08"),
        "Periféricos": Decimal("0.12"),
        "Servidores": Decimal("0.10"),
        "Redes": Decimal("0.11"),
        "Impresión": Decimal("0.09"),
    }


def test_canales_repartidos_en_los_tres_niveles(seeded):
    session, _ = seeded
    channels = session.scalars(select(Canal)).all()
    assert Counter(c.nivel.nombre for c in channels) == {"Oro": 8, "Plata": 14, "Bronce": 18}
    assert len({c.nit for c in channels}) == 40
    demo = next(c for c in channels if c.nit == DEMO_CHANNEL_NIT)
    assert demo.nivel.nombre == "Plata"


def test_promociones_vigentes_vencidas_y_futuras(seeded):
    session, _ = seeded
    promos = session.scalars(select(Promocion)).all()
    vigentes = [p for p in promos if p.fecha_inicio <= TODAY <= p.fecha_fin]
    vencidas = [p for p in promos if p.fecha_fin < TODAY]
    futuras = [p for p in promos if p.fecha_inicio > TODAY]
    assert (len(vigentes), len(vencidas), len(futuras)) == (36, 15, 10)
    assert all(p.fecha_inicio <= p.fecha_fin for p in promos)
    assert all(Decimal("0.03") <= p.descuento <= Decimal("0.12") for p in promos)


def test_una_sola_promocion_por_referencia_y_solo_sobre_cotizables(seeded):
    session, _ = seeded
    skus = [p.referencia for p in session.scalars(select(Promocion))]
    assert len(skus) == len(set(skus))
    assert "SIN-COSTO" not in skus


def test_promocion_de_demo_vigente_al_5_por_ciento(seeded):
    session, _ = seeded
    promo = session.scalars(select(Promocion).where(Promocion.referencia == DEMO_SKU)).one()
    assert promo.descuento == Decimal("0.05")
    assert promo.fecha_inicio <= TODAY <= promo.fecha_fin


def test_parametros_de_plazos_y_horario(seeded):
    session, _ = seeded
    params = {p.clave: p.valor for p in session.scalars(select(Parametro))}
    assert params["sla_aprobacion_minutos"] == "60"
    assert params["sla_respuesta_minutos"] == "240"
    assert params["seguimiento_minutos"] == "2880"
    assert params["vigencia_minutos"] == "10080"
    assert params["horario_habil_activo"] == "true"


def test_las_promociones_semilla_no_dejan_el_margen_bajo_el_minimo(session):
    """Con la categoría conocida, el descuento se limita para que ni el nivel Oro quede bajo el mínimo."""
    products = [{"sku": DEMO_SKU, "costo": "620.00", "precio_lista": "800.00", "categoria": "Portátiles"}]
    # Margen bruto de 15 % a 24 % en Periféricos (mínimo 12 %): varias no admiten promoción alguna.
    for i in range(100):
        lista = Decimal("100.00")
        costo = lista * (Decimal("0.85") - Decimal(i % 10) / 100)
        products.append({"sku": f"PER-{i:03d}", "costo": str(costo), "precio_lista": str(lista), "categoria": "Periféricos"})
    seed_all(session, products, NOW)

    by_sku = {p["sku"]: p for p in products}
    promos = [p for p in session.scalars(select(Promocion)) if p.referencia != DEMO_SKU]
    assert len(promos) >= 20
    for promo in promos:
        product = by_sku[promo.referencia]
        precio = Decimal(product["precio_lista"]) * Decimal("0.94") * (1 - promo.descuento)  # canal Oro
        margen = (precio - Decimal(product["costo"])) / precio
        assert margen >= Decimal("0.12"), (promo.referencia, promo.descuento, margen)
        assert promo.descuento >= Decimal("0.02")
