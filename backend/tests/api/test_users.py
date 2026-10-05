"""Gestión de usuarios: solo el administrador (Tabla 32)."""

import pytest

NUEVO = {
    "usuario": "ejecutivo3",
    "nombre": "Sara Peña",
    "email": "ejecutivo3@cotiza.example.com",
    "rol": "ejecutivo",
    "password": "Clave-Segura-1",
}


@pytest.mark.parametrize("rol", ["ejecutivo", "aprobador", "gerente", "pricing"])
def test_solo_el_administrador_gestiona_usuarios(client, as_user, rol):
    headers = as_user(rol)
    assert client.get("/api/usuarios", headers=headers).status_code == 403
    assert client.post("/api/usuarios", json=NUEVO, headers=headers).status_code == 403
    assert client.put("/api/usuarios/1", json={"activo": False}, headers=headers).status_code == 403


def test_listado_sin_exponer_contrasenas(client, as_user):
    usuarios = client.get("/api/usuarios", headers=as_user("admin")).json()
    assert sorted(u["rol"] for u in usuarios) == ["admin", "aprobador", "ejecutivo", "gerente", "pricing"]
    assert all("password" not in u and "password_hash" not in u for u in usuarios)


def test_crear_usuario_y_que_pueda_iniciar_sesion(client, as_user):
    creado = client.post("/api/usuarios", json=NUEVO, headers=as_user("admin"))
    assert creado.status_code == 201
    assert creado.json()["activo"] is True

    login = client.post("/api/auth/login", json={"usuario": "ejecutivo3", "password": "Clave-Segura-1"})
    assert login.status_code == 200
    assert login.json()["usuario"]["rol"] == "ejecutivo"


def test_usuario_duplicado(client, as_user):
    response = client.post("/api/usuarios", json={**NUEVO, "usuario": "ejecutivo"}, headers=as_user("admin"))
    assert response.status_code == 409


@pytest.mark.parametrize(
    "cambios",
    [{"rol": "superusuario"}, {"password": "corta"}, {"usuario": "Con Espacios"}, {"nombre": ""}],
)
def test_datos_invalidos_al_crear(client, as_user, cambios):
    assert client.post("/api/usuarios", json={**NUEVO, **cambios}, headers=as_user("admin")).status_code == 422


def test_cambiar_rol_nombre_y_contrasena(client, as_user):
    admin = as_user("admin")
    creado = client.post("/api/usuarios", json=NUEVO, headers=admin).json()

    response = client.put(
        f"/api/usuarios/{creado['id']}",
        json={"rol": "aprobador", "nombre": "Sara Peña Ruiz", "password": "Otra-Clave-22"},
        headers=admin,
    )
    assert response.status_code == 200
    assert response.json()["rol"] == "aprobador" and response.json()["nombre"] == "Sara Peña Ruiz"

    assert client.post("/api/auth/login", json={"usuario": "ejecutivo3", "password": "Clave-Segura-1"}).status_code == 401
    assert client.post("/api/auth/login", json={"usuario": "ejecutivo3", "password": "Otra-Clave-22"}).status_code == 200


def test_desactivar_un_usuario_le_corta_el_acceso(client, as_user):
    admin = as_user("admin")
    creado = client.post("/api/usuarios", json=NUEVO, headers=admin).json()
    assert client.put(f"/api/usuarios/{creado['id']}", json={"activo": False}, headers=admin).json()["activo"] is False
    login = client.post("/api/auth/login", json={"usuario": "ejecutivo3", "password": "Clave-Segura-1"})
    assert login.status_code == 401


def test_el_administrador_no_puede_dejarse_sin_acceso(client, as_user):
    admin = as_user("admin")
    yo = client.get("/api/auth/me", headers=admin).json()
    assert client.put(f"/api/usuarios/{yo['id']}", json={"activo": False}, headers=admin).status_code == 409
    assert client.put(f"/api/usuarios/{yo['id']}", json={"rol": "ejecutivo"}, headers=admin).status_code == 409
    assert client.put(f"/api/usuarios/{yo['id']}", json={"nombre": "Admin Principal"}, headers=admin).status_code == 200


def test_usuario_inexistente(client, as_user):
    assert client.put("/api/usuarios/999999", json={"activo": False}, headers=as_user("admin")).status_code == 404
