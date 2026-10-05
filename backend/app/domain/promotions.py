"""Reglas de calidad de las promociones (Tabla 45): fechas coherentes y sin superposición."""

from datetime import date
from decimal import Decimal

from app.domain.errors import DomainError
from app.domain.pricing_engine import ONE, ZERO


class InvalidPromotionError(DomainError):
    """La promoción no cumple las reglas de calidad de datos."""


def overlaps(inicio_a: date, fin_a: date, inicio_b: date, fin_b: date) -> bool:
    """Dos vigencias (ambos extremos inclusive) comparten al menos un día."""
    return inicio_a <= fin_b and inicio_b <= fin_a


def validate_promotion(descuento: Decimal, fecha_inicio: date, fecha_fin: date) -> None:
    if not ZERO < descuento < ONE:
        raise InvalidPromotionError("El descuento de la promoción debe ser mayor que 0 % y menor que 100 %")
    if fecha_inicio > fecha_fin:
        raise InvalidPromotionError("La fecha de inicio de la promoción no puede ser posterior a la de fin")
