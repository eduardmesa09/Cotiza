"""Servicio ERP simulado: catálogo, costos, precios de lista y existencias por API REST.

Sustituye al ERP de Intcomex en el MVP (restricción R3). El estado vive en memoria: los
cambios de precio o existencias hechos por la API se pierden al reiniciar el contenedor.
"""

import unicodedata
from decimal import Decimal

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from app.catalog import CATEGORY_NAMES, DEFAULT_SEED, Product, generate_catalog


class ProductOut(BaseModel):
    sku: str
    descripcion: str
    categoria: str
    marca: str
    costo: Decimal | None
    precio_lista: Decimal | None


class InventoryOut(BaseModel):
    sku: str
    existencias: int


class PriceUpdate(BaseModel):
    precio_lista: Decimal = Field(gt=0, decimal_places=2)


class StockUpdate(BaseModel):
    existencias: int = Field(ge=0)


def _normalize(text: str) -> str:
    """Minúsculas y sin tildes, para que 'portatil' encuentre 'Portátil'."""
    decomposed = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn")


def create_app(seed: int = DEFAULT_SEED) -> FastAPI:
    app = FastAPI(title="ERP simulado — COTIZA+", version="1.0.0")

    products: dict[str, Product] = {p.sku: p for p in generate_catalog(seed)}
    search_index = {sku: _normalize(f"{p.sku} {p.descripcion}") for sku, p in products.items()}

    def get_or_404(sku: str) -> Product:
        product = products.get(sku.upper())
        if product is None:
            raise HTTPException(status_code=404, detail=f"Referencia {sku} no existe")
        return product

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "referencias": len(products)}

    @app.get("/categories")
    def categories() -> list[str]:
        return list(CATEGORY_NAMES)

    @app.get("/products", response_model=list[ProductOut])
    def search_products(
        q: str = Query("", description="Texto a buscar en el código o la descripción"),
        limit: int = Query(20, ge=1, le=1000),
    ) -> list[Product]:
        tokens = _normalize(q).split()
        matches = [p for sku, p in products.items() if all(t in search_index[sku] for t in tokens)]
        # Las coincidencias por inicio de código van primero: es lo que espera un autocompletado.
        prefix = _normalize(q.strip())
        matches.sort(key=lambda p: (not p.sku.lower().startswith(prefix), p.sku))
        return matches[:limit]

    @app.get("/products/{sku}", response_model=ProductOut)
    def get_product(sku: str) -> Product:
        return get_or_404(sku)

    @app.patch("/products/{sku}/price", response_model=ProductOut)
    def update_price(sku: str, body: PriceUpdate) -> Product:
        """Cambia el precio de lista. Permite demostrar el congelamiento de precios (RN-13)."""
        product = get_or_404(sku)
        product.precio_lista = body.precio_lista
        return product

    @app.get("/inventory/{sku}", response_model=InventoryOut)
    def get_inventory(sku: str) -> Product:
        return get_or_404(sku)

    @app.patch("/inventory/{sku}", response_model=InventoryOut)
    def update_inventory(sku: str, body: StockUpdate) -> Product:
        """Ajusta las existencias. Permite demostrar la alerta de bajo pedido (RN-10)."""
        product = get_or_404(sku)
        product.existencias = body.existencias
        return product

    return app


app = create_app()
