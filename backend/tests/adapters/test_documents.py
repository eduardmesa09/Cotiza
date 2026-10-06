"""Generación real del PDF con WeasyPrint y almacenamiento en disco."""

from datetime import datetime
from decimal import Decimal as D
from io import BytesIO
from zoneinfo import ZoneInfo

import pytest
from pypdf import PdfReader

from app.adapters.local_storage import LocalStorageAdapter
from app.adapters.weasyprint_doc import WeasyPrintDocumentAdapter, format_datetime, format_money
from app.application.documents import CONDICIONES_COMERCIALES
from app.domain.errors import NotFoundError

BOGOTA = ZoneInfo("America/Bogota")

DATOS = {
    "numero": "COT-000042",
    "version": 2,
    "emitida_en": datetime(2026, 10, 5, 10, 5, tzinfo=BOGOTA),
    "vigente_hasta": datetime(2026, 10, 12, 10, 5, tzinfo=BOGOTA),
    "moneda": "USD",
    "canal": {
        "nombre": "Soluciones Andinas TI S.A.S.",
        "nit": "900123456-7",
        "ciudad": "Bogotá",
        "contacto_nombre": "Mariana Suárez",
        "contacto_email": "compras@canal01.example.com",
    },
    "ejecutivo": "Camila Torres",
    "lineas": [
        {
            "referencia": "POR-DEMO01",
            "descripcion": "Portátil empresarial 14 pulgadas",
            "cantidad": 20,
            "precio_unitario": D("729.60"),
            "total": D("14592.00"),
            "bajo_pedido": False,
        },
        {
            "referencia": "SRV-00001",
            "descripcion": "Servidor rack 1U",
            "cantidad": 2,
            "precio_unitario": D("1785.58"),
            "total": D("3571.16"),
            "bajo_pedido": True,
        },
    ],
    "total": D("18163.16"),
    "condiciones": list(CONDICIONES_COMERCIALES),
}


@pytest.fixture(scope="module")
def pdf_text() -> str:
    content = WeasyPrintDocumentAdapter().render_quote(DATOS)
    assert content.startswith(b"%PDF")
    reader = PdfReader(BytesIO(content))
    assert len(reader.pages) == 1
    # Se compara sin espacios: el extractor a veces parte palabras por el interletrado de la fuente.
    return "".join("".join(page.extract_text().split()) for page in reader.pages)


def compacto(texto: str) -> str:
    return "".join(texto.split())


def test_el_pdf_identifica_la_cotizacion_y_al_canal(pdf_text):
    for esperado in ("COT-000042", "v2", "Soluciones Andinas TI S.A.S.", "900123456-7", "Camila Torres"):
        assert compacto(esperado) in pdf_text


def test_el_pdf_contiene_las_lineas_con_precio_y_el_total(pdf_text):
    for esperado in ("POR-DEMO01", "Portátil empresarial 14 pulgadas", "729,60", "14.592,00", "SRV-00001", "1.785,58"):
        assert compacto(esperado) in pdf_text
    assert "18.163,16" in pdf_text


def test_el_pdf_muestra_la_vigencia_y_las_condiciones_comerciales(pdf_text):
    assert compacto("Fecha de emisión: 5 de octubre de 2026, 10:05") in pdf_text
    assert compacto("Válida hasta: 12 de octubre de 2026, 10:05") in pdf_text
    assert compacto("Condiciones comerciales").upper() in pdf_text.upper()
    assert compacto("antes de impuestos") in pdf_text


def test_el_pdf_distingue_disponible_y_bajo_pedido(pdf_text):
    assert "Disponible" in pdf_text and compacto("Bajo pedido") in pdf_text


def test_el_pdf_no_revela_costo_ni_margen(pdf_text):
    assert "costo" not in pdf_text.lower() and "margen" not in pdf_text.lower()


def test_el_html_escapa_el_contenido():
    datos = {**DATOS, "canal": {**DATOS["canal"], "nombre": "<script>alert(1)</script>"}}
    html = WeasyPrintDocumentAdapter().render_html(datos)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_formato_de_dinero_y_fecha():
    assert format_money(D("14592.5")) == "14.592,50"
    assert format_money(D("0.5")) == "0,50"
    assert format_money(D("1234567.891")) == "1.234.567,89"
    assert format_datetime(datetime(2026, 3, 1, 8, 5, tzinfo=BOGOTA)) == "1 de marzo de 2026, 08:05"


# --- Almacenamiento local -------------------------------------------------------------


def test_guardar_y_leer_un_archivo(tmp_path):
    storage = LocalStorageAdapter(tmp_path / "pdfs")
    ruta = storage.save("COT-000042-v2.pdf", b"%PDF-contenido")
    assert ruta == "COT-000042-v2.pdf"
    assert (tmp_path / "pdfs" / ruta).read_bytes() == b"%PDF-contenido"
    assert storage.read(ruta) == b"%PDF-contenido"


def test_guardar_dos_veces_sobrescribe(tmp_path):
    storage = LocalStorageAdapter(tmp_path)
    storage.save("a.pdf", b"uno")
    storage.save("a.pdf", b"dos")
    assert storage.read("a.pdf") == b"dos"


def test_leer_un_archivo_inexistente(tmp_path):
    with pytest.raises(NotFoundError):
        LocalStorageAdapter(tmp_path).read("no-existe.pdf")


@pytest.mark.parametrize("ruta", ["../secreto.txt", "../../etc/passwd", "/etc/passwd"])
def test_no_se_sale_de_la_carpeta_de_almacenamiento(tmp_path, ruta):
    (tmp_path / "secreto.txt").write_text("privado")
    storage = LocalStorageAdapter(tmp_path / "pdfs")
    with pytest.raises(NotFoundError):
        storage.read(ruta)
    with pytest.raises(NotFoundError):
        storage.save(ruta, b"x")
