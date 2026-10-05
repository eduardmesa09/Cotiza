from dataclasses import dataclass

from app.domain.business_time import BusinessCalendar


@dataclass(frozen=True)
class BusinessSettings:
    """Plazos y calendario de la operación. Vienen de la tabla de parámetros."""

    sla_aprobacion_minutos: int  # RN-09
    sla_respuesta_minutos: int  # compromiso de respuesta al canal (K4)
    seguimiento_minutos: int  # RN-12
    vigencia_minutos: int  # RN-11
    calendar: BusinessCalendar
