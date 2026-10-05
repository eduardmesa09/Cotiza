"""Atajos para las pruebas que recorren la API."""

from datetime import timedelta


def quote_body(clock, canal_id: int, lineas: list[tuple], minutos_desde_recepcion: int = 30) -> dict:
    """Cuerpo de una cotización. Cada línea es (referencia, cantidad) o (referencia, cantidad, adicional)."""
    return {
        "canal_id": canal_id,
        "recibida_en": (clock.now() - timedelta(minutes=minutos_desde_recepcion)).isoformat(),
        "lineas": [
            {"referencia": l[0], "cantidad": l[1], "descuento_adicional": l[2] if len(l) > 2 else "0"} for l in lineas
        ],
    }


def create_quote(client, headers, clock, canal_id: int, lineas: list[tuple]) -> dict:
    response = client.post("/api/cotizaciones", json=quote_body(clock, canal_id, lineas), headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def calculate(client, headers, quote_id: int) -> dict:
    response = client.post(f"/api/cotizaciones/{quote_id}/calcular", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def issue(client, headers, quote_id: int) -> dict:
    response = client.post(f"/api/cotizaciones/{quote_id}/emitir", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def create_calculated(client, headers, clock, canal_id: int, lineas: list[tuple]) -> dict:
    return calculate(client, headers, create_quote(client, headers, clock, canal_id, lineas)["id"])


def event_types(client, headers, quote_id: int) -> list[str]:
    response = client.get(f"/api/cotizaciones/{quote_id}/eventos", headers=headers)
    assert response.status_code == 200, response.text
    return [e["tipo"] for e in response.json()]


def line(quote: dict, referencia: str) -> dict:
    return next(l for l in quote["lineas"] if l["referencia"] == referencia)
