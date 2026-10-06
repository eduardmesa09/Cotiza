"""Contenido del documento de cotización que recibe el canal (M5).

Aquí se decide qué datos van al documento; cómo se dibuja es asunto del adaptador. El costo
y el margen son información interna y nunca se incluyen.
"""

from zoneinfo import ZoneInfo

from app.domain.parties import Channel
from app.domain.quote import Quote

CONDICIONES_COMERCIALES = (
    "Precios expresados en dólares estadounidenses (USD), antes de impuestos.",
    "Los precios aplican para las cantidades cotizadas; un cambio de cantidad requiere una nueva cotización.",
    "Las líneas marcadas como «Bajo pedido» están sujetas a tiempo de entrega por confirmar.",
    "La disponibilidad se confirma al recibir la orden de compra.",
    "Vencida la vigencia, los precios y condiciones dejan de ser válidos y debe solicitarse una nueva cotización.",
)


def build_quote_document(quote: Quote, channel: Channel, ejecutivo_nombre: str, tz: ZoneInfo) -> dict:
    return {
        "numero": quote.numero,
        "version": quote.version,
        "emitida_en": quote.emitida_en.astimezone(tz),
        "vigente_hasta": quote.vigente_hasta.astimezone(tz),
        "moneda": "USD",
        "canal": {
            "nombre": channel.nombre,
            "nit": channel.nit,
            "ciudad": channel.ciudad,
            "contacto_nombre": channel.contacto_nombre,
            "contacto_email": channel.contacto_email,
        },
        "ejecutivo": ejecutivo_nombre,
        "lineas": [
            {
                "referencia": linea.referencia,
                "descripcion": linea.resultado.descripcion,
                "cantidad": linea.cantidad,
                "precio_unitario": linea.resultado.precio_unitario,
                "total": linea.resultado.total,
                "bajo_pedido": linea.bajo_pedido,
            }
            for linea in quote.lineas
        ],
        "total": quote.total,
        "condiciones": list(CONDICIONES_COMERCIALES),
    }
