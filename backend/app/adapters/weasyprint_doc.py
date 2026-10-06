"""Adaptador MVP de DocumentPort: plantilla HTML única convertida a PDF con WeasyPrint.

En la arquitectura objetivo lo sustituye un worker asíncrono (sección 7.2.1); la plantilla
puede conservarse.
"""

from datetime import datetime
from decimal import Decimal
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

MESES = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)  # fmt: skip


def format_money(value: Decimal) -> str:
    """14592.5 -> '14.592,50' (separadores usados en Colombia)."""
    return f"{value:,.2f}".replace(",", "§").replace(".", ",").replace("§", ".")


def format_datetime(value: datetime) -> str:
    """Fecha larga en español con hora de 24 h, en la zona horaria que ya trae el valor."""
    return f"{value.day} de {MESES[value.month - 1]} de {value.year}, {value:%H:%M}"


class WeasyPrintDocumentAdapter:
    def __init__(self) -> None:
        self.env = Environment(
            loader=FileSystemLoader(Path(__file__).parent / "templates"),
            autoescape=select_autoescape(["html"]),
        )
        self.env.filters["dinero"] = format_money
        self.env.filters["fecha_hora"] = format_datetime

    def render_html(self, datos: dict) -> str:
        return self.env.get_template("cotizacion.html").render(**datos)

    def render_quote(self, datos: dict) -> bytes:
        # Se importa aquí: WeasyPrint carga bibliotecas del sistema que solo hacen falta al generar.
        from weasyprint import HTML

        return HTML(string=self.render_html(datos)).write_pdf()
