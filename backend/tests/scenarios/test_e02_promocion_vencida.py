"""E2. Promoción vencida: se descarta, se aplica la escala por volumen si corresponde y el
descarte queda registrado (RN-04, RN-05)."""

from datetime import date
from decimal import Decimal

from app.infra.models import Promocion
from tests.conftest import T0
from tests.helpers import create_calculated, issue, line


def _promocion_vencida_ayer(db) -> None:
    db.add(
        Promocion(
            referencia="RED-0001",
            nombre="Promo de septiembre",
            descuento=Decimal("0.10"),
            fecha_inicio=date(2026, 9, 1),
            fecha_fin=date(2026, 10, 4),  # la cotización se calcula el 5 de octubre
            creada_en=T0,
        )
    )
    db.commit()


def test_e2_promocion_vencida_se_descarta_y_aplica_el_volumen(client, as_user, clock, demo_channel, db):
    _promocion_vencida_ayer(db)
    ejecutivo = as_user("ejecutivo")

    quote = create_calculated(client, ejecutivo, clock, demo_channel.id, [("RED-0001", 20)])

    linea = line(quote, "RED-0001")
    # 125 × 0,96 (Plata) × 0,98 (volumen 10–49 u) = 117,60. Con la promoción del 10 % habría sido 108,00.
    assert linea["precio_unitario"] == "117.60"
    assert linea["promocion_fin"] is None
    reglas = {r["regla"]: r["descripcion"] for r in linea["reglas_aplicadas"]}
    assert "descartada: venció el 2026-10-04" in reglas["RN-04"]
    assert "Escala por volumen" in reglas["RN-03"]
    assert quote["evaluacion"] == "LISTA_PARA_EMITIR"


def test_e2_el_descarte_queda_en_el_registro_de_eventos(client, as_user, clock, demo_channel, db):
    _promocion_vencida_ayer(db)
    ejecutivo = as_user("ejecutivo")
    quote = create_calculated(client, ejecutivo, clock, demo_channel.id, [("RED-0001", 20)])

    eventos = client.get(f"/api/cotizaciones/{quote['id']}/eventos", headers=ejecutivo).json()
    calculada = next(e for e in eventos if e["tipo"] == "COTIZACION_CALCULADA")
    descartes = calculada["payload"]["promociones_descartadas"]
    assert len(descartes) == 1
    assert descartes[0]["referencia"] == "RED-0001"
    assert "Promo de septiembre" in descartes[0]["detalle"]


def test_e2_promocion_vencida_sin_volumen_deja_solo_el_descuento_de_nivel(client, as_user, clock, demo_channel, db):
    _promocion_vencida_ayer(db)
    quote = create_calculated(client, as_user("ejecutivo"), clock, demo_channel.id, [("RED-0001", 5)])
    assert line(quote, "RED-0001")["precio_unitario"] == "120.00"


def test_e2_la_promocion_vencida_no_acorta_la_vigencia(client, as_user, clock, demo_channel, db):
    _promocion_vencida_ayer(db)
    ejecutivo = as_user("ejecutivo")
    quote = create_calculated(client, ejecutivo, clock, demo_channel.id, [("RED-0001", 20)])
    emitida = issue(client, ejecutivo, quote["id"])
    assert emitida["vigente_hasta"].startswith("2026-10-12")  # 7 días calendario


def test_rn11_la_promocion_vigente_que_termina_pronto_acota_la_vigencia(client, as_user, clock, demo_channel, db):
    db.add(
        Promocion(
            referencia="RED-0001",
            nombre="Promo que termina el 7",
            descuento=Decimal("0.05"),
            fecha_inicio=date(2026, 10, 1),
            fecha_fin=date(2026, 10, 7),
            creada_en=T0,
        )
    )
    db.commit()
    ejecutivo = as_user("ejecutivo")
    quote = create_calculated(client, ejecutivo, clock, demo_channel.id, [("RED-0001", 20)])
    assert line(quote, "RED-0001")["precio_unitario"] == "114.00"  # 120 × 0,95
    emitida = issue(client, ejecutivo, quote["id"])
    # Fin del 7 de octubre en Bogotá = 8 de octubre 05:00 UTC.
    assert emitida["vigente_hasta"] in ("2026-10-08T05:00:00Z", "2026-10-08T00:00:00-05:00")
