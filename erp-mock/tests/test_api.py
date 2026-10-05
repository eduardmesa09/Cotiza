import pytest
from fastapi.testclient import TestClient

from app.catalog import DEMO_SKU
from app.main import create_app


@pytest.fixture
def client() -> TestClient:
    # Una aplicación nueva por prueba: los cambios de precio y existencias no se filtran.
    return TestClient(create_app())


def test_health(client):
    assert client.get("/health").json() == {"status": "ok", "referencias": 500}


def test_categorias(client):
    assert client.get("/categories").json() == ["Portátiles", "Periféricos", "Servidores", "Redes", "Impresión"]


def test_busqueda_por_codigo_pone_primero_la_coincidencia_por_prefijo(client):
    results = client.get("/products", params={"q": "srv-0000"}).json()
    assert results
    assert all(r["sku"].startswith("SRV-0000") for r in results)


def test_busqueda_por_descripcion_ignora_tildes_y_mayusculas(client):
    results = client.get("/products", params={"q": "PORTATIL lenovo", "limit": 50}).json()
    assert results
    assert all("Portátil" in r["descripcion"] and "Lenovo" in r["descripcion"] for r in results)


def test_busqueda_respeta_el_limite_y_sin_texto_lista_todo(client):
    assert len(client.get("/products", params={"limit": 5}).json()) == 5
    assert len(client.get("/products", params={"limit": 1000}).json()) == 500


def test_busqueda_sin_coincidencias(client):
    assert client.get("/products", params={"q": "zzzzzz"}).json() == []


def test_detalle_de_referencia(client):
    body = client.get(f"/products/{DEMO_SKU}").json()
    assert body["costo"] == "620.00"
    assert body["precio_lista"] == "800.00"
    assert body["categoria"] == "Portátiles"
    assert "existencias" not in body


def test_detalle_acepta_codigo_en_minusculas(client):
    assert client.get(f"/products/{DEMO_SKU.lower()}").status_code == 200


def test_referencia_inexistente_devuelve_404(client):
    assert client.get("/products/NO-EXISTE").status_code == 404
    assert client.get("/inventory/NO-EXISTE").status_code == 404


def test_referencias_sin_costo_se_exponen_con_costo_nulo(client):
    products = client.get("/products", params={"limit": 1000}).json()
    assert sum(1 for p in products if p["costo"] is None) == 8
    assert sum(1 for p in products if p["precio_lista"] is None) == 2


def test_existencias(client):
    assert client.get(f"/inventory/{DEMO_SKU}").json() == {"sku": DEMO_SKU, "existencias": 150}


def test_cambio_de_precio_de_lista(client):
    r = client.patch(f"/products/{DEMO_SKU}/price", json={"precio_lista": "850.00"})
    assert r.status_code == 200
    assert client.get(f"/products/{DEMO_SKU}").json()["precio_lista"] == "850.00"


def test_cambio_de_precio_rechaza_valores_no_positivos(client):
    assert client.patch(f"/products/{DEMO_SKU}/price", json={"precio_lista": "0"}).status_code == 422


def test_ajuste_de_existencias(client):
    r = client.patch(f"/inventory/{DEMO_SKU}", json={"existencias": 3})
    assert r.status_code == 200
    assert client.get(f"/inventory/{DEMO_SKU}").json()["existencias"] == 3
    assert client.patch(f"/inventory/{DEMO_SKU}", json={"existencias": -1}).status_code == 422
