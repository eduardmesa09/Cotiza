"""Infraestructura común de pruebas.

Las pruebas que tocan la base de datos usan una base aparte (cotiza_test) en el mismo
servidor PostgreSQL. El esquema se crea con las migraciones reales y cada prueba corre
dentro de una transacción que se revierte al terminar.
"""

from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.infra.db import get_session
from app.infra.settings import get_settings
from app.main import app

TEST_DB_NAME = "cotiza_test"


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


@pytest.fixture
def client(session: Session) -> Iterator[TestClient]:
    app.dependency_overrides[get_session] = lambda: session
    yield TestClient(app)
    app.dependency_overrides.clear()
