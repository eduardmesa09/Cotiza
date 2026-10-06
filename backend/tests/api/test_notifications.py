"""Notificaciones dentro de la aplicación: cada usuario ve y marca solo las suyas."""

from app.infra.seeds import DEMO_SKU
from tests.helpers import approval_queue, create_pending, resolve

BAJO_MARGEN = [(DEMO_SKU, 20, "0.09")]


def test_sin_notificaciones(client, as_user):
    assert client.get("/api/notificaciones", headers=as_user("ejecutivo")).json() == {"no_leidas": 0, "items": []}


def test_cada_usuario_ve_solo_sus_notificaciones(client, as_user, clock, demo_channel):
    ejecutivo, aprobador = as_user("ejecutivo"), as_user("aprobador")
    quote = create_pending(client, ejecutivo, clock, demo_channel.id, BAJO_MARGEN)

    del_aprobador = client.get("/api/notificaciones", headers=aprobador).json()
    assert del_aprobador["no_leidas"] == 1
    assert del_aprobador["items"][0]["cotizacion_id"] == quote["id"]
    assert quote["numero"] in del_aprobador["items"][0]["mensaje"]
    # Ni el ejecutivo ni el gerente reciben la de la solicitud.
    assert client.get("/api/notificaciones", headers=ejecutivo).json()["no_leidas"] == 0
    assert client.get("/api/notificaciones", headers=as_user("gerente")).json()["no_leidas"] == 0


def test_marcar_como_leida(client, as_user, clock, demo_channel):
    ejecutivo, aprobador = as_user("ejecutivo"), as_user("aprobador")
    create_pending(client, ejecutivo, clock, demo_channel.id, BAJO_MARGEN)
    notificacion = client.get("/api/notificaciones", headers=aprobador).json()["items"][0]

    # Otro usuario no puede marcar una notificación ajena.
    assert client.post(f"/api/notificaciones/{notificacion['id']}/leer", headers=ejecutivo).status_code == 404
    assert client.post(f"/api/notificaciones/{notificacion['id']}/leer", headers=aprobador).status_code == 204

    despues = client.get("/api/notificaciones", headers=aprobador).json()
    assert despues["no_leidas"] == 0 and despues["items"][0]["leida"] is True
    assert client.post("/api/notificaciones/999999/leer", headers=aprobador).status_code == 404


def test_marcar_todas_como_leidas_y_orden_mas_reciente_primero(client, as_user, clock, demo_channel):
    ejecutivo, aprobador = as_user("ejecutivo"), as_user("aprobador")
    create_pending(client, ejecutivo, clock, demo_channel.id, BAJO_MARGEN)
    clock.advance(minutes=5)
    segunda = create_pending(client, ejecutivo, clock, demo_channel.id, [(DEMO_SKU, 30, "0.09")])

    bandeja = client.get("/api/notificaciones", headers=aprobador).json()
    assert bandeja["no_leidas"] == 2
    assert bandeja["items"][0]["cotizacion_id"] == segunda["id"]

    assert client.post("/api/notificaciones/leer-todas", headers=aprobador).status_code == 204
    assert client.get("/api/notificaciones", headers=aprobador).json()["no_leidas"] == 0


def test_el_ejecutivo_recibe_la_resolucion(client, as_user, clock, demo_channel):
    ejecutivo, aprobador = as_user("ejecutivo"), as_user("aprobador")
    create_pending(client, ejecutivo, clock, demo_channel.id, BAJO_MARGEN)
    resolve(client, aprobador, approval_queue(client, aprobador)[0]["id"], "aprobar", "Adelante")
    bandeja = client.get("/api/notificaciones", headers=ejecutivo).json()
    assert bandeja["no_leidas"] == 1
    assert "ya puede confirmar la emisión" in bandeja["items"][0]["mensaje"]


def test_las_notificaciones_exigen_sesion(client):
    assert client.get("/api/notificaciones").status_code == 401
