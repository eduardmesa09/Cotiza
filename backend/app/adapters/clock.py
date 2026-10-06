from datetime import datetime, timezone


class SystemClock:
    """ClockPort real: hora del sistema en UTC."""

    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class SettableClock:
    """ClockPort que se fija a voluntad. Lo usa el escenario de demo para recrear semanas de
    operación pasada con los mismos casos de uso que la aplicación real."""

    def __init__(self, now: datetime) -> None:
        self.current = now

    def now(self) -> datetime:
        return self.current

    def set(self, now: datetime) -> None:
        self.current = now
