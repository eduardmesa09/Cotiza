"""Datos semilla del MVP. Se ejecuta en cada arranque de la API y es idempotente:
cada tabla solo se llena si está vacía.

Uso: python -m app.infra.seeds
"""

import random
import time
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import httpx
from faker import Faker
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.infra.db import get_session_factory
from app.infra.models import (
    Canal,
    EscalaVolumen,
    MargenCategoria,
    NivelCanal,
    Parametro,
    Promocion,
    Usuario,
)
from app.infra.security import hash_password
from app.infra.settings import get_settings

SEED = 2026
DEFAULT_PASSWORD = "Cotiza2026*"

# Referencia y canal del ejemplo de la sección 6.6.3 del informe.
DEMO_SKU = "POR-DEMO01"
DEMO_CHANNEL_NIT = "900123456-7"

USERS = [
    # (usuario, nombre, rol)
    ("ejecutivo", "Camila Torres", "ejecutivo"),
    ("aprobador", "Andrés Pardo", "aprobador"),
    ("gerente", "Patricia Gómez", "gerente"),
    ("pricing", "Felipe Rincón", "pricing"),
    ("admin", "Administrador del sistema", "admin"),
]

# RN-02
LEVELS = [("Oro", "0.06"), ("Plata", "0.04"), ("Bronce", "0.02")]
CHANNELS_PER_LEVEL = {"Oro": 8, "Plata": 14, "Bronce": 18}

# RN-03: (cantidad mínima, cantidad máxima, descuento)
VOLUME_TIERS = [(10, 49, "0.02"), (50, 99, "0.04"), (100, None, "0.06")]

# RN-07
MIN_MARGINS = [
    ("Portátiles", "0.08"),
    ("Periféricos", "0.12"),
    ("Servidores", "0.10"),
    ("Redes", "0.11"),
    ("Impresión", "0.09"),
]

PARAMETERS = [
    ("sla_aprobacion_minutos", "60", "RN-09: plazo para resolver una aprobación antes de escalar al gerente."),
    ("sla_respuesta_minutos", "240", "Compromiso de respuesta al canal (4 h); base del indicador K4."),
    ("seguimiento_minutos", "2880", "RN-12: tiempo tras la emisión para crear la tarea de seguimiento (48 h)."),
    ("vigencia_minutos", "10080", "RN-11: vigencia máxima de la cotización (7 días calendario)."),
    ("horario_habil_activo", "true", "Si es false, los plazos y KPIs corren en tiempo de reloj (útil en la demo)."),
    ("horario_habil_inicio", "09:00", "Inicio de la jornada hábil."),
    ("horario_habil_fin", "17:00", "Fin de la jornada hábil (jornada de 8 horas)."),
    ("horario_habil_dias", "1,2,3,4,5", "Días hábiles en numeración ISO (1 = lunes)."),
    ("zona_horaria", "America/Bogota", "Zona horaria de la operación."),
    ("planificador_intervalo_segundos", "30", "Cada cuánto se revisan plazos vencidos (SLA, seguimiento, vigencia)."),
]

# Nombres ficticios de canales: {a} y {b} son apellidos generados con Faker.
CHANNEL_NAME_TEMPLATES = [
    "Tecnología {a} S.A.S.",
    "{a} y {b} Sistemas Ltda.",
    "Soluciones Informáticas {a} S.A.S.",
    "Distribuciones {a} {b} S.A.",
    "Compu{a} S.A.S.",
    "Redes y Servicios {a} Ltda.",
    "Grupo {a} Tecnología S.A.S.",
    "Integradores {a} y {b} S.A.S.",
]

CITIES = ["Bogotá", "Medellín", "Cali", "Barranquilla", "Bucaramanga", "Cartagena", "Pereira", "Manizales", "Cúcuta", "Ibagué"]

PROMO_NAMES = [
    "Promoción de fabricante",
    "Liquidación de inventario",
    "Campaña de temporada",
    "Incentivo de lanzamiento",
    "Bono por renovación tecnológica",
]


def _is_empty(session: Session, model) -> bool:
    return session.scalar(select(func.count()).select_from(model)) == 0


def seed_users(session: Session, now: datetime) -> None:
    if not _is_empty(session, Usuario):
        return
    password_hash = hash_password(DEFAULT_PASSWORD)
    for usuario, nombre, rol in USERS:
        session.add(
            Usuario(
                usuario=usuario,
                nombre=nombre,
                email=f"{usuario}@cotiza.example.com",
                password_hash=password_hash,
                rol=rol,
                activo=True,
                creado_en=now,
            )
        )


def seed_pricing_rules(session: Session) -> None:
    if _is_empty(session, NivelCanal):
        session.add_all(NivelCanal(nombre=n, descuento=Decimal(d)) for n, d in LEVELS)
    if _is_empty(session, EscalaVolumen):
        session.add_all(
            EscalaVolumen(cantidad_min=lo, cantidad_max=hi, descuento=Decimal(d)) for lo, hi, d in VOLUME_TIERS
        )
    if _is_empty(session, MargenCategoria):
        session.add_all(MargenCategoria(categoria=c, margen_minimo=Decimal(m)) for c, m in MIN_MARGINS)
    if _is_empty(session, Parametro):
        session.add_all(Parametro(clave=k, valor=v, descripcion=d) for k, v, d in PARAMETERS)
    session.flush()


