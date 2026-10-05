from collections import Counter
from decimal import Decimal

from app.catalog import CATEGORY_NAMES, DEMO_SKU, TOTAL_PRODUCTS, generate_catalog


def test_genera_500_referencias_con_codigo_y_descripcion_unicos():
    products = generate_catalog()
    assert len(products) == TOTAL_PRODUCTS == 500
    assert len({p.sku for p in products}) == 500
    assert len({p.descripcion for p in products}) == 500


def test_cubre_las_cinco_categorias():
    por_categoria = Counter(p.categoria for p in generate_catalog())
    assert set(por_categoria) == set(CATEGORY_NAMES)
    assert len(CATEGORY_NAMES) == 5
    assert all(n >= 50 for n in por_categoria.values())


def test_precio_de_lista_y_costo_son_coherentes():
    for p in generate_catalog():
        if p.costo is None or p.precio_lista is None:
            continue
        assert p.costo > 0
        assert p.precio_lista >= p.costo
        margen_bruto = (p.precio_lista - p.costo) / p.precio_lista
        assert Decimal("0.10") <= margen_bruto <= Decimal("0.25"), (p.sku, margen_bruto)


def test_incluye_referencias_con_datos_incompletos():
    products = generate_catalog()
    sin_costo = [p for p in products if p.costo is None]
    sin_lista = [p for p in products if p.precio_lista is None]
    assert len(sin_costo) == 8
    assert len(sin_lista) == 2
    assert not {p.sku for p in sin_costo} & {p.sku for p in sin_lista}


def test_existencias_variadas_con_ceros_y_bajas():
    stocks = [p.existencias for p in generate_catalog()]
    assert all(s >= 0 for s in stocks)
    assert sum(1 for s in stocks if s == 0) >= 20
    assert sum(1 for s in stocks if 0 < s < 10) >= 20
    assert sum(1 for s in stocks if s >= 100) >= 50


def test_referencia_de_demo_reproduce_el_ejemplo_del_informe():
    demo = next(p for p in generate_catalog() if p.sku == DEMO_SKU)
    assert demo.costo == Decimal("620.00")
    assert demo.precio_lista == Decimal("800.00")
    assert demo.categoria == "Portátiles"
    assert demo.existencias >= 100


def test_la_misma_semilla_produce_el_mismo_catalogo():
    assert generate_catalog(seed=7) == generate_catalog(seed=7)
    assert generate_catalog(seed=7) != generate_catalog(seed=8)
