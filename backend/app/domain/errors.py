class DomainError(Exception):
    """Error de negocio: una regla del dominio impide la operación."""


class InvalidTransitionError(DomainError):
    """La cotización no puede pasar por esa transición desde su estado actual."""


class InvalidLineError(DomainError):
    """Los datos de entrada de una línea no son válidos (cantidad, descuento adicional)."""


class PricingConfigError(DomainError):
    """Falta un parámetro de precios: nivel de canal o margen mínimo de la categoría."""


class ExpiredPromotionError(DomainError):
    """Una promoción aplicada en el cálculo ya terminó: hay que recalcular antes de emitir."""
