from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.infra.models import Usuario
from app.infra.security import create_access_token
from app.infra.seeds import DEFAULT_PASSWORD


def test_login_correcto_devuelve_token_y_datos_del_usuario(client, db):
    response = client.post("/api/auth/login", json={"usuario": "ejecutivo", "password": DEFAULT_PASSWORD})
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["usuario"]["rol"] == "ejecutivo"
    assert body["usuario"]["nombre"] == "Camila Torres"
    assert "password_hash" not in body["usuario"]

    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200
    assert me.json()["usuario"] == "ejecutivo"


def test_login_no_distingue_mayusculas_ni_espacios_en_el_usuario(client, db):
    response = client.post("/api/auth/login", json={"usuario": " Ejecutivo ", "password": DEFAULT_PASSWORD})
    assert response.status_code == 200


def test_login_con_contrasena_errada_o_usuario_inexistente_da_el_mismo_error(client, db):
    errada = client.post("/api/auth/login", json={"usuario": "ejecutivo", "password": "incorrecta"})
    inexistente = client.post("/api/auth/login", json={"usuario": "nadie", "password": DEFAULT_PASSWORD})
    assert errada.status_code == inexistente.status_code == 401
    assert errada.json() == inexistente.json()


def test_usuario_inactivo_no_inicia_sesion_y_su_token_deja_de_servir(client, db, as_user):
    headers = as_user("ejecutivo")
    assert client.get("/api/auth/me", headers=headers).status_code == 200

    user = db.scalars(select(Usuario).where(Usuario.usuario == "ejecutivo")).one()
    user.activo = False
    db.commit()

    assert client.get("/api/auth/me", headers=headers).status_code == 401
    login = client.post("/api/auth/login", json={"usuario": "ejecutivo", "password": DEFAULT_PASSWORD})
    assert login.status_code == 401


def test_sin_token_o_con_token_invalido_responde_401(client, db):
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer no-es-un-token"}).status_code == 401
    assert client.get("/api/cotizaciones").status_code == 401
    assert client.get("/api/catalogo").status_code == 401


def test_token_expirado_responde_401(client, db):
    user = db.scalars(select(Usuario).where(Usuario.usuario == "ejecutivo")).one()
    # Emitido hace dos días: ya expiró (duración de 8 horas).
    viejo = create_access_token(user.id, user.rol, datetime.now(timezone.utc) - timedelta(days=2))
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {viejo}"}).status_code == 401
