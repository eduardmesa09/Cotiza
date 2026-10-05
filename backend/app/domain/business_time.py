"""Tiempo hábil: cuánto tiempo de jornada hay entre dos instantes y cuándo vence un plazo.

Módulo puro. El calendario (jornada, días y zona horaria) es un dato que viene de los
parámetros de la base de datos. Con `activo=False` todo corre en tiempo de reloj, lo que
permite demostrar los plazos en minutos reales.

No modela festivos: queda fuera del alcance del MVP.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class BusinessCalendar:
    inicio: time
    fin: time
    dias: frozenset[int]  # numeración ISO: 1 = lunes ... 7 = domingo
    tz: ZoneInfo
    activo: bool = True

    def __post_init__(self) -> None:
        if self.inicio >= self.fin:
            raise ValueError("La jornada hábil debe empezar antes de terminar")
        if not self.dias or not self.dias <= frozenset(range(1, 8)):
            raise ValueError("Los días hábiles deben ser un conjunto no vacío de valores entre 1 y 7")

    def window(self, day: date) -> tuple[datetime, datetime] | None:
        """Inicio y fin de la jornada de ese día, o None si no es hábil."""
        if day.isoweekday() not in self.dias:
            return None
        return datetime.combine(day, self.inicio, self.tz), datetime.combine(day, self.fin, self.tz)


def _require_aware(*moments: datetime) -> None:
    if any(m.tzinfo is None for m in moments):
        raise ValueError("Las fechas deben tener zona horaria")


def business_time_between(start: datetime, end: datetime, calendar: BusinessCalendar) -> timedelta:
    """Tiempo hábil transcurrido entre dos instantes. Si `end` no es posterior, cero."""
    _require_aware(start, end)
    if end <= start:
        return timedelta(0)
    if not calendar.activo:
        return end - start

    start, end = start.astimezone(calendar.tz), end.astimezone(calendar.tz)
    total = timedelta(0)
    day = start.date()
    while day <= end.date():
        window = calendar.window(day)
        if window is not None:
            lo, hi = max(window[0], start), min(window[1], end)
            if hi > lo:
                total += hi - lo
        day += timedelta(days=1)
    return total


def add_business_time(start: datetime, duration: timedelta, calendar: BusinessCalendar) -> datetime:
    """Instante en que se cumple `duration` de tiempo hábil contado desde `start`."""
    _require_aware(start)
    if duration < timedelta(0):
        raise ValueError("La duración no puede ser negativa")
    if not calendar.activo:
        return start + duration

    current = start.astimezone(calendar.tz)
    remaining = duration
    day = current.date()
    while True:
        window = calendar.window(day)
        if window is not None:
            lo = max(window[0], current)
            if lo < window[1]:
                available = window[1] - lo
                if remaining <= available:
                    return (lo + remaining).astimezone(start.tzinfo)
                remaining -= available
        day += timedelta(days=1)
