"""Adaptador MVP de CatalogPort e InventoryPort: consume el ERP simulado por HTTP.

En la arquitectura objetivo se sustituye por el adaptador REST del ERP real (sección 7.3)
sin tocar el núcleo.
"""

from collections.abc import Sequence
from decimal import Decimal

import httpx

from app.domain.errors import ExternalServiceError
from app.domain.pricing_engine import ProductData


def _to_product(data: dict) -> ProductData:
    return ProductData(
        referencia=data["sku"],
        descripcion=data["descripcion"],
        categoria=data["categoria"],
        costo=Decimal(data["costo"]) if data["costo"] is not None else None,
        precio_lista=Decimal(data["precio_lista"]) if data["precio_lista"] is not None else None,
    )


class ErpHttpAdapter:
    def __init__(self, client: httpx.Client) -> None:
        self.client = client

    def _get(self, path: str, **params) -> httpx.Response:
        try:
            response = self.client.get(path, params=params or None)
        except httpx.HTTPError as exc:
            raise ExternalServiceError("El ERP no está disponible; intente de nuevo en unos segundos") from exc
        if response.status_code >= 500:
            raise ExternalServiceError(f"El ERP respondió con error {response.status_code}")
        return response

    # CatalogPort

    def get(self, referencia: str) -> ProductData | None:
        response = self._get(f"/products/{referencia}")
        if response.status_code == 404:
            return None
        return _to_product(response.json())

    def search(self, texto: str, limite: int = 20) -> Sequence[ProductData]:
        return [_to_product(item) for item in self._get("/products", q=texto, limit=limite).json()]

    # InventoryPort

    def stock(self, referencia: str) -> int:
        response = self._get(f"/inventory/{referencia}")
        if response.status_code == 404:
            return 0
        return int(response.json()["existencias"])
