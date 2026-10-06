from fastapi import APIRouter, Depends, Query

from app.api.deps import CurrentUser, get_catalog, get_current_user, get_customers
from app.api.schemas import ChannelOut, ProductOut
from app.domain.pricing_engine import ProductData
from app.ports.external import CatalogPort, CustomerPort

router = APIRouter(prefix="/api", tags=["Catálogo y canales"])


def _product_out(product: ProductData) -> ProductOut:
    return ProductOut(
        referencia=product.referencia,
        descripcion=product.descripcion,
        categoria=product.categoria,
        costo=product.costo,
        precio_lista=product.precio_lista,
        # RN-01: se avisa desde el buscador, antes de agregar la línea.
        cotizable=product.costo is not None and product.precio_lista is not None,
    )


@router.get("/catalogo", response_model=list[ProductOut])
def search_catalog(
    q: str = Query("", max_length=80, description="Código o descripción"),
    limite: int = Query(15, ge=1, le=1000),
    catalog: CatalogPort = Depends(get_catalog),
    _: CurrentUser = Depends(get_current_user),
) -> list[ProductOut]:
    """Buscador con autocompletado por código o descripción (M1). Sin texto y con un límite
    amplio devuelve el catálogo completo, que la pantalla de cotización agrupa por categoría."""
    return [_product_out(p) for p in catalog.search(q, limite)]


@router.get("/canales", response_model=list[ChannelOut])
def list_channels(
    customers: CustomerPort = Depends(get_customers), _: CurrentUser = Depends(get_current_user)
) -> list:
    return list(customers.list())