def seed_channels(session: Session) -> None:
    """40 canales ficticios repartidos entre los tres niveles."""
    if not _is_empty(session, Canal):
        return
    fake = Faker("es_CO")
    fake.seed_instance(SEED)
    levels = {n.nombre: n.id for n in session.scalars(select(NivelCanal))}

    session.add(
        Canal(
            nit=DEMO_CHANNEL_NIT,
            nombre="Soluciones Andinas TI S.A.S. (demo)",
            ciudad="Bogotá",
            contacto_nombre="Mariana Suárez",
            contacto_email="compras@canal01.example.com",
            nivel_id=levels["Plata"],
        )
    )
    names = {"Soluciones Andinas TI S.A.S. (demo)"}
    number = 1
    for level, quantity in CHANNELS_PER_LEVEL.items():
        # El canal de demo ya ocupa uno de los cupos de Plata.
        for _ in range(quantity - (1 if level == "Plata" else 0)):
            number += 1
            name = fake.random_element(CHANNEL_NAME_TEMPLATES).format(a=fake.last_name(), b=fake.last_name())
            while name in names:
                name = fake.random_element(CHANNEL_NAME_TEMPLATES).format(a=fake.last_name(), b=fake.last_name())
            names.add(name)
            session.add(
                Canal(
                    nit=f"9{fake.unique.random_number(digits=8, fix_len=True)}-{fake.random_digit()}",
                    nombre=name,
                    ciudad=fake.random_element(CITIES),
                    contacto_nombre=fake.name(),
                    contacto_email=f"compras@canal{number:02d}.example.com",
                    nivel_id=levels[level],
                )
            )


def seed_promotions(session: Session, products: list[dict], today: date, now: datetime) -> None:
    """Promociones vigentes, vencidas y futuras, una por referencia (sin superposición)."""
    if not _is_empty(session, Promocion):
        return
    rng = random.Random(SEED)
    quotable = sorted(
        p["sku"] for p in products if p["costo"] is not None and p["precio_lista"] is not None and p["sku"] != DEMO_SKU
    )
    chosen = rng.sample(quotable, k=min(60, len(quotable)))

    def add(sku: str, discount: str, start: date, end: date, name: str | None = None) -> None:
        session.add(
            Promocion(
                referencia=sku,
                nombre=name or rng.choice(PROMO_NAMES),
                descuento=Decimal(discount),
                fecha_inicio=start,
                fecha_fin=end,
                creada_en=now,
            )
        )

    def discount() -> str:
        return f"0.{rng.randint(3, 12):02d}"

    # La promoción del 5 % del ejemplo del informe, vigente con holgura.
    if any(p["sku"] == DEMO_SKU for p in products):
        add(DEMO_SKU, "0.05", today - timedelta(days=10), today + timedelta(days=30), "Promoción de fabricante (demo)")

    for i, sku in enumerate(chosen):
        if i < 35:  # vigentes; algunas terminan pronto para que acoten la vigencia (RN-11)
            add(sku, discount(), today - timedelta(days=rng.randint(1, 30)), today + timedelta(days=rng.randint(2, 45)))
        elif i < 50:  # vencidas: el motor debe descartarlas (RN-04)
            end = today - timedelta(days=rng.randint(1, 60))
            add(sku, discount(), end - timedelta(days=rng.randint(10, 40)), end)
        else:  # futuras: todavía no aplican
            start = today + timedelta(days=rng.randint(3, 30))
            add(sku, discount(), start, start + timedelta(days=rng.randint(10, 40)))


def seed_all(session: Session, products: list[dict], now: datetime) -> dict[str, int]:
    seed_users(session, now)
    seed_pricing_rules(session)
    seed_channels(session)
    seed_promotions(session, products, now.date(), now)
    session.flush()
    models = (Usuario, NivelCanal, Canal, EscalaVolumen, MargenCategoria, Promocion, Parametro)
    return {m.__tablename__: session.scalar(select(func.count()).select_from(m)) for m in models}


def fetch_products(base_url: str, attempts: int = 10) -> list[dict]:
    """Lee el catálogo del ERP simulado; las promociones se asocian a referencias reales."""
    for attempt in range(1, attempts + 1):
        try:
            response = httpx.get(f"{base_url}/products", params={"limit": 1000}, timeout=10)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError:
            if attempt == attempts:
                raise
            time.sleep(2)
    return []


def main() -> None:
    products = fetch_products(get_settings().erp_base_url)
    with get_session_factory()() as session:
        counts = seed_all(session, products, datetime.now(timezone.utc))
        session.commit()
    print("Semillas listas:", ", ".join(f"{table}={n}" for table, n in counts.items()))


if __name__ == "__main__":
    main()
