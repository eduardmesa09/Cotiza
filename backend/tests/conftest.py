"""Infraestructura común de pruebas.

Las pruebas que tocan la base de datos usan una base aparte (cotiza_test) en el mismo
servidor PostgreSQL. El esquema se crea con las migraciones reales y cada prueba corre
dentro de una transacción que se revierte al terminar.

Los sistemas externos se sustituyen por dobles: un ERP en memoria y un reloj que cada prueba
adelanta a voluntad. Así los escenarios con plazos (SLA, 48 h, vigencia) son deterministas.
"""

import os

# Antes de importar la aplicación: bcrypt con costo mínimo para que las pruebas sean rápidas.
os.environ.setdefault("BCRYPT_ROUNDS", "4")

from collections.abc import Callable, Iterator
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.api.deps import get_catalog, get_clock, get_inventory
from app.domain.pricing_engine import ProductData
from app.infra.db import get_session
from app.infra.models import Canal, Usuario
from app.infra.security import create_access_token
from app.infra.seeds import DEMO_CHANNEL_NIT, DEMO_SKU, seed_all
from app.infra.settings import get_settings
from app.main import app

TEST_DB_NAME = "cotiza_test"

# Lunes 5 de octubre de 2026, 10:00 en Bogotá (15:00 UTC): dentro del horario hábil.
T0 = datetime(2026, 10, 5, 15, 0, tzinfo=timezone.utc)


# --- Base de datos --------------------------------------------------------------------


@pytest.fixture(scope="session")
def test_db_url() -> str:
    base = make_url(get_settings().database_url)
    admin_engine = create_engine(base, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS {TEST_DB_NAME} WITH (FORCE)"))
        conn.execute(text(f"CREATE DATABASE {TEST_DB_NAME}"))
    admin_engine.dispose()
    return base.set(database=TEST_DB_NAME).render_as_string(hide_password=False)


@pytest.fixture(scope="session")
def alembic_config(test_db_url: str) -> Config:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", test_db_url)
    return config


@pytest.fixture(scope="session")
def engine(test_db_url: str, alembic_config: Config) -> Iterator[Engine]:
    command.upgrade(alembic_config, "head")
    engine = create_engine(test_db_url)
    yield engine
    engine.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    connection = engine.connect()
    transaction = connection.begin()
    # Con savepoints, un commit dentro del código probado no escapa de la transacción externa.
    session = Session(bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False)
    yield session
    session.close()
    transaction.rollback()
    connection.close()


# --- Dobles de los sistemas externos --------------------------------------------------


class FakeClock:
    def __init__(self, now: datetime) -> None:
        self.current = now

    def now(self) -> datetime:
        return self.current

    def advance(self, **delta) -> datetime:
        self.current += timedelta(**delta)
        return self.current


class FakeErp:
    """CatalogPort e InventoryPort en memoria."""

    def __init__(self) -> None:
        self.products: dict[str, ProductData] = {}
        self.stocks: dict[str, int] = {}

    def add(self, referencia, categoria, costo, lista, existencias=0, descripcion=None) -> None:
        self.products[referencia] = ProductData(
            referencia,
            descripcion or f"Producto {referencia}",
            categoria,
            Decimal(costo) if costo is not None else None,
            Decimal(lista) if lista is not None else None,
        )
        self.stocks[referencia] = existencias

    def set_list_price(self, referencia: str, lista: str) -> None:
        p = self.products[referencia]
        self.products[referencia] = ProductData(p.referencia, p.descripcion, p.categoria, p.costo, Decimal(lista))

    def get(self, referencia: str) -> ProductData | None:
        return self.products.get(referencia)

    def search(self, texto: str, limite: int = 20) -> list[ProductData]:
        texto = texto.lower()
        found = [p for p in self.products.values() if texto in p.referencia.lower() or texto in p.descripcion.lower()]
        return found[:limite]

    def stock(self, referencia: str) -> int:
        return self.stocks.get(referencia, 0)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(T0)


@pytest.fixture
def erp() -> FakeErp:
    erp = FakeErp()
    # La referencia del ejemplo del informe (6.6.3) y otras para los escenarios.
    erp.add(DEMO_SKU, "Portátiles", "620.00", "800.00", existencias=150, descripcion="Portátil empresarial (demo)")
    erp.add("PER-0001", "Periféricos", "50.00", "62.50", existencias=5, descripcion="Monitor 24 pulgadas")
    erp.add("RED-0001", "Redes", "100.00", "125.00", existencias=500, descripcion="Switch 24 puertos")
    erp.add("SRV-0001", "Servidores", "2000.00", "2500.00", existencias=0, descripcion="Servidor rack 1U")
    erp.add("SIN-COSTO", "Impresión", None, "90.00", existencias=10, descripcion="Impresora sin costo cargado")
    return erp


# --- Datos y cliente ------------------------------------------------------------------


@pytest.fixture
def db(session: Session) -> Session:
    """Sesión con los datos semilla: usuarios, reglas, 40 canales y la promoción de demo."""
    seed_all(session, [{"sku": DEMO_SKU, "costo": "620.00", "precio_lista": "800.00"}], T0)
    session.commit()
    return session


@pytest.fixture
def client(session: Session, erp: FakeErp, clock: FakeClock) -> Iterator[TestClient]:
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_catalog] = lambda: erp
    app.dependency_overrides[get_inventory] = lambda: erp
    app.dependency_overrides[get_clock] = lambda: clock
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def as_user(db: Session) -> Callable[[str], dict]:
    """Cabeceras de autenticación de un usuario semilla, por nombre de usuario."""

    def headers(usuario: str) -> dict:
        user = db.scalars(select(Usuario).where(Usuario.usuario == usuario)).one()
        return {"Authorization": f"Bearer {create_access_token(user.id, user.rol)}"}

    return headers


@pytest.fixture
def demo_channel(db: Session) -> Canal:
    """Canal de nivel Plata del ejemplo del informe."""
    return db.scalars(select(Canal).where(Canal.nit == DEMO_CHANNEL_NIT)).one()
