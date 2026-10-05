"""Adaptador HTTP del ERP: traduce las respuestas del servicio a los tipos del dominio."""

from decimal import Decimal

import httpx
import pytest

from app.adapters.erp_http import ErpHttpAdapter
from app.domain.errors import ExternalServiceError

PRODUCT = {
    "sku": "POR-DEMO01",
    "descripcion": "Portátil (demo)",
    "categoria": "Portátiles",
    "marca": "Lenovo",
    "costo": "620.00",
    "precio_lista": "800.00",
}


def adapter(handler) -> ErpHttpAdapter:
    return ErpHttpAdapter(httpx.Client(base_url="http://erp", transport=httpx.MockTransport(handler)))


def test_get_convierte_a_producto_con_decimales():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/products/POR-DEMO01"
        return httpx.Response(200, json=PRODUCT)

    product = adapter(handler).get("POR-DEMO01")
    assert product.referencia == "POR-DEMO01"
    assert product.categoria == "Portátiles"
    assert product.costo == Decimal("620.00") and product.precio_lista == Decimal("800.00")


def test_get_conserva_los_datos_faltantes_como_nulos():
    product = adapter(lambda r: httpx.Response(200, json={**PRODUCT, "costo": None})).get("X")
    assert product.costo is None and product.precio_lista == Decimal("800.00")


def test_get_de_referencia_inexistente_devuelve_none():
    assert adapter(lambda r: httpx.Response(404, json={"detail": "no existe"})).get("NO-EXISTE") is None


def test_search_envia_texto_y_limite():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/products"
        assert request.url.params["q"] == "portatil lenovo"
        assert request.url.params["limit"] == "7"
        return httpx.Response(200, json=[PRODUCT, {**PRODUCT, "sku": "POR-00002"}])

    result = adapter(handler).search("portatil lenovo", 7)
    assert [p.referencia for p in result] == ["POR-DEMO01", "POR-00002"]


def test_stock():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/inventory/POR-DEMO01"
        return httpx.Response(200, json={"sku": "POR-DEMO01", "existencias": 150})

    assert adapter(handler).stock("POR-DEMO01") == 150


def test_stock_de_referencia_inexistente_es_cero():
    assert adapter(lambda r: httpx.Response(404, json={})).stock("NO-EXISTE") == 0


def test_error_del_erp_se_traduce_a_error_de_dominio():
    with pytest.raises(ExternalServiceError):
        adapter(lambda r: httpx.Response(500)).get("X")


def test_erp_caido_se_traduce_a_error_de_dominio():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("sin conexión")

    with pytest.raises(ExternalServiceError, match="no está disponible"):
        adapter(handler).stock("X")
