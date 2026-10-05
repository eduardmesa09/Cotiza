"""Generación del catálogo simulado del ERP.

Los datos son ficticios (restricción R4 del proyecto) y deterministas: la misma semilla
produce siempre el mismo catálogo, de modo que las demos y las pruebas son repetibles.
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from itertools import count

from faker import Faker

DEFAULT_SEED = 2026
TOTAL_PRODUCTS = 500

# Referencia fija del ejemplo de la sección 6.6.3 del informe (costo 620, lista 800).
DEMO_SKU = "POR-DEMO01"


@dataclass
class Product:
    sku: str
    descripcion: str
    categoria: str
    marca: str
    costo: Decimal | None
    precio_lista: Decimal | None
    existencias: int


@dataclass(frozen=True)
class Family:
    """Una familia de productos: plantilla de descripción, opciones y rango de costo en USD."""

    plantilla: str
    marcas: tuple[str, ...]
    opciones: dict[str, tuple[str, ...]]
    costo: tuple[float, float]


@dataclass(frozen=True)
class CategorySpec:
    nombre: str
    prefijo: str
    cantidad: int
    # Margen bruto sobre el precio de lista, (lista - costo) / lista, siempre entre 10 % y 25 %.
    margen_bruto: tuple[float, float]
    max_existencias: int
    familias: tuple[Family, ...]


CATEGORIES: tuple[CategorySpec, ...] = (
    CategorySpec(
        "Portátiles", "POR", 129, (0.14, 0.245), 400,
        (
            Family(
                'Portátil {marca} {modelo} {cpu} {ram} {disco} {pantalla}',
                ("Lenovo", "HP", "Dell", "ASUS", "Acer"),
                {
                    "modelo": ("ProLine 14", "ProLine 15", "WorkBook 440", "WorkBook 850", "Travel X1", "Essential 3"),
                    "cpu": ("Core i3", "Core i5", "Core i7", "Ryzen 5", "Ryzen 7"),
                    "ram": ("8GB", "16GB", "32GB"),
                    "disco": ("256GB SSD", "512GB SSD", "1TB SSD"),
                    "pantalla": ('14"', '15.6"'),
                },
                (380, 1450),
            ),
            Family(
                'Estación de trabajo móvil {marca} {modelo} {cpu} {ram} {disco} {gpu}',
                ("Lenovo", "HP", "Dell"),
                {
                    "modelo": ("Studio P16", "Precision M5", "ZWork 16"),
                    "cpu": ("Core i7", "Core i9", "Ryzen 9"),
                    "ram": ("32GB", "64GB"),
                    "disco": ("1TB SSD", "2TB SSD"),
                    "gpu": ("RTX A1000", "RTX A2000", "RTX 4060"),
                },
                (1600, 3200),
            ),
        ),
    ),
    CategorySpec(
        "Periféricos", "PER", 150, (0.18, 0.245), 800,
        (
            Family(
                'Monitor {marca} {tam} {res} {panel}',
                ("LG", "Samsung", "Dell", "HP", "AOC"),
                {"tam": ('22"', '24"', '27"', '32"'), "res": ("FHD", "QHD", "4K"), "panel": ("IPS", "VA")},
                (85, 420),
            ),
            Family(
                'Teclado {marca} {tipo} {conexion} {idioma}',
                ("Logitech", "Genius", "HP", "Microsoft"),
                {"tipo": ("estándar", "ergonómico", "mecánico", "compacto"), "conexion": ("USB", "inalámbrico", "Bluetooth"), "idioma": ("español", "inglés")},
                (9, 95),
            ),
            Family(
                'Mouse {marca} {tipo} {conexion} {color}',
                ("Logitech", "Genius", "HP", "Microsoft"),
                {"tipo": ("óptico", "ergonómico", "vertical", "de precisión"), "conexion": ("USB", "inalámbrico", "Bluetooth"), "color": ("negro", "gris", "blanco")},
                (5, 70),
            ),
            Family(
                'Diadema {marca} {tipo} {conexion} con micrófono',
                ("Jabra", "Logitech", "Poly", "HP"),
                {"tipo": ("mono", "estéreo", "con cancelación de ruido"), "conexion": ("USB-A", "USB-C", "Bluetooth")},
                (22, 210),
            ),
            Family(
                'Cámara web {marca} {res} {extra}',
                ("Logitech", "Poly", "Genius"),
                {"res": ("HD 720p", "FHD 1080p", "4K"), "extra": ("con micrófono", "con tapa de privacidad", "gran angular")},
                (18, 160),
            ),
            Family(
                'Base de conexión {marca} {tipo} {potencia}',
                ("Dell", "HP", "Lenovo", "Targus"),
                {"tipo": ("USB-C", "Thunderbolt 4", "universal USB 3.0"), "potencia": ("65W", "90W", "130W")},
                (70, 260),
            ),
            Family(
                'Disco externo {marca} {cap} {tipo}',
                ("Seagate", "WD", "Kingston", "ADATA"),
                {"cap": ("1TB", "2TB", "4TB"), "tipo": ("HDD USB 3.0", "SSD USB-C", "SSD resistente")},
                (42, 240),
            ),
        ),
    ),
    CategorySpec(
        "Servidores", "SRV", 60, (0.16, 0.245), 40,
        (
            Family(
                'Servidor torre {marca} {modelo} {cpu} {ram} {disco}',
                ("Dell", "HPE", "Lenovo"),
                {
                    "modelo": ("Tower T150", "Tower T350", "ML30 Gen11", "ST50 V3"),
                    "cpu": ("Xeon E-2414", "Xeon E-2434", "Xeon E-2468"),
                    "ram": ("16GB", "32GB", "64GB"),
                    "disco": ("2x1TB SATA", "2x2TB SATA", "2x480GB SSD"),
                },
                (900, 2600),
            ),
            Family(
                'Servidor rack {marca} {modelo} {cpu} {ram} {disco}',
                ("Dell", "HPE", "Lenovo"),
                {
                    "modelo": ("Rack R450 1U", "Rack R650 1U", "DL360 Gen11 1U", "DL380 Gen11 2U", "SR630 V3 1U"),
                    "cpu": ("Xeon Silver 4410Y", "Xeon Silver 4416+", "Xeon Gold 5418Y"),
                    "ram": ("32GB", "64GB", "128GB"),
                    "disco": ("2x480GB SSD", "4x960GB SSD", "4x1.2TB SAS"),
                },
                (2400, 9800),
            ),
        ),
    ),
    CategorySpec(
        "Redes", "RED", 90, (0.17, 0.245), 500,
        (
            Family(
                'Switch {marca} {puertos} puertos {vel} {tipo}',
                ("Cisco", "TP-Link", "Aruba", "Ubiquiti", "MikroTik"),
                {"puertos": ("8", "16", "24", "48"), "vel": ("Gigabit", "Gigabit PoE+", "Multigigabit"), "tipo": ("no administrable", "administrable L2", "administrable L3")},
                (28, 2900),
            ),
            Family(
                'Punto de acceso {marca} {wifi} {uso} {extra}',
                ("Ubiquiti", "Aruba", "TP-Link", "Cisco"),
                {"wifi": ("Wi-Fi 6", "Wi-Fi 6E", "Wi-Fi 7"), "uso": ("interior", "exterior"), "extra": ("PoE", "malla", "alta densidad")},
                (65, 640),
            ),
            Family(
                'Router {marca} {tipo} {wan} {extra}',
                ("MikroTik", "TP-Link", "Cisco"),
                {"tipo": ("empresarial", "para sucursal", "de borde"), "wan": ("doble WAN", "WAN Gigabit", "WAN SFP+"), "extra": ("con VPN", "con balanceo", "con Wi-Fi 6")},
                (55, 1200),
            ),
            Family(
                'Firewall {marca} {modelo} {licencia}',
                ("Fortinet", "Sophos", "Cisco"),
                {"modelo": ("serie 40", "serie 60", "serie 80", "serie 100"), "licencia": ("sin licencia", "con protección 1 año", "con protección 3 años")},
                (380, 4200),
            ),
        ),
    ),
    CategorySpec(
        "Impresión", "IMP", 70, (0.15, 0.245), 300,
        (
            Family(
                'Impresora láser {marca} {tipo} {vel} {conexion}',
                ("HP", "Brother", "Lexmark", "Canon"),
                {"tipo": ("monocromática", "a color"), "vel": ("30 ppm", "40 ppm", "50 ppm"), "conexion": ("USB", "red", "red y Wi-Fi")},
                (110, 780),
            ),
            Family(
                'Multifuncional {marca} {tec} {formato} {conexion}',
                ("HP", "Epson", "Brother", "Canon"),
                {"tec": ("láser monocromática", "láser a color", "de tinta continua"), "formato": ("carta", "oficio", "A3"), "conexion": ("red", "red y Wi-Fi", "red y dúplex")},
                (160, 1900),
            ),
            Family(
                'Tóner {marca} {color} {rend}',
                ("HP", "Brother", "Lexmark", "Canon"),
                {"color": ("negro", "cian", "magenta", "amarillo"), "rend": ("rendimiento estándar", "alto rendimiento", "extra alto rendimiento")},
                (35, 240),
            ),
        ),
    ),
)

CATEGORY_NAMES: tuple[str, ...] = tuple(c.nombre for c in CATEGORIES)

# Posiciones (dentro del catálogo generado) de las referencias con datos incompletos (RN-01).
_WITHOUT_COST = (17, 64, 133, 188, 251, 307, 362, 440)
_WITHOUT_LIST_PRICE = (95, 410)


def _money(value: float) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _stock(fake: Faker, max_stock: int) -> int:
    """Existencias variadas: una parte en cero, otra baja y el resto con inventario normal."""
    r = fake.random.random()
    if r < 0.12:
        return 0
    if r < 0.30:
        return fake.random.randint(1, 9)
    return fake.random.randint(10, max_stock)


def generate_catalog(seed: int = DEFAULT_SEED) -> list[Product]:
    fake = Faker("es_CO")
    fake.seed_instance(seed)

    products = [
        Product(
            sku=DEMO_SKU,
            descripcion='Portátil empresarial Lenovo ProLine 14 Core i5 16GB 512GB SSD 14" (demo)',
            categoria="Portátiles",
            marca="Lenovo",
            costo=Decimal("620.00"),
            precio_lista=Decimal("800.00"),
            existencias=150,
        )
    ]
    seen = {products[0].descripcion}

    for cat in CATEGORIES:
        numbers = count(1)
        generated = 0
        while generated < cat.cantidad:
            fam = fake.random_element(cat.familias)
            marca = fake.random_element(fam.marcas)
            options = {k: fake.random_element(v) for k, v in fam.opciones.items()}
            descripcion = fam.plantilla.format(marca=marca, **options)
            if descripcion in seen:
                continue
            seen.add(descripcion)

            costo = _money(fake.random.uniform(*fam.costo))
            margen = Decimal(str(round(fake.random.uniform(*cat.margen_bruto), 4)))
            precio_lista = (costo / (1 - margen)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            products.append(
                Product(
                    sku=f"{cat.prefijo}-{next(numbers):05d}",
                    descripcion=descripcion,
                    categoria=cat.nombre,
                    marca=marca,
                    costo=costo,
                    precio_lista=precio_lista,
                    existencias=_stock(fake, cat.max_existencias),
                )
            )
            generated += 1

    for i in _WITHOUT_COST:
        products[i].costo = None
    for i in _WITHOUT_LIST_PRICE:
        products[i].precio_lista = None

    assert len(products) == TOTAL_PRODUCTS
    return products
