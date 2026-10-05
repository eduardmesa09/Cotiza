"""Plazos del ciclo de la cotización: SLA de aprobación, seguimiento y vigencia. Módulo puro."""

from collections.abc import Iterable
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.domain.business_time import BusinessCalendar, add_business_time
from app.domain.errors import ExpiredPromotionError


def approval_due(solicitada_en: datetime, sla_minutos: int, calendar: BusinessCalendar) -> datetime:
    """RN-09: vencimiento del SLA de aprobación, contado en tiempo hábil."""
    return add_business_time(solicitada_en, timedelta(minutes=sla_minutos), calendar)


def follow_up_due(emitida_en: datetime, seguimiento_minutos: int) -> datetime:
    """RN-12: momento en que una cotización emitida sin cierre pasa a seguimiento (48 h)."""
    return emitida_en + timedelta(minutes=seguimiento_minutos)


def valid_until(
    emitida_en: datetime,
    vigencia_minutos: int,
    fines_promocion: Iterable[date],
    tz: ZoneInfo,
) -> datetime:
    """RN-11: vigencia máxima (7 días calendario) o fin de la promoción aplicada, lo primero.

    Una promoción vale hasta el final de su último día en la zona horaria de la operación.
    Si alguna promoción aplicada ya terminó al emitir, los precios calculados dejaron de ser
    válidos y hay que recalcular.
    """
    limite = emitida_en + timedelta(minutes=vigencia_minutos)
    for fin in fines_promocion:
        fin_promocion = datetime.combine(fin + timedelta(days=1), time.min, tz)
        if fin_promocion <= emitida_en:
            raise ExpiredPromotionError(
                f"La promoción aplicada venció el {fin.isoformat()}: recalcule la cotización antes de emitir"
            )
        limite = min(limite, fin_promocion)
    return limite
